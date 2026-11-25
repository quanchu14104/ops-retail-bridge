from contextlib import contextmanager
from datetime import date, datetime

from bridge.receipts import SOURCE_NAME, build_receipts, received_pos_in_window, write_receipts
from tests.conftest import TZ, shift_at


def test_window_keeps_received_pos_of_last_seven_business_days(ops):
    pos = ops["pos"] + [
        {"id": 1, "code": "PO-SENT", "status": "SENT", "expected_date": "2024-06-26", "received_at": None},
        {"id": 2, "code": "PO-OLD-API", "status": "RECEIVED", "expected_date": "2024-06-24"},  # chưa có received_at
    ]
    kept = received_pos_in_window(pos, date(2024, 6, 26))
    # 25/06 và 24/06 (dự phòng expected_date) nằm trong 20/06–26/06; 19/06 và 18/06 nằm ngoài
    assert [p["code"] for p in kept] == ["PO240624-07623", "PO-OLD-API"]


def test_receipts_use_thanh_lam_ids_shifted_times_and_stable_event_ids(ops, crosswalk_rows):
    ts = shift_at(hour=9)
    sku_to_product = {r["ops_sku"]: r["product_id"] for r in crosswalk_rows}
    po = ops["pos"][0]
    recs = build_receipts([po], ops["details"], sku_to_product, ts)
    lines = ops["details"][po["id"]]["lines"]
    assert [r.event_id for r in recs] == [f"ops:{po['code']}:{line['line_id']}" for line in lines]
    assert [r.quantity for r in recs] == [line["received_qty"] for line in lines]
    assert recs[0].product_id == sku_to_product[lines[0]["sku"]]
    assert {r.received_at for r in recs} == {datetime(2026, 11, 18, 8, 0, tzinfo=TZ)}  # 25/06/2024 08:00 + 876 ngày
    assert {r.source_document_id for r in recs} == {po["code"]}


class FakeCursor:
    def __init__(self, log):
        self.log, self.rowcount = log, 0

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))
        self.rowcount = 3 if sql.lstrip().startswith("DELETE") else 1

    def executemany(self, sql, rows):
        self.log.append((" ".join(sql.split()), list(rows)))


class FakeConn:
    def __init__(self):
        self.log, self.transactions = [], 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        self.log.append(("BEGIN", None))
        yield
        self.log.append(("COMMIT", None))

    def cursor(self):
        return FakeCursor(self.log)


def test_write_is_one_transaction_with_delete_then_insert_and_no_promotions_feed(ops, crosswalk_rows):
    ts = shift_at()
    sku_to_product = {r["ops_sku"]: r["product_id"] for r in crosswalk_rows}
    recs = build_receipts([ops["pos"][0]], ops["details"], sku_to_product, ts)
    conn = FakeConn()
    out = write_receipts(conn, recs, store_code="TLM-DEMO-01", kiosk_id="kiosk-01", store_name="Thanh Lam Mart",
                         address="12 Phố Demo", phone="024", now=ts.now)
    assert out == {"deleted": 3, "inserted": len(recs)}
    assert conn.transactions == 1
    sql = [s for s, _ in conn.log]
    assert sql[0] == "BEGIN" and sql[-1] == "COMMIT"
    tables = [s.split()[2] for s in sql[1:-1]]
    assert tables == ["retail_organizations(organization_code,", "retail_stores(store_code,",
                      "retail_kiosks(kiosk_id,", "retail_data_feeds(store_code,", "inventory_receipts",
                      "inventory_receipts(event_id,"]
    feed_sql, feed_params = conn.log[4]
    assert "'RECEIVING'" in feed_sql and "PROMOTIONS" not in " ".join(sql)
    assert feed_params[0] == "TLM-DEMO-01" and (feed_params[4] - feed_params[3]).days == 7
    assert conn.log[5][1] == (SOURCE_NAME,)
    inserted = conn.log[6][1]
    assert all(row[1] == "TLM-DEMO-01" and row[5] == SOURCE_NAME for row in inserted)
