# Nối Ops Chest ↔ Retail-AI qua nền dữ liệu sản phẩm dùng chung (giai đoạn 1)

> User duyệt ngày 19/11/2026. File này là bản chuẩn để triển khai.
> So với bản duyệt có bảy điều chỉnh:
> 1. Đổi cổng của Retail-AI sang 8020/5190. Lý do nằm ở mục "Ghi chú triển khai" cuối file.
> 2. Phần "hàng mới về" phải sửa 1 dòng ở `backend/services/retail_information.py` của Retail-AI (user duyệt khi
>    triển khai, 19/11/2026). Chi tiết ở mục 6 và README của bridge.
> 3. Câu trả lời "hàng mới về" của kiosk được sửa giờ và câu chữ trong `backend/api/main.py` của Retail-AI (user
>    duyệt khi triển khai, 19/11/2026): giờ địa phương thay cho UTC, ngôn ngữ người mua thay cho "phiếu nhận hàng".
>    Chi tiết ở mục 6 và README của bridge.
> 4. Cấu hình demo của Retail-AI chuyển từ `.env` sang biến môi trường của tiến trình (user duyệt khi triển khai,
>    19/11/2026), vì `.env` làm hỏng test Retail-AI chạy tại chỗ. Chi tiết ở mục 7.
> 5. Câu kiosk nói khi thiếu dữ liệu hàng mới về được đổi sang ngôn ngữ người mua (user duyệt khi triển khai,
>    19/11/2026; chỉ chuỗi trong `_localized_stock_arrival_unavailable` của `backend/api/main.py`). Chi tiết ở mục 6.
> 6. `price_vnd` của mặt hàng có feed là **giá người mua trả lúc này** (`min(unit_price_vnd, sale_price_vnd)`), không
>    còn giữ giá thường (user duyệt ngày 20/11/2026). Lý do: catalog Thanh Lam Mart đã quy ước `price_vnd` là giá đang áp
>    dụng, và mọi câu trả lời giá cùng thẻ sản phẩm của kiosk đọc trường này, nên kiosk từng báo giá gốc cho món đang
>    giảm cận date (test vai người mua). Giá thường nằm ở `list_price_vnd`. Chi tiết ở mục 5.
> 7. Hai sửa đổi Retail-AI sau khi test vai người mua (user duyệt ngày 20/11/2026): "hàng mới về" xếp món còn bán được
>    lên trước và ghi "đã bán hết" cho món hết hàng (`backend/services/retail_tools.py`); câu "có món nào / mặt hàng
>    nào đang giảm giá?" vào danh sách khuyến mãi thay vì bị hiểu là tên sản phẩm (`backend/api/main.py`).

## Context

Hai sub-project do hai người làm song song, không liên quan gì nhau:
- **Ops Chest** (`ops_chest/`, repo `quanchu14104/ops_chest`): agent quản lý kho theo lô và HSD.
- **Retail-AI** (`Retail-AI-/`, repo `chinhdz102/Retail-AI-`): kiosk/chatbot chăm sóc khách hàng.

Mục tiêu là nối hai bên bằng một nền dữ liệu hàng hoá dùng chung. Mỗi bên vẫn chỉ làm đúng việc của mình, code nối nằm ngoài cả hai, và sửa code mỗi bên ở mức tối thiểu.

Bốn sự thật định hình thiết kế:
1. **Hai bên không có sản phẩm nào trùng nhau.**
   - Ops Chest có 164 mặt hàng tươi FRN (điểm bán số 18). Mã số ẩn danh, tên là "Mặt hàng 412 · nhóm 3.1".
   - Retail-AI có 3.099 sản phẩm thực tế xin từ cửa hàng **Thanh Lam Mart** (lưu ở file kỹ thuật `data/winmart_products.json`).
   - Vì vậy phải *tạo* bảng ánh xạ (crosswalk). Ánh xạ này là **giả định demo** và phải ghi rõ như vậy.
