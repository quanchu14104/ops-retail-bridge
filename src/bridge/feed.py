"""Bộ xuất `ops_feed.json` theo hợp đồng `ops-feed` v1 (xem contract/ops_feed.v1.md).

Danh sách trường được phép xuất là TUYỆT ĐỐI: mỗi phần tử được dựng lại từ các khoá liệt kê dưới đây, không
bao giờ sao chép nguyên response của Ops Chest. Giá vốn, nguồn hàng, value_at_risk, dự báo (expected_*) và
phương án xử lý (options) là dữ liệu nội bộ và không bao giờ rời Ops Chest.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from bridge.timeshift import TimeShift

CONTRACT = "ops-feed"
VERSION = 1
HEADER_FIELDS = ("contract", "version", "published_at", "ops_business_date", "date_shift_days", "store_name",
                 "items")
ITEM_FIELDS = ("product_id", "ops_sku", "status", "sellable_qty", "earliest_expiry", "unit_price_vnd",
               "sale_price_vnd", "promotion_text", "coverage_complete", "lots")
LOT_FIELDS = ("qty", "expiry", "markdown_pct")
FORBIDDEN_KEYS = ("unit_cost", "supplier", "value_at_risk", "options", "actual_unit_cost")
FORBIDDEN_PREFIXES = ("expected_",)


class ContractViolation(ValueError):
    pass


def effective_markdown(lot: dict, ts: TimeShift) -> float:
    """Mức giảm đang áp dụng lúc xuất: ngày bán cuối và đã qua giờ giảm giá tối thì lấy mức tối
    (`evening_markdown_pct`, nếu Ops Chest có trường này), ngược lại lấy `markdown_pct`."""
    md = float(lot.get("markdown_pct") or 0.0)
    hour = lot.get("markdown_hour")
    if int(lot.get("days_left", 1)) == 0 and hour is not None and ts.now.hour >= int(hour):
        md = max(md, float(lot.get("evening_markdown_pct") or 0.0))
    return md


def sale_price(unit_price: int, markdown: float) -> int:
    """Giá sau giảm, làm tròn đến 100 đồng như tem giá bán lẻ: 50 đồng trở lên làm tròn lên.
    Dùng Decimal vì `round()` làm tròn .5 về số chẵn (8.450 → 8.400 nhưng 7.950 → 8.000)."""
    hundreds = Decimal(unit_price) * (1 - Decimal(str(markdown))) / 100
    return int(hundreds.quantize(Decimal(1), rounding=ROUND_HALF_UP)) * 100


def _pct(md: float) -> str:
    v = round(md * 100, 1)
    return f"{v:g}"


def promotion_text(lots: list[dict]) -> str | None:
    by_level: dict[tuple[float, date], int] = defaultdict(int)
    for lot in lots:
        if lot["markdown_pct"] > 0 and lot["qty"] > 0:
            by_level[(lot["markdown_pct"], date.fromisoformat(lot["expiry"]))] += lot["qty"]
    if not by_level:
        return None
    parts = [f"Giảm {_pct(md)}% cho {qty} sản phẩm HSD {exp:%d/%m}"
             for (md, exp), qty in sorted(by_level.items(), key=lambda kv: (-kv[0][0], kv[0][1]))]
    return "; ".join(parts)


def build_item(row: dict, product: dict, lots: list[dict], ts: TimeShift) -> dict:
    on_hand = int(product.get("on_hand") or 0)
    unit_price = int(product["unit_price"])
    total_listed = sum(int(lot["qty"]) for lot in lots)
    expired_qty = sum(int(lot["qty"]) for lot in lots if int(lot["days_left"]) < 0)
    active = product.get("status", "ACTIVE") == "ACTIVE"
    # Mặt hàng ngừng kinh doanh: không xuất lô, HSD hay khuyến mãi, để kiosk không quảng cáo hàng không bán.
    sellable = [lot for lot in lots if active and int(lot["days_left"]) >= 0 and int(lot["qty"]) > 0]
    coverage_complete = total_listed == on_hand
    # Lô không có trong danh sách sắp hết hạn (nếu có) được coi là còn xa hạn, nên vẫn bán được.
    sellable_qty = max(0, on_hand - expired_qty) if not coverage_complete else sum(int(x["qty"]) for x in sellable)
    out_lots = sorted(({"qty": int(lot["qty"]), "expiry": ts.date(lot["expiry_date"]).isoformat(),
                        "markdown_pct": round(effective_markdown(lot, ts), 4)} for lot in sellable),
                      key=lambda x: (x["expiry"], -x["markdown_pct"]))
    status = "INACTIVE" if not active else ("IN_STOCK" if sellable_qty > 0 else "OUT_OF_STOCK")
    discounted = [x for x in out_lots if x["markdown_pct"] > 0]
    return {
        "product_id": row["product_id"],
        "ops_sku": row["ops_sku"],
        "status": status,
        "sellable_qty": sellable_qty if active else 0,
        "earliest_expiry": out_lots[0]["expiry"] if out_lots else None,
        "unit_price_vnd": unit_price,
        "sale_price_vnd": min([unit_price] + [sale_price(unit_price, x["markdown_pct"]) for x in discounted]),
        "promotion_text": promotion_text(out_lots),
        "coverage_complete": coverage_complete,
        "lots": out_lots,
    }


def build_feed(meta: dict, products: list[dict], expiring: dict, crosswalk: list[dict], ts: TimeShift
               ) -> tuple[dict, list[str]]:
    """Dựng feed từ response Ops Chest. Trả về (feed, cảnh báo)."""
    warnings: list[str] = []
    by_sku = {p["sku"]: p for p in products}
    lots_by_sku: dict[str, list[dict]] = defaultdict(list)
    for lot in expiring.get("lots", []):
        lots_by_sku[lot["sku"]].append(lot)
    items = []
    for row in sorted(crosswalk, key=lambda r: r["ops_sku"]):
        p = by_sku.get(row["ops_sku"])
        if p is None:
            warnings.append(f"{row['ops_sku']}: không có trong /api/products của Ops Chest")
            continue
        items.append(build_item(row, p, lots_by_sku.get(row["ops_sku"], []), ts))
    feed = {
        "contract": CONTRACT,
        "version": VERSION,
        "published_at": ts.now.isoformat(timespec="seconds"),
        "ops_business_date": ts.ops_today.isoformat(),
        "date_shift_days": ts.days,
        "store_name": meta.get("store_name") or "",
        "items": items,
    }
    validate(feed)
    return feed, warnings


def _scan_forbidden(obj, path: str = "") -> list[str]:
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS or k.startswith(FORBIDDEN_PREFIXES):
                hits.append(f"{path}.{k}")
            hits += _scan_forbidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _scan_forbidden(v, f"{path}[{i}]")
    return hits


def validate(feed: dict) -> None:
    """Kiểm tra hợp đồng: đúng tập khoá ở mọi cấp và không có trường nội bộ."""
    if feed.get("contract") != CONTRACT or feed.get("version") != VERSION:
        raise ContractViolation("Sai contract/version")
    if tuple(feed) != HEADER_FIELDS:
        raise ContractViolation(f"Khoá phần đầu feed không đúng: {list(feed)}")
    for item in feed["items"]:
        if tuple(item) != ITEM_FIELDS:
            raise ContractViolation(f"Khoá item không đúng: {list(item)}")
        for lot in item["lots"]:
            if tuple(lot) != LOT_FIELDS:
                raise ContractViolation(f"Khoá lô không đúng: {list(lot)}")
    hits = _scan_forbidden(feed)
    if hits:
        raise ContractViolation(f"Feed chứa trường nội bộ: {hits[:5]}")


def write_atomic(feed: dict, path: Path) -> None:
    """Ghi file tạm cùng thư mục rồi os.replace, để bên đọc không bao giờ thấy file dở dang."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(feed, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _replace_with_retry(src: str, dst: Path, attempts: int = 10, delay: float = 0.05) -> None:
    """Trên Windows, os.replace báo PermissionError khi bên đọc (Retail-AI) đang mở file đích. Lần đọc chỉ kéo dài
    vài mili giây, nên thử lại một lúc trước khi bỏ cuộc."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay * (i + 1))
