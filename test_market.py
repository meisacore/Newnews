import unittest
from market import Exchange, Bots, SUPPLY, RESERVE_ACCOUNT, GRADUATION_SOLD, SCALE

class MarketTests(unittest.TestCase):
    def setUp(self):
        self.e=Exchange()
        self.e.register('alice',cash=10**13)
        self.e.register('bob',cash=10**13)
        self.e.register('bot',role='bot',cash=10**13)
        self.t=self.e.launch('alice','Frog','FROG').id

    def test_human_only_launch_and_zero_allocation(self):
        self.assertEqual(self.e.accounts['alice']['tokens'][self.t],0)
        self.assertEqual(self.e.accounts[RESERVE_ACCOUNT]['tokens'][self.t],SUPPLY)
        with self.assertRaises(PermissionError): self.e.launch('bot','Bot','BOT')

    def test_creator_pays_same_price(self):
        a=self.e.curve_buy('alice',self.t,10)
        self.e.curve_sell('alice',self.t,10)
        b=self.e.curve_buy('bob',self.t,10)
        self.assertEqual(a,b)
        self.assertEqual(self.e.accounts['alice']['tokens'][self.t],0)

    def test_curves_differ(self):
        ids=[self.e.launch('alice',x,x,curve_type=k).id for x,k in [('LIN','linear'),('EXP','exponential'),('CP','constant_product')]]
        costs=[self.e._curve_cost(t,0,1000) for t in ids]
        self.assertEqual(len(set(costs)),3)

    def test_buy_sell_conservation(self):
        before=self.e.accounts['alice']['cash']
        paid=self.e.curve_buy('alice',self.t,100)
        refunded=self.e.curve_sell('alice',self.t,100)
        self.assertGreater(paid,refunded)
        self.assertEqual(self.e.accounts['alice']['cash'],before - paid + refunded)
        self.assertEqual(self.e.curves[self.t]['sold'],0)
        self.assertEqual(sum(a['tokens'][self.t] for a in self.e.accounts.values()),SUPPLY)

    def test_slippage_and_cash(self):
        with self.assertRaises(ValueError): self.e.curve_buy('alice',self.t,100,max_cost=1)
        self.assertEqual(self.e.curves[self.t]['sold'],0)
        with self.assertRaises(ValueError): self.e.curve_sell('alice',self.t,1)
        self.e.register('poor',cash=1)
        with self.assertRaises(ValueError): self.e.curve_buy('poor',self.t,10)

    def test_no_orderbook_before_graduation(self):
        with self.assertRaises(ValueError): self.e.submit('alice',self.t,'buy',1,100)

    def test_graduation_and_amm_two_way(self):
        self.e.curve_buy('alice', self.t, GRADUATION_SOLD)
        self.assertTrue(self.e.curves[self.t]['graduated'])
        pool = self.e.pools[self.t]
        self.assertGreater(pool['cash'], 0)
        self.assertGreater(pool['tokens'], 0)
        with self.assertRaises(ValueError): self.e.curve_buy('bob', self.t, 1)
        spent = self.e.amm_trade('bob', self.t, 'buy', 3)
        self.assertGreater(spent, 0)
        proceeds = self.e.amm_trade('bob', self.t, 'sell', 3)
        self.assertGreater(proceeds, 0)
        self.assertLessEqual(proceeds, spent)
        self.assertEqual(self.e.accounts['bob']['tokens'][self.t], 0)
        self.assert_supply()

    def assert_supply(self):
        total = sum(a['tokens'][self.t] for a in self.e.accounts.values())
        total += self.e.pools.get(self.t, {}).get('tokens', 0)
        self.assertEqual(total, SUPPLY)

    def test_many_small_refunds_do_not_insolvent_reserve(self):
        import random
        rng = random.Random(13)
        initial_cash = sum(a['cash'] for a in self.e.accounts.values()) + self.e.fees_collected
        for _ in range(10000):
            held = self.e.accounts['alice']['tokens'][self.t]
            if held and rng.random() < .52:
                self.e.curve_sell('alice', self.t, rng.randint(1, min(held, 5)))
            elif self.e.curves[self.t]['sold'] < GRADUATION_SOLD - 5:
                self.e.curve_buy('alice', self.t, rng.randint(1, 5))
            self.assertGreaterEqual(self.e.accounts[RESERVE_ACCOUNT]['cash'], 0)
            self.assert_supply()
        final_cash = sum(a['cash'] for a in self.e.accounts.values()) + self.e.fees_collected
        self.assertEqual(initial_cash, final_cash)

    def test_spot_price_is_not_average_execution_price(self):
        paid = self.e.curve_buy('alice', self.t, 5000)
        self.assertGreater(self.e.last[self.t], paid // 5000)
        self.assertEqual(self.e.last[self.t], self.e.spot_price(self.t))

    def test_amm_cash_conservation(self):
        self.e.curve_buy('alice', self.t, GRADUATION_SOLD)
        initial = sum(a['cash'] for a in self.e.accounts.values()) + self.e.pools[self.t]['cash'] + self.e.fees_collected
        for _ in range(100):
            self.e.amm_trade('bob', self.t, 'buy', 1)
            self.e.amm_trade('bob', self.t, 'sell', 1)
        final = sum(a['cash'] for a in self.e.accounts.values()) + self.e.pools[self.t]['cash'] + self.e.fees_collected
        self.assertEqual(initial, final)
        self.assert_supply()

    def test_bot_activity(self):
        t2=self.e.launch('alice','Quiet','QUIET',activity='quiet').id
        t3=self.e.launch('alice','Mania','MANIA',activity='mania').id
        bots=Bots(self.e,seed=3)
        for _ in range(30): bots.tick()
        quiet=sum(x['token']==t2 for x in self.e.trades)
        mania=sum(x['token']==t3 for x in self.e.trades)
        self.assertGreater(mania,quiet)
        self.assertEqual(self.e.accounts['maker']['role'],'bot')

    def test_invalid_curve(self):
        with self.assertRaises(ValueError): self.e.launch('alice','Bad','BAD',curve_type='bad')
        with self.assertRaises(ValueError): self.e.launch('alice','Bad','BAD',activity='ultra')

if __name__=='__main__': unittest.main()