2. **Dữ liệu vận hành chỉ chảy một chiều, Ops Chest → kiosk.** Gồm tồn, HSD, giảm giá cận date và hàng mới về. Mỗi trường chỉ có một chủ.
3. **Hai hệ thống ở hai năm khác nhau.**
   - Đồng hồ giả lập của Ops Chest là 26/06/2024. Retail-AI dùng ngày thật.
   - Nếu chuyển HSD nguyên gốc, `sellable_stock` (`Retail-AI-/backend/products/catalog.py:64`) sẽ coi mọi lô là hết hạn.
   - Bridge phải **dời trục thời gian**.
4. **Không thể không sửa code Retail-AI.**
   - Cả hai repository đều gán cứng `expiry_at=None` (`snapshot_repository.py:45`, `postgres_repository.py:376`).
   - Ghi đè file JSON catalog sẽ làm mất mọi vị trí kệ, vì planogram so khớp theo SHA-256 của file (`planogram.py:57`).

**Quyết định đã chốt với user (cập nhật 25/11/2026 đồng bộ nguồn Thanh Lam Mart)**
- **Tên hàng:** Ops Chest hiển thị tên sản phẩm Thanh Lam Mart qua một seam nhỏ, mặc định tắt.
- **Câu chuyện demo:** cửa hàng bán lẻ độc lập **Thanh Lam Mart**, làm việc trực tiếp với các nhà cung cấp.
- **Phạm vi giai đoạn 1:** còn hàng, HSD, hàng cận date giảm giá, hàng mới về.
- **Giá bán:** 164 mặt hàng lấy **giá Thanh Lam Mart, áp lúc seed**.
- **Code nối:** đặt ở **repo riêng `Q:\WORKSPACE\bridge`**.

## Kiến trúc

```
Thanh Lam Mart catalog (Retail-AI/data/winmart_products.json, chỉ đọc) ─┐
FRN store 18 (ops_chest/.../frn/stores_daily.csv.gz, chỉ đọc) ──────────┴─▶ bridge crosswalk ─▶ bridge/data/crosswalk.csv
                                                                        │
              bridge overrides ─▶ out/ops_catalog_overrides.json ─▶ [Ops Chest seed + seam]
                                                                        │
Ops Chest REST (/api/meta, /api/products, /api/inventory/expiring, /api/purchase-orders)
              │ pull bằng tài khoản nhân viên (chỉ xem)
              ▼
         bridge sync ─┬─▶ out/ops_feed.json (ghi atomic) ─▶ [Retail-AI OpsOverlayRepository, file mới]
                      └─▶ Retail-AI Postgres: retail_stores / retail_kiosks /
                          retail_data_feeds(RECEIVING) / inventory_receipts   (bảng đã có sẵn, Retail-AI chỉ đọc)
```

Không dùng chung DB vật lý: mỗi app giữ DB và migration riêng. Bridge không import code của bên nào. Nó giao tiếp với Ops Chest qua REST và với Retail-AI qua file JSON theo hợp đồng cùng các bảng feed. Theo `docs/retail-information-data-design.md` của Retail-AI, các bảng feed này được thiết kế để nguồn bên ngoài nạp vào.

### Chủ sở hữu từng trường (hợp đồng dữ liệu)

| Trường | Chủ | Bên dùng |
|---|---|---|
| Danh tính sản phẩm: id, barcode, tên, brand, danh mục, uom, ảnh | Catalog Thanh Lam Mart | Kiosk (trực tiếp); Ops Chest (tên qua crosswalk) |
| Giá bán thường của 164 mặt hàng | Thanh Lam Mart → nạp vào Ops Chest lúc seed; sau đó Ops Chest là chủ | Kiosk qua feed |
| Tồn bán được, HSD theo lô, giảm giá cận date | Ops Chest | Kiosk qua feed |
| Hàng mới về (PO đã nhận) | Ops Chest | Kiosk qua `inventory_receipts` |
| Vị trí kệ | Planogram của Retail-AI | Kiosk |
| Giá vốn, nguồn hàng, thỏa thuận, dự báo, value_at_risk | Ops Chest, **nội bộ** | Không bao giờ xuất ra |
| Tồn và giá của ~2.935 mặt hàng không ánh xạ | Snapshot Thanh Lam Mart, như hiện nay | Kiosk |

