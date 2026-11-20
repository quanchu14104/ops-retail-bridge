# Bridge Ops Chest → Retail-AI (giai đoạn 1, demo)

Cầu nối **một chiều** giữa hai sub-project độc lập:

- **Ops Chest** (`ops_chest/`): agent quản lý kho theo lô và HSD. Dữ liệu thật FreshRetailNet-50K, điểm bán 18,
  164 mặt hàng tươi.
- **Retail-AI** (`Retail-AI-/`): kiosk/chatbot chăm sóc khách hàng, catalog 3.099 sản phẩm Thanh Lam Mart.

Mỗi bên vẫn chỉ làm việc của mình. Bridge không import code của bên nào: nó đọc REST của Ops Chest và ghi
(a) file `out/ops_feed.json` theo [hợp đồng v1](contract/ops_feed.v1.md), (b) các bảng feed có sẵn trong
Postgres của Retail-AI cho hàng mới về. Thiết kế đầy đủ: [docs/plan-giai-doan-1.md](docs/plan-giai-doan-1.md).

```
Thanh Lam Mart catalog (Retail-AI, chỉ đọc) ─┐
FRN điểm bán 18 (Ops Chest, chỉ đọc) ─┴─▶ bridge crosswalk ─▶ data/crosswalk.csv
                                               │
              bridge overrides ─▶ out/ops_catalog_overrides.json ─▶ [Ops Chest seed + seam]
                                               │
Ops Chest REST (tài khoản nhân viên, chỉ xem)  ▼
              bridge sync ─┬─▶ out/ops_feed.json ─▶ [Retail-AI OpsOverlayRepository]
                           └─▶ Retail-AI Postgres: retail_stores / retail_kiosks /
                               retail_data_feeds(RECEIVING) / inventory_receipts
```

## Dựng trên máy mới

Ba repo phải nằm **cạnh nhau trong cùng một thư mục cha** (gọi là `WORKSPACE`, đặt ở đâu cũng được). Bridge tự tìm
hai repo kia theo vị trí tương đối, không cần ổ `Q:`.

```
WORKSPACE\
├─ ops_chest\     github.com/quanchu14104/ops_chest          (công khai)
├─ Retail-AI-\    github.com/chinhdz102/Retail-AI-           (công khai)
└─ bridge\        github.com/quanchu14104/ops-retail-bridge  (riêng tư: nhờ chủ repo mời làm collaborator)
```

