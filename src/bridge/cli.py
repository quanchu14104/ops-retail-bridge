"""CLI: `uv run bridge crosswalk build|check`, `uv run bridge overrides`, `uv run bridge sync --once|--every N`."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date

from bridge import crosswalk, overrides
from bridge.config import Config
from bridge.feed import build_feed, write_atomic
from bridge.ops_client import OpsChestError, OpsClient
from bridge.receipts import build_receipts, received_pos_in_window, write_receipts
from bridge.timeshift import TimeShift

EXIT_OPS_UNAVAILABLE = 2
EXIT_RETAIL_DB = 3
EXIT_CHECK_FAILED = 4


def _client(cfg: Config) -> OpsClient:
    return OpsClient(cfg.ops_chest_url, cfg.ops_chest_user, cfg.ops_chest_password)


def cmd_crosswalk_build(cfg: Config, args) -> int:
    winmart = crosswalk.load_winmart(cfg.winmart_catalog_path)
    frn = crosswalk.load_frn_items(cfg.frn_data_path, cfg.frn_store_id)
    manual = []
    if cfg.crosswalk_path.exists() and not args.reset_manual:
        manual = [r for r in crosswalk.read_csv(cfg.crosswalk_path) if r["method"] == crosswalk.METHOD_MANUAL]
    rows = crosswalk.build(frn, winmart, manual)
    crosswalk.write_csv(rows, cfg.crosswalk_path)
    print(f"Đã ghi {len(rows)} dòng vào {cfg.crosswalk_path} (giữ {len(manual)} dòng sửa tay)")
    return cmd_crosswalk_check(cfg, argparse.Namespace(ops=False))


def cmd_crosswalk_check(cfg: Config, args) -> int:
    winmart = crosswalk.load_winmart(cfg.winmart_catalog_path)
    rows = crosswalk.read_csv(cfg.crosswalk_path)
    frn = crosswalk.load_frn_items(cfg.frn_data_path, cfg.frn_store_id) if cfg.frn_data_path.exists() else None
    ops_skus = None
    if args.ops:
        try:
            ops_skus = {p["sku"] for p in _client(cfg).products()}
        except OpsChestError as e:
            print(f"LỖI: {e}", file=sys.stderr)
            return EXIT_OPS_UNAVAILABLE
    res = crosswalk.check(rows, winmart, crosswalk.file_sha256(cfg.winmart_catalog_path),
                          expected=len(frn) if frn else 164, frn=frn, ops_skus=ops_skus)
    for line in res.info:
        print(line)
    for line in res.warnings:
        print(f"CẢNH BÁO: {line}")
    for line in res.errors:
        print(f"LỖI: {line}", file=sys.stderr)
    print("crosswalk check: OK" if res.ok else "crosswalk check: THẤT BẠI")
    return 0 if res.ok else EXIT_CHECK_FAILED


def cmd_overrides(cfg: Config, args) -> int:
    rows = crosswalk.read_csv(cfg.crosswalk_path)
    doc = overrides.build(rows, crosswalk.file_sha256(cfg.winmart_catalog_path),
                          crosswalk.file_sha256(cfg.crosswalk_path))
    overrides.write(doc, cfg.overrides_path)
    print(f"Đã ghi {cfg.overrides_path}: {len(doc['products'])} mặt hàng, {len(doc['suppliers'])} kho tổng")
    for code, s in doc["suppliers"].items():
        print(f"  {code}: {s['name']} <{s['email']}>")
    return 0


def sync_once(cfg: Config, receipts: bool = True) -> int:
    rows = crosswalk.read_csv(cfg.crosswalk_path)
    client = _client(cfg)
    try:  # Lấy hết từ Ops Chest TRƯỚC khi ghi gì, để Ops Chest lỗi giữa chừng không để lại kết quả dở dang.
        meta = client.meta()
        products = client.products()
        expiring = client.expiring(days=120)
        pos, details = [], {}
        if receipts:
            ops_today = date.fromisoformat(meta["today"])
            pos = received_pos_in_window(client.purchase_orders(status="RECEIVED", limit=300), ops_today)
            details = {po["id"]: client.purchase_order(po["id"]) for po in pos}
    except OpsChestError as e:
        print(f"LỖI: {e}. Giữ nguyên feed cũ tại {cfg.ops_feed_path}.", file=sys.stderr)
        return EXIT_OPS_UNAVAILABLE

    ts = TimeShift.compute(date.fromisoformat(meta["today"]), tz=cfg.timezone)
    feed, warnings = build_feed(meta, products, expiring, rows, ts)
    write_atomic(feed, cfg.ops_feed_path)
    items = feed["items"]
    print(f"[{feed['published_at']}] feed v1 → {cfg.ops_feed_path}: {len(items)} mặt hàng, "
          f"{sum(i['status'] == 'IN_STOCK' for i in items)} còn hàng, "
          f"{sum(i['promotion_text'] is not None for i in items)} đang giảm giá; "
          f"ngày Ops {feed['ops_business_date']}, dời {feed['date_shift_days']} ngày")
    for w in warnings[:10]:
        print(f"CẢNH BÁO: {w}")
    if not receipts:
        return 0

    sku_to_product = {r["ops_sku"]: r["product_id"] for r in rows}
    recs = build_receipts(pos, details, sku_to_product, ts)
    try:
        import psycopg

        with psycopg.connect(cfg.retail_database_url, connect_timeout=5) as conn:
            out = write_receipts(conn, recs, store_code=cfg.store_code, kiosk_id=cfg.kiosk_id,
                                 store_name=meta.get("store_name") or cfg.store_code, address=cfg.store_address,
                                 phone=cfg.store_phone, now=ts.now)
    except Exception as e:  # psycopg.Error, OSError: feed vẫn đã ghi, báo lỗi phần Postgres
        print(f"LỖI: ghi hàng mới về vào Postgres của Retail-AI thất bại ({type(e).__name__}: {e})",
              file=sys.stderr)
        return EXIT_RETAIL_DB
    print(f"hàng mới về → Retail-AI Postgres: {len(pos)} PO, xoá {out['deleted']}, chèn {out['inserted']} dòng "
          f"inventory_receipts (store {cfg.store_code}, kiosk {cfg.kiosk_id})")
    return 0


def cmd_sync(cfg: Config, args) -> int:
    if not args.every:
        return sync_once(cfg, receipts=not args.no_receipts)
    print(f"Sync mỗi {args.every} giây, Ctrl+C để dừng.")
    try:
        while True:
            started = time.monotonic()
            try:
                sync_once(cfg, receipts=not args.no_receipts)
            except Exception as e:  # noqa: BLE001 - một lần sync lỗi không được làm dừng vòng lặp (feed cũ giữ nguyên)
                print(f"LỖI: sync thất bại ({type(e).__name__}: {e}). Giữ nguyên feed cũ, thử lại sau "
                      f"{args.every} giây.", file=sys.stderr)
            # Nhịp cố định: lần sau bắt đầu `every` giây sau lần trước, không cộng dồn thời gian chạy.
            time.sleep(max(0.0, args.every - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            # line_buffering: log của `sync --every` chạy nền đọc được ngay, không bị đệm tới khi dừng.
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    ap = argparse.ArgumentParser(prog="bridge", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    cw = sub.add_parser("crosswalk", help="Ánh xạ FRN → WinMart (giả định demo)")
    cw_sub = cw.add_subparsers(dest="action", required=True)
    b = cw_sub.add_parser("build", help="Sinh data/crosswalk.csv (giữ dòng method=manual)")
    b.add_argument("--reset-manual", action="store_true", help="Bỏ cả dòng sửa tay")
    c = cw_sub.add_parser("check", help="Kiểm tra crosswalk")
    c.add_argument("--ops", action="store_true", help="Đối chiếu tập SKU với /api/products của Ops Chest")
    sub.add_parser("overrides", help="Sinh out/ops_catalog_overrides.json cho seed của Ops Chest")
    s = sub.add_parser("sync", help="Xuất ops_feed.json và hàng mới về")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Chạy một lần (mặc định)")
    mode.add_argument("--every", type=int, metavar="GIÂY", help="Chạy lặp lại mỗi N giây")
    s.add_argument("--no-receipts", action="store_true", help="Chỉ xuất feed, không ghi Postgres")
    args = ap.parse_args(argv)
    cfg = Config.load()
    if args.cmd == "crosswalk":
        return cmd_crosswalk_build(cfg, args) if args.action == "build" else cmd_crosswalk_check(cfg, args)
    if args.cmd == "overrides":
        return cmd_overrides(cfg, args)
    return cmd_sync(cfg, args)


if __name__ == "__main__":
    raise SystemExit(main())
