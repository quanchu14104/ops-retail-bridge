from datetime import UTC, date, datetime, timedelta

from bridge.timeshift import TimeShift
from tests.conftest import TZ, shift_at


def test_shift_is_real_today_minus_ops_today_in_store_timezone():
    ts = shift_at()
    assert ts.days == 876
    assert ts.date("2024-06-26") == date(2026, 11, 19)
    assert ts.date(date(2024, 6, 28)) == date(2026, 11, 21)
    # 23:30 UTC ngày 18/11 đã là 19/11 ở Asia/Ho_Chi_Minh
    late = TimeShift.compute(date(2024, 6, 26), now=datetime(2026, 11, 18, 23, 30, tzinfo=UTC))
    assert late.real_today == date(2026, 11, 19) and late.days == 876


def test_events_are_shifted_and_never_in_the_future():
    ts = shift_at(hour=9)
    assert ts.event("2024-06-25T08:00:00") == datetime(2026, 11, 18, 8, 0, tzinfo=TZ)
    assert ts.event("2024-06-26T08:00:00") == datetime(2026, 11, 19, 8, 0, tzinfo=TZ)
    early = shift_at(hour=7)
    assert early.event("2024-06-26T08:00:00") == early.now  # 08:00 hôm nay chưa tới lúc 07:00
    assert early.event("2024-06-27") == early.now
    assert ts.event("2024-06-24") == datetime(2026, 11, 17, 8, 0, tzinfo=TZ)  # chỉ có ngày: hiểu là 08:00


def test_advancing_ops_by_one_day_reduces_the_shift_by_one():
    now = datetime(2026, 11, 19, 9, tzinfo=TZ)
    a = TimeShift.compute(date(2024, 6, 26), now=now)
    b = TimeShift.compute(date(2024, 6, 27), now=now)
    assert b.days == a.days - 1
    # Số ngày còn lại của lô (HSD 27/06/2024) được giữ nguyên qua phép dời: mai → hôm nay sau khi tua 1 ngày
    assert a.date("2024-06-27") == a.real_today + timedelta(days=1)
    assert b.date("2024-06-27") == b.real_today
