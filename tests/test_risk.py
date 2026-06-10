from datetime import date

from src.risk.manager import RiskManager


def test_blocks_oversized_entries():
    rm = RiskManager(max_position_size=2, max_daily_loss=1000)
    assert rm.allow_entry(4)          # 2 NQ + 2 ES is fine
    assert not rm.allow_entry(5)      # exceeds 2 * per-leg cap


def test_daily_loss_limit_blocks_and_resets():
    rm = RiskManager(max_position_size=3, max_daily_loss=1000)
    d1, d2 = date(2026, 6, 1), date(2026, 6, 2)
    rm.record_pnl(-600, today=d1)
    assert rm.allow_entry(2, today=d1)
    rm.record_pnl(-500, today=d1)
    assert not rm.allow_entry(2, today=d1)   # -1100 breaches the limit
    assert rm.allow_entry(2, today=d2)       # resets the next day


def test_wins_offset_losses():
    rm = RiskManager(max_daily_loss=1000)
    d = date(2026, 6, 1)
    rm.record_pnl(-900, today=d)
    rm.record_pnl(500, today=d)
    assert rm.allow_entry(2, today=d)