### Mức sửa code (mặc định tắt, nên test cũ không đổi)
- **Ops Chest: khoảng 25 dòng ở 4 file**, chỉ đi qua một PR.
- **Retail-AI: 1 file mới và khoảng 6 dòng ở 2 file.** Phần "hàng mới về" cần sửa thêm 1 dòng ở
  `backend/services/retail_information.py` (xem mục 6). Khi triển khai, factory thực tế là khoảng 10 dòng.
- Còn lại chỉ là `.env` và cờ cổng.

## Các bước thực hiện

### 0. Chuẩn bị repo
- Ops Chest đang có 40 file sửa chưa commit, trên nhánh `main`. Các file seam đụng tới không nằm trong số này.
  - Cách ưu tiên: nhờ chủ repo commit WIP trước.
  - Nếu chưa được: dùng `git worktree` tách từ HEAD (chi tiết ở mục Ghi chú triển khai).
- Tạo nhánh `feat/catalog-overrides` (Ops Chest) và `feat/ops-feed-overlay` (Retail-AI).
- Chạy `git init` cho `Q:\WORKSPACE\bridge`, giữ nguyên thư mục `docs/` đã có.
- Không push và không tạo PR khi user chưa đồng ý.

### 1. Khung bridge và hợp đồng v1

Cấu trúc thư mục `bridge/`:
- `pyproject.toml`: Python ≥3.12, chạy bằng `uv run`. Phụ thuộc runtime là `psycopg[binary]`; phụ thuộc dev là pytest và ruff.
- `.env.example`: `OPS_CHEST_URL`, `OPS_CHEST_USER/PASSWORD` (dùng tài khoản nhân viên `nhanvien`), `RETAIL_DATABASE_URL`, `WINMART_CATALOG_PATH`, `FRN_DATA_PATH`, `STORE_CODE=WMP-DEMO-01`, `KIOSK_ID=kiosk-01` (mặc định của Retail-AI, `schemas.py:16`), `STORE_ADDRESS`, `STORE_PHONE`.
- `contract/ops_feed.v1.md` và `contract/ops_feed.example.json`.
- `src/bridge/`: `config.py`, `timeshift.py`, `crosswalk.py`, `overrides.py`, `ops_client.py`, `feed.py`, `receipts.py`, `cli.py`.
- `tests/fixtures/`: response Ops Chest đã ghi lại.
- `out/`: đưa vào gitignore.

Mỗi phần tử trong `items` của feed v1 có các trường sau:
- `product_id` (mã SKU trong `winmart_products.json`), `ops_sku`, `status`
- `sellable_qty`, `earliest_expiry`
- `unit_price_vnd`, `sale_price_vnd`, `promotion_text`
- `coverage_complete`
- `lots[{qty, expiry, markdown_pct}]`

Phần đầu feed gồm: `contract: "ops-feed"`, `version: 1`, `published_at`, `ops_business_date`, `date_shift_days`, `store_name`.

**Danh sách trường được phép xuất là tuyệt đối.** Bridge loại bỏ `unit_cost`, `supplier`, `value_at_risk`, `expected_*`, `options` có trong response của Ops Chest.

### 2. Crosswalk FRN → Thanh Lam Mart (`bridge crosswalk build|check`)

**Nguồn**
- 164 mặt hàng FRN của điểm bán 18. Thông tin gồm management_group (7 nhóm, cỡ 80/40/21/8/6/6/3), cat1 (22) và cat2 (45). Lấy từ file CSV FRN (CC BY 4.0).
- Kiểm tra chéo với tập SKU `F{id:04d}` do `/api/products` trả về.

**Pool Thanh Lam Mart:** 249 mặt hàng tươi ngắn ngày.
- Lấy từ sub_department "Thực phẩm Tươi sống, Chế biến".
- Loại các danh mục "Thủy hải sản khô" và "Măng".
- Loại các dòng bị quarantine vì `sale_price_vnd > price_vnd`. Pool hiện có 0 dòng như vậy.

