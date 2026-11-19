"""Sinh `out/ops_catalog_overrides.json` cho seam lúc seed của Ops Chest (CATALOG_OVERRIDES_PATH).

- Tên và giá bán Thanh Lam Mart cho từng SKU đã ánh xạ (giá vốn do Ops Chest tính lại theo tỷ lệ cũ).
- 7 nguồn hàng đổi thành "Nhà cung cấp Thanh Lam Mart – {ngành hàng} (demo)", dùng chung email `.test`. Mã NCC01…NCC07
  khớp nhóm FRN đã sắp xếp tăng dần, đúng quy tắc của `build_frn_catalog`.
- Lead time, lịch giao, đơn tối thiểu và thỏa thuận trả hàng KHÔNG có trong file, nên giữ nguyên.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

FORMAT = "ops-catalog-overrides"
VERSION = 1
SUPPLIER_EMAIL = "dathang@khotong-demo.test"
DISCLAIMER = ("Giả định demo: tên/giá Thanh Lam Mart gán cho mặt hàng FRN qua crosswalk tự đặt; nguồn hàng là kho tổng "
              "giả định, email chỉ rơi vào Mailpit (.test).")


def supplier_names(rows: list[dict]) -> dict[str, str]:
    """NCC{n} (theo thứ tự nhóm FRN tăng dần) → tên kho tổng theo ngành hàng chiếm đa số của nhóm."""
    groups = sorted({r["frn_group"] for r in rows})
    size = Counter(r["frn_group"] for r in rows)
    dept = {g: Counter(r["thanh_lam_category"].split(" > ")[0] for r in rows if r["frn_group"] == g)
            .most_common(1)[0][0] for g in groups}
    seen: Counter = Counter()
    label: dict[int, str] = {}
    for g in sorted(groups, key=lambda g: (-size[g], g)):
        seen[dept[g]] += 1
        label[g] = dept[g] if seen[dept[g]] == 1 else f"{dept[g]} {seen[dept[g]]}"
    return {f"NCC{n + 1:02d}": f"Nhà cung cấp Thanh Lam Mart – {label[g]} (demo)" for n, g in enumerate(groups)}


def build(rows: list[dict], thanh_lam_sha: str = "", crosswalk_sha: str = "", now: datetime | None = None) -> dict:
    return {
        "format": FORMAT,
        "version": VERSION,
        "generated_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "source": {"thanh_lam_catalog_sha256": thanh_lam_sha, "crosswalk_sha256": crosswalk_sha},
        "products": {r["ops_sku"]: {"name": r["thanh_lam_name"], "unit_price": int(r["price_vnd"]),
                                    "thanh_lam_product_id": r["product_id"]}
                     for r in sorted(rows, key=lambda r: r["ops_sku"])},
        "suppliers": {code: {"name": name, "email": SUPPLIER_EMAIL} for code, name in supplier_names(rows).items()},
    }


def write(doc: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
