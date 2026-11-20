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
| Ops Chest API (`doanbackup`, nhánh `main`, SQLite) | 8000 |
| Ops Chest UI | 5173 |
| Mailpit | 8025 / 1025 |
| Postgres của Retail-AI (Docker) | 5432 |
| Retail-AI API | 8020 |
| Kiosk | 5190 |

**Không chạy docker compose đầy đủ của Ops Chest cùng lúc**: Postgres của nó cũng giành cổng 5432. Chỉ bật
riêng Mailpit: `docker compose -f Q:/WORKSPACE/doanbackup/docker-compose.yml up -d mailpit`.

Cấu hình chạy cho cả 4 dịch vụ nằm ở `Q:/WORKSPACE/.claude/launch.json` (tên: `ops-chest-api`, `ops-chest-ui`,
`retail-ai-api`, `retail-kiosk`). Biến môi trường cho demo nằm ngoài hai repo con, không chứa secret:
[`demo/ops-chest.env`](demo/ops-chest.env) cho Ops Chest và [`demo/retail-ai.env`](demo/retail-ai.env) cho
Retail-AI API và kiosk.

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
cd Q:\WORKSPACE\doanbackup\backend
uv run python -m app.sim.seed --reset

# 5. Chạy Ops Chest API/UI, Retail-AI API, kiosk theo bảng cổng (launch.json)

# 6. Sync liên tục
cd Q:\WORKSPACE\bridge
uv run bridge crosswalk check --ops    # đối chiếu 164 SKU với /api/products
uv run bridge sync --every 120         # hoặc --once
```

**Cấu hình demo của Retail-AI đặt ở biến môi trường của tiến trình, KHÔNG ghi vào `.env` của Retail-AI.** Bộ test
của Retail-AI đọc `side/Retail-AI-/.env`. Nếu để `CATALOG_REPOSITORY=snapshot` và `OPS_FEED_PATH` trong đó, chạy
`uv run pytest -q` tại chỗ sẽ hỏng hàng chục test (nhánh trả lời cố định chạy trước LLM). Vì vậy:

- `side/Retail-AI-/.env` và `apps/kiosk-airi/.env` giữ giá trị mặc định như `.env.example` (chỉ chứa secret của
  máy, nếu có).
- Retail-AI API nhận `CATALOG_REPOSITORY=snapshot`, `OPS_FEED_PATH=Q:/WORKSPACE/bridge/out/ops_feed.json`,
  `CORS_ORIGINS=http://127.0.0.1:5190,http://localhost:5190` từ khối `env` của `retail-ai-api` trong `launch.json`
  (biến môi trường của tiến trình được pydantic-settings ưu tiên hơn `.env`).
- Kiosk nhận `VITE_API_BASE_URL=http://127.0.0.1:8020` từ khối `env` của `retail-kiosk`. Vite có đọc `VITE_*` từ
  biến môi trường của tiến trình và ưu tiên chúng hơn `.env`: đã kiểm chứng `/src/api.ts` do Vite phục vụ mang giá
  trị 8020 trong khi `apps/kiosk-airi/.env` vẫn là 8000, và kiosk gọi `http://127.0.0.1:8020/sessions`.
- Chạy tay ngoài `launch.json`: nạp `demo/retail-ai.env` vào môi trường trước khi chạy
  (bash: `set -a; . Q:/WORKSPACE/bridge/demo/retail-ai.env; set +a`).

## Điều chỉnh so với plan đã duyệt

**Retail-AI phải sửa 1 dòng cho phần hàng mới về** (user duyệt ngày 19/11/2026). Plan ban đầu ghi phần này "không
sửa dòng nào", nhưng `backend/services/retail_information.py` trả DATA_UNAVAILABLE cho mọi tra cứu chi nhánh
(cửa hàng, khuyến mãi theo campaign, hàng mới về) khi `CATALOG_REPOSITORY` khác `postgres`. Kiosk chạy chế độ
snapshot nên không bao giờ đọc `inventory_receipts`. Điều kiện đổi thành
`settings.catalog_repository != "postgres" and not settings.ops_feed_path`, kèm 1 test. Khi `OPS_FEED_PATH` để
trống, hành vi giữ nguyên như cũ.