**Thuật toán tất định, giữ nguyên cấu trúc**
1. Ghép nhóm FRN với ngành hàng Thanh Lam Mart theo kích cỡ: 80 → Rau củ, 40 → Trái cây, 21 → Thịt. Các nhóm còn lại vào Thủy hải sản, Bánh mỳ và Thức ăn nấu sẵn.
2. Trong mỗi nhóm, ghép cat1 với danh mục con theo kích cỡ.
3. Ghép từng mặt hàng theo hạng nhu cầu, đối ứng với thứ tự `item_no`. Kết quả là ánh xạ 1:1, và các mặt hàng thay thế (cùng cat2) vẫn nằm cùng danh mục.

**Đầu ra `data/crosswalk.csv`** gồm các cột: ops_sku, frn_id, frn_group, frn_cat1, frn_cat2, product_id, winmart_name, winmart_category, price_vnd, method (`auto-v1` hoặc `manual`), note. File được commit và cho phép sửa tay (tên cột `winmart_*` giữ nguyên để tương thích).

**`check` kiểm tra:**
- Có đủ 164 dòng và duy nhất ở cả hai phía.
- Mọi product_id có trong file catalog Thanh Lam Mart (`winmart_products.json`) và không bị quarantine.
- In ra SHA-256 của file catalog đã dùng.

### 3. Seam Ops Chest và nạp lại dữ liệu (PR duy nhất vào Ops Chest)

Thay đổi code:
- `backend/app/config.py`: thêm `catalog_overrides_path: str | None = None`.
- `backend/app/sim/frn_catalog.py`: thêm hàm `apply_catalog_overrides(suppliers, products, path)`.
  - Ghi đè `name`. Ghi đè `unit_price`, rồi tính lại `unit_cost` theo **đúng tỷ lệ giá vốn/giá bán cũ**.
  - Ghi đè `name` và `email` của nguồn hàng.
  - Khi không có path thì không làm gì.
  - **Không đổi `category`**, vì `frn_category_policy` tách mã nhóm từ chuỗi "Nhóm tươi N".
- `backend/app/sim/seed.py:60`: gọi hàm ngay sau `build_frn_catalog`, tức trước `StoreSim`. Nhờ vậy 90 ngày lịch sử cũng dùng giá mới.
- `backend/app/api/routes_core.py`: thêm trường `received_at` vào `GET /api/purchase-orders`. Thay đổi chỉ cộng thêm, không phá gì.
- Test mới `backend/tests/test_catalog_overrides.py`: kiểm tra có ghi đè (tên, giá, tỷ lệ giá vốn, nguồn hàng) và không làm gì khi không đặt biến.

Vì sao seam đặt ở seed:
- Bộ backtest (`backtest.py:184`) và test FRN gọi `build_frn_catalog` trực tiếp nên không bị ảnh hưởng.
- Chức năng tua nhanh (`advance.py:162`) chỉ lấy nhu cầu từ spec. Giá bán lấy từ DB (`advance.py:88`), nên vẫn nhất quán.

**Bridge `overrides`** sinh file `out/ops_catalog_overrides.json` gồm:
- Tên và giá Thanh Lam Mart cho từng SKU.
- 7 nguồn hàng đổi thành "Nhà cung cấp Thanh Lam Mart – {Rau củ, Trái cây, …} (demo)". Mã NCC01…NCC07 khớp với nhóm FRN đã sắp xếp, đúng quy tắc trong `build_frn_catalog`. Tất cả dùng chung email `dathang@khotong-demo.test`.
- Tham số lead time, lịch giao, đơn tối thiểu và thỏa thuận trả hàng **giữ nguyên**, nên engine không đổi.

Cấu hình Ops Chest `.env` (chỉ thêm dòng, không đụng key LLM):
- `CATALOG_OVERRIDES_PATH`
- `STORE_NAME="Thanh Lam Mart"`, `STORE_ADDRESS`, `STORE_PHONE`
- `SMTP_FROM=cuahang-demo@thanhlammart-demo.test`

Sau đó chạy `uv run python -m app.sim.seed --reset`. Email vẫn chỉ rơi vào Mailpit, dùng tên miền `.test` và có hậu tố "(demo)".

