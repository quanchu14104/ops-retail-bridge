import copy
import json
from pathlib import Path

import pytest

from bridge.feed import (
    ITEM_FIELDS,
    LOT_FIELDS,
    ContractViolation,
    build_feed,
    sale_price,
    validate,
    write_atomic,
)
from tests.conftest import ROOT, shift_at


def _items(feed):
    return {i["ops_sku"]: i for i in feed["items"]}


def _feed(ops, rows, ts):
    feed, warnings = build_feed(ops["meta"], ops["products"], ops["expiring"], rows, ts)
    return feed, warnings


def test_only_allowed_fields_leave_ops_chest(ops, crosswalk_rows, ts):
    raw = json.dumps(ops["expiring"])
    assert all(k in raw for k in ("unit_cost", "supplier", "value_at_risk", "expected_waste", "options"))
    feed, warnings = _feed(ops, crosswalk_rows, ts)
    text = json.dumps(feed, ensure_ascii=False)
    for forbidden in ("unit_cost", "supplier", "value_at_risk", "expected_", "options", "Kho tổng"):
        assert forbidden not in text
    assert len(feed["items"]) == 5  # fixture có 5 SKU; 159 SKU còn lại báo cảnh báo
    assert len(warnings) == 159
    for item in feed["items"]:
        assert tuple(item) == ITEM_FIELDS
        assert all(tuple(lot) == LOT_FIELDS for lot in item["lots"])


def test_validate_rejects_leaks_and_unknown_fields(ops, crosswalk_rows, ts):
    feed, _ = _feed(ops, crosswalk_rows, ts)
    leaked = copy.deepcopy(feed)
    leaked["items"][0]["lots"].append({"qty": 1, "expiry": "2026-11-19", "unit_cost": 1})
    with pytest.raises(ContractViolation):
        validate(leaked)
    extra = copy.deepcopy(feed)
    extra["items"][0]["supplier"] = "x"
    with pytest.raises(ContractViolation):
        validate(extra)
    wrong = dict(feed, version=2)
    with pytest.raises(ContractViolation):
        validate(wrong)


def test_header_and_date_shift(ops, crosswalk_rows, ts):
    feed, _ = _feed(ops, crosswalk_rows, ts)
    assert (feed["contract"], feed["version"]) == ("ops-feed", 1)
    assert feed["published_at"] == "2026-11-19T09:00:00+07:00"
    assert feed["ops_business_date"] == "2024-06-26"
    assert feed["date_shift_days"] == 876
    assert feed["store_name"] == "WinMart+ Demo (giả định)"
    item = _items(feed)["F0599"]  # lô 13 cái, HSD 26/06/2024 (ngày bán cuối)
    assert item["product_id"] == "WIN_10281592"
    assert item["earliest_expiry"] == "2026-11-19"
    assert item["lots"] == [{"qty": 13, "expiry": "2026-11-19", "markdown_pct": 0.0}]
    assert (item["status"], item["sellable_qty"], item["coverage_complete"]) == ("IN_STOCK", 13, True)
    assert item["unit_price_vnd"] == item["sale_price_vnd"] == 299900
    assert item["promotion_text"] is None


def test_same_product_with_several_lots(ops, crosswalk_rows, ts):
    item = _items(_feed(ops, crosswalk_rows, ts)[0])["F0829"]
    assert item["sellable_qty"] == 5
    assert item["earliest_expiry"] == "2026-11-19"
    assert [lot["expiry"] for lot in item["lots"]] == ["2026-11-19", "2026-11-20"]
    lots = [lot for lot in ops["expiring"]["lots"] if lot["sku"] == "F0829"]
    lots[0]["markdown_pct"], lots[1]["markdown_pct"] = 0.3, 0.1
    item = _items(_feed(ops, crosswalk_rows, ts)[0])["F0829"]
    unit = item["unit_price_vnd"]
    assert item["sale_price_vnd"] == sale_price(unit, 0.3)
    assert item["promotion_text"] == "Giảm 30% cho 2 sản phẩm HSD 19/11; Giảm 10% cho 3 sản phẩm HSD 20/11"


