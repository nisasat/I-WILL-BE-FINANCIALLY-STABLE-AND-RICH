"""Live/paper trading loop.

Runs the same signal engine as the backtest (`src.strategies.signals`) on
daily bars pulled from IBKR, once per polling interval. This is deliberately
simple and conservative: one spread position at a time, market orders,
risk-manager gate on every entry.

IMPORTANT: run this against a PAPER account (TWS port 7497 / Gateway 4002)
until you have verified behavior. Futures losses can exceed your deposit.
"""

import logging
import time
from typing import Any

import numpy as np

from ..broker.ibkr import IBKRClient
from ..risk.manager import RiskManager
from ..strategies import signals
from ..strategies.signals import FLAT, LONG_SPREAD, SHORT_SPREAD

logger = logging.getLogger("bot.live")


class LiveTrader:
    def __init__(self, config: dict[str, Any]):
        self.cfg = config
        ib_cfg = config["ibkr"]
        self.client = IBKRClient(ib_cfg["host"], int(ib_cfg["port"]), int(ib_cfg["client_id"]))
        risk_cfg = config["risk"]
        self.risk = RiskManager(
            max_position_size=int(risk_cfg["max_position_size"]),
            max_daily_loss=float(risk_cfg["max_daily_loss"]),
        )
        self.position_dir = FLAT
        self.holding_bars = 0
        self.es_size = 0
        self.nq_size = 0

    def run(self, poll_seconds: int = 3600) -> None:
        s = self.cfg["strategy"]
        self.client.connect()
        try:
            while True:
                try:
                    self._step(s)
                except Exception:
                    logger.exception("live step failed; retrying next poll")
                time.sleep(poll_seconds)
        finally:
            self._flatten()
            self.client.disconnect()

    def _step(self, s: dict[str, Any]) -> None:
        lookback = int(s["beta_lookback"]) + 5
        nq = self.client.daily_bars("NQ", lookback)
        es = self.client.daily_bars("ES", lookback)
        n = min(len(nq), len(es))
        state = signals.spread_state(
            np.asarray(nq["close"])[-n:],
            np.asarray(es["close"])[-n:],
            int(s["beta_lookback"]),
            int(s["z_lookback"]),
        )
        if state is None:
            logger.info("not enough history yet (%d bars)", n)
            return

        sig = signals.next_signal(
            position=self.position_dir,
            holding_bars=self.holding_bars,
            state=state,
            entry_z=float(s["entry_z"]),
            exit_z=float(s["exit_z"]),
            stop_z=float(s["stop_z"]),
            max_holding_bars=int(s["max_holding_bars"]),
        )
        logger.info("z=%.2f beta=%.3f action=%s", state.zscore, state.beta, sig.action)

        if self.position_dir != FLAT:
            self.holding_bars += 1

        if sig.action == "exit":
            self._flatten()
        elif sig.action in ("enter_long", "enter_short") and self.position_dir == FLAT:
            self._enter(sig.action, state, nq["close"].iloc[-1], es["close"].iloc[-1], s)

    def _enter(self, action: str, state, nq_price: float, es_price: float, s: dict) -> None:
        nq_size = min(int(s["nq_contracts"]), self.risk.max_position_size)
        es_size = signals.es_hedge_contracts(nq_size, state.beta, float(nq_price), float(es_price))
        if not self.risk.allow_entry(nq_size + es_size):
            logger.warning("entry blocked by risk manager")
            return
        sign = 1 if action == "enter_long" else -1
        self.client.market_order("NQ", sign * nq_size)
        self.client.market_order("ES", -sign * es_size)
        self.position_dir = LONG_SPREAD if sign == 1 else SHORT_SPREAD
        self.nq_size, self.es_size = sign * nq_size, -sign * es_size
        self.holding_bars = 0

    def _flatten(self) -> None:
        if self.position_dir == FLAT:
            return
        if self.nq_size:
            self.client.market_order("NQ", -self.nq_size)
        if self.es_size:
            self.client.market_order("ES", -self.es_size)
        self.position_dir = FLAT
        self.nq_size = self.es_size = 0
        self.holding_bars = 0
