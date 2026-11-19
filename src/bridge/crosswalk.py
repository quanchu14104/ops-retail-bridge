"""Crosswalk FRN → WinMart: ánh xạ 1:1 cho 164 mặt hàng tươi của điểm bán FRN số 18.

GIẢ ĐỊNH DEMO. FreshRetailNet-50K (Dingdong, CC BY 4.0) chỉ có mã số ẩn danh, không cho biết mã nhóm nào là rau,
thịt hay hải sản. Hai hệ thống không có sản phẩm nào trùng nhau, nên ánh xạ này được TẠO RA bằng một thuật toán
tất định giữ nguyên cấu trúc; nó không phản ánh mặt hàng thật nào của FRN.

Thuật toán `auto-v1`:
1. Pool WinMart: sub_department "Thực phẩm Tươi sống, Chế biến", bỏ các dòng có "Thủy hải sản khô" hoặc "Măng"
   trong category_hierarchy, bỏ dòng bị quarantine (sale_price_vnd > price_vnd). Ngành hàng = cấp 3 của hierarchy,
   danh mục con = cấp 4.
2. Ghép nhóm FRN (management_group) với ngành hàng theo kích cỡ giảm dần (80 → Rau củ, 40 → Trái cây, 21 → Thịt,
   …). Nhóm thừa vào ngành hàng còn nhiều chỗ nhất.
3. Trong mỗi nhóm, ghép cat1 với danh mục con theo kích cỡ giảm dần (con trỏ vòng, dùng chung cho các nhóm cùng
   ngành hàng). Danh mục con hết chỗ thì tràn sang danh mục con kế tiếp và ghi chú lại.
4. Trong mỗi cặp, mặt hàng FRN xếp theo hạng nhu cầu (tổng demand 60 ngày đầu, giống Ops Chest) đối ứng với
   mặt hàng WinMart xếp theo item_no. Mặt hàng thay thế (cùng cat2, nên cùng cat1) vì vậy nằm cùng danh mục con.
Dòng `method=manual` (sửa tay) được giữ nguyên khi chạy lại `build`.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

FRESH_SUB_DEPARTMENT = "Thực phẩm Tươi sống, Chế biến"
EXCLUDED_HIERARCHY_TERMS = ("Thủy hải sản khô", "Măng")
HISTORY_DAYS_FOR_RATE = 60
METHOD_AUTO = "auto-v1"
METHOD_MANUAL = "manual"
COLUMNS = ["ops_sku", "frn_id", "frn_group", "frn_cat1", "frn_cat2", "product_id", "winmart_name",
           "winmart_category", "price_vnd", "method", "note"]
HEADER_COMMENT = ("# GIẢ ĐỊNH DEMO: ánh xạ FRN→WinMart tự đặt bằng thuật toán auto-v1 (bridge crosswalk build), "
                  "không phản ánh mặt hàng thật của FRN. Dòng method=manual là sửa tay và được giữ khi build lại.")


@dataclass(frozen=True)
class FrnItem:
    frn_id: int
    group: int
    cat1: int
    cat2: int
    demand: float  # tổng demand 60 ngày đầu (đơn vị FRN)

    @property
    def ops_sku(self) -> str:
        return f"F{self.frn_id:04d}"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_winmart(path: Path) -> list[dict]:
    rows = json.loads(path.read_bytes())
    if not isinstance(rows, list):
        raise ValueError(f"{path}: catalog WinMart phải là một mảng JSON")
    return rows


def is_quarantined(row: dict) -> bool:
    return int(row["sale_price_vnd"]) > int(row["price_vnd"])


def _levels(row: dict) -> list[str]:
    return [p.strip() for p in (row.get("category_hierarchy") or "").split(">")]


def department(row: dict) -> str:
    lv = _levels(row)
    return lv[2] if len(lv) > 2 else (row.get("category_name") or "")


def subcategory(row: dict) -> str:
    lv = _levels(row)
    return lv[3] if len(lv) > 3 else department(row)


def winmart_category(row: dict) -> str:
    return " > ".join(_levels(row)[2:]) or (row.get("category_name") or "")


def winmart_pool(rows: list[dict]) -> list[dict]:
    return [r for r in rows
            if r.get("sub_department") == FRESH_SUB_DEPARTMENT
            and not any(t in (r.get("category_hierarchy") or "") for t in EXCLUDED_HIERARCHY_TERMS)
            and not is_quarantined(r)]


def load_frn_items(path: Path, store_id: int = 18) -> list[FrnItem]:
    meta: dict[int, tuple[int, int, int]] = {}
    demand: dict[int, list[tuple[int, float]]] = defaultdict(list)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["store_id"]) != store_id:
                continue
            pid = int(r["product_id"])
            meta.setdefault(pid, (int(r["management_group_id"]), int(r["first_category_id"]),
                                  int(r["second_category_id"])))
            demand[pid].append((int(r["day"]), float(r["demand"])))
    if not meta:
        raise ValueError(f"Không có điểm bán FRN {store_id} trong {path}")
    out = []
    for pid, (g, c1, c2) in meta.items():
        days = sorted(demand[pid])[:HISTORY_DAYS_FOR_RATE]
        out.append(FrnItem(pid, g, c1, c2, sum(v for _, v in days)))
    return sorted(out, key=lambda x: x.frn_id)


def _item_no_key(row: dict):
    no = str(row.get("item_no") or "")
    return (0, int(no), "") if no.isdigit() else (1, 0, no)


def _by_size(counter: Counter) -> list:
    return [k for k, _ in sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def assign_departments(frn: list[FrnItem], pool: list[dict]) -> dict[int, str]:
    """Nhóm FRN → ngành hàng WinMart, theo kích cỡ giảm dần; nhóm thừa vào ngành còn nhiều chỗ nhất."""
    gsize = Counter(i.group for i in frn)
    capacity = Counter(department(r) for r in pool)
    depts = _by_size(capacity)
    remaining = dict(capacity)
    out: dict[int, str] = {}
    for n, g in enumerate(_by_size(gsize)):
        dept = depts[n] if n < len(depts) and remaining[depts[n]] >= gsize[g] else None
        if dept is None:
            dept = max(depts, key=lambda d: (remaining[d], -depts.index(d)))
        if remaining[dept] < gsize[g]:
            raise ValueError(f"Pool WinMart không đủ chỗ cho nhóm FRN {g} ({gsize[g]} mặt hàng)")
        remaining[dept] -= gsize[g]
        out[g] = dept
    return out


def build(frn: list[FrnItem], winmart_rows: list[dict], manual: list[dict] | None = None) -> list[dict]:
    """Trả về các dòng crosswalk (dict theo COLUMNS), sắp theo ops_sku."""
    manual = manual or []
    pinned_frn = {int(m["frn_id"]) for m in manual}
    pinned_pid = {m["product_id"] for m in manual}
    full_pool = winmart_pool(winmart_rows)
    by_id = {r["product_id"]: r for r in winmart_rows}
    todo = [i for i in frn if i.frn_id not in pinned_frn]
    pool = [r for r in full_pool if r["product_id"] not in pinned_pid]

    dept_of = assign_departments(frn, full_pool)  # gán theo cấu trúc đầy đủ để dòng sửa tay không làm lệch nhóm
    free: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in sorted(pool, key=_item_no_key):
        free[department(r)][subcategory(r)].append(r)
    sub_order = {d: _by_size(Counter({s: len(v) for s, v in subs.items()})) for d, subs in free.items()}
    cursor: Counter = Counter()

    rows: list[dict] = []
    gsize = Counter(i.group for i in frn)
    for g in _by_size(gsize):
        dept = dept_of[g]
        items_g = [i for i in todo if i.group == g]
        c1size = Counter(i.cat1 for i in frn if i.group == g)
        for c1 in _by_size(c1size):
            items = sorted((i for i in items_g if i.cat1 == c1), key=lambda i: (-i.demand, i.frn_id))
            if not items:
                continue
            order = sub_order[dept]
            start = cursor[dept] % len(order)
            cursor[dept] += 1
            ring = order[start:] + order[:start]
            target = next((s for s in ring if free[dept][s]), order[start])  # bỏ qua danh mục con đã hết chỗ
            for it in items:
                sub = next((s for s in ring if free[dept][s]), None)
                if sub is None:
                    raise ValueError(f"Hết mặt hàng WinMart trong ngành {dept}")
                r = free[dept][sub].pop(0)
                note = "giả định demo" if sub == target else f"giả định demo; tràn từ danh mục con {target}"
                rows.append(_row(it, r, METHOD_AUTO, note))
    for m in manual:
        it = next((i for i in frn if i.frn_id == int(m["frn_id"])), None)
        r = by_id.get(m["product_id"])
        if it is None or r is None:
            raise ValueError(f"Dòng sửa tay không hợp lệ: {m}")
        rows.append(_row(it, r, METHOD_MANUAL, m.get("note") or "sửa tay"))
    return sorted(rows, key=lambda x: x["ops_sku"])


def _row(it: FrnItem, r: dict, method: str, note: str) -> dict:
    return {"ops_sku": it.ops_sku, "frn_id": it.frn_id, "frn_group": it.group, "frn_cat1": it.cat1,
            "frn_cat2": it.cat2, "product_id": r["product_id"], "winmart_name": r["name"],
            "winmart_category": winmart_category(r), "price_vnd": int(r["price_vnd"]), "method": method,
            "note": note}


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    buf.write(HEADER_COMMENT + "\n")
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8")


def read_csv(path: Path) -> list[dict]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    rows = list(csv.DictReader(lines))
    for r in rows:
        for k in ("frn_id", "frn_group", "frn_cat1", "frn_cat2", "price_vnd"):
            r[k] = int(r[k])
    return rows


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]
    info: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def check(rows: list[dict], winmart_rows: list[dict], winmart_sha: str, expected: int = 164,
          frn: list[FrnItem] | None = None, ops_skus: set[str] | None = None) -> CheckResult:
    errors: list[str] = []
    warnings: list[str] = []
    info = [f"WinMart catalog SHA-256: {winmart_sha}", f"Số dòng crosswalk: {len(rows)}"]
    if len(rows) != expected:
        errors.append(f"Cần đúng {expected} dòng, đang có {len(rows)}")
    for col in ("ops_sku", "frn_id", "product_id"):
        dup = [k for k, n in Counter(r[col] for r in rows).items() if n > 1]
        if dup:
            errors.append(f"Trùng {col}: {dup[:10]}")
    for r in rows:
        if r["ops_sku"] != f"F{r['frn_id']:04d}":
            errors.append(f"{r['ops_sku']}: không khớp frn_id {r['frn_id']}")
        if r["method"] not in (METHOD_AUTO, METHOD_MANUAL):
            errors.append(f"{r['ops_sku']}: method không hợp lệ {r['method']!r}")
    by_id = {w["product_id"]: w for w in winmart_rows}
    for r in rows:
        w = by_id.get(r["product_id"])
        if w is None:
            errors.append(f"{r['ops_sku']}: {r['product_id']} không có trong file WinMart")
        elif is_quarantined(w):
            errors.append(f"{r['ops_sku']}: {r['product_id']} bị quarantine (sale_price_vnd > price_vnd)")
        elif int(w["price_vnd"]) != r["price_vnd"] or w["name"] != r["winmart_name"]:
            warnings.append(f"{r['ops_sku']}: tên/giá trong crosswalk khác file WinMart hiện tại")
    if frn is not None:
        want = {i.ops_sku for i in frn}
        have = {r["ops_sku"] for r in rows}
        if want != have:
            errors.append(f"Lệch tập SKU với FRN: thiếu {sorted(want - have)[:10]}, thừa {sorted(have - want)[:10]}")
    if ops_skus is not None:
        have = {r["ops_sku"] for r in rows}
        if ops_skus != have:
            errors.append(f"Lệch tập SKU với Ops Chest /api/products: thiếu {sorted(ops_skus - have)[:10]}, "
                          f"thừa {sorted(have - ops_skus)[:10]}")
        else:
            info.append(f"Khớp {len(have)} SKU với Ops Chest /api/products")
    cat2_subs: dict[int, set[str]] = defaultdict(set)
    for r in rows:
        cat2_subs[r["frn_cat2"]].add(" > ".join(r["winmart_category"].split(" > ")[:2]))
    split = sum(1 for s in cat2_subs.values() if len(s) > 1)
    info.append(f"Nhóm cat2 nằm trọn trong một danh mục con WinMart: {len(cat2_subs) - split}/{len(cat2_subs)}")
    info.append("Phân bố ngành hàng: " + ", ".join(
        f"{k} {v}" for k, v in Counter(r["winmart_category"].split(" > ")[0] for r in rows).most_common()))
    return CheckResult(errors, warnings, info)
