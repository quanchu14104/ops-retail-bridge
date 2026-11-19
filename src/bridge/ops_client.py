"""Client REST chỉ-đọc cho Ops Chest, đăng nhập bằng tài khoản nhân viên (chỉ xem). Chỉ dùng thư viện chuẩn."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class OpsChestError(RuntimeError):
    """Ops Chest không phản hồi hoặc trả lỗi; bridge không được ghi đè dữ liệu cũ."""


class OpsClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self._token: str | None = None

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise OpsChestError(f"Ops Chest {method} {path} trả HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            reason = getattr(e, "reason", e)
            raise OpsChestError(f"Không kết nối được Ops Chest tại {self.base_url} ({reason})") from e
        except json.JSONDecodeError as e:
            raise OpsChestError(f"Ops Chest {method} {path} trả dữ liệu không phải JSON") from e

    def login(self) -> None:
        out = self._request("POST", "/api/auth/login", body={"username": self.username, "password": self.password})
        self._token = out["token"]

    def get(self, path: str, **params):
        if self._token is None:
            self.login()
        return self._request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def meta(self) -> dict:
        return self.get("/api/meta")

    def products(self) -> list[dict]:
        return self.get("/api/products", limit=500)

    def expiring(self, days: int = 120) -> dict:
        return self.get("/api/inventory/expiring", days=days)

    def purchase_orders(self, status: str | None = None, limit: int = 300) -> list[dict]:
        return self.get("/api/purchase-orders", status=status, limit=limit)

    def purchase_order(self, po_id: int) -> dict:
        return self.get(f"/api/purchase-orders/{po_id}")
