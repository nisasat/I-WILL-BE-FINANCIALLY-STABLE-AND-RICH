import numpy as np

from src.backtest.runner import format_results, run_backtest
from src.data.historical import generate_synthetic_pair
from src.strategies import signals
from src.utils.config import load_config


def test_synthetic_pair_is_cointegrated():
    nq, es = generate_synthetic_pair(n_bars=1000, seed=7)
    assert len(nq) == len(es) == 1000
    assert (nq[["open", "high", "low", "close"]] > 0).all().all()
    assert (nq["high"] >= nq[["open", "close"]].max(axis=1) - 1e-9).all()

    log_nq = np.log(np.asarray(nq["close"]))
    log_es = np.log(np.asarray(es["close"]))
    beta = signals.hedge_ratio(log_nq, log_es)
    spread = log_nq - beta * log_es
    # mean-reverting spread: lag-1 autocorrelation of changes is negative-ish
    # and the spread stays bounded, unlike a random walk
    assert abs(beta - 1.12) < 0.1
    assert spread.std() < 0.05


def test_backtest_runs_and_trades_on_synthetic_data():
    nq, es = generate_synthetic_pair(n_bars=1200, seed=42)
    config = load_config("nonexistent.yaml")  # defaults
    results = run_backtest(nq, es, config)

    assert results["closed_trades"] > 0
    assert results["final_value"] > 0
    assert isinstance(results["trade_pnls"], list)
    # report renders without raising
    assert "Backtest results" in format_results(results)