### 4. Bộ xuất feed (`bridge sync`)

Trình tự:
1. `ops_client` đăng nhập bằng `POST /api/auth/login` với tài khoản nhân viên. Sau đó gọi `GET /api/meta` (lấy `today`), `/api/products?limit=500` và `/api/inventory/expiring?days=120` (với hàng FRN, mốc 120 ngày bao trùm mọi lô).
2. `timeshift` tính `shift = ngày thật (Asia/Ho_Chi_Minh) − ops_today`. Mọi ngày và giờ đều được dời theo `shift`. Kết quả không bao giờ vượt quá thời điểm hiện tại.

Quy tắc tính:
- **Lô bán được:** các lô có `days_left ≥ 0`.
- **`earliest_expiry`:** `expiry_date` nhỏ nhất trong các lô bán được, sau khi dời ngày.
- **`coverage_complete`:** bằng `false` khi tổng số lượng của các lô (kể cả lô EXPIRED) khác `on_hand`.
- **Giảm giá có hiệu lực tại thời điểm xuất:**
  - Dùng `evening_markdown_pct` nếu là ngày bán cuối và đã qua `markdown_hour`. Ngược lại dùng `markdown_pct`.
  - `promotion_text` có dạng "Giảm 30% cho 5 sản phẩm HSD 20/11".
  - `sale_price_vnd` là giá thấp nhất đang áp dụng.
- **Ghi file:** ghi `out/ops_feed.json` kiểu atomic, tức ghi file tạm rồi `os.replace`.
- **Khi Ops Chest không phản hồi:** không ghi đè feed cũ, báo lỗi rõ ràng và trả exit code khác 0.

Test dùng fixture Ops Chest đã ghi, kiểm tra: danh sách trường được phép, phép dời ngày, giảm giá tối, `coverage_complete`, và trường hợp cùng mặt hàng có nhiều lô.

### 5. Adapter của Retail-AI (PR vào Retail-AI)

File mới `backend/products/ops_overlay_repository.py`:
- Bọc `SnapshotProductRepository`. File catalog `winmart_products.json` giữ nguyên, nên **planogram vẫn khớp hash**.
- Mỗi lần gọi thì `stat` file feed và nạp lại khi mtime hoặc size đổi. Feed hỏng (sai `contract` hoặc `version`) thì giữ feed hợp lệ gần nhất và ghi log.
- Ghép dữ liệu vào từng mặt hàng đã ánh xạ bằng `ProductSnapshot.model_copy(update=…)`:
  - `stock` ← `sellable_qty`
  - `expiry_at` ← `earliest_expiry`
  - `promotion`, `sale_price_vnd`, `list_price_vnd`, `price_quality_status` ← các trường giá trong feed
  - `data_timestamp` ← `published_at`
- ~~**`price_vnd` giữ giá thường**, vì chỉ một phần số hàng đang được giảm.~~ Điều chỉnh 20/11/2026 (điều chỉnh 6 ở
  đầu file): `price_vnd` = `min(unit_price_vnd, sale_price_vnd)`, cùng quy ước với hàng Thanh Lam Mart thường;
  `list_price_vnd` giữ giá thường, `promotion` nói rõ bao nhiêu sản phẩm được giảm.
- Các phương thức:
  - `search` gọi `search_products(products=…)`, với alias danh mục giống repository gốc.
  - `get_product_snapshot` trả mặt hàng đã ghép.
  - `list_promotions` đưa hàng cận date của Ops Chest **lên đầu**. Nếu không, chúng bị chìm trong 580 khuyến mãi trong snapshot ban đầu.
  - `list_catalog_additions` chuyển nguyên cho repository gốc.
- Feed cũ vẫn được áp. `data_timestamp` để lộ tuổi dữ liệu (kiosk đã nói "theo dữ liệu ngày …", `main.py:274`), và lô quá hạn tự thành không bán được.

