import json
from datetime import UTC, datetime

from bridge import overrides


def test_overrides_carry_winmart_names_prices_and_central_warehouses(crosswalk_rows, tmp_path):
    doc = overrides.build(crosswalk_rows, "w" * 64, "c" * 64, now=datetime(2026, 11, 19, tzinfo=UTC))
    assert (doc["format"], doc["version"]) == ("ops-catalog-overrides", 1)
    assert len(doc["products"]) == 164
    row = next(r for r in crosswalk_rows if r["ops_sku"] == "F0004")
    assert doc["products"]["F0004"] == {"name": row["winmart_name"], "unit_price": row["price_vnd"],
                                        "winmart_product_id": row["product_id"]}
    sups = doc["suppliers"]
    assert list(sups) == [f"NCC{n:02d}" for n in range(1, 8)]
    # NCC{n} theo nhóm FRN tăng dần (0..6), giống build_frn_catalog của Ops Chest
    assert sups["NCC07"]["name"] == "Kho tổng WinMart – Rau củ (demo)"  # nhóm 6 (80 mặt hàng)
    assert sups["NCC06"]["name"] == "Kho tổng WinMart – Trái cây (demo)"
    assert sups["NCC03"]["name"] == "Kho tổng WinMart – Thịt (demo)"
    assert len({s["name"] for s in sups.values()}) == 7
    assert all(s["email"] == "dathang@khotong-demo.test" and s["name"].endswith("(demo)") for s in sups.values())
    # Lead time, lịch giao, đơn tối thiểu, thỏa thuận: không ghi đè
    assert all(set(s) == {"name", "email"} for s in sups.values())
    assert all(set(p) == {"name", "unit_price", "winmart_product_id"} for p in doc["products"].values())

    path = tmp_path / "out" / "ops_catalog_overrides.json"
    overrides.write(doc, path)
    assert json.loads(path.read_text(encoding="utf-8")) == doc