**Cần cài trước:** Git, [uv](https://docs.astral.sh/uv/) (`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`),
Node.js LTS, Docker Desktop (cho Postgres của Retail-AI và Mailpit). Máy đang có bản Retail-AI cũ thì **xoá thư mục
cũ** và clone lại theo các bước dưới.

```powershell
mkdir WORKSPACE
cd WORKSPACE
git clone https://github.com/quanchu14104/ops_chest.git
git clone https://github.com/chinhdz102/Retail-AI-.git
git clone https://github.com/quanchu14104/ops-retail-bridge.git bridge
.\bridge\scripts\setup.ps1
```

`setup.ps1` chạy lại bao nhiêu lần cũng được. Nó kiểm tra 3 repo và công cụ, chạy `uv sync`/`npm ci`, tạo các file
`.env` từ `.env.example`, kiểm tra crosswalk, sinh `out/ops_catalog_overrides.json`, seed DB demo của Ops Chest
(tên và giá Thanh Lam Mart), bật Postgres của Retail-AI rồi nạp catalog Thanh Lam Mart, bật Mailpit, và ghi
`WORKSPACE\.claude\launch.json` cho Claude Code. Thêm `-ResetDemo` để seed lại DB demo, `-SkipDocker` khi chưa có
Docker, `-SkipInstall` để bỏ qua bước cài thư viện.

**Khoá API: mỗi người tự điền khoá của mình**, không gửi file `.env` cho nhau, không commit khoá:
- `ops_chest\.env`: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` cho trợ lý chat của Ops Chest (ví dụ Groq:
  `https://api.groq.com/openai/v1`, model `openai/gpt-oss-20b`).
- `Retail-AI-\.env`: `GROQ_API_KEY` cho phần trò chuyện tự do trên kiosk.

Không có khoá thì demo vẫn chạy: Ops Chest không chat được, kiosk chỉ trả lời các câu cố định (giá, khuyến mãi,
hàng mới về, thông tin cửa hàng).

**Chạy demo:**

```powershell
.\bridge\scripts\start-demo.ps1
```

Script mở 5 cửa sổ PowerShell: Ops Chest API, Ops Chest UI, Retail-AI API, kiosk và bridge sync (2 phút một lần),
đồng thời bật Postgres và Mailpit nếu Docker đang chạy. Đóng cửa sổ nào thì dịch vụ đó dừng.

| Mở | Địa chỉ | Tài khoản |
|---|---|---|
| Ops Chest (Store Manager) | http://localhost:5173 | `quanly` / `quanly123`; nhân viên `nhanvien` / `nhanvien123` |
| Kiosk (người mua) | http://127.0.0.1:5190 | |
| Mailpit (email đặt hàng) | http://localhost:8025 | |

Dùng Claude Code thì mở thư mục `WORKSPACE`: 4 dịch vụ có sẵn trong `.claude\launch.json` với tên `ops-chest-api`,
`ops-chest-ui`, `retail-ai-api`, `retail-kiosk` (bản mẫu: [`demo/launch.json`](demo/launch.json)).

## ⚠️ Các giả định demo

- **Ánh xạ FRN → Thanh Lam Mart là tự đặt.** FRN chỉ có mã số ẩn danh và hai bên không có sản phẩm nào trùng nhau.
  `data/crosswalk.csv` được sinh bằng thuật toán tất định `auto-v1`, giữ nguyên cấu trúc (nhóm → ngành hàng,
  cat1 → danh mục con, theo kích cỡ; mặt hàng theo hạng nhu cầu ↔ `item_no`). Nó **không** cho biết mặt hàng FRN
  thật là gì. Mỗi dòng có ghi chú "giả định demo"; dòng `method=manual` là sửa tay và được giữ khi build lại.
- **Cửa hàng thuộc chuỗi Thanh Lam Mart, nhập từ kho tổng.** 7 nguồn hàng của Ops Chest đổi tên thành
  "Nhà cung cấp Thanh Lam Mart – {ngành hàng} (demo)", email `dathang@khotong-demo.test`. Email chỉ rơi vào Mailpit.
  Tên cửa hàng "Thanh Lam Mart", địa chỉ và số điện thoại là giả định.
- **`shelf_life_days` vẫn là số giả lập 1–3 ngày** của Ops Chest, kể cả với trái cây nhập khẩu (thực tế để được
  lâu hơn).
- **Chữ "NCC/Nhà cung cấp" trên UI và prompt Ops Chest chưa đổi thành "kho"** (~140 chỗ, giai đoạn 2).
- Giá bán 164 mặt hàng là giá Thanh Lam Mart, nạp vào Ops Chest **lúc seed**; giá vốn tính lại theo đúng tỷ lệ giá
  vốn/giá bán cũ. Sau đó Ops Chest là chủ giá.

## Ai sở hữu trường nào

| Trường | Chủ | Bên dùng |
|---|---|---|
| Danh tính sản phẩm: id, barcode, tên, brand, danh mục, uom, ảnh | Catalog Thanh Lam Mart | Kiosk; Ops Chest (tên qua crosswalk) |
| Giá bán thường của 164 mặt hàng | Thanh Lam Mart → Ops Chest lúc seed; sau đó Ops Chest | Kiosk qua feed |
| Tồn bán được, HSD theo lô, giảm giá cận date | Ops Chest | Kiosk qua feed |
| Hàng mới về (PO đã nhận) | Ops Chest | Kiosk qua `inventory_receipts` |
| Vị trí kệ | Planogram của Retail-AI | Kiosk |
| Giá vốn, nguồn hàng, thỏa thuận, dự báo, value_at_risk | Ops Chest, **nội bộ** | Không bao giờ xuất ra |
| Tồn và giá của ~2.935 mặt hàng không ánh xạ | Snapshot Thanh Lam Mart | Kiosk |

## Dời trục thời gian

Ops Chest chạy đồng hồ giả lập (sau seed: 26/06/2024), Retail-AI dùng ngày thật. Nếu chuyển HSD nguyên gốc,
kiosk coi mọi lô là hết hạn. Mỗi lần sync, bridge tính
`shift = ngày thật (Asia/Ho_Chi_Minh) − ngày nghiệp vụ Ops Chest` (ghi trong `date_shift_days` của feed) và cộng
vào mọi ngày/giờ lấy từ Ops Chest. Mốc sự kiện đã xảy ra (giờ nhận hàng) bị chặn ở thời điểm hiện tại. Tua nhanh
Ops Chest 1 ngày thì `shift` giảm 1, nên số ngày còn lại của mỗi lô vẫn đúng.

## Cổng

| Dịch vụ | Cổng |
|---|---|
| Ops Chest API (`ops_chest`, nhánh `main`, SQLite) | 8000 |
| Ops Chest UI | 5173 |
| Mailpit | 8025 / 1025 |
| Postgres của Retail-AI (Docker) | 5432 |
| Retail-AI API | 8020 |
| Kiosk | 5190 |

**Không chạy docker compose đầy đủ của Ops Chest cùng lúc**: Postgres của nó cũng giành cổng 5432. Chỉ bật
riêng Mailpit: `docker compose up -d mailpit` trong `ops_chest\` (`setup.ps1` và `start-demo.ps1` đã làm việc này).

Cấu hình chạy cho cả 4 dịch vụ nằm ở `WORKSPACE\.claude\launch.json`, chép từ [`demo/launch.json`](demo/launch.json)
(tên: `ops-chest-api`, `ops-chest-ui`, `retail-ai-api`, `retail-kiosk`). Biến môi trường cho demo nằm ngoài hai
repo con, không chứa secret:
[`demo/ops-chest.env`](demo/ops-chest.env) cho Ops Chest và [`demo/retail-ai.env`](demo/retail-ai.env) cho
Retail-AI API và kiosk.

## Thứ tự khởi động (chạy tay, từng bước)

`setup.ps1` và `start-demo.ps1` làm đúng các bước này. Mọi lệnh Python chạy qua `uv run`. Các lệnh dưới đây chạy từ
thư mục `WORKSPACE`.

```powershell
# 0. Bridge
cd bridge; Copy-Item .env.example .env; uv sync

# 1. Crosswalk (đã commit sẵn; chỉ build lại khi catalog Thanh Lam Mart hoặc FRN đổi)
uv run bridge crosswalk check
uv run bridge overrides                # → out/ops_catalog_overrides.json
cd ..

# 2. Postgres + catalog của Retail-AI (bảng products là đích khoá ngoại của inventory_receipts)
cd Retail-AI-; docker compose up -d postgres; uv run python scripts/import_thanh_lam.py --apply; cd ..

# 3. Mailpit (chỉ service này của Ops Chest)
cd ops_chest; docker compose up -d mailpit; cd ..

# 4. Seed Ops Chest kèm overrides: nạp bridge\demo\ops-chest.env vào môi trường của tiến trình rồi seed
cd ops_chest\backend; uv run python -m app.sim.seed --reset; cd ..\..

# 5. Chạy Ops Chest API/UI, Retail-AI API, kiosk theo bảng cổng (launch.json hoặc start-demo.ps1)

# 6. Sync liên tục
cd bridge
uv run bridge crosswalk check --ops    # đối chiếu 164 SKU với /api/products
uv run bridge sync --every 120         # hoặc --once
```

**Cấu hình demo của Retail-AI đặt ở biến môi trường của tiến trình, KHÔNG ghi vào `.env` của Retail-AI.** Bộ test
của Retail-AI đọc `Retail-AI-/.env`. Nếu để `CATALOG_REPOSITORY=snapshot` và `OPS_FEED_PATH` trong đó, chạy
`uv run pytest -q` tại chỗ sẽ hỏng hàng chục test (nhánh trả lời cố định chạy trước LLM). Vì vậy:

- `Retail-AI-/.env` và `apps/kiosk-airi/.env` giữ giá trị mặc định như `.env.example` (chỉ chứa secret của
  máy, nếu có).
- Retail-AI API nhận `CATALOG_REPOSITORY=snapshot`, `OPS_FEED_PATH=../bridge/out/ops_feed.json` (tính từ `Retail-AI-/`),
  `CORS_ORIGINS=http://127.0.0.1:5190,http://localhost:5190` từ khối `env` của `retail-ai-api` trong `launch.json`
  (biến môi trường của tiến trình được pydantic-settings ưu tiên hơn `.env`).
- Kiosk nhận `VITE_API_BASE_URL=http://127.0.0.1:8020` từ khối `env` của `retail-kiosk`. Vite có đọc `VITE_*` từ
  biến môi trường của tiến trình và ưu tiên chúng hơn `.env`: đã kiểm chứng `/src/api.ts` do Vite phục vụ mang giá
  trị 8020 trong khi `apps/kiosk-airi/.env` vẫn là 8000, và kiosk gọi `http://127.0.0.1:8020/sessions`.
- Chạy tay ngoài `launch.json`: nạp `demo/retail-ai.env` vào môi trường trước khi chạy (`start-demo.ps1` tự làm).

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
ban đầu ghi các biến demo vào `Retail-AI-/.env` và `apps/kiosk-airi/.env`; cách đó làm hỏng test Retail-AI chạy
tại chỗ. Giờ `uv run pytest -q` trong `Retail-AI-` xanh mà không cần ép biến nào.

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
| `bridge crosswalk check [--ops]` | Đủ 164 dòng, duy nhất hai phía, product_id có trong file Thanh Lam Mart và không bị quarantine, in SHA-256 file Thanh Lam Mart; `--ops` đối chiếu với Ops Chest |
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
loại). Test crosswalk trên dữ liệu thật tự bỏ qua nếu không có file Thanh Lam Mart/FRN.

## Ngoài phạm vi giai đoạn 1

Đổi chữ "NCC" trên UI/prompt Ops Chest; feed PROMOTIONS có cấu trúc (cố ý không tạo: tra campaign sẽ trả
SUCCESS rỗng và che khuyến mãi theo sản phẩm); overlay cho chế độ catalog Postgres; luồng ngược kiosk → Ops
Chest; HSD theo loại hàng thật; dùng chung DB vật lý.
