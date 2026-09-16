"""Top-level matching engine, routing orders to per-symbol order books."""
from __future__ import annotations

import warnings
from typing import Callable, Dict, List, Optional

from .models import Order, Trade
from .order_book import OrderBook

TradeListener = Callable[[Trade], None]


class MatchingEngine:
    """Owns one OrderBook per symbol, dispatches orders, and publishes a
    stream of execution events (Trades) as they occur.

    Every trade produced by any symbol's book is, in execution order:
      1. appended to an engine-wide, append-only log (query it later with
         `trade_history`), and
      2. broadcast synchronously to every subscriber registered via
         `on_trade`, before `submit_order` returns.

    `Trade` itself is a frozen dataclass, so once published a trade record
    can't be altered by a subscriber or by code holding a stale reference.
    """

    def __init__(self) -> None:
        self._books: Dict[str, OrderBook] = {}
        self._trade_log: List[Trade] = []
        self._listeners: List[TradeListener] = []

    def submit_order(self, order: Order) -> List[Trade]:
        """Submit an order for matching. Returns any trades it generated."""
        trades = self._book_for(order.symbol).submit(order)
        for trade in trades:
            self._publish(trade)
        return trades

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """Cancel a resting order. Returns True if it was found and removed."""
        book = self._books.get(symbol)
        return book.cancel(order_id) if book else False

    def order_book(self, symbol: str) -> Optional[OrderBook]:
        return self._books.get(symbol)

    def depth(self, symbol: str, levels: int = 5):
        return self._book_for(symbol).depth(levels)

    def best_bid_ask(self, symbol: str):
        book = self._book_for(symbol)
        return book.best_bid(), book.best_ask()

    # ------------------------------------------------------------------ #
    # Execution event stream
    # ------------------------------------------------------------------ #
    def on_trade(self, listener: TradeListener) -> None:
        """Subscribe to the trade stream.

        `listener` is called with each Trade, synchronously, in execution
        order, as part of the `submit_order` call that produced it.
        """
        self._listeners.append(listener)

    def off_trade(self, listener: TradeListener) -> bool:
        """Unsubscribe a listener. Returns True if it was registered."""
        try:
            self._listeners.remove(listener)
            return True
        except ValueError:
            return False

    def trade_history(self, symbol: Optional[str] = None) -> List[Trade]:
        """The full, ordered log of every trade executed so far.

        Pass `symbol` to filter to one symbol's trades. The returned list
        is a snapshot copy; mutating it does not affect the engine's log.
        """
        if symbol is None:
            return list(self._trade_log)
        return [trade for trade in self._trade_log if trade.symbol == symbol]

    def _publish(self, trade: Trade) -> None:
        self._trade_log.append(trade)
        # Iterate a copy: a listener that subscribes/unsubscribes during
        # its own call must not corrupt this pass over `_listeners`.
        for listener in list(self._listeners):
            try:
                listener(trade)
            except Exception as exc:
                # One broken subscriber must not stop other subscribers
                # from being notified, or break matching for the caller.
                warnings.warn(f"on_trade listener {listener!r} raised {exc!r}", RuntimeWarning)

    def _book_for(self, symbol: str) -> OrderBook:
        if symbol not in self._books:
            self._books[symbol] = OrderBook(symbol)
        return self._books[symbol]
