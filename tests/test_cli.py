import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

from bridge import cli
from tests.conftest import ROOT, load


class StubOps(BaseHTTPRequestHandler):
    """Ops Chest giả: trả response đã ghi, kiểm tra có Bearer token."""

    def log_message(self, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        if urlparse(self.path).path == "/api/auth/login" and body == {"username": "nhanvien",
                                                                       "password": "nhanvien123"}:
            return self._send(200, {"token": "t0k", "user": {"role": "staff"}})
        return self._send(401, {"detail": "Sai tên đăng nhập hoặc mật khẩu"})

    def do_GET(self):
        path = urlparse(self.path).path
        if path != "/api/meta" and self.headers.get("Authorization") != "Bearer t0k":
            return self._send(401, {"detail": "unauthorized"})
        routes = {"/api/meta": "ops_meta.json", "/api/products": "ops_products.json",
                  "/api/inventory/expiring": "ops_expiring.json", "/api/purchase-orders": "ops_purchase_orders.json"}
        if path in routes:
            return self._send(200, load(routes[path]))
        if path.startswith("/api/purchase-orders/"):
            return self._send(200, load(f"ops_purchase_order_{path.rsplit('/', 1)[1]}.json"))
        return self._send(404, {"detail": "not found"})


@pytest.fixture()
def stub_ops():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubOps)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPS_FEED_PATH", str(tmp_path / "ops_feed.json"))
    monkeypatch.setenv("CROSSWALK_PATH", str(ROOT / "data" / "crosswalk.csv"))
    monkeypatch.setenv("OPS_CHEST_USER", "nhanvien")
    monkeypatch.setenv("OPS_CHEST_PASSWORD", "nhanvien123")
    monkeypatch.setenv("RETAIL_DATABASE_URL", f"postgresql://x:y@127.0.0.1:{_free_port()}/none")
    return tmp_path / "ops_feed.json"


def test_sync_writes_feed_then_keeps_it_when_ops_chest_is_down(monkeypatch, env, stub_ops, capsys):
    monkeypatch.setenv("OPS_CHEST_URL", stub_ops)
    assert cli.main(["sync", "--once", "--no-receipts"]) == 0
    feed = json.loads(env.read_text(encoding="utf-8"))
    assert feed["contract"] == "ops-feed" and len(feed["items"]) == 5
    before = env.read_bytes()

    monkeypatch.setenv("OPS_CHEST_URL", f"http://127.0.0.1:{_free_port()}")
    assert cli.main(["sync", "--once"]) == cli.EXIT_OPS_UNAVAILABLE
    err = capsys.readouterr().err
    assert "Không kết nối được Ops Chest" in err and "Giữ nguyên feed cũ" in err
    assert env.read_bytes() == before


def test_sync_reports_retail_database_failure_after_writing_feed(monkeypatch, env, stub_ops, capsys):
    monkeypatch.setenv("OPS_CHEST_URL", stub_ops)
    assert cli.main(["sync", "--once"]) == cli.EXIT_RETAIL_DB
    assert env.exists()
    assert "Postgres của Retail-AI thất bại" in capsys.readouterr().err


def test_wrong_credentials_fail_without_writing(monkeypatch, env, stub_ops, capsys):
    monkeypatch.setenv("OPS_CHEST_URL", stub_ops)
    monkeypatch.setenv("OPS_CHEST_PASSWORD", "sai")
    assert cli.main(["sync", "--once", "--no-receipts"]) == cli.EXIT_OPS_UNAVAILABLE
    assert not env.exists()
    assert "HTTP 401" in capsys.readouterr().err


def test_sync_loop_survives_an_unexpected_error(monkeypatch, env, capsys):
    calls = []

    def boom(cfg, receipts=True):
        calls.append(receipts)
        if len(calls) == 1:
            raise PermissionError(5, "Access is denied")
        raise KeyboardInterrupt  # dừng vòng lặp ở lần thứ hai

    monkeypatch.setattr(cli, "sync_once", boom)
    monkeypatch.setattr(cli.time, "sleep", lambda _s: None)
    assert cli.main(["sync", "--every", "1", "--no-receipts"]) == 0
    assert calls == [False, False]  # lần lỗi đầu không làm chết vòng lặp
    assert "sync thất bại (PermissionError" in capsys.readouterr().err


def test_sync_loop_keeps_a_fixed_cadence(monkeypatch, env):
    clock = iter([0.0, 30.0, 120.0, 125.0, 240.0])  # lần 1 chạy mất 30 giây, lần 2 mất 5 giây
    slept, runs = [], []

    def fake_sync(cfg, receipts=True):
        runs.append(1)
        if len(runs) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(cli, "sync_once", fake_sync)
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(cli.time, "sleep", slept.append)
    assert cli.main(["sync", "--every", "120", "--no-receipts"]) == 0
    assert slept == [90.0, 115.0]  # 120 trừ thời gian chạy, không phải 120 cố định


def test_default_paths_point_at_sibling_repos(tmp_path):
    from bridge.config import ROOT, WORKSPACE, Config

    cfg = Config.load(env={}, env_file=tmp_path / "missing.env")
    assert WORKSPACE == ROOT.parent
    assert cfg.winmart_catalog_path == WORKSPACE / "Retail-AI-" / "data" / "winmart_products.json"
    frn = WORKSPACE / "ops_chest" / "backend" / "app" / "sim" / "data" / "frn" / "stores_daily.csv.gz"
    assert cfg.frn_data_path == frn
    assert cfg.ops_feed_path == ROOT / "out" / "ops_feed.json"
    custom = Config.load(env={"FRN_DATA_PATH": "D:/x/frn.csv.gz"}, env_file=tmp_path / "m")
    assert custom.frn_data_path.as_posix() == "D:/x/frn.csv.gz"
