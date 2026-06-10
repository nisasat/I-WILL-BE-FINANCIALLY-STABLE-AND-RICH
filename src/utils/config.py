"""YAML config loading with sane defaults."""

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "ibkr": {"host": "127.0.0.1", "port": 7497, "client_id": 1, "account": ""},
    "data": {"historical_dir": "data/historical", "default_timeframe": "1d"},
    "backtest": {
        "starting_cash": 150_000.0,
        "commission_per_contract": 2.5,  # one-way, per contract
        "slippage_points": 0.25,         # one tick on both NQ and ES
    },
    "strategy": {
        "beta_lookback": 90,
        "z_lookback": 30,
        "entry_z": 2.0,
        "exit_z": 0.5,
        "stop_z": 3.5,
        "max_holding_bars": 25,
        "nq_contracts": 1,
    },
    "risk": {"max_position_size": 3, "max_daily_loss": 2_000.0},
    "logging": {"level": "INFO", "file": "logs/bot.log"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path = "config/settings.yaml") -> dict[str, Any]:
    """Load YAML config from *path*, merged on top of DEFAULT_CONFIG.

    A missing file is fine — defaults are returned so backtests work out of
    the box.
    """
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    with open(path) as f:
        user_cfg = yaml.safe_load(f) or {}
    return _deep_merge(DEFAULT_CONFIG, user_cfg)
