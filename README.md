# Bridge Ops Chest → Retail-AI (giai đoạn 1, demo)

Cầu nối **một chiều** giữa hai sub-project độc lập:

- **Ops Chest** (`doanbackup/`): agent quản lý kho theo lô và HSD. Dữ liệu thật FreshRetailNet-50K, điểm bán 18,
  164 mặt hàng tươi.
- **Retail-AI** (`side/Retail-AI-/`): kiosk/chatbot chăm sóc khách hàng, catalog 3.099 sản phẩm WinMart.

Mỗi bên vẫn chỉ làm việc của mình. Bridge không import code của bên nào: nó đọc REST của Ops Chest và ghi
(a) file `out/ops_feed.json` theo [hợp đồng v1](contract/ops_feed.v1.md), (b) các bảng feed có sẵn trong
Postgres của Retail-AI cho hàng mới về. Thiết kế đầy đủ: [docs/plan-giai-doan-1.md](docs/plan-giai-doan-1.md).

```
WinMart catalog (Retail-AI, chỉ đọc) ─┐
FRN điểm bán 18 (Ops Chest, chỉ đọc) ─┴─▶ bridge crosswalk ─▶ data/crosswalk.csv
                                               │
              bridge overrides ─▶ out/ops_catalog_overrides.json ─▶ [Ops Chest seed + seam]
                                               │
Ops Chest REST (tài khoản nhân viên, chỉ xem)  ▼
              bridge sync ─┬─▶ out/ops_feed.json ─▶ [Retail-AI OpsOverlayRepository]
                           └─▶ Retail-AI Postgres: retail_stores / retail_kiosks /
                               retail_data_feeds(RECEIVING) / inventory_receipts
```

## ⚠️ Các giả định demo

- **Ánh xạ FRN → WinMart là tự đặt.** FRN chỉ có mã số ẩn danh và hai bên không có sản phẩm nào trùng nhau.
  `data/crosswalk.csv` được sinh bằng thuật toán tất định `auto-v1`, giữ nguyên cấu trúc (nhóm → ngành hàng,
  cat1 → danh mục con, theo kích cỡ; mặt hàng theo hạng nhu cầu ↔ `item_no`). Nó **không** cho biết mặt hàng FRN
  thật là gì. Mỗi dòng có ghi chú "giả định demo"; dòng `method=manual` là sửa tay và được giữ khi build lại.
- **Cửa hàng thuộc chuỗi WinMart, nhập từ kho tổng.** 7 nguồn hàng của Ops Chest đổi tên thành
  "Kho tổng WinMart – {ngành hàng} (demo)", email `dathang@khotong-demo.test`. Email chỉ rơi vào Mailpit.
  Tên cửa hàng "WinMart+ Demo (giả định)", địa chỉ và số điện thoại là giả định.
- **`shelf_life_days` vẫn là số giả lập 1–3 ngày** của Ops Chest, kể cả với trái cây nhập khẩu (thực tế để được
  lâu hơn).
- **Chữ "NCC/Nhà cung cấp" trên UI và prompt Ops Chest chưa đổi thành "kho"** (~140 chỗ, giai đoạn 2).
- Giá bán 164 mặt hàng là giá WinMart, nạp vào Ops Chest **lúc seed**; giá vốn tính lại theo đúng tỷ lệ giá
  vốn/giá bán cũ. Sau đó Ops Chest là chủ giá.

## Ai sở hữu trường nào

| Trường | Chủ | Bên dùng |
|---|---|---|
| Danh tính sản phẩm: id, barcode, tên, brand, danh mục, uom, ảnh | Catalog WinMart | Kiosk; Ops Chest (tên qua crosswalk) |
| Giá bán thường của 164 mặt hàng | WinMart → Ops Chest lúc seed; sau đó Ops Chest | Kiosk qua feed |
| Tồn bán được, HSD theo lô, giảm giá cận date | Ops Chest | Kiosk qua feed |
| Hàng mới về (PO đã nhận) | Ops Chest | Kiosk qua `inventory_receipts` |
| Vị trí kệ | Planogram của Retail-AI | Kiosk |
| Giá vốn, nguồn hàng, thỏa thuận, dự báo, value_at_risk | Ops Chest, **nội bộ** | Không bao giờ xuất ra |
| Tồn và giá của ~2.935 mặt hàng không ánh xạ | Snapshot WinMart | Kiosk |

## Dời trục thời gian

Ops Chest chạy đồng hồ giả lập (sau seed: 26/06/2024), Retail-AI dùng ngày thật. Nếu chuyển HSD nguyên gốc,
kiosk coi mọi lô là hết hạn. Mỗi lần sync, bridge tính
`shift = ngày thật (Asia/Ho_Chi_Minh) − ngày nghiệp vụ Ops Chest` (ghi trong `date_shift_days` của feed) và cộng
vào mọi ngày/giờ lấy từ Ops Chest. Mốc sự kiện đã xảy ra (giờ nhận hàng) bị chặn ở thời điểm hiện tại. Tua nhanh
Ops Chest 1 ngày thì `shift` giảm 1, nên số ngày còn lại của mỗi lô vẫn đúng.

