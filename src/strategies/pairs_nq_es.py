"""NQ/ES spread mean-reversion strategy (backtrader implementation).

Trades the beta-hedged log spread between NQ and ES:
  - rolling OLS hedge ratio over `beta_lookback` bars
  - z-score of the spread over `z_lookback` bars
  - enter long spread (long NQ / short ES) at z <= -entry_z, short at
    z >= entry_z; exit on reversion (|z| <= exit_z), blow-out stop
    (|z| >= stop_z) or a time stop (`max_holding_bars`)
  - ES leg sized to dollar-hedge the NQ leg using the contract multipliers
"""

import numpy as np

from ..risk.manager import RiskManager
from . import signals
from .base import BaseStrategy
from .signals import FLAT, LONG_SPREAD, SHORT_SPREAD


class PairsNqEsStrategy(BaseStrategy):
    params = dict(
        beta_lookback=90,
        z_lookback=30,
        entry_z=2.0,
        exit_z=0.5,
        stop_z=3.5,
        max_holding_bars=25,
        nq_contracts=1,
        nq_mult=20.0,
        es_mult=50.0,
        risk_manager=None,
    )

    def __init__(self):
        super().__init__()
        self.nq = self.datas[0]
        self.es = self.datas[1]
        self.position_dir = FLAT
        self.holding_bars = 0
        self.risk: RiskManager = self.p.risk_manager or RiskManager()
        self.zscores: list[float] = []  # exported for analysis/tests

    def next(self):
        closes_nq = np.array(self.nq.close.get(size=self.p.beta_lookback))
        closes_es = np.array(self.es.close.get(size=self.p.beta_lookback))
        state = signals.spread_state(
            closes_nq, closes_es, self.p.beta_lookback, self.p.z_lookback
        )
        if state is None:
            return
        self.zscores.append(state.zscore)

        if self.position_dir != FLAT:
            self.holding_bars += 1

        sig = signals.next_signal(
            position=self.position_dir,
            holding_bars=self.holding_bars,
            state=state,
            entry_z=self.p.entry_z,
            exit_z=self.p.exit_z,
            stop_z=self.p.stop_z,
            max_holding_bars=self.p.max_holding_bars,
        )

        if sig.action == "exit":
            self._close_spread(state.zscore)
        elif sig.action in ("enter_long", "enter_short"):
            self._open_spread(sig.action, state)

    def _open_spread(self, action: str, state: signals.SpreadState) -> None:
        nq_size = min(self.p.nq_contracts, self.risk.max_position_size)
        es_size = signals.es_hedge_contracts(
            nq_size,
            state.beta,
            float(self.nq.close[0]),
            float(self.es.close[0]),
            self.p.nq_mult,
            self.p.es_mult,
        )
        if not self.risk.allow_entry(nq_size + es_size, today=self.nq.datetime.date(0)):
            self.log(f"entry blocked by risk manager (z={state.zscore:.2f})")
            return

        if action == "enter_long":
            self.buy(data=self.nq, size=nq_size)
            self.sell(data=self.es, size=es_size)
            self.position_dir = LONG_SPREAD
        else:
            self.sell(data=self.nq, size=nq_size)
            self.buy(data=self.es, size=es_size)
            self.position_dir = SHORT_SPREAD
        self.holding_bars = 0
        self.log(
            f"ENTER {action[6:].upper()} spread z={state.zscore:.2f} "
            f"beta={state.beta:.3f} NQx{nq_size} ESx{es_size}"
        )

    def _close_spread(self, zscore: float) -> None:
        self.close(data=self.nq)
        self.close(data=self.es)
        self.log(f"EXIT spread z={zscore:.2f} after {self.holding_bars} bars")
        self.position_dir = FLAT
        self.holding_bars = 0

    def notify_trade(self, trade):
        super().notify_trade(trade)
        if trade.isclosed:
            self.risk.record_pnl(trade.pnlcomm, today=self.nq.datetime.date(0))
