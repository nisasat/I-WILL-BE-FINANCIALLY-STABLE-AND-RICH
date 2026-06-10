"""Risk guards that sit between strategy signals and order execution."""

import logging
from dataclasses import dataclass, field
from datetime import date


@dataclass
class RiskManager:
    """Position-size cap and daily loss limit.

    `record_pnl` must be fed realized PnL (the strategy does this from
    notify_trade in backtests; the live loop does it from fills). Once the
    daily loss limit is breached, `allow_entry` returns False until the next
    calendar day.
    """

    max_position_size: int = 3
    max_daily_loss: float = 2_000.0
    _day: date | None = None
    _daily_pnl: float = 0.0
    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("bot.risk"), repr=False
    )

    def _roll_day(self, today: date) -> None:
        if self._day != today:
            self._day = today
            self._daily_pnl = 0.0

    def record_pnl(self, pnl: float, today: date | None = None) -> None:
        self._roll_day(today or date.today())
        self._daily_pnl += pnl

    def allow_entry(self, total_contracts: int, today: date | None = None) -> bool:
        self._roll_day(today or date.today())
        if total_contracts > 2 * self.max_position_size:
            self._logger.warning(
                "entry blocked: %d contracts exceeds cap %d per leg",
                total_contracts,
                self.max_position_size,
            )
            return False
        if self._daily_pnl <= -abs(self.max_daily_loss):
            self._logger.warning(
                "entry blocked: daily pnl %.2f breached loss limit %.2f",
                self._daily_pnl,
                self.max_daily_loss,
            )
            return False
        return True

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl
