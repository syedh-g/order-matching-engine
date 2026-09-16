"""Top-level matching engine, routing orders to per-symbol order books."""
from __future__ import annotations

from typing import Dict, List, Optional

from .models import Order, Trade
from .order_book import OrderBook


class MatchingEngine:
    """Owns one OrderBook per symbol and dispatches orders to the right one."""

    def __init__(self) -> None:
        self._books: Dict[str, OrderBook] = {}

    def submit_order(self, order: Order) -> List[Trade]:
        """Submit an order for matching. Returns any trades it generated."""
        return self._book_for(order.symbol).submit(order)

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

    def _book_for(self, symbol: str) -> OrderBook:
        if symbol not in self._books:
            self._books[symbol] = OrderBook(symbol)
        return self._books[symbol]