Sửa file cũ:
- `backend/config.py`: thêm `ops_feed_path: str = ""`.
- `backend/products/repository.py` (`get_product_repository`):
  - Khi dùng snapshot và có `ops_feed_path` thì bọc repository bằng adapter, có cache.
  - Nếu có `ops_feed_path` mà chế độ không phải snapshot thì báo lỗi, vì giai đoạn 1 chỉ hỗ trợ snapshot.

Test mới `tests/test_ops_overlay_repository.py`, fixture copy từ `bridge/contract/ops_feed.example.json`. Các trường hợp: ghép đúng trường; bộ lọc `in_stock` dùng tồn đã ghép; vị trí kệ vẫn còn; thứ tự `list_promotions`; feed hỏng hoặc cũ; tắt tính năng thì hành vi không đổi.

### 6. Hàng mới về → Postgres của Retail-AI (sửa 1 dòng code Retail-AI)

> Điều chỉnh khi triển khai (user duyệt 19/11/2026): `lookup_retail_information` trả DATA_UNAVAILABLE khi
> `CATALOG_REPOSITORY != postgres`, nên kiosk chạy snapshot không đọc được `inventory_receipts`. Điều kiện đổi thành
> `settings.catalog_repository != "postgres" and not settings.ops_feed_path`, kèm 1 test. Hệ quả: khi bật
> `OPS_FEED_PATH`, Postgres của Retail-AI phải luôn chạy; nếu tắt, tra campaign trả TEMPORARY_FAILURE và câu hỏi
> khuyến mãi nhận câu báo không khả dụng thay vì danh sách hàng giảm giá.
>
> Điều chỉnh thứ hai (user duyệt 19/11/2026): Retail-AI phục vụ người mua, Ops Chest phục vụ Store Manager. Câu trả
> lời "hàng mới về" in giờ UTC (22:06 giờ Việt Nam hiện thành 15:06) và dùng từ nội bộ "phiếu nhận hàng". Sửa trong
> `_localized_retail_information_observation` (`backend/api/main.py`): đổi mốc thời gian có múi giờ sang múi giờ
> cửa hàng (mặc định Asia/Ho_Chi_Minh), câu mới "Hàng mới về gần đây tại …: … (về lúc dd/mm/yyyy HH:MM)" và "Trong 7
> ngày qua, … chưa ghi nhận hàng mới về"; tiếng Anh, tiếng Trung tương ứng. Logic kiểm tra feed giữ nguyên.
>
> Điều chỉnh thứ ba (user duyệt 19/11/2026): khi feed RECEIVING thiếu hoặc cũ, kiosk nói "Mình chưa có phiếu nhận
> hàng đã xác minh nên chưa thể xác nhận món nào vừa nhập kho." Chuỗi trong `_localized_stock_arrival_unavailable`
> đổi thành "Hiện mình chưa có thông tin hàng mới về của cửa hàng nên chưa thể cho bạn biết món nào vừa về. Bạn có
> thể hỏi nhân viên cửa hàng nhé." (và tiếng Anh, tiếng Trung tương ứng). Không đổi logic hay nơi gọi.

Chuẩn bị bằng lệnh có sẵn của Retail-AI: `docker compose up -d postgres` và `uv run python scripts/import_winmart.py --apply`. Bảng `products` sau khi import là đích khoá ngoại cho `inventory_receipts`. Catalog của kiosk vẫn chạy chế độ snapshot.

Mỗi lần sync, `bridge/receipts.py` chạy trong một transaction:
- Upsert `retail_organizations('thanh_lam_mart')`.
- Upsert `retail_stores(STORE_CODE, tên từ /api/meta, địa chỉ và SĐT từ .env, source_name='ops-chest-bridge (demo)')`.
- Upsert `retail_kiosks(KIOSK_ID → STORE_CODE)`.
- Upsert `retail_data_feeds(RECEIVING, ACTIVE, last_success_at=now, coverage 7 ngày, coverage_complete=true)`.
- Xoá rồi chèn lại `inventory_receipts` thuộc `source_name='ops-chest-bridge'`. Dữ liệu lấy từ PO RECEIVED trong 7 ngày nghiệp vụ gần nhất (`GET /api/purchase-orders` cùng chi tiết từng PO):
  - `event_id = ops:{po_code}:{line_id}`
  - `quantity = received_qty`
  - `received_at` = `received_at` của PO sau khi dời ngày. Nếu chưa có thì lấy `expected_date`.

