import numpy as np

from src.strategies import signals
from src.strategies.signals import FLAT, LONG_SPREAD, SHORT_SPREAD, SpreadState


def make_state(z: float, beta: float = 1.1) -> SpreadState:
    return SpreadState(beta=beta, zscore=z)


def test_hedge_ratio_recovers_known_beta():
    rng = np.random.default_rng(0)
    log_es = np.cumsum(rng.normal(0, 0.01, 500)) + np.log(4000)
    log_nq = 0.5 + 1.25 * log_es + rng.normal(0, 0.001, 500)
    beta = signals.hedge_ratio(log_nq, log_es)
    assert abs(beta - 1.25) < 0.05


def test_spread_state_needs_enough_history():
    closes = np.full(50, 100.0)
    assert signals.spread_state(closes, closes, beta_lookback=90, z_lookback=30) is None


def test_spread_state_rejects_zero_variance():
    closes = np.full(100, 100.0)
    assert signals.spread_state(closes, closes, beta_lookback=90, z_lookback=30) is None


def test_entry_signals_from_flat():
    kw = dict(entry_z=2.0, exit_z=0.5, stop_z=3.5, max_holding_bars=25)
    assert signals.next_signal(FLAT, 0, make_state(-2.5), **kw).action == "enter_long"
    assert signals.next_signal(FLAT, 0, make_state(2.5), **kw).action == "enter_short"
    assert signals.next_signal(FLAT, 0, make_state(1.0), **kw).action == "hold"


def test_exit_on_reversion_stop_and_time():
    kw = dict(entry_z=2.0, exit_z=0.5, stop_z=3.5, max_holding_bars=25)
    # reversion
    assert signals.next_signal(LONG_SPREAD, 3, make_state(-0.2), **kw).action == "exit"
    assert signals.next_signal(SHORT_SPREAD, 3, make_state(0.2), **kw).action == "exit"
    # blow-out stop
    assert signals.next_signal(LONG_SPREAD, 3, make_state(-4.0), **kw).action == "exit"
    # time stop
    assert signals.next_signal(LONG_SPREAD, 25, make_state(-1.5), **kw).action == "exit"
    # still holding
    assert signals.next_signal(LONG_SPREAD, 3, make_state(-1.5), **kw).action == "hold"


def test_es_hedge_contracts_dollar_neutral():
    # 1 NQ at 21000 = $420k notional; ES at 6000 = $300k/contract.
    # beta 1.1 -> 1.1 * 1.4 = 1.54 -> 2 contracts.
    assert signals.es_hedge_contracts(1, 1.1, 21000, 6000) == 2
    assert signals.es_hedge_contracts(1, 0.7, 21000, 6000) == 1