**Hệ quả: khi bật `OPS_FEED_PATH`, Postgres của Retail-AI phải luôn chạy.** Câu hỏi khuyến mãi đi qua tra campaign
trước (`list_active_store_promotions`). Nếu Postgres tắt, tra cứu này trả TEMPORARY_FAILURE và `backend/api/main.py`
(~dòng 3426) coi đó là câu trả lời cuối. Khi đó, "có khuyến mãi gì không?" nhận câu "Mình chưa tra cứu được catalog
lúc này…" thay vì danh sách hàng giảm giá; "hàng mới về" cũng vậy. Đã kiểm chứng ngày 19/11/2026: dừng container
Postgres thì cả hai câu báo không khả dụng, bật lại thì phục hồi. Khi Postgres chạy mà không có feed PROMOTIONS,
tra campaign trả DATA_UNAVAILABLE và kiosk chuyển sang danh sách khuyến mãi theo sản phẩm (hàng cận date của Ops
Chest đứng đầu).

Tác dụng phụ đã biết: kiosk trả lời được thông tin cửa hàng demo (tên, địa chỉ, SĐT) từ `retail_stores`.

**Câu trả lời "hàng mới về" dùng ngôn ngữ người mua và giờ địa phương** (user duyệt ngày 19/11/2026, sửa trong
`_localized_retail_information_observation` của `backend/api/main.py`). Kiosk phục vụ người mua, nên không dùng
từ nội bộ "phiếu nhận hàng". Câu mới: "Hàng mới về gần đây tại {cửa hàng}: {sản phẩm} (về lúc dd/mm/yyyy HH:MM);
…", hoặc "Trong 7 ngày qua, {cửa hàng} chưa ghi nhận hàng mới về" khi feed phủ đủ 7 ngày mà không có hàng. Mọi mốc
thời gian chi nhánh (hàng về, ngày xác minh cửa hàng, hạn campaign) được đổi từ UTC sang múi giờ của cửa hàng
(`retail_stores.timezone`, mặc định Asia/Ho_Chi_Minh; dùng UTC+7 cố định khi máy không có tz database, vd Windows
thiếu gói `tzdata`).

Khi thiếu dữ liệu hàng mới về (feed RECEIVING không có, không ACTIVE hoặc cũ hơn 24 giờ), kiosk cũng nói bằng ngôn
ngữ người mua (user duyệt ngày 19/11/2026, chỉ đổi chuỗi trong `_localized_stock_arrival_unavailable`): "Hiện mình
chưa có thông tin hàng mới về của cửa hàng nên chưa thể cho bạn biết món nào vừa về. Bạn có thể hỏi nhân viên cửa
hàng nhé." Câu cũ dùng từ "phiếu nhận hàng", "nhập kho".

**Cấu hình demo của Retail-AI chuyển khỏi `.env`** (user duyệt ngày 19/11/2026): xem mục "Thứ tự khởi động". Plan
ban đầu ghi các biến demo vào `side/Retail-AI-/.env` và `apps/kiosk-airi/.env`; cách đó làm hỏng test Retail-AI chạy
tại chỗ. Giờ `uv run pytest -q` trong `side/Retail-AI-` xanh mà không cần ép biến nào.

## Hạn chế đã biết (thuộc Retail-AI, ngoài phạm vi bridge)

- Test kiosk (vitest) hỏng 41/66 trên Node v26 vì `localStorage` thử nghiệm của Node che mất `localStorage` của
  jsdom ("localStorage is not available because --localstorage-file was not provided"). Không liên quan tới bridge
  hay `.env`: chạy `NODE_OPTIONS=--no-experimental-webstorage npx vitest run` thì 66/66 xanh.

- Câu "có món nào đang giảm giá không?" được bộ nhận diện ý định của Retail-AI chuyển sang gợi ý sản phẩm (khớp
  chữ "giảm" với tên sản phẩm), kể cả khi tắt overlay. "có khuyến mãi gì không?" hay "hôm nay có giảm giá gì
  không?" thì vào danh sách khuyến mãi.

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
