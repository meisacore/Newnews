import unittest
from market import Exchange, Bots, GRADUATION_SOLD, SUPPLY, RESERVE_ACCOUNT

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.ex=Exchange()
        self.ex.register('human',cash=10**13)
        self.token=self.ex.launch('human','Agent Test','AGNT',activity='mania').id
        self.bots=Bots(self.ex,seed=5)

    def test_no_forced_trades_and_bounded_risk(self):
        for _ in range(75): self.bots.tick()
        self.assertGreater(self.bots.decisions[self.token]['hold'],0)
        for a in self.bots.traders.values():
            self.assertGreaterEqual(self.ex.accounts[a.name]['cash'],0)
            self.assertEqual(a.positions[self.token].quantity,self.ex.accounts[a.name]['tokens'][self.token])
        self.assertEqual(sum(a['tokens'][self.token] for a in self.ex.accounts.values())+self.ex.pools.get(self.token,{}).get('tokens',0),SUPPLY)

    def test_realized_profit_is_actual_cashflow(self):
        t=self.bots.traders['momentum']
        self.assertTrue(self.bots._execute(t,self.token,'buy'))
        pos=t.positions[self.token]
        basis=pos.cost_basis
        held=pos.quantity
        self.assertGreater(held,0)
        self.ex.curve_buy('human',self.token,5000)
        self.assertTrue(self.bots._execute(t,self.token,'sell'))
        self.assertEqual(pos.quantity,0)
        self.assertEqual(pos.cost_basis,0)
        self.assertEqual(pos.realized_pnl,self.ex.accounts[t.name]['cash']-t.initial_cash)
        self.assertEqual(pos.wins+pos.losses,1)
        self.assertEqual(self.ex.accounts[t.name]['tokens'][self.token],0)

    def test_agents_continue_after_graduation(self):
        self.ex.curve_buy('human',self.token,GRADUATION_SOLD)
        self.assertTrue(self.ex.curves[self.token]['graduated'])
        for _ in range(40): self.bots.tick()
        self.assertTrue(self.bots.performance())
        self.assertEqual(sum(a['tokens'][self.token] for a in self.ex.accounts.values())+self.ex.pools[self.token]['tokens'],SUPPLY)

    def test_reproducible_seed(self):
        def run():
            e=Exchange();e.register('human');token=e.launch('human','Test','TEST',activity='active').id
            b=Bots(e,seed=22)
            for _ in range(25): b.tick()
            return [(x['agent'],x['side'],x['quantity']) for x in b.events],dict(b.decisions[token])
        self.assertEqual(run(),run())

if __name__=='__main__': unittest.main()
