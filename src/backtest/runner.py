"""Cerebro wiring: feeds, futures commissions, analyzers, result reporting."""

import logging
from typing import Any

import backtrader as bt
import pandas as pd

from ..data.feeds import make_feed
from ..risk.manager import RiskManager
from ..strategies.pairs_nq_es import PairsNqEsStrategy

logger = logging.getLogger("bot.backtest")

# Approximate CME initial margins; only affect buying-power checks, not PnL.
CONTRACTS = {
    "NQ": {"mult": 20.0, "margin": 24_000.0},
    "ES": {"mult": 50.0, "margin": 13_000.0},
}


def run_backtest(
    nq: pd.DataFrame,
    es: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Run the NQ/ES pairs strategy over the given data, return metrics."""
    bt_cfg = config["backtest"]
    strat_cfg = config["strategy"]
    risk_cfg = config["risk"]

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(float(bt_cfg["starting_cash"]))
    cerebro.broker.set_slippage_fixed(float(bt_cfg["slippage_points"]))

    for name, df in (("NQ", nq), ("ES", es)):
        cerebro.adddata(make_feed(df, name))
        spec = CONTRACTS[name]
        cerebro.broker.setcommission(
            commission=float(bt_cfg["commission_per_contract"]),
            margin=spec["margin"],
            mult=spec["mult"],
            name=name,
        )

    risk = RiskManager(
        max_position_size=int(risk_cfg["max_position_size"]),
        max_daily_loss=float(risk_cfg["max_daily_loss"]),
    )
    cerebro.addstrategy(
        PairsNqEsStrategy,
        beta_lookback=int(strat_cfg["beta_lookback"]),
        z_lookback=int(strat_cfg["z_lookback"]),
        entry_z=float(strat_cfg["entry_z"]),
        exit_z=float(strat_cfg["exit_z"]),
        stop_z=float(strat_cfg["stop_z"]),
        max_holding_bars=int(strat_cfg["max_holding_bars"]),
        nq_contracts=int(strat_cfg["nq_contracts"]),
        risk_manager=risk,
    )

    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        timeframe=bt.TimeFrame.Days,
        riskfreerate=0.0,
        annualize=True,
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")

    strat = cerebro.run()[0]

    trades = strat.analyzers.trades.get_analysis()
    total = trades.get("total", {}).get("closed", 0)
    won = trades.get("won", {}).get("total", 0)

    results = {
        "starting_cash": float(bt_cfg["starting_cash"]),
        "final_value": cerebro.broker.getvalue(),
        "net_pnl": cerebro.broker.getvalue() - float(bt_cfg["starting_cash"]),
        "sharpe": strat.analyzers.sharpe.get_analysis().get("sharperatio"),
        "max_drawdown_pct": strat.analyzers.drawdown.get_analysis()["max"]["drawdown"],
        "max_drawdown_money": strat.analyzers.drawdown.get_analysis()["max"]["moneydown"],
        "annual_return_pct": strat.analyzers.returns.get_analysis().get("rnorm100"),
        "sqn": strat.analyzers.sqn.get_analysis().get("sqn"),
        "closed_trades": total,
        "win_rate": (won / total) if total else None,
        "trade_pnls": strat.trade_pnls,
    }
    return results


def format_results(results: dict[str, Any]) -> str:
    win_rate = results["win_rate"]
    sharpe = results["sharpe"]
    lines = [
        "================ Backtest results ================",
        f"Starting cash:    ${results['starting_cash']:>12,.2f}",
        f"Final value:      ${results['final_value']:>12,.2f}",
        f"Net PnL:          ${results['net_pnl']:>12,.2f}",
        f"Annual return:    {results['annual_return_pct'] or 0:.2f}%",
        f"Sharpe (ann.):    {sharpe if sharpe is not None else float('nan'):.2f}",
        f"Max drawdown:     {results['max_drawdown_pct']:.2f}% "
        f"(${results['max_drawdown_money']:,.2f})",
        f"SQN:              {results['sqn'] or 0:.2f}",
        f"Closed trades:    {results['closed_trades']}",
        f"Win rate:         {win_rate * 100:.1f}%" if win_rate is not None else "Win rate:         n/a",
        "==================================================",
    ]
    return "\n".join(lines)
