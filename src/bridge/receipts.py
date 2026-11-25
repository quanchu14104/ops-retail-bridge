"""Hàng mới về: PO đã nhận của Ops Chest → các bảng feed có sẵn trong Postgres của Retail-AI.

Mỗi lần sync chạy trong MỘT transaction: upsert tổ chức, cửa hàng, kiosk, feed RECEIVING, rồi xoá và chèn lại
toàn bộ `inventory_receipts` thuộc `source_name='ops-chest-bridge'`. Cách xoá-chèn-lại tự sửa dữ liệu sau khi Ops
Chest tua nhanh hoặc seed lại. KHÔNG tạo feed PROMOTIONS (nếu tạo, tra campaign trả SUCCESS rỗng và che mất
khuyến mãi theo sản phẩm của kiosk).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from bridge.timeshift import TimeShift

SOURCE_NAME = "ops-chest-bridge"
STORE_SOURCE_NAME = "ops-chest-bridge (demo)"
ORG_CODE = "thanh_lam_mart"
WINDOW_DAYS = 7


@dataclass(frozen=True)
class Receipt:
    event_id: str
    product_id: str
    quantity: int
    received_at: datetime
    source_document_id: str


def _ops_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value).date() if ("T" in value or " " in value) else date.fromisoformat(value)


def received_pos_in_window(pos: list[dict], ops_today: date, days: int = WINDOW_DAYS) -> list[dict]:
    """PO RECEIVED có ngày nhận (hoặc ngày dự kiến nếu chưa có) trong `days` ngày nghiệp vụ gần nhất."""
    start = ops_today - timedelta(days=days - 1)
    out = []
    for po in pos:
        if po.get("status") != "RECEIVED":
            continue
        d = _ops_date(po.get("received_at")) or _ops_date(po.get("expected_date"))
        if d is not None and start <= d <= ops_today:
            out.append(po)
    return out


def build_receipts(pos: list[dict], details: dict[int, dict], sku_to_product: dict[str, str],
                   ts: TimeShift) -> list[Receipt]:
    out = []
    for po in pos:
        detail = details[po["id"]]
        when = ts.event(po.get("received_at") or po["expected_date"])
        for line in detail.get("lines", []):
            pid = sku_to_product.get(line.get("sku"))
            qty = int(line.get("received_qty") or 0)
            if pid is None or qty <= 0:
                continue
            out.append(Receipt(f"ops:{po['code']}:{line['line_id']}", pid, qty, when, po["code"]))
    return out


def write_receipts(conn, receipts: list[Receipt], *, store_code: str, kiosk_id: str, store_name: str,
                   address: str, phone: str, now: datetime) -> dict:
    """Ghi vào Postgres của Retail-AI trong một transaction. `conn` là psycopg.Connection."""
    with conn.transaction():
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO retail_organizations(organization_code, legal_name, display_name, organization_type)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (organization_code) DO UPDATE SET active = true, updated_at = now()""",
            (ORG_CODE, "Cửa hàng bán lẻ Thanh Lam Mart", "Thanh Lam Mart", "INDEPENDENT_STORE"),
        )
        cur.execute(
            """INSERT INTO retail_stores(store_code, organization_code, store_name, address, phone, timezone,
                                         source_name, verified_at, active)
               VALUES (%s, %s, %s, %s, %s, 'Asia/Ho_Chi_Minh', %s, %s, true)
               ON CONFLICT (store_code) DO UPDATE SET organization_code = EXCLUDED.organization_code,
                   store_name = EXCLUDED.store_name, address = EXCLUDED.address, phone = EXCLUDED.phone,
                   source_name = EXCLUDED.source_name, verified_at = EXCLUDED.verified_at, active = true,
                   updated_at = now()""",
            (store_code, ORG_CODE, store_name, address, phone, STORE_SOURCE_NAME, now),
        )
        cur.execute(
            """INSERT INTO retail_kiosks(kiosk_id, store_code, active) VALUES (%s, %s, true)
               ON CONFLICT (kiosk_id) DO UPDATE SET store_code = EXCLUDED.store_code, active = true,
                   updated_at = now()""",
            (kiosk_id, store_code),
        )
        cur.execute(
            """INSERT INTO retail_data_feeds(store_code, feed_name, provider, status, last_success_at,
                                             coverage_start_at, coverage_end_at, coverage_complete)
               VALUES (%s, 'RECEIVING', %s, 'ACTIVE', %s, %s, %s, true)
               ON CONFLICT (store_code, feed_name) DO UPDATE SET provider = EXCLUDED.provider,
                   status = 'ACTIVE', last_success_at = EXCLUDED.last_success_at,
                   coverage_start_at = EXCLUDED.coverage_start_at, coverage_end_at = EXCLUDED.coverage_end_at,
                   coverage_complete = true, updated_at = now()""",
            (store_code, STORE_SOURCE_NAME, now, now - timedelta(days=WINDOW_DAYS), now),
        )
        cur.execute("DELETE FROM inventory_receipts WHERE source_name = %s", (SOURCE_NAME,))
        deleted = cur.rowcount
        cur.executemany(
            """INSERT INTO inventory_receipts(event_id, store_code, product_id, quantity, received_at,
                                              receiving_step, source_name, source_document_id)
               VALUES (%s, %s, %s, %s, %s, 'RECEIVED', %s, %s)""",
            [(r.event_id, store_code, r.product_id, r.quantity, r.received_at, SOURCE_NAME, r.source_document_id)
             for r in receipts],
        )
    return {"deleted": deleted, "inserted": len(receipts)}
