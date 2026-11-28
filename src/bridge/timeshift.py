"""Dời trục thời gian giữa ngày nghiệp vụ của Ops Chest và ngày hiện tại của Retail-AI.

Ops Chest vận hành theo mốc ngày nghiệp vụ (vd 26/06/2024), trong khi Retail-AI dùng ngày hiện tại. Nếu giữ HSD gốc,
kiosk sẽ coi mọi lô là hết hạn. Bridge tính `shift = ngày thật (Asia/Ho_Chi_Minh) − ngày nghiệp vụ Ops Chest` (số ngày
nguyên) rồi cộng `shift` vào MỌI ngày và giờ lấy từ Ops Chest. Mốc sự kiện đã xảy ra (giờ nhận hàng, giờ xuất
feed) không bao giờ vượt quá thời điểm hiện tại; HSD là ngày trong tương lai nên chỉ dời, không chặn.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TimeShift:
    ops_today: date
    real_today: date
    tz: ZoneInfo
    now: datetime  # aware

    @classmethod
    def compute(cls, ops_today: date, now: datetime | None = None, tz: str = "Asia/Ho_Chi_Minh") -> TimeShift:
        zone = ZoneInfo(tz)
        current = (now or datetime.now(zone)).astimezone(zone)
        return cls(ops_today=ops_today, real_today=current.date(), tz=zone, now=current)

    @property
    def days(self) -> int:
        return (self.real_today - self.ops_today).days

    def date(self, d: date | str) -> date:
        """Dời một ngày (HSD, ngày dự kiến) — không chặn theo hiện tại."""
        if isinstance(d, str):
            d = date.fromisoformat(d)
        return d + timedelta(days=self.days)

    def event(self, value: datetime | date | str) -> datetime:
        """Dời một mốc sự kiện đã xảy ra. Giờ không kèm múi giờ được hiểu là giờ địa phương của cửa hàng.
        Kết quả bị chặn ở thời điểm hiện tại."""
        if isinstance(value, str):
            value = datetime.fromisoformat(value) if "T" in value or " " in value else date.fromisoformat(value)
        if not isinstance(value, datetime):
            value = datetime.combine(value, time(8, 0))
        if value.tzinfo is None:
            value = value.replace(tzinfo=self.tz)
        shifted = value + timedelta(days=self.days)
        return min(shifted, self.now)