Cách làm xoá và chèn lại tự sửa được dữ liệu sau khi tua nhanh hoặc `seed --reset`.

**Không tạo feed PROMOTIONS.** Nếu tạo, phần tra campaign trả về SUCCESS rỗng và che mất khuyến mãi theo sản phẩm (`main.py:3421-3437`).

Tác dụng phụ đã biết: kiosk sẽ trả lời được thông tin cửa hàng demo (tên, địa chỉ), khớp với Ops Chest.

### 7. Cách chạy và README của bridge

Phân bổ cổng (chỉ dùng config):

| Dịch vụ | Cổng |
|---|---|
| Ops Chest API (chạy local, SQLite) | 8000 |
| Ops Chest UI | 5173 |
| Mailpit | 8025 / 1025 |
| Postgres của Retail-AI (Docker) | 5432 |
| Retail-AI API (`--port 8020`) | 8020 |
| Kiosk (`-- --port 5190`) | 5190 |

**Không chạy docker compose của Ops Chest cùng lúc**, vì sẽ có hai Postgres cùng giành cổng 5432.

Cấu hình Retail-AI:
- ~~`.env`~~ biến môi trường của tiến trình API: `CATALOG_REPOSITORY=snapshot`, `OPS_FEED_PATH=Q:/WORKSPACE/bridge/out/ops_feed.json`, `CORS_ORIGINS=http://127.0.0.1:5190,http://localhost:5190`.
- ~~`apps/kiosk-airi/.env`~~ biến môi trường của tiến trình kiosk: `VITE_API_BASE_URL=http://127.0.0.1:8020`.

> Điều chỉnh khi triển khai (user duyệt 19/11/2026): bộ test của Retail-AI đọc `Retail-AI-/.env`, nên để các
> biến demo trong đó làm hỏng test chạy tại chỗ. Các biến demo chuyển sang khối `env` trong
> `Q:/WORKSPACE/.claude/launch.json` và file `bridge/demo/retail-ai.env`; hai file `.env` của Retail-AI giữ giá trị
> mặc định như `.env.example`. Vite đọc `VITE_*` từ biến môi trường của tiến trình nên kiosk không mất tính năng.

Chạy bridge liên tục bằng `uv run bridge sync --every 120`.

README của bridge ghi rõ:
- Thứ tự khởi động và bảng chủ sở hữu.
- **Các giả định demo:**
  - Ánh xạ FRN→Thanh Lam Mart là tự đặt.
  - `shelf_life_days` vẫn là số giả lập 1–3 ngày, dù trái cây nhập khẩu thực tế để được lâu hơn.
- Phép dời trục thời gian.

## Ngoài phạm vi giai đoạn 1
- Đổi chữ "NCC/Nhà cung cấp" trên UI và prompt của Ops Chest: khoảng 140 chỗ. Làm ở giai đoạn 2 nếu chủ repo đồng ý.
- Đẩy giảm giá cận date thành campaign có cấu trúc (feed PROMOTIONS).
- Hỗ trợ ghép dữ liệu cho chế độ catalog Postgres.
- Luồng ngược từ kiosk về Ops Chest, ví dụ báo hàng lỗi qua `report_product_issue`.
- Đổi HSD theo loại hàng thật.
- Dùng chung DB vật lý.

## Kiểm thử

Unit test:
- Bridge: `cd bridge && uv run pytest -q && uv run ruff check .`
- Ops Chest: `cd <worktree>/backend && uv run pytest -q`. Toàn bộ test cũ phải xanh khi seam tắt, cộng thêm test mới.
- Retail-AI: `cd Retail-AI- && uv run pytest -q && uv run ruff check .`

