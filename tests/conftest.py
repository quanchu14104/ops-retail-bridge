"""Fixture: response Ops Chest ghi lại ngày 19/11/2026 từ worktree feat/catalog-overrides (seed FRN kèm overrides,
ngày nghiệp vụ 26/06/2024), cắt còn 5 SKU và 3 PO. Giữ nguyên các trường nội bộ (unit_cost, supplier,
value_at_risk, expected_*, options) để test chứng minh bridge loại bỏ chúng."""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bridge import crosswalk
from bridge.timeshift import TimeShift

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def ops():
    return {
        "meta": load("ops_meta.json"),
        "products": load("ops_products.json"),
        "expiring": load("ops_expiring.json"),
        "pos": load("ops_purchase_orders.json"),
        "details": {p["id"]: load(f"ops_purchase_order_{p['id']}.json") for p in load("ops_purchase_orders.json")},
    }


@pytest.fixture(scope="session")
def crosswalk_rows():
    return crosswalk.read_csv(ROOT / "data" / "crosswalk.csv")


def shift_at(hour: int = 9, minute: int = 0, day: date = date(2026, 11, 19)) -> TimeShift:
    return TimeShift.compute(date(2024, 6, 26), now=datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ))


@pytest.fixture()
def ts():
    return shift_at()
