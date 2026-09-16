"""Interactive demo of the matching engine.

Run with:  python demo.py
"""
from matching_engine import MatchingEngine, Order, OrderType, Side


def print_trades(trades):
    if not trades:
        print("  (no trades)")
    for t in trades:
        print(f"  TRADE  {t.quantity} @ {t.price}   (buy #{t.buy_order_id} / sell #{t.sell_order_id})")


def print_book(engine: MatchingEngine, symbol: str) -> None:
    book = engine.order_book(symbol)
    depth = book.depth()
    print(f"\n  {'BIDS':>16} | {'ASKS':<16}")
    rows = max(len(depth["bids"]), len(depth["asks"]))
    for i in range(rows):
        bid = f"{depth['bids'][i][1]} @ {depth['bids'][i][0]}" if i < len(depth["bids"]) else ""
        ask = f"{depth['asks'][i][1]} @ {depth['asks'][i][0]}" if i < len(depth["asks"]) else ""
        print(f"  {bid:>16} | {ask:<16}")
    print()


def main() -> None:
    engine = MatchingEngine()
    symbol = "BTC-USD"

    print("1) Resting limit orders build up the book")
    for side, price, qty in [
        (Side.SELL, 101, 2),
        (Side.SELL, 102, 3),
        (Side.SELL, 100, 1),
        (Side.BUY, 98, 4),
        (Side.BUY, 99, 2),
    ]:
        order = Order(side=side, order_type=OrderType.LIMIT, price=price, quantity=qty, symbol=symbol)
        trades = engine.submit_order(order)
        print(f"  submit {order.side.value:4} {qty} @ {price} -> id {order.id}")
        print_trades(trades)
    print_book(engine, symbol)

    print("2) A crossing limit buy order eats into the ask side (price-time priority)")
    order = Order(side=Side.BUY, order_type=OrderType.LIMIT, price=101, quantity=3, symbol=symbol)
    print(f"  submit {order.side.value} {order.quantity} @ {order.price} -> id {order.id}")
    print_trades(engine.submit_order(order))
    print_book(engine, symbol)

    print("3) A market sell order sweeps the best available bids")
    order = Order(side=Side.SELL, order_type=OrderType.MARKET, quantity=5, symbol=symbol)
    print(f"  submit {order.side.value} MARKET {order.quantity}")
    print_trades(engine.submit_order(order))
    print_book(engine, symbol)

    print("4) Cancelling a resting order removes it from the book")
    order = Order(side=Side.BUY, order_type=OrderType.LIMIT, price=90, quantity=10, symbol=symbol)
    engine.submit_order(order)
    print(f"  resting order id {order.id} @ 90, cancel -> {engine.cancel_order(symbol, order.id)}")
    print_book(engine, symbol)

    print("5) The engine publishes a stream of execution events")
    engine.on_trade(lambda t: print(f"  [live] {t.quantity} @ {t.price} (buy #{t.buy_order_id} / sell #{t.sell_order_id})"))
    engine.submit_order(Order(side=Side.SELL, order_type=OrderType.LIMIT, price=105, quantity=3, symbol=symbol))
    print("  submitting a crossing buy order -> the listener above fires live:")
    engine.submit_order(Order(side=Side.BUY, order_type=OrderType.LIMIT, price=105, quantity=3, symbol=symbol))
    print(f"\n  full trade history so far ({len(engine.trade_history(symbol))} trades):")
    for t in engine.trade_history(symbol):
        print(f"    {t}")


if __name__ == "__main__":
    main()
