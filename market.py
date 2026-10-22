"""Fictional token-launch exchange. No real money, chains or external feeds."""
from collections import defaultdict, deque
from dataclasses import dataclass
import random
import re
import math
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext

SUPPLY = 1_000_000_000
STARTING_CASH = 1_000_000_000_000  # microcents: 1_000_000 units = 1 cent; $10,000
SCALE = 1_000_000
BASE_PRICE = 20 * SCALE  # microcents per token; $0.20 at launch
CURVE_ALLOCATION = GRADUATION_SOLD = 10_000
MAX_TOKENS = 40
POOL_FEE_BPS = 30
LAUNCH_FEE = 100 * 100 * SCALE
RESERVE_ACCOUNT = "__system_launch_reserve__"


@dataclass
class Order:
    id: int
    owner: str
    token: str
    side: str
    qty: int
    price: int
    remaining: int


@dataclass(frozen=True)
class Token:
    id: str
    name: str
    ticker: str
    creator: str
    description: str = ''
    image_url: str = ''
    supply: int = SUPPLY
    curve_type: str = "linear"
    activity: str = "active"


class Exchange:
    def __init__(self):
        self.accounts = {}
        self.tokens = {}
        self.books = defaultdict(lambda: {'buy': [], 'sell': []})
        self.trades = deque(maxlen=4000)
        self.trade_count = defaultdict(int)
        self.recent = defaultdict(lambda: deque(maxlen=80))
        self.net_invested = defaultdict(int)
        self.pools = {}
        self.fees_collected = 0
        self.next_id = 1
        self.next_token_id = 1
        self.last = {}
        self.curves = {}
        self.bot_ticks = defaultdict(int)
        # A non-player inventory account. Only the exchange can create its asks.
        self.register(RESERVE_ACCOUNT, role="reserve", cash=0)

    def register(self, who, role='human', cash=STARTING_CASH):
        if not isinstance(who, str) or not who.strip():
            raise ValueError('account ID required')
        if who in self.accounts:
            raise ValueError('account already exists')
        if role not in ('human', 'bot', 'reserve'):
            raise ValueError('role must be human, bot, or reserve')
        if role == 'reserve' and who != RESERVE_ACCOUNT:
            raise PermissionError('reserve accounts are internal')
        if who == RESERVE_ACCOUNT and role != 'reserve':
            raise PermissionError('reserved account name')
        if type(cash) is not int or cash < 0:
            raise ValueError('cash must be a nonnegative integer')
        self.accounts[who] = {
            'role': role, 'cash': cash, 'tokens': defaultdict(int),
            'locked_cash': 0, 'locked_tokens': defaultdict(int)
        }

    def launch(self, who, name, ticker, description='', image_url='', curve_type='linear',
               activity='active', initial_price=None, initial_quantity=None):
        """Only humans launch. Supply stays in system custody until paid for."""
        a = self._account(who)
        if a['role'] != 'human':
            raise PermissionError('only humans can launch')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            raise ValueError('invalid name')
        if not isinstance(ticker, str) or not re.fullmatch(r'[A-Za-z0-9]{2,10}', ticker):
            raise ValueError('invalid ticker')
        if not isinstance(description, str) or len(description) > 500:
            raise ValueError('invalid description')
        if not isinstance(image_url, str) or len(image_url) > 1000:
            raise ValueError('invalid image URL')
        if curve_type not in ('linear', 'exponential', 'constant_product'):
            raise ValueError('invalid curve type')
        if activity not in ('quiet', 'active', 'mania'):
            raise ValueError('invalid activity')
        if len(self.tokens) >= MAX_TOKENS:
            raise ValueError('market launch limit reached')
        if a['cash'] - a['locked_cash'] < LAUNCH_FEE:
            raise ValueError('insufficient cash for launch fee')
        if initial_price is not None or initial_quantity is not None:
            raise ValueError('fixed-price reserve orders have been replaced by curves')
        token_id = f'TKN{self.next_token_id:06d}'
        self.next_token_id += 1
        token = Token(token_id, name.strip(), ticker.upper(), who, description, image_url,
                      curve_type=curve_type, activity=activity)
        a['cash'] -= LAUNCH_FEE
        self.fees_collected += LAUNCH_FEE
        self.tokens[token_id] = token
        self.accounts[RESERVE_ACCOUNT]['tokens'][token_id] = SUPPLY
        self.curves[token_id] = {'sold': 0, 'raised': 0, 'graduated': False}
        self.last[token_id] = BASE_PRICE
        return token

    def _curve_cost(self, token, start, qty, rounding=ROUND_CEILING):
        """Integral of price curve, in integer microcents; buys round up."""
        if qty <= 0 or start < 0 or start + qty > GRADUATION_SOLD:
            raise ValueError('invalid curve quantity')
        with localcontext() as ctx:
            ctx.prec = 45
            x = Decimal(start) / Decimal(GRADUATION_SOLD)
            y = Decimal(start + qty) / Decimal(GRADUATION_SOLD)
            unit = Decimal(GRADUATION_SOLD)
            if self.tokens[token].curve_type == 'linear':
                integral = (y - x) + (y*y - x*x) / 2
            elif self.tokens[token].curve_type == 'exponential':
                integral = (Decimal('0.7') * y).exp() - (Decimal('0.7') * x).exp()
                integral /= Decimal('0.7')
            else:
                # virtual reserves; marginal price 1/(1 - x/2)^2
                if y >= Decimal('2'):
                    raise ValueError('curve reserve boundary')
                integral = 2 / (2-y) * 2 - 2 / (2-x) * 2
            return int((integral * unit * BASE_PRICE).to_integral_value(rounding=rounding))

    def curve_buy(self, who, token, qty, max_cost=None):
        a = self._account(who)
        if a['role'] == 'reserve':
            raise PermissionError('reserve cannot trade')
        state = self._curve(token)
        if state['graduated']:
            raise ValueError('token has graduated: use the order book')
        if type(qty) is not int or qty <= 0 or state['sold'] + qty > GRADUATION_SOLD:
            raise ValueError('invalid quantity or graduation limit exceeded')
        base_cost = self._curve_cost(token, state['sold'], qty)
        fee = (base_cost * POOL_FEE_BPS + 9999) // 10000
        cost = base_cost + fee
        if max_cost is not None and cost > max_cost:
            raise ValueError('slippage limit exceeded')
        if self.available(who, token)[0] < cost:
            raise ValueError('insufficient cash')
        a['cash'] -= cost
        a['tokens'][token] += qty
        self.accounts[RESERVE_ACCOUNT]['tokens'][token] -= qty
        self.accounts[RESERVE_ACCOUNT]['cash'] += base_cost
        self.fees_collected += fee
        state['sold'] += qty
        state['raised'] += base_cost
        self.last[token] = self.spot_price(token)
        self._record({'token': token, 'phase': 'curve', 'side': 'buy',
                            'price_microcents': cost // qty, 'quantity': qty,
                            'buyer': who, 'seller': RESERVE_ACCOUNT, 'cost': cost, 'exec_price': cost // qty})
        if state['sold'] == GRADUATION_SOLD:
            self._graduate(token)
        return cost

    def curve_sell(self, who, token, qty, min_refund=None):
        a = self._account(who)
        if a['role'] == 'reserve':
            raise PermissionError('reserve cannot trade')
        state = self._curve(token)
        if state['graduated']:
            raise ValueError('token has graduated: use the order book')
        if type(qty) is not int or qty <= 0 or qty > state['sold']:
            raise ValueError('invalid sell quantity')
        if self.available(who, token)[1] < qty:
            raise ValueError('insufficient tokens')
        gross_refund = self._curve_cost(token, state['sold'] - qty, qty, ROUND_FLOOR)
        fee = gross_refund * POOL_FEE_BPS // 10000
        refund = gross_refund - fee
        if min_refund is not None and refund < min_refund:
            raise ValueError('slippage limit exceeded')
        if self.accounts[RESERVE_ACCOUNT]['cash'] < gross_refund:
            raise ValueError('insufficient reserve cash')
        a['tokens'][token] -= qty
        a['cash'] += refund
        self.accounts[RESERVE_ACCOUNT]['tokens'][token] += qty
        self.accounts[RESERVE_ACCOUNT]['cash'] -= gross_refund
        self.fees_collected += fee
        state['sold'] -= qty
        state['raised'] -= gross_refund
        self.last[token] = self.spot_price(token)
        self._record({'token': token, 'phase': 'curve', 'side': 'sell',
                            'price_microcents': refund // qty, 'quantity': qty,
                            'buyer': RESERVE_ACCOUNT, 'seller': who, 'cost': refund, 'exec_price': refund // qty})
        return refund

    def _curve(self, token):
        if token not in self.curves:
            raise ValueError('unknown token')
        return self.curves[token]

    def spot_price(self, token):
        state = self._curve(token)
        if state['graduated']:
            pool = self.pools[token]
            return max(1, pool['cash'] // pool['tokens'])
        with localcontext() as ctx:
            ctx.prec = 45
            x = Decimal(state['sold']) / Decimal(GRADUATION_SOLD)
            curve = self.tokens[token].curve_type
            if curve == 'linear':
                factor = 1 + x
            elif curve == 'exponential':
                factor = (Decimal('0.7') * x).exp()
            else:
                factor = 1 / (1 - x / 2) ** 2
            return max(1, int((factor * BASE_PRICE).to_integral_value(rounding=ROUND_CEILING)))

    def _record(self, trade):
        self.trades.append(trade)
        token = trade['token']
        self.trade_count[token] += 1
        self.recent[token].append(trade)
        amount = trade['cost']
        if trade['buyer'] != RESERVE_ACCOUNT:
            self.net_invested[(trade['buyer'], token)] += amount
        if trade['seller'] != RESERVE_ACCOUNT:
            self.net_invested[(trade['seller'], token)] -= amount

    def _graduate(self, token):
        state = self.curves[token]
        # All actual curve proceeds fund the pool. Tokens come from EXISTING reserve supply.
        # Set the starting pool ratio to the final marginal curve price (integer precision).
        price = self.spot_price(token)
        cash = state['raised']
        tokens = cash // price
        if tokens < 2 or tokens > self.accounts[RESERVE_ACCOUNT]['tokens'][token]:
            raise ValueError('insufficient inventory for graduation')
        self.accounts[RESERVE_ACCOUNT]['cash'] -= cash
        self.accounts[RESERVE_ACCOUNT]['tokens'][token] -= tokens
        self.pools[token] = {'cash': cash, 'tokens': tokens, 'fee_bps': POOL_FEE_BPS}
        state['graduated'] = True
        self.last[token] = self.spot_price(token)

    def amm_quote(self, token, side, qty):
        if token not in self.pools:
            raise ValueError('token not graduated')
        if side not in ('buy', 'sell') or type(qty) is not int or qty <= 0:
            raise ValueError('invalid side or quantity')
        pool = self.pools[token]
        x, y = pool['tokens'], pool['cash']
        fee = pool['fee_bps']
        if side == 'buy':
            if qty >= x:
                raise ValueError('insufficient pool tokens')
            # exact-output buy: round required input up, including input fee
            net_input = (y * qty + (x - qty) - 1) // (x - qty)
            gross = (net_input * 10000 + (10000 - fee) - 1) // (10000 - fee)
            return gross
        # exact-input sell: fee deducted from input token amount
        gross = y * qty // (x + qty)
        return gross * (10000 - fee) // 10000

    def amm_trade(self, who, token, side, qty, max_cost=None, min_refund=None):
        a = self._account(who)
        if a['role'] == 'reserve':
            raise PermissionError('reserve cannot trade')
        amount = self.amm_quote(token, side, qty)
        pool = self.pools[token]
        if side == 'buy':
            if max_cost is not None and amount > max_cost:
                raise ValueError('slippage limit exceeded')
            if self.available(who, token)[0] < amount:
                raise ValueError('insufficient cash')
            a['cash'] -= amount
            a['tokens'][token] += qty
            pool['cash'] += amount
            pool['tokens'] -= qty
            buyer, seller = who, RESERVE_ACCOUNT
        else:
            if min_refund is not None and amount < min_refund:
                raise ValueError('slippage limit exceeded')
            if self.available(who, token)[1] < qty:
                raise ValueError('insufficient tokens')
            a['tokens'][token] -= qty
            a['cash'] += amount
            pool['tokens'] += qty
            pool['cash'] -= amount
            buyer, seller = RESERVE_ACCOUNT, who
        self.last[token] = self.spot_price(token)
        self._record({'token': token, 'phase': 'amm', 'side': side,
                      'price_microcents': self.last[token], 'exec_price': amount // qty,
                      'quantity': qty, 'buyer': buyer, 'seller': seller, 'cost': amount})
        return amount

    def _account(self, who):
        if who not in self.accounts:
            raise ValueError('unknown account: register first')
        return self.accounts[who]

    def available(self, who, token):
        a = self._account(who)
        return a['cash'] - a['locked_cash'], a['tokens'][token] - a['locked_tokens'][token]

    def submit(self, who, token, side, qty, price=None):
        raise ValueError('order book disabled: use amm_trade after graduation')

    def _submit(self, who, token, side, qty, price=None, internal=False):
        a = self._account(who)
        if a['role'] == 'reserve' and not internal:
            raise PermissionError('reserve orders are exchange-controlled')
        if token in self.curves and not self.curves[token]['graduated']:
            raise ValueError('token is on bonding curve: use curve_buy/curve_sell')
        if token not in self.tokens:
            raise ValueError('unknown token')
        if side not in ('buy', 'sell') or type(qty) is not int or qty <= 0:
            raise ValueError('side must be buy/sell; qty must be positive integer')
        if price is not None and (type(price) is not int or price <= 0):
            raise ValueError('price must be positive integer cents or None for market order')
        market = price is None
        book = self.books[token]
        opposite = 'sell' if side == 'buy' else 'buy'
        book[opposite].sort(key=lambda o: (o.price if side == 'buy' else -o.price, o.id))
        eligible = [o for o in book[opposite] if o.owner != who and
                    (market or (o.price <= price if side == 'buy' else o.price >= price))]
        if market and not eligible:
            raise ValueError('no opposite-side liquidity')
        cash, held = self.available(who, token)
        if side == 'sell' and held < qty:
            raise ValueError('insufficient available simulated tokens')
        if side == 'buy':
            if market:
                remaining = qty
                cost = 0
                for resting in eligible:
                    take = min(remaining, resting.remaining)
                    cost += take * resting.price
                    remaining -= take
                    if not remaining:
                        break
            else:
                cost = qty * price
            if cash < cost:
                raise ValueError('insufficient available simulated cash')
        order = Order(self.next_id, who, token, side, qty, price or 0, qty)
        self.next_id += 1
        if not market:
            if side == 'buy':
                self.accounts[who]['locked_cash'] += qty * price
            else:
                self.accounts[who]['locked_tokens'][token] += qty
        for resting in list(book[opposite]):
            if not order.remaining:
                break
            if resting.owner == who:
                continue
            if not market and not (resting.price <= price if side == 'buy' else resting.price >= price):
                break
            n = min(order.remaining, resting.remaining)
            p = resting.price
            buyer = who if side == 'buy' else resting.owner
            seller = who if side == 'sell' else resting.owner
            self.accounts[buyer]['cash'] -= n * p
            self.accounts[buyer]['tokens'][token] += n
            self.accounts[seller]['cash'] += n * p
            self.accounts[seller]['tokens'][token] -= n
            for item in (order, resting):
                if item.price:
                    a = self.accounts[item.owner]
                    if item.side == 'buy':
                        a['locked_cash'] -= n * item.price
                    else:
                        a['locked_tokens'][token] -= n
            order.remaining -= n
            resting.remaining -= n
            self.last[token] = p
            self._record({'token': token, 'phase': 'orderbook', 'side': side, 'price_microcents': p, 'quantity': n,
                                'buyer': buyer, 'seller': seller, 'taker': who, 'cost': n*p})
            if not resting.remaining:
                book[opposite].remove(resting)
        if order.remaining and not market:
            book[side].append(order)
        return order

    def cancel(self, who, order_id):
        if self._account(who)['role'] == 'reserve':
            raise PermissionError('reserve orders cannot be cancelled by players')
        for token, sides in self.books.items():
            for side, orders in sides.items():
                for order in orders:
                    if order.id == order_id and order.owner == who:
                        if side == 'buy':
                            self.accounts[who]['locked_cash'] -= order.remaining * order.price
                        else:
                            self.accounts[who]['locked_tokens'][token] -= order.remaining
                        orders.remove(order)
                        return True
        return False

    def depth(self, token):
        if token not in self.tokens:
            raise ValueError('unknown token')
        result = {}
        for side in ('buy', 'sell'):
            levels = defaultdict(int)
            for order in self.books[token][side]:
                levels[order.price] += order.remaining
            result[side] = sorted(levels.items(), reverse=(side == 'buy'))
        return result


# Imported at module end to keep existing server and test imports compatible.
from agents import Bots

def demo():
    ex = Exchange()
    ex.register('alice')
    ex.register('bob')
    bots = Bots(ex)
    tokens = [ex.launch('alice', 'Moon Frog', 'FROG', curve_type='linear', activity='active'),
              ex.launch('bob', 'Rocket', 'RCKT', curve_type='exponential', activity='mania'),
              ex.launch('alice', 'Pebble', 'PBL', curve_type='constant_product', activity='quiet')]
    for token in tokens:
        ex.curve_buy('alice', token.id, 100)
    for _ in range(50):
        bots.tick()
    for token in tokens:
        st = ex.curves[token.id]
        print(token.ticker, token.curve_type, token.activity,
              'sold:', st['sold'], 'spot microcents:', ex.last[token.id],
              'trades:', sum(t['token'] == token.id for t in ex.trades))
    print('Creator FROG:', ex.accounts['alice']['tokens'][tokens[0].id], '(purchased, not gifted)')
    return ex


if __name__ == '__main__':
    demo()
