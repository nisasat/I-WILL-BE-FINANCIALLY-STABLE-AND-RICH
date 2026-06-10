"""Pure-python signal engine for the NQ/ES spread.

Kept free of backtrader so the exact same math drives both the backtest
strategy and the live trading loop (and is easy to unit-test).
"""

from dataclasses import dataclass

import numpy as np

FLAT, LONG_SPREAD, SHORT_SPREAD = 0, 1, -1


@dataclass
class SpreadState:
    beta: float
    zscore: float


@dataclass
class Signal:
    action: str  # "enter_long", "enter_short", "exit", "hold"
    state: SpreadState


def hedge_ratio(log_nq: np.ndarray, log_es: np.ndarray) -> float:
    """OLS slope of log(NQ) on log(ES)."""
    es_centered = log_es - log_es.mean()
    denom = float(np.dot(es_centered, es_centered))
    if denom == 0.0:
        return 1.0
    return float(np.dot(es_centered, log_nq - log_nq.mean()) / denom)


def spread_state(
    nq_closes: np.ndarray,
    es_closes: np.ndarray,
    beta_lookback: int,
    z_lookback: int,
) -> SpreadState | None:
    """Compute the current hedge ratio and spread z-score.

    Returns None until enough history has accumulated, or when the spread
    has no variance (degenerate input).
    """
    if len(nq_closes) < beta_lookback or len(es_closes) < beta_lookback:
        return None

    log_nq = np.log(nq_closes[-beta_lookback:])
    log_es = np.log(es_closes[-beta_lookback:])
    beta = hedge_ratio(log_nq, log_es)

    spread = log_nq - beta * log_es
    window = spread[-z_lookback:]
    std = float(window.std(ddof=1))
    if std == 0.0 or not np.isfinite(std):
        return None
    z = float((spread[-1] - window.mean()) / std)
    return SpreadState(beta=beta, zscore=z)


def next_signal(
    position: int,
    holding_bars: int,
    state: SpreadState,
    entry_z: float,
    exit_z: float,
    stop_z: float,
    max_holding_bars: int,
) -> Signal:
    """Decide the next action given current position and spread state.

    Position convention: LONG_SPREAD = long NQ / short ES (entered when the
    spread is *below* its mean, z < -entry_z); SHORT_SPREAD is the mirror.
    """
    z = state.zscore

    if position == FLAT:
        if z <= -entry_z:
            return Signal("enter_long", state)
        if z >= entry_z:
            return Signal("enter_short", state)
        return Signal("hold", state)

    # In a position: stop out if the spread blows further out, exit on
    # reversion to the mean or when the time stop hits.
    if abs(z) >= stop_z:
        return Signal("exit", state)
    if holding_bars >= max_holding_bars:
        return Signal("exit", state)
    if position == LONG_SPREAD and z >= -exit_z:
        return Signal("exit", state)
    if position == SHORT_SPREAD and z <= exit_z:
        return Signal("exit", state)
    return Signal("hold", state)


def es_hedge_contracts(
    nq_contracts: int,
    beta: float,
    nq_price: float,
    es_price: float,
    nq_mult: float = 20.0,
    es_mult: float = 50.0,
) -> int:
    """ES contracts needed to dollar-hedge *nq_contracts* NQ at ratio *beta*."""
    notional_ratio = (nq_price * nq_mult) / (es_price * es_mult)
    return max(1, round(beta * notional_ratio * nq_contracts))
