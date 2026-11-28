from collections import Counter

import pytest

from bridge import crosswalk
from bridge.config import Config
from tests.conftest import ROOT

CFG = Config.load(env={})
REAL_DATA = CFG.thanh_lam_catalog_path.exists() and CFG.frn_data_path.exists()
needs_data = pytest.mark.skipif(not REAL_DATA, reason="cần file Thanh Lam Mart (Retail-AI) và FRN (Ops Chest)")


def _w(pid, item_no, dept, sub, price=10_000, sale=None, extra=""):
    return {"product_id": pid, "item_no": str(item_no), "name": f"SP {pid}", "price_vnd": price,
            "sale_price_vnd": price if sale is None else sale, "sub_department": crosswalk.FRESH_SUB_DEPARTMENT,
            "category_name": sub, "category_hierarchy": f"Thực phẩm > {crosswalk.FRESH_SUB_DEPARTMENT} > {dept} > "
                                                        f"{sub}{extra}"}


def test_pool_excludes_dried_seafood_bamboo_and_quarantine():
    rows = [_w("A", 1, "Rau củ", "Rau ăn lá"), _w("B", 2, "Rau củ", "Măng", extra=" > Măng sơ chế"),
            _w("C", 3, "Thủy hải sản", "Thủy hải sản khô"), _w("D", 4, "Thịt", "Lợn", sale=12_000),
            dict(_w("E", 5, "Rau củ", "Rau ăn lá"), sub_department="Thực phẩm công nghệ")]
    assert [r["product_id"] for r in crosswalk.thanh_lam_pool(rows)] == ["A"]


def test_structure_preserving_assignment_on_a_small_world():
    frn = [crosswalk.FrnItem(i, g, c1, c1 * 10, demand) for i, g, c1, demand in [
        (1, 0, 1, 5.0), (2, 0, 1, 9.0), (3, 0, 2, 1.0),  # nhóm lớn: 3 mặt hàng
        (4, 1, 3, 2.0),                                   # nhóm nhỏ
    ]]
    pool = [_w("R1", 30, "Rau củ", "Lá"), _w("R2", 10, "Rau củ", "Lá"), _w("R3", 20, "Rau củ", "Củ"),
            _w("R4", 40, "Rau củ", "Lá"), _w("T1", 50, "Trái cây", "Nội địa")]
    rows = crosswalk.build(frn, pool)
    got = {r["frn_id"]: r["product_id"] for r in rows}
    # nhóm 0 (3) → Rau củ (4); cat1=1 (2 món) → danh mục con lớn nhất "Lá"; nhu cầu cao nhất ↔ item_no nhỏ nhất
    assert got == {2: "R2", 1: "R1", 3: "R3", 4: "T1"}
    assert {r["method"] for r in rows} == {"auto-v1"}
    assert all("crosswalk auto-v1" in r["note"] for r in rows)


@needs_data
def test_real_crosswalk_is_one_to_one_and_reproducible():
    thanh_lam = crosswalk.load_thanh_lam(CFG.thanh_lam_catalog_path)
    frn = crosswalk.load_frn_items(CFG.frn_data_path, 18)
    assert len(frn) == 164
    assert len(crosswalk.thanh_lam_pool(thanh_lam)) == 249
    assert sorted(Counter(i.group for i in frn).values(), reverse=True) == [80, 40, 21, 8, 6, 6, 3]
    rows = crosswalk.build(frn, thanh_lam)
    assert rows == crosswalk.build(frn, thanh_lam)
    res = crosswalk.check(rows, thanh_lam, "sha", frn=frn)
    assert res.ok, res.errors
    dept = {g: Counter(r["thanh_lam_category"].split(" > ")[0] for r in rows if r["frn_group"] == g) for g in range(7)}
    assert dept[6] == {"Rau củ": 80} and dept[5] == {"Trái cây": 40} and dept[2] == {"Thịt": 21}
    # Bản đã commit (data/crosswalk.csv) đúng là kết quả của thuật toán trên dữ liệu hiện tại
    committed = crosswalk.read_csv(ROOT / "data" / "crosswalk.csv")
    assert [(r["ops_sku"], r["product_id"]) for r in committed] == [(r["ops_sku"], r["product_id"]) for r in rows]


@needs_data
def test_manual_rows_survive_rebuild_and_check_catches_errors(crosswalk_rows):
    thanh_lam = crosswalk.load_thanh_lam(CFG.thanh_lam_catalog_path)
    frn = crosswalk.load_frn_items(CFG.frn_data_path, 18)
    used = {r["product_id"] for r in crosswalk_rows}
    spare = next(r for r in crosswalk.thanh_lam_pool(thanh_lam) if r["product_id"] not in used)
    manual = [{"frn_id": 4, "product_id": spare["product_id"], "note": "đổi tay thủ công"}]
    rows = crosswalk.build(frn, thanh_lam, manual)
    row = next(r for r in rows if r["ops_sku"] == "F0004")
    assert (row["product_id"], row["method"], row["note"]) == (spare["product_id"], "manual", "đổi tay thủ công")
    assert crosswalk.check(rows, thanh_lam, "sha", frn=frn).ok

    broken = [dict(r) for r in crosswalk_rows]
    broken[1]["product_id"] = broken[0]["product_id"]
    broken[2]["product_id"] = "TLM_KHONG_CO"
    quarantined = next(r for r in thanh_lam if crosswalk.is_quarantined(r))
    broken[3]["product_id"] = quarantined["product_id"]
    res = crosswalk.check(broken[:-1], thanh_lam, "sha", frn=frn, ops_skus={r["ops_sku"] for r in crosswalk_rows})
    joined = " | ".join(res.errors)
    assert "Cần đúng 164 dòng" in joined and "Trùng product_id" in joined
    assert "không có trong file Thanh Lam Mart" in joined and "quarantine" in joined
    assert "Lệch tập SKU với FRN" in joined and "Lệch tập SKU với Ops Chest" in joined