def test_out_of_stock_product(ops, crosswalk_rows, ts):
    item = _items(_feed(ops, crosswalk_rows, ts)[0])["F0005"]
    assert (item["status"], item["sellable_qty"], item["earliest_expiry"], item["lots"]) == (
        "OUT_OF_STOCK", 0, None, [])
    assert item["coverage_complete"] is True


def test_evening_markdown_applies_on_last_day_after_markdown_hour(ops, crosswalk_rows):
    lot = next(lot for lot in ops["expiring"]["lots"] if lot["sku"] == "F0599")
    assert lot["days_left"] == 0 and lot["markdown_hour"] == 11
    lot.update(markdown_pct=0.2, evening_markdown_pct=0.4)
    morning = _items(_feed(ops, crosswalk_rows, shift_at(hour=10, minute=59))[0])["F0599"]
    evening = _items(_feed(ops, crosswalk_rows, shift_at(hour=11))[0])["F0599"]
    assert morning["lots"][0]["markdown_pct"] == 0.2
    assert morning["promotion_text"] == "Giảm 20% cho 13 sản phẩm HSD 19/11"
    assert evening["lots"][0]["markdown_pct"] == 0.4
    assert evening["sale_price_vnd"] == 179900  # 299.900 × 0,6 = 179.940 → làm tròn 100 đồng
    assert evening["promotion_text"] == "Giảm 40% cho 13 sản phẩm HSD 19/11"
    # Lô chưa tới ngày bán cuối không dùng mức tối
    later = next(lot for lot in ops["expiring"]["lots"] if lot["sku"] == "F0829" and lot["days_left"] == 1)
    later.update(markdown_pct=0.1, evening_markdown_pct=0.5)
    item = _items(_feed(ops, crosswalk_rows, shift_at(hour=20))[0])["F0829"]
    assert [lot["markdown_pct"] for lot in item["lots"]] == [0.0, 0.1]
    # Ops Chest bản hiện tại không có evening_markdown_pct: coi là 0, giữ markdown_pct
    del lot["evening_markdown_pct"]
    assert _items(_feed(ops, crosswalk_rows, shift_at(hour=20))[0])["F0599"]["lots"][0]["markdown_pct"] == 0.2


def test_coverage_complete_and_expired_lots(ops, crosswalk_rows, ts):
    product = next(p for p in ops["products"] if p["sku"] == "F0599")
    expired = dict(next(lot for lot in ops["expiring"]["lots"] if lot["sku"] == "F0599"),
                   lot_id=999, qty=4, days_left=-1, expiry_date="2024-06-25", status="EXPIRED")
    ops["expiring"]["lots"].append(expired)
    product["on_hand"] = 17  # 13 + 4 lô quá hạn
    item = _items(_feed(ops, crosswalk_rows, ts)[0])["F0599"]
    assert (item["sellable_qty"], item["coverage_complete"]) == (13, True)
    assert [lot["qty"] for lot in item["lots"]] == [13]  # lô quá hạn không xuất
    product["on_hand"] = 30  # Ops Chest còn lô ngoài danh sách sắp hết hạn
    item = _items(_feed(ops, crosswalk_rows, ts)[0])["F0599"]
    assert (item["sellable_qty"], item["coverage_complete"]) == (26, False)


def test_contract_example_is_valid():
    example = json.loads((ROOT / "contract" / "ops_feed.example.json").read_text(encoding="utf-8"))
    validate(example)


def test_atomic_write_keeps_old_feed_on_failure(tmp_path, ops, crosswalk_rows, ts):
    path = tmp_path / "out" / "ops_feed.json"
    feed, _ = _feed(ops, crosswalk_rows, ts)
    write_atomic(feed, path)
    assert json.loads(path.read_text(encoding="utf-8")) == feed
    before = path.read_bytes()
    with pytest.raises(TypeError):
        write_atomic({"bad": object()}, path)
    assert path.read_bytes() == before
    assert [p.name for p in Path(path.parent).iterdir()] == ["ops_feed.json"]
