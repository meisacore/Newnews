"""Simulated trading agents: three behaviour types, one shared sizing rule.

No LLM, no external data, deterministic for a given seed.

How it works
------------
* Every token has a hidden *fair value* F. It random-walks with a drift set by
  the economy regime (bust / flat / boom) plus heavy-tailed news shocks.
  The regime is the "economy good or bad" dial: bots.set_economy('boom').
* Agents never trade the same way twice, but they all size positions with the
  same mean-variance rule:

      target fraction = expected return / (risk aversion * variance)   [0..1]
      target position = target fraction * max position (cap% of equity)

  The types only differ in how they form the expected return:
    - fundamentalist: expects price to move back toward its own noisy
      estimate of F (whale, dip, maker)
    - chartist: expects the recent trend to continue (momentum, scalper,
      hunter) or reverse (contrarian)
    - noise: random demand with finite capital (noise)
* Buys only happen when the expected edge beats the round-trip fee hurdle, so
  agents don't bleed money churning.
* Hard risk controls (stop-loss, take-profit, max holding age) still use
  executable sell quotes and override everything else.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, field
import math
import random
from market import GRADUATION_SOLD, RESERVE_ACCOUNT

# --- model parameters -------------------------------------------------------
HORIZON = 20            # ticks over which expected return / variance are measured
VAR_FLOOR = 1e-5        # per-tick return variance floor (keeps sizing finite)
KAPPA = 0.15            # fundamentalist pull toward fair value per horizon
HURDLE = 0.006          # min expected return before a buy (about round-trip fees)
MIN_TRADE_BAND = 0.20   # ignore rebalances smaller than 20% of max position
STOP_LOSS, TAKE_PROFIT, MAX_AGE = -0.075, 0.12, 65

ECONOMY_DRIFT = {'bust': -0.0006, 'flat': 0.0, 'boom': 0.0006}   # per tick
SHOCK_SIGMA = 0.004     # std of per-tick news shock (Student-t, df=3, clipped)
SHOCK_CLIP = 0.03
REGIME_FLIP_PROB = 0.01
REGIME_WEIGHTS = (('flat', 5), ('boom', 2.5), ('bust', 2.5))

PROFILES = {
    # kind, risk aversion, estimate noise / trend window+gain, order size, position cap
    'whale':      dict(kind='fund',  lam=6,  noise=.004, order=.04, cap=.15),
    'dip':        dict(kind='fund',  lam=12, noise=.012, order=.02, cap=.08),
    'maker':      dict(kind='fund',  lam=20, noise=.010, order=.02, cap=.08, rebalance=True),
    'momentum':   dict(kind='chart', lam=10, window=10, gain=.5,  order=.02, cap=.08),
    'scalper':    dict(kind='chart', lam=10, window=4,  gain=.5,  order=.02, cap=.08),
    'contrarian': dict(kind='chart', lam=12, window=10, gain=-.4, order=.02, cap=.08),
    'hunter':     dict(kind='chart', lam=10, window=4,  gain=.5,  order=.02, cap=.08, max_age=40),
    'noise':      dict(kind='noise', lam=1,  order=.02, cap=.08),
}


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


@dataclass
class Position:
    quantity: int = 0
    cost_basis: int = 0   # cash actually paid for remaining units, including fees
    realized_pnl: int = 0
    wins: int = 0
    losses: int = 0
    entries: int = 0
    exits: int = 0
    peak_equity: int = 0
    max_drawdown_bps: int = 0
    entry_tick: int = 0

@dataclass
class Trader:
    name: str
    strategy: str
    initial_cash: int
    cooldown_until: int = 0
    observations: dict = field(default_factory=dict)
    positions: dict = field(default_factory=lambda: defaultdict(Position))


class Bots:
    """Agents see sequential live observations and submit real curve/AMM trades.

    Each strategy has independent capital, position state, risk limits and exit
    logic. Events are decisions, not forced trades. Prices are endogenous; the
    hidden fair value only moves what agents *believe*, never the price itself.
    """
    STRATEGIES = ('maker', 'noise', 'momentum', 'dip', 'whale', 'scalper', 'contrarian', 'hunter')

    def __init__(self, exchange, seed=7):
        self.ex = exchange
        self.rng = random.Random(seed)
        self.time = 0
        self.age = defaultdict(int)
        self.history = defaultdict(lambda: deque(maxlen=120))
        self.decisions = defaultdict(lambda: defaultdict(int))
        self.events = deque(maxlen=500)
        self.traders = {}
        self.fair = {}                 # token -> hidden fair value (microcents, float)
        self.economy = 'flat'          # 'bust' | 'flat' | 'boom'
        self.auto_economy = True       # regime flips on its own unless set_economy() is called
        # Each agent receives finite starting capital. Existing bot accounts are
        # respected, but never topped up on tick.
        budgets = {'maker': 1500, 'noise': 450, 'momentum': 1100,
                   'dip': 950, 'whale': 2200, 'scalper': 650,
                   'contrarian': 850, 'hunter': 800}
        unit = 100 * 1_000_000  # microcents in $1
        for name in self.STRATEGIES:
            if name not in exchange.accounts:
                exchange.register(name, role='bot', cash=budgets[name]*unit)
            elif exchange.accounts[name]['role'] != 'bot':
                raise ValueError('bot account required: '+name)
            self.traders[name] = Trader(name, name, exchange.accounts[name]['cash'])

    # --- economy / fair value -------------------------------------------------
    def set_economy(self, regime):
        """Force the regime ('bust', 'flat', 'boom') and stop random flips."""
        if regime not in ECONOMY_DRIFT:
            raise ValueError('regime must be bust, flat or boom')
        self.economy = regime
        self.auto_economy = False

    def _step_economy(self):
        if self.auto_economy and self.rng.random() < REGIME_FLIP_PROB:
            names, weights = zip(*REGIME_WEIGHTS)
            self.economy = self.rng.choices(names, weights=weights)[0]

    def _step_fair(self, token):
        if token not in self.fair:
            self.fair[token] = float(self.ex.spot_price(token))
            return
        # Student-t(3) scaled to unit variance is z / sqrt(chi2_3); fat-tailed news.
        z = self.rng.gauss(0, 1)
        chi = sum(self.rng.gauss(0, 1)**2 for _ in range(3))
        shock = _clip(SHOCK_SIGMA*z/math.sqrt(max(chi, 1e-9)), -SHOCK_CLIP, SHOCK_CLIP)
        self.fair[token] *= math.exp(ECONOMY_DRIFT[self.economy] + shock)

    # --- quotes / accounting (unchanged behaviour) ----------------------------
    def _quote(self, token, side, qty):
        if qty <= 0:
            return None
        state = self.ex.curves[token]
        if state['graduated']:
            try:
                return self.ex.amm_quote(token, side, qty)
            except ValueError:
                return None
        if side == 'buy':
            if qty > GRADUATION_SOLD-state['sold']:
                return None
            gross = self.ex._curve_cost(token, state['sold'], qty)
            return gross + (gross*30+9999)//10000
        if qty > state['sold']:
            return None
        from decimal import ROUND_FLOOR
        gross = self.ex._curve_cost(token, state['sold']-qty, qty, ROUND_FLOOR)
        return gross - gross*30//10000

    def _equity(self, trader):
        cash = self.ex.accounts[trader.name]['cash']
        liquidation = 0
        for token, pos in trader.positions.items():
            if pos.quantity:
                liquidation += self._quote(token, 'sell', pos.quantity) or 0
        return cash + liquidation

    def performance(self):
        result = []
        for t in self.traders.values():
            cash = self.ex.accounts[t.name]['cash']
            equity = self._equity(t)
            realized = sum(p.realized_pnl for p in t.positions.values())
            unrealized = sum((self._quote(tok, 'sell', p.quantity) or 0)-p.cost_basis
                             for tok,p in t.positions.items() if p.quantity)
            result.append({'agent':t.name,'strategy':t.strategy,'cash_microcents':cash,
                'equity_microcents':equity,'realized_pnl_microcents':realized,
                'unrealized_pnl_microcents':unrealized,
                'return_bps':round((equity-t.initial_cash)*10000/max(1,t.initial_cash)),
                'wins':sum(p.wins for p in t.positions.values()),
                'losses':sum(p.losses for p in t.positions.values()),
                'max_drawdown_bps':max((p.max_drawdown_bps for p in t.positions.values()),default=0),
                'positions':{tok:p.quantity for tok,p in t.positions.items() if p.quantity}})
        return result

    def _mark_drawdown(self, trader, token):
        pos = trader.positions[token]
        equity = self._equity(trader)
        pos.peak_equity = max(pos.peak_equity, equity)
        if pos.peak_equity:
            pos.max_drawdown_bps = max(pos.max_drawdown_bps,
                 (pos.peak_equity-equity)*10000//pos.peak_equity)

    # --- decision model --------------------------------------------------------
    def _variance(self, token):
        """Per-tick log-return variance over the last ~30 ticks."""
        h = list(self.history[token])[-31:]
        rets = [math.log(b/a) for a, b in zip(h, h[1:]) if a > 0 and b > 0]
        if len(rets) < 3:
            return VAR_FLOOR
        m = sum(rets)/len(rets)
        return max(VAR_FLOOR, sum((r-m)**2 for r in rets)/len(rets))

    def _target(self, prof, token, spot):
        """Return (target fraction of max position, buy_allowed) or None for no view."""
        kind = prof['kind']
        if kind == 'noise':
            r = self.rng.random()
            if r < .5:
                return None                       # no opinion: hold
            return (self.rng.random()*.6 if r < .8 else 0.0), True
        hist = self.history[token]
        sig2 = self._variance(token)*HORIZON
        lam = prof['lam']
        if kind == 'fund':
            est = self.fair[token]*math.exp(self.rng.gauss(0, prof['noise']))
            mu = KAPPA*(est/max(1, spot)-1)
            if prof.get('rebalance'):             # inventory rebalancer: aims for mid-size, tilts with mu
                return _clip(.5 + mu/(lam*sig2)), True
            return _clip(mu/(lam*sig2)), mu >= HURDLE
        # chartist
        if prof.get('max_age') and self.age[token] > prof['max_age']:
            return 0.0, False                     # sniper: only plays young tokens
        w = prof['window']
        if len(hist) <= w:
            return None
        trend = spot/max(1, hist[-1-w])-1
        mu = prof['gain']*trend
        return _clip(mu/(lam*sig2)), mu >= HURDLE

    def _decide(self, t, token):
        """Return (side, value_cap, sell_fraction) or None to hold."""
        if len(self.history[token]) < 4 or token not in self.fair:
            return None
        p = t.positions[token]
        exposure = 0
        if p.quantity:
            # All open positions are evaluated at executable sell proceeds, not mark price.
            exposure = self._quote(token, 'sell', p.quantity) or 0
            pnl_pct = exposure/max(1, p.cost_basis)-1
            if pnl_pct <= STOP_LOSS or pnl_pct >= TAKE_PROFIT or self.time-p.entry_tick >= MAX_AGE:
                return ('sell', None, 1.0)
        prof = PROFILES[t.strategy]
        res = self._target(prof, token, self.ex.spot_price(token))
        if res is None:
            return None
        frac, buy_ok = res
        max_pos = self._equity(t)*prof['cap']
        gap = frac*max_pos-exposure
        band = max_pos*MIN_TRADE_BAND
        if gap > band and buy_ok:
            return ('buy', gap, None)
        if -gap > band and p.quantity:
            return ('sell', None, min(1.0, -gap/max(1, exposure)))
        return None

    def _execute(self, t, token, side, value=None, frac=None):
        ex = self.ex
        p = t.positions[token]
        cash, held = ex.available(t.name, token)
        equity = self._equity(t)
        prof = PROFILES[t.strategy]
        # Risk budget: a slice of available cash per order, capped at a share of
        # total portfolio equity in this token (whales get larger limits).
        order_budget = int(cash*prof['order'])
        max_position = int(equity*prof['cap'])
        exposure = self._quote(token,'sell',held) or 0
        if side == 'buy':
            budget = min(order_budget,max(0,max_position-exposure))
            if value is not None:
                budget = min(budget,int(value))
            if budget <= 0:
                return False
            spot = ex.spot_price(token)
            hi = max(1,min(10000,budget//max(1,spot)))
            lo = 0
            while lo < hi:
                mid = (lo+hi+1)//2
                q = self._quote(token,'buy',mid)
                if q is not None and q <= budget: lo=mid
                else: hi=mid-1
            qty=lo
            if not qty: return False
            paid = self._quote(token,'buy',qty)
            if ex.curves[token]['graduated']:
                actual=ex.amm_trade(t.name,token,'buy',qty,max_cost=paid)
            else:
                actual=ex.curve_buy(t.name,token,qty,max_cost=paid)
            p.cost_basis+=actual
            p.quantity+=qty
            p.entries+=1
            p.entry_tick=self.time if p.quantity==qty else p.entry_tick
        else:
            if not p.quantity or not held: return False
            qty=min(held,p.quantity)
            if frac is not None and frac < 1:      # partial trim toward target
                qty=max(1,int(qty*frac))
            proceeds=self._quote(token,'sell',qty)
            if proceeds is None or proceeds<=0: return False
            if ex.curves[token]['graduated']:
                actual=ex.amm_trade(t.name,token,'sell',qty,min_refund=proceeds)
            else:
                actual=ex.curve_sell(t.name,token,qty,min_refund=proceeds)
            basis=p.cost_basis if qty==p.quantity else p.cost_basis*qty//p.quantity
            p.cost_basis-=basis
            p.quantity-=qty
            p.realized_pnl+=actual-basis
            p.wins+=actual>basis
            p.losses+=actual<basis
            p.exits+=1
        self.decisions[token][side]+=1
        self.events.append({'tick':self.time,'agent':t.name,'token':token,'side':side,
                            'quantity':qty,'cash_flow':actual})
        self._mark_drawdown(t,token)
        return True

    def tick(self):
        self.time+=1
        self._step_economy()
        for token in list(self.ex.tokens):
            self.age[token]+=1
            self._step_fair(token)
            self.history[token].append(self.ex.spot_price(token))   # one price per tick
            profile=self.ex.tokens[token].activity
            opportunities={'quiet':2,'active':5,'mania':10}[profile]
            # Random pick each opportunity avoids a fixed first-mover advantage.
            for _ in range(opportunities):
                t=self.traders[self.rng.choice(self.STRATEGIES)]
                if t.cooldown_until>self.time:
                    self.decisions[token]['hold']+=1
                    continue
                decision=self._decide(t,token)
                if decision is None:
                    self.decisions[token]['hold']+=1
                    continue
                side,value,frac=decision
                try:
                    traded=self._execute(t,token,side,value,frac)
                except ValueError:
                    traded=False
                if traded:
                    t.cooldown_until=self.time+{'quiet':3,'active':2,'mania':1}[profile]
                else:
                    self.decisions[token]['hold']+=1
