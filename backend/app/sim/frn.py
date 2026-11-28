"""Du lieu lich su ban hang Thanh Lam Mart da chuan hoa cho du bao va kiem chung hoi cuu.

Chua cac tap du lieu giu lai de kiem chung (khong dung de huan luyen mo hinh). Moi dong: mot (diem, mat hang, ngay).
`demand` = nhu cau uoc tinh (ngay het hang da khoi phuc theo ho so ban theo gio), `sale` = so ban quan sat.
Ca hai o don vi chuan hoa; nhan voi K (meta.json) ra so don vi thuc te tai Thanh Lam Mart.
"""
from __future__ import annotations

import csv
import gzip
import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data" / "frn"
ARTIFACTS = Path(__file__).resolve().parent.parent / "ml" / "artifacts"
DEFAULT_K = 10.0


@dataclass
class FrnSeries:
    store_id: int
    product_id: int
    management_group_id: int
    first_category_id: int
    second_category_id: int
    third_category_id: int
    sale: list[float] = field(default_factory=list)
    demand: list[float] = field(default_factory=list)
    stock_hours: list[int] = field(default_factory=list)
    discount: list[float] = field(default_factory=list)
    activity: list[int] = field(default_factory=list)


@dataclass
class FrnStore:
    store_id: int
    dates: list[date]
    holiday: list[int]
    series: dict[int, FrnSeries]

    def day_index(self, d: date) -> int | None:
        i = (d - self.dates[0]).days
        return i if 0 <= i < len(self.dates) else None


def data_file() -> Path:
    return DATA_DIR / "stores_daily.csv.gz"


def available() -> bool:
    return data_file().exists()


@lru_cache(maxsize=1)
def meta() -> dict:
    p = ARTIFACTS / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def k_scale() -> float:
    return float(meta().get("k_scale", DEFAULT_K))


def demo_store_id() -> int:
    return int(meta().get("demo_store", 18))


@lru_cache(maxsize=1)
def _all(path: str) -> dict[int, FrnStore]:
    stores: dict[int, dict] = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sid, pid, day = int(r["store_id"]), int(r["product_id"]), int(r["day"])
            st = stores.setdefault(sid, {"dates": {}, "holiday": {}, "series": {}})
            st["dates"][day] = date.fromisoformat(r["dt"])
            st["holiday"][day] = int(r["holiday"])
            s = st["series"].get(pid)
            if s is None:
                s = st["series"][pid] = FrnSeries(sid, pid, int(r["management_group_id"]), int(r["first_category_id"]),
                                                  int(r["second_category_id"]), int(r["third_category_id"]))
                s._rows = {}  # type: ignore[attr-defined]
            s._rows[day] = r  # type: ignore[attr-defined]
    out = {}
    for sid, st in stores.items():
        days = sorted(st["dates"])
        for s in st["series"].values():
            rows = s._rows  # type: ignore[attr-defined]
            s.sale = [float(rows[d]["sale"]) for d in days]
            s.demand = [float(rows[d]["demand"]) for d in days]
            s.stock_hours = [int(rows[d]["stock_hours"]) for d in days]
            s.discount = [float(rows[d]["discount"]) for d in days]
            s.activity = [int(rows[d]["activity"]) for d in days]
            del s._rows  # type: ignore[attr-defined]
        out[sid] = FrnStore(sid, [st["dates"][d] for d in days], [st["holiday"][d] for d in days], st["series"])
    return out


def stores(path: Path | None = None) -> dict[int, FrnStore]:
    return _all(str(path or data_file()))


def store(store_id: int | None = None, path: Path | None = None) -> FrnStore:
    all_ = stores(path)
    sid = demo_store_id() if store_id is None else store_id
    if sid not in all_:
        raise KeyError(f"Không có dữ liệu điểm bán {sid} trong {path or data_file()}")
    return all_[sid]


@lru_cache(maxsize=1)
def elasticity() -> dict:
    p = DATA_DIR / "elasticity.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@lru_cache(maxsize=1)
def dayparts() -> dict:
    p = DATA_DIR / "dayparts.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def holiday_of(st: FrnStore):
    """Co ngay le/cuoi tuan theo ngay; ngoai khoang du lieu thi coi cuoi tuan la ngay le."""
    flags = {d: f for d, f in zip(st.dates, st.holiday)}
    return lambda d: flags.get(d, 1 if d.weekday() >= 5 else 0)


def statics_for(store_id: int, sku: str) -> tuple[int, int, int] | None:
    """Ma nhom nganh hang cua mat hang OC (sku dang 'F0412'), None neu khong thuoc tap hang tuoi chuan hoa."""
    if not available() or not sku.startswith("F") or not sku[1:].isdigit():
        return None
    s = stores().get(store_id, None)
    x = s.series.get(int(sku[1:])) if s else None
    return (x.management_group_id, x.first_category_id, x.second_category_id) if x else None


def store_size(store_id: int) -> int | None:
    """So mat hang cua tap du lieu diem ban: bac quy mo trong bo chon."""
    if not available():
        return None
    s = stores().get(store_id, None)
    return len(s.series) if s else None