**End-to-end** (chạy đủ các dịch vụ theo bảng cổng):
1. Seed Ops Chest kèm overrides. `GET /api/products` phải trả tên và giá Thanh Lam Mart, nguồn hàng là "Nhà cung cấp Thanh Lam Mart – …".
2. `bridge sync --once`. Feed phải hợp lệ, và `grep` không thấy `unit_cost` hay `supplier`.
3. Gọi `GET :8020/products/{product_id}/snapshot` cho một mặt hàng đã ánh xạ. Kết quả phải có:
   - `stock` bằng tồn bán được ở Ops Chest.
   - `expiry_at` ≥ hôm nay.
   - Vẫn còn `shelf`.
   - `data_timestamp` bằng `published_at`.
4. Đăng nhập Ops Chest bằng tài khoản quản lý, duyệt một đề xuất giảm giá rồi sync. Hỏi `POST :8020/agent/respond` "có món nào đang giảm giá không?": món đó phải được liệt kê đầu tiên.
5. Hỏi "hôm nay có hàng gì mới về?": kiosk phải liệt kê PO đã nhận, với tên Thanh Lam Mart.
6. Tua nhanh Ops Chest 1 ngày (`POST /api/sim/advance`) rồi sync: tồn và HSD phải đổi, `date_shift_days` giảm 1.
7. Tắt Ops Chest rồi sync: bridge báo lỗi, feed giữ nguyên, kiosk trả dữ liệu cũ kèm mốc thời gian cũ. Bật lại thì hồi phục.
8. Một mặt hàng không ánh xạ (ví dụ dầu gội) phải giữ nguyên giá trị snapshot.

## Ghi chú triển khai (kiểm tra môi trường ngày 19/11/2026)

**Công cụ**
- `python` không có trên PATH, chỉ có alias của Microsoft Store. Luôn chạy qua `uv run`. Máy có `uv` 0.13.1, Node, `git` 2.56.
- Docker 29.8.2 đã cài, nhưng `docker info` không trả về phiên bản server, nên daemon có thể chưa chạy.
  - Khi cần Postgres mà daemon đang tắt: nhờ user bật Docker Desktop, không tự cài gì.

**File `.env`**
- `ops_chest/.env` đã có và chứa key LLM. Chỉ được thêm dòng, không in nội dung, không copy key sang project khác.
- `Retail-AI-/.env` và `Retail-AI-/apps/kiosk-airi/.env` chưa có. Tạo từ `.env.example`, giữ giá trị
  mặc định; biến demo đặt ở biến môi trường của tiến trình (xem mục 7).
- Thiếu `GROQ_API_KEY` thì hỏi user. Nếu không có key, ưu tiên kiểm thử tất định (`/products/{id}/snapshot`, `/products/search`, test repository) và ghi rõ kịch bản nào chưa chạy được.

**Ops Chest (worktree)**
- Repo đang ở `main` với 40 file WIP. Không đụng tới chúng.
- Tạo worktree: `git -C Q:/WORKSPACE/ops_chest worktree add Q:/WORKSPACE/worktrees/ops-chest-catalog-overrides -b feat/catalog-overrides`.
- Dữ liệu FRN (`backend/app/sim/data/frn/*`) và model LightGBM (`backend/app/ml/artifacts/*`) đều được git track, nên worktree đủ dữ liệu. `.gitattributes` giữ LF cho file model.
- Worktree không có `.env`. Truyền biến môi trường qua lệnh, hoặc dùng một file env riêng nằm ngoài repo.

**Retail-AI:** repo sạch, đang ở `main`. Tạo nhánh `feat/ops-feed-overlay` ngay tại chỗ.

**Cổng:** `ops_chest/.claude/launch.json` đã dùng 8010/5180 cho cấu hình scratch của Ops Chest. Vì vậy Retail-AI dùng 8020 (API) và 5190 (kiosk).

**Tài khoản demo** (seed tạo; đã ghi công khai trong `ops_chest/.env.example`):
- Bridge dùng `nhanvien` (chỉ xem).
- Kiểm thử dùng `quanly` để duyệt đề xuất giảm giá.
- Tạo đề xuất bằng `POST /api/proposals/generate`, hoặc bằng chức năng tua nhanh (bản tin sáng tự tạo đề xuất). Cách này không cần LLM.