## Cổng

| Dịch vụ | Cổng |
|---|---|
| Ops Chest API (worktree `feat/catalog-overrides`, SQLite) | 8000 |
| Ops Chest UI | 5173 |
| Mailpit | 8025 / 1025 |
| Postgres của Retail-AI (Docker) | 5432 |
| Retail-AI API | 8020 |
| Kiosk | 5190 |

**Không chạy docker compose đầy đủ của Ops Chest cùng lúc**: Postgres của nó cũng giành cổng 5432. Chỉ bật
riêng Mailpit: `docker compose -f Q:/WORKSPACE/doanbackup/docker-compose.yml up -d mailpit`.

Cấu hình chạy cho cả 4 dịch vụ nằm ở `Q:/WORKSPACE/.claude/launch.json` (tên: `ops-chest-api`, `ops-chest-ui`,
`retail-ai-api`, `retail-kiosk`). Biến môi trường của Ops Chest cho demo nằm ở
[`demo/ops-chest.env`](demo/ops-chest.env) (ngoài repo Ops Chest, không chứa key LLM).

## Thứ tự khởi động

Mọi lệnh Python chạy qua `uv run` (máy không có `python` trên PATH).

```powershell
# 0. Bridge
cd Q:\WORKSPACE\bridge
Copy-Item .env.example .env            # sửa nếu cần
uv sync

# 1. Crosswalk (đã commit sẵn; chỉ build lại khi catalog WinMart hoặc FRN đổi)
uv run bridge crosswalk check
uv run bridge overrides                # → out/ops_catalog_overrides.json

# 2. Postgres + catalog của Retail-AI (bảng products là đích khoá ngoại của inventory_receipts)
cd Q:\WORKSPACE\side\Retail-AI-
docker compose up -d postgres
uv run python scripts/import_winmart.py --apply

# 3. Mailpit (chỉ service này của Ops Chest)
docker compose -f Q:/WORKSPACE/doanbackup/docker-compose.yml up -d mailpit

# 4. Seed Ops Chest kèm overrides (bash: set -a; . Q:/WORKSPACE/bridge/demo/ops-chest.env; set +a)
cd Q:\WORKSPACE\worktrees\ops-chest-catalog-overrides\backend
uv run python -m app.sim.seed --reset

# 5. Chạy Ops Chest API/UI, Retail-AI API, kiosk theo bảng cổng (launch.json)

# 6. Sync liên tục
cd Q:\WORKSPACE\bridge
uv run bridge crosswalk check --ops    # đối chiếu 164 SKU với /api/products
uv run bridge sync --every 120         # hoặc --once
```

Retail-AI cần trong `.env`: `CATALOG_REPOSITORY=snapshot`, `OPS_FEED_PATH=Q:/WORKSPACE/bridge/out/ops_feed.json`,
`CORS_ORIGINS=http://127.0.0.1:5190,http://localhost:5190`; kiosk cần
`apps/kiosk-airi/.env`: `VITE_API_BASE_URL=http://127.0.0.1:8020`.

## Lệnh

| Lệnh | Việc làm |
|---|---|
| `bridge crosswalk build [--reset-manual]` | Sinh `data/crosswalk.csv` (giữ dòng sửa tay) rồi chạy check |
| `bridge crosswalk check [--ops]` | Đủ 164 dòng, duy nhất hai phía, product_id có trong file WinMart và không bị quarantine, in SHA-256 file WinMart; `--ops` đối chiếu với Ops Chest |
| `bridge overrides` | Sinh `out/ops_catalog_overrides.json` cho seam lúc seed của Ops Chest |
| `bridge sync --once` / `--every N` | Xuất feed (ghi atomic) và hàng mới về; `--no-receipts` chỉ xuất feed |

Exit code của `sync`: `0` thành công; `2` Ops Chest không phản hồi hoặc từ chối (feed cũ giữ nguyên);
`3` ghi Postgres của Retail-AI thất bại (feed đã ghi). `crosswalk check` thất bại trả `4`.

## Kiểm thử

```powershell
uv run pytest -q
uv run ruff check .
```

Test dùng response Ops Chest đã ghi lại trong `tests/fixtures/` (giữ cả trường nội bộ để chứng minh chúng bị
loại). Test crosswalk trên dữ liệu thật tự bỏ qua nếu không có file WinMart/FRN.

## Ngoài phạm vi giai đoạn 1

Đổi chữ "NCC" trên UI/prompt Ops Chest; feed PROMOTIONS có cấu trúc (cố ý không tạo: tra campaign sẽ trả
SUCCESS rỗng và che khuyến mãi theo sản phẩm); overlay cho chế độ catalog Postgres; luồng ngược kiosk → Ops
Chest; HSD theo loại hàng thật; dùng chung DB vật lý.
