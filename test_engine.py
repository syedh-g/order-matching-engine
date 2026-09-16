"""Unit tests for the matching engine. Run with: python -m unittest test_engine.py"""
import dataclasses
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


class TestTradeIsImmutable(unittest.TestCase):
    def test_trade_fields_cannot_be_reassigned(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 5))
        trades = engine.submit_order(limit(Side.BUY, 100, 5))

        with self.assertRaises(dataclasses.FrozenInstanceError):
            trades[0].price = 999


class TestTradeHistory(unittest.TestCase):
    def test_history_accumulates_across_submissions_in_order(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 2))
        engine.submit_order(limit(Side.SELL, 101, 2))
        engine.submit_order(limit(Side.BUY, 101, 4))  # sweeps both levels

        history = engine.trade_history()
        self.assertEqual(len(history), 2)
        self.assertEqual([t.price for t in history], [100, 101])

    def test_history_persists_after_being_returned_from_submit(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 5))
        engine.submit_order(limit(Side.BUY, 100, 5))

        # trade_history is queryable independently, not just the return value
        self.assertEqual(len(engine.trade_history()), 1)

    def test_history_filters_by_symbol(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 5, symbol="AAA"))
        engine.submit_order(limit(Side.BUY, 100, 5, symbol="AAA"))
        engine.submit_order(limit(Side.SELL, 50, 3, symbol="BBB"))
        engine.submit_order(limit(Side.BUY, 50, 3, symbol="BBB"))

        self.assertEqual(len(engine.trade_history()), 2)
        self.assertEqual(len(engine.trade_history(symbol="AAA")), 1)
        self.assertEqual(engine.trade_history(symbol="AAA")[0].symbol, "AAA")

    def test_returned_history_is_a_copy(self):
        engine = MatchingEngine()
        engine.submit_order(limit(Side.SELL, 100, 5))
        engine.submit_order(limit(Side.BUY, 100, 5))

        history = engine.trade_history()
        history.clear()  # mutating the returned list...

        self.assertEqual(len(engine.trade_history()), 1)  # ...must not affect the engine


class TestTradeSubscribers(unittest.TestCase):
    def test_listener_is_called_synchronously_for_each_trade(self):
        engine = MatchingEngine()
        received = []
        engine.on_trade(received.append)

        engine.submit_order(limit(Side.SELL, 100, 5))
        self.assertEqual(received, [])  # no trade yet, nothing to publish

        engine.submit_order(limit(Side.BUY, 100, 5))
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].price, 100)

    def test_multiple_listeners_all_receive_the_trade(self):
        engine = MatchingEngine()
        a, b = [], []
        engine.on_trade(a.append)
        engine.on_trade(b.append)

        engine.submit_order(limit(Side.SELL, 100, 5))
        engine.submit_order(limit(Side.BUY, 100, 5))

        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)

    def test_off_trade_unsubscribes(self):
        engine = MatchingEngine()
        received = []
        engine.on_trade(received.append)
        self.assertTrue(engine.off_trade(received.append))

        engine.submit_order(limit(Side.SELL, 100, 5))
        engine.submit_order(limit(Side.BUY, 100, 5))

        self.assertEqual(received, [])

    def test_off_trade_on_unregistered_listener_returns_false(self):
        engine = MatchingEngine()
        self.assertFalse(engine.off_trade(lambda trade: None))

    def test_broken_listener_does_not_break_matching_or_other_listeners(self):
        engine = MatchingEngine()
        received = []

        def broken_listener(trade):
            raise RuntimeError("boom")

        engine.on_trade(broken_listener)
        engine.on_trade(received.append)

        with self.assertWarns(RuntimeWarning):
            trades = engine.submit_order(limit(Side.SELL, 100, 5))
            trades += engine.submit_order(limit(Side.BUY, 100, 5))

        self.assertEqual(len(trades), 1)  # matching still succeeded
        self.assertEqual(len(received), 1)  # the other listener still ran


if __name__ == "__main__":
    unittest.main()
