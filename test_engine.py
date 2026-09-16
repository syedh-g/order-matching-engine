"""Unit tests for the matching engine. Run with: python -m unittest test_engine.py"""
import unittest

from matching_engine import MatchingEngine, Order, OrderStatus, OrderType, Side


def limit(side, price, qty, symbol="TEST"):
    return Order(side=side, order_type=OrderType.LIMIT, price=price, quantity=qty, symbol=symbol)


def market(side, qty, symbol="TEST"):
    return Order(side=side, order_type=OrderType.MARKET, quantity=qty, symbol=symbol)


class TestOrderValidation(unittest.TestCase):
    def test_limit_requires_price(self):
        with self.assertRaises(ValueError):
            Order(side=Side.BUY, order_type=OrderType.LIMIT, quantity=1)

    def test_market_rejects_price(self):
        with self.assertRaises(ValueError):
            Order(side=Side.BUY, order_type=OrderType.MARKET, quantity=1, price=100)

    def test_quantity_must_be_positive(self):
        with self.assertRaises(ValueError):
            Order(side=Side.BUY, order_type=OrderType.LIMIT, quantity=0, price=100)


class TestNoMatch(unittest.TestCase):
    def test_non_crossing_orders_rest_on_book(self):
        engine = MatchingEngine()
        buy = engine.submit_order(limit(Side.BUY, 99, 5))
        sell = engine.submit_order(limit(Side.SELL, 101, 5))
        self.assertEqual(buy, [])
        self.assertEqual(sell, [])
        self.assertEqual(engine.best_bid_ask("TEST"), (99, 101))


class TestMatching(unittest.TestCase):
    def test_exact_match_fills_both_fully(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 5))
        trades = engine.submit_order(limit(Side.BUY, 100, 5))

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].price, 100)
        self.assertEqual(trades[0].quantity, 5)
        self.assertIsNone(engine.order_book("TEST").best_bid())
        self.assertIsNone(engine.order_book("TEST").best_ask())

    def test_partial_fill_leaves_remainder_resting(self):
        engine = MatchingEngine()
        resting_sell = limit(Side.SELL, 100, 10)
        engine.submit_order(resting_sell)

        trades = engine.submit_order(limit(Side.BUY, 100, 4))

        self.assertEqual(trades[0].quantity, 4)
        self.assertEqual(resting_sell.remaining, 6)
        self.assertEqual(resting_sell.status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(engine.order_book("TEST").best_ask(), 100)

    def test_incoming_order_trades_at_resting_price_not_its_own(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 95, 5))  # willing to sell cheaper
        trades = engine.submit_order(limit(Side.BUY, 100, 5))  # willing to pay more

        self.assertEqual(trades[0].price, 95)  # trade executes at the resting order's price

    def test_price_time_priority(self):
        engine = MatchingEngine()
        first = limit(Side.SELL, 100, 3)
        second = limit(Side.SELL, 100, 3)
        engine.submit_order(first)
        engine.submit_order(second)

        trades = engine.submit_order(limit(Side.BUY, 100, 3))

        self.assertEqual(trades[0].sell_order_id, first.id)
        self.assertEqual(first.status, OrderStatus.FILLED)
        self.assertEqual(second.status, OrderStatus.OPEN)

    def test_better_price_takes_priority_over_arrival_time(self):
        engine = MatchingEngine()
        worse = limit(Side.SELL, 102, 3)
        better = limit(Side.SELL, 100, 3)  # arrives after `worse` but is cheaper
        engine.submit_order(worse)
        engine.submit_order(better)

        trades = engine.submit_order(limit(Side.BUY, 105, 3))

        self.assertEqual(trades[0].sell_order_id, better.id)
        self.assertEqual(trades[0].price, 100)

    def test_order_can_sweep_multiple_price_levels(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 2))
        engine.submit_order(limit(Side.SELL, 101, 2))
        engine.submit_order(limit(Side.SELL, 102, 2))

        trades = engine.submit_order(limit(Side.BUY, 102, 5))

        self.assertEqual(len(trades), 3)
        self.assertEqual([t.price for t in trades], [100, 101, 102])
        self.assertEqual(sum(t.quantity for t in trades), 5)
        # 1 unit left resting at 102
        self.assertEqual(engine.order_book("TEST").best_ask(), 102)
        self.assertEqual(engine.order_book("TEST").depth()["asks"], [(102, 1)])


class TestMarketOrders(unittest.TestCase):
    def test_market_order_sweeps_book(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 2))
        engine.submit_order(limit(Side.SELL, 101, 3))

        trades = engine.submit_order(market(Side.BUY, 4))

        self.assertEqual(len(trades), 2)
        self.assertEqual(sum(t.quantity for t in trades), 4)

    def test_market_order_never_rests(self):
        engine = MatchingEngine()
        order = market(Side.BUY, 10)  # nothing on the book to match
        trades = engine.submit_order(order)

        self.assertEqual(trades, [])
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNone(engine.order_book("TEST").best_bid())

    def test_market_order_unfilled_remainder_is_cancelled_not_resting(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 2))
        order = market(Side.BUY, 5)
        trades = engine.submit_order(order)

        self.assertEqual(sum(t.quantity for t in trades), 2)
        self.assertEqual(order.remaining, 3)
        self.assertEqual(order.status, OrderStatus.CANCELLED)


class TestCancellation(unittest.TestCase):
    def test_cancel_removes_resting_order(self):
        engine = MatchingEngine()
        order = limit(Side.BUY, 99, 5)
        engine.submit_order(order)

        self.assertTrue(engine.cancel_order("TEST", order.id))
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertIsNone(engine.order_book("TEST").best_bid())

    def test_cancel_unknown_order_returns_false(self):
        engine = MatchingEngine()
        self.assertFalse(engine.cancel_order("TEST", 9999))

    def test_cancelled_order_does_not_participate_in_future_matches(self):
        engine = MatchingEngine()
        order = limit(Side.BUY, 100, 5)
        engine.submit_order(order)
        engine.cancel_order("TEST", order.id)

        trades = engine.submit_order(limit(Side.SELL, 100, 5))
        self.assertEqual(trades, [])


class TestMultiSymbol(unittest.TestCase):
    def test_symbols_do_not_cross_match(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 5, symbol="AAA"))
        trades = engine.submit_order(limit(Side.BUY, 100, 5, symbol="BBB"))

        self.assertEqual(trades, [])
        self.assertEqual(engine.order_book("AAA").best_ask(), 100)
        self.assertEqual(engine.order_book("BBB").best_bid(), 100)


if __name__ == "__main__":
    unittest.main()
