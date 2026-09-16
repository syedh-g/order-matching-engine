"""Core data models: Order, Trade, and their supporting enums."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from time import time_ns
from typing import Optional


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(Enum):
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


_id_counter = itertools.count(1)


@dataclass
class Order:
    """A single buy or sell order.

    Limit orders must carry a price and rest on the book if not fully
    filled. Market orders must not carry a price; any quantity left
    unfilled after matching is discarded rather than resting on the book.
    """

    side: Side
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    symbol: str = "DEFAULT"
    id: int = field(default_factory=lambda: next(_id_counter))
    timestamp: int = field(default_factory=time_ns)
    remaining: float = field(init=False)
    status: OrderStatus = field(default=OrderStatus.OPEN, init=False)

    def __post_init__(self) -> None:
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("Limit orders must have a price")
        if self.order_type == OrderType.MARKET and self.price is not None:
            raise ValueError("Market orders must not have a price")
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")
        self.remaining = self.quantity

    @property
    def filled(self) -> float:
        return self.quantity - self.remaining

    def __repr__(self) -> str:
        price = f"{self.price}" if self.price is not None else "MKT"
        return (
            f"Order(id={self.id}, {self.side.value}, {self.order_type.value}, "
            f"price={price}, qty={self.quantity}, remaining={self.remaining}, "
            f"status={self.status.value})"
        )


@dataclass(frozen=True)
class Trade:
    """A single, immutable execution resulting from matching two orders."""

    symbol: str
    price: float
    quantity: float
    buy_order_id: int
    sell_order_id: int
    timestamp: int = field(default_factory=time_ns)

    def __repr__(self) -> str:
        return (
            f"Trade(symbol={self.symbol}, price={self.price}, qty={self.quantity}, "
            f"buy_id={self.buy_order_id}, sell_id={self.sell_order_id})"
        )
