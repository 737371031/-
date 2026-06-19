#!/usr/bin/env python3
import argparse
import base64
import contextlib
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import socketserver
import tempfile
import time
import urllib.error
import urllib.request
from http import cookies
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
MODELS_FILE = BASE_DIR / "models.json"
CONFIG_FILE = BASE_DIR / "model-admin-config.json"
SELF_CONFIG_FILE = BASE_DIR / "subscription-self-config.json"
SELF_AUDIT_FILE = BASE_DIR / "subscription-self-audit.log"
SESSION_COOKIE = "model_admin_session"
SELF_SESSION_COOKIE = "subscription_self_session"
PBKDF2_ITERATIONS = 260000
SESSION_TTL_SECONDS = 12 * 60 * 60
SELF_SESSION_TTL_SECONDS = 30 * 60
SUB2API_TIMEOUT_SECONDS = 20
RATE_LIMITS = {}

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux servers have fcntl.
    fcntl = None


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@contextlib.contextmanager
def file_lock(path: Path):
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a", encoding="utf-8") as lock:
        if fcntl:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path, content: str, mode: int = 0o644) -> None:
    if not os.access(path.parent, os.W_OK):
        raise RuntimeError("当前目录不可写，请检查服务器权限")

    with file_lock(path):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)
        os.chmod(path, mode)


def read_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with CONFIG_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_config(config: dict) -> None:
    atomic_write_text(CONFIG_FILE, json.dumps(config, ensure_ascii=False, indent=2) + "\n", 0o600)


def read_self_config() -> dict:
    if not SELF_CONFIG_FILE.exists():
        return {}
    with SELF_CONFIG_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def ensure_self_config() -> dict:
    config = read_self_config()
    if config.get("session_secret"):
        return config
    config = {"session_secret": secrets.token_hex(32)}
    atomic_write_text(SELF_CONFIG_FILE, json.dumps(config, ensure_ascii=False, indent=2) + "\n", 0o600)
    return config


def password_hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    ).hex()


def verify_password(password: str, config: dict) -> bool:
    salt = str(config.get("password_salt", ""))
    expected = str(config.get("password_hash", ""))
    if not salt or not expected:
        return False
    actual = password_hash(password, salt)
    return hmac.compare_digest(actual, expected)


def make_session_cookie(config: dict) -> str:
    secret = bytes.fromhex(str(config["session_secret"]))
    payload = f"{int(time.time())}:{secrets.token_hex(12)}"
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{b64url(payload.encode('utf-8'))}.{b64url(signature)}"


def verify_session_cookie(value: str, config: dict) -> bool:
    try:
        payload_b64, signature_b64 = value.split(".", 1)
        payload = b64url_decode(payload_b64)
        signature = b64url_decode(signature_b64)
        secret = bytes.fromhex(str(config["session_secret"]))
        expected = hmac.new(secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        created_at = int(payload.decode("utf-8").split(":", 1)[0])
        return time.time() - created_at <= SESSION_TTL_SECONDS
    except Exception:
        return False


def make_signed_payload(payload: dict, secret_hex: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    secret = bytes.fromhex(secret_hex)
    signature = hmac.new(secret, body, hashlib.sha256).digest()
    return f"{b64url(body)}.{b64url(signature)}"


def verify_signed_payload(value: str, secret_hex: str) -> Optional[dict]:
    try:
        body_b64, signature_b64 = value.split(".", 1)
        body = b64url_decode(body_b64)
        signature = b64url_decode(signature_b64)
        secret = bytes.fromhex(secret_hex)
        expected = hmac.new(secret, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(body.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def default_catalog() -> dict:
    return {"title": "模型服务目录", "updatedAt": time.strftime("%Y-%m-%d"), "models": []}


def normalize_catalog(catalog: dict) -> dict:
    if not isinstance(catalog, dict):
        raise ValueError("catalog 必须是对象")

    title = str(catalog.get("title") or "模型服务目录").strip()
    updated_at = str(catalog.get("updatedAt") or time.strftime("%Y-%m-%d")).strip()
    models = catalog.get("models")
    if not title:
        raise ValueError("目录标题不能为空")
    if not isinstance(models, list):
        raise ValueError("models 必须是数组")

    allowed_types = {"text", "image", "embed", "audio", "video"}
    allowed_statuses = {"ready", "beta", "offline"}
    ids = set()
    normalized = []

    for index, model in enumerate(models, start=1):
        if not isinstance(model, dict):
            raise ValueError(f"第 {index} 个模型格式不正确")

        item = {
            "name": str(model.get("name") or "").strip(),
            "id": str(model.get("id") or "").strip(),
            "provider": str(model.get("provider") or "").strip(),
            "type": str(model.get("type") or "text").strip(),
            "context": str(model.get("context") or "").strip(),
            "price": str(model.get("price") or "").strip(),
            "status": str(model.get("status") or "ready").strip(),
            "description": str(model.get("description") or "").strip(),
        }

        if not item["name"] or not item["id"]:
            raise ValueError(f"第 {index} 个模型缺少名称或 ID")
        if item["id"] in ids:
            raise ValueError(f"模型 ID 重复：{item['id']}")
        if item["type"] not in allowed_types:
            raise ValueError(f"模型类型不支持：{item['type']}")
        if item["status"] not in allowed_statuses:
            raise ValueError(f"模型状态不支持：{item['status']}")

        ids.add(item["id"])
        normalized.append(item)

    return {"title": title, "updatedAt": updated_at, "models": normalized}


def sub2api_base_url() -> str:
    return os.environ.get("SUB2API_BASE_URL", "").strip().rstrip("/")


def sub2api_api_prefix() -> str:
    value = os.environ.get("SUB2API_API_PREFIX", "/api/v1").strip().rstrip("/")
    return value if value.startswith("/") else "/api/v1"


def sub2api_admin_key() -> str:
    return os.environ.get("SUB2API_ADMIN_KEY", "").strip()


def sub2api_admin_key_header() -> str:
    return os.environ.get("SUB2API_ADMIN_KEY_HEADER", "x-api-key").strip() or "x-api-key"


def sub2api_auth_me_path() -> str:
    value = os.environ.get("SUB2API_AUTH_ME_PATH", "/auth/me").strip()
    return value if value.startswith("/") else "/auth/me"


def self_api_path() -> str:
    value = os.environ.get("SELF_SERVICE_API_PATH", "/self-api").strip().rstrip("/")
    return value if value.startswith("/") else "/self-api"


def self_cookie_path() -> str:
    value = os.environ.get("SELF_SERVICE_COOKIE_PATH", "/ai-catalog").strip()
    return value if value.startswith("/") else "/"


def sub2api_configured() -> bool:
    return bool(sub2api_base_url() and sub2api_admin_key())


def redact_sensitive(value: str) -> str:
    redacted = str(value)
    for key in ("token", "admin_key", "x-api-key", "authorization"):
        redacted = redacted.replace(key + "=", key + "=REDACTED")
    return redacted


def check_rate_limit(scope: str, identity: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    key = f"{scope}:{identity}"
    bucket = [ts for ts in RATE_LIMITS.get(key, []) if now - ts < window_seconds]
    if len(bucket) >= limit:
        RATE_LIMITS[key] = bucket
        return False
    bucket.append(now)
    RATE_LIMITS[key] = bucket
    return True


def parse_user_id(value) -> int:
    try:
        user_id = int(str(value).strip())
    except Exception:
        raise ValueError("用户 ID 不正确")
    if user_id <= 0:
        raise ValueError("用户 ID 不正确")
    return user_id


def unwrap_sub2api_response(payload):
    if isinstance(payload, dict) and "code" in payload:
        if payload.get("code") == 0:
            return payload.get("data")
        raise RuntimeError(str(payload.get("message") or payload.get("error") or "Sub2API 请求失败"))
    return payload


def find_user_id(payload) -> Optional[int]:
    if isinstance(payload, dict):
        for key in ("id", "user_id"):
            if key in payload:
                try:
                    value = int(payload[key])
                    if value > 0:
                        return value
                except Exception:
                    pass
        for key in ("user", "profile", "data"):
            found = find_user_id(payload.get(key))
            if found:
                return found
    return None


def extract_subscription_items(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "subscriptions", "records", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = extract_subscription_items(value)
                if nested:
                    return nested
    return []


def safe_subscription(item: dict) -> dict:
    group = item.get("group") if isinstance(item.get("group"), dict) else {}
    plan = item.get("plan") if isinstance(item.get("plan"), dict) else {}
    return {
        "id": item.get("id"),
        "status": item.get("status") or "",
        "platform": item.get("platform") or group.get("platform") or "",
        "group_id": item.get("group_id") or group.get("id"),
        "group_name": item.get("group_name") or group.get("name") or plan.get("name") or "",
        "created_at": item.get("created_at") or item.get("start_at") or "",
        "expires_at": item.get("expires_at") or item.get("expired_at") or item.get("end_at") or item.get("valid_until") or "",
        "quota": item.get("quota") or item.get("quota_limit") or item.get("monthly_quota") or "",
        "used": item.get("used") or item.get("quota_used") or item.get("monthly_used") or "",
    }


def sub2api_request(method: str, path: str, body=None, bearer_token: str = "", admin: bool = False):
    base = sub2api_base_url()
    if not base:
        raise RuntimeError("未配置 SUB2API_BASE_URL")
    url = base + sub2api_api_prefix() + path
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer_token:
        headers["Authorization"] = "Bearer " + bearer_token
    if admin:
        key = sub2api_admin_key()
        if not key:
            raise RuntimeError("未配置 SUB2API_ADMIN_KEY")
        headers[sub2api_admin_key_header()] = key

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=SUB2API_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
            payload = unwrap_sub2api_response(payload)
            message = payload.get("message") if isinstance(payload, dict) else None
        except Exception:
            message = None
        raise RuntimeError(message or f"Sub2API 返回 HTTP {exc.code}")
    except urllib.error.URLError:
        raise RuntimeError("无法连接 Sub2API 服务")

    if not raw.strip():
        return {}
    return unwrap_sub2api_response(json.loads(raw))


def write_self_audit(event: str, user_id: int, subscription_id: int = 0, client_ip: str = "") -> None:
    line = json.dumps({
        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "user_id": user_id,
        "subscription_id": subscription_id,
        "client_ip": client_ip,
    }, ensure_ascii=False, separators=(",", ":")) + "\n"
    with file_lock(SELF_AUDIT_FILE):
        with SELF_AUDIT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line)
        try:
            os.chmod(SELF_AUDIT_FILE, 0o600)
        except OSError:
            pass


class ModelAdminHandler(SimpleHTTPRequestHandler):
    server_version = "ModelAdminPython/1.0"

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def log_message(self, format, *args):
        sanitized_args = tuple(redact_sensitive(str(arg)) for arg in args)
        super().log_message(format, *sanitized_args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if self.is_self_api_path(parsed.path):
            self.handle_self_api("GET", parsed)
            return
        if self.is_api_path(parsed.path):
            self.handle_api("GET", parsed)
            return
        if self.is_subscriptions_page(parsed.path):
            if not self.allow_subscriptions_page(parsed):
                self.respond_plain_error(404, "Not Found")
                return
            super().do_GET()
            return
        if self.is_forbidden_static(parsed.path):
            self.respond_plain_error(403, "Forbidden")
            return
        super().do_GET()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if self.is_self_api_path(parsed.path) or self.is_api_path(parsed.path):
            self.respond_plain_error(405, "Method Not Allowed", head_only=True)
            return
        if self.is_subscriptions_page(parsed.path):
            if not self.allow_subscriptions_page(parsed):
                self.respond_plain_error(404, "Not Found", head_only=True)
                return
            super().do_HEAD()
            return
        if self.is_forbidden_static(parsed.path):
            self.respond_plain_error(403, "Forbidden", head_only=True)
            return
        super().do_HEAD()

    def do_POST(self):
        parsed = urlparse(self.path)
        if self.is_self_api_path(parsed.path):
            self.handle_self_api("POST", parsed)
            return
        if self.is_api_path(parsed.path):
            self.handle_api("POST", parsed)
            return
        self.respond_plain_error(404, "Not Found")

    def is_api_path(self, path: str) -> bool:
        return path.rstrip("/") in {"/api", "/api.php"}

    def is_self_api_path(self, path: str) -> bool:
        return path.rstrip("/") == self_api_path()

    def is_subscriptions_page(self, path: str) -> bool:
        return Path(urlparse(path).path).name == "subscriptions.html"

    def allow_subscriptions_page(self, parsed) -> bool:
        params = parse_qs(parsed.query)
        user_id = params.get("user_id", [""])[0]
        token = params.get("token", [""])[0]
        endpoint = params.get("endpoint", params.get("api", [""]))[0]
        if not (user_id and token and endpoint):
            return False
        if not endpoint.startswith("/") or "://" in endpoint:
            return False
        try:
            parse_user_id(user_id)
        except ValueError:
            return False
        return 20 <= len(token) <= 4096

    def is_forbidden_static(self, path: str) -> bool:
        name = Path(urlparse(path).path).name
        return (
            name.startswith(".")
            or name in {"api.php", "server.py", "model-admin-config.php", "model-admin-config.json", "subscription-self-config.json"}
            or name.endswith(".env")
            or name.endswith(".log")
            or name.endswith(".lock")
            or name.endswith(".tmp")
            or name.endswith(".pyc")
        )

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self.respond({"ok": False, "message": "请求 JSON 格式不正确"}, 400)
            raise

    def respond_plain_error(self, status: int, message: str, head_only: bool = False):
        body = b"" if head_only else (message + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def respond(self, payload: dict, status: int = 200, extra_headers: Optional[dict] = None):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def get_cookie(self, name: str) -> str:
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        if name not in jar:
            return ""
        return jar[name].value

    def is_authenticated(self) -> bool:
        config = read_config()
        token = self.get_cookie(SESSION_COOKIE)
        return bool(config and token and verify_session_cookie(token, config))

    def require_login(self) -> bool:
        if not self.is_authenticated():
            self.respond({"ok": False, "message": "请先登录"}, 401)
            return False
        return True

    def set_session(self, config: dict):
        token = make_session_cookie(config)
        return {
            "Set-Cookie": (
                f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; "
                f"Max-Age={SESSION_TTL_SECONDS}"
            )
        }

    def clear_session(self):
        return {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"}

    def self_user_id(self) -> Optional[int]:
        config = read_self_config()
        secret = str(config.get("session_secret") or "")
        if not secret:
            return None
        payload = verify_signed_payload(self.get_cookie(SELF_SESSION_COOKIE), secret)
        if not payload:
            return None
        try:
            return int(payload.get("uid"))
        except Exception:
            return None

    def require_self_user(self) -> Optional[int]:
        user_id = self.self_user_id()
        if not user_id:
            self.respond({"ok": False, "message": "Not found"}, 404)
            return None
        return user_id

    def make_self_session_headers(self, user_id: int) -> dict:
        config = ensure_self_config()
        payload = {"uid": user_id, "exp": int(time.time()) + SELF_SESSION_TTL_SECONDS, "nonce": secrets.token_hex(8)}
        token = make_signed_payload(payload, str(config["session_secret"]))
        cookie = (
            f"{SELF_SESSION_COOKIE}={token}; Path={self_cookie_path()}; HttpOnly; SameSite=Lax; "
            f"Secure; Max-Age={SELF_SESSION_TTL_SECONDS}"
        )
        return {"Set-Cookie": cookie}

    def clear_self_session_headers(self) -> dict:
        return {"Set-Cookie": f"{SELF_SESSION_COOKIE}=; Path={self_cookie_path()}; HttpOnly; SameSite=Lax; Secure; Max-Age=0"}

    def client_identity(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        return self.client_address[0] if self.client_address else "unknown"

    def list_user_subscriptions(self, user_id: int) -> list:
        payload = sub2api_request(
            "GET",
            f"/admin/users/{user_id}/subscriptions?page=1&page_size=100",
            admin=True,
        )
        return extract_subscription_items(payload)

    def handle_self_api(self, method: str, parsed):
        action = parse_qs(parsed.query).get("action", [""])[0]
        try:
            if method == "GET" and action == "status":
                user_id = self.self_user_id()
                self.respond({
                    "ok": True,
                    "configured": sub2api_configured(),
                    "authenticated": bool(user_id),
                    "user_id": user_id,
                })
                return

            if method == "GET" and action == "subscriptions":
                user_id = self.require_self_user()
                if not user_id:
                    return
                items = [safe_subscription(item) for item in self.list_user_subscriptions(user_id)]
                self.respond({"ok": True, "subscriptions": items})
                return

            if method != "POST":
                self.respond({"ok": False, "message": "不支持的请求"}, 405)
                return

            body = self.read_json_body()
            identity = self.client_identity()

            if action == "start":
                if not check_rate_limit("self_start", identity, 30, 3600):
                    self.respond({"ok": False, "message": "请求过于频繁，请稍后再试"}, 429)
                    return
                if not sub2api_configured():
                    self.respond({"ok": False, "message": "自助撤销服务尚未配置"}, 503)
                    return
                user_id = parse_user_id(body.get("user_id"))
                token = str(body.get("token") or "").strip()
                if len(token) < 20 or len(token) > 4096:
                    self.respond({"ok": False, "message": "登录凭证无效，请从 Sub2API 用户中心重新打开"}, 401)
                    return
                me = sub2api_request("GET", sub2api_auth_me_path(), bearer_token=token)
                verified_user_id = find_user_id(me)
                if verified_user_id != user_id:
                    self.respond({"ok": False, "message": "用户身份校验失败"}, 403)
                    return
                write_self_audit("login", user_id, 0, identity)
                self.respond({"ok": True, "user_id": user_id}, extra_headers=self.make_self_session_headers(user_id))
                return

            if action == "cancel":
                if not check_rate_limit("self_cancel", identity, 12, 3600):
                    self.respond({"ok": False, "message": "撤销请求过于频繁，请稍后再试"}, 429)
                    return
                user_id = self.require_self_user()
                if not user_id:
                    return
                subscription_id = parse_user_id(body.get("subscription_id"))
                subscriptions = self.list_user_subscriptions(user_id)
                owned = None
                for item in subscriptions:
                    try:
                        if int(item.get("id")) == subscription_id:
                            owned = item
                            break
                    except Exception:
                        pass
                if not owned:
                    self.respond({"ok": False, "message": "没有找到属于当前用户的订阅"}, 404)
                    return
                if str(owned.get("status") or "").lower() in {"revoked", "expired", "cancelled", "canceled"}:
                    self.respond({"ok": False, "message": "该订阅已经不可撤销"}, 409)
                    return
                sub2api_request("DELETE", f"/admin/subscriptions/{subscription_id}", admin=True)
                write_self_audit("cancel", user_id, subscription_id, identity)
                items = [safe_subscription(item) for item in self.list_user_subscriptions(user_id)]
                self.respond({"ok": True, "message": "订阅已撤销", "subscriptions": items})
                return

            if action == "logout":
                self.respond({"ok": True, "message": "已退出"}, extra_headers=self.clear_self_session_headers())
                return

            self.respond({"ok": False, "message": "未知操作"}, 404)
        except json.JSONDecodeError:
            return
        except ValueError as exc:
            self.respond({"ok": False, "message": str(exc)}, 422)
        except RuntimeError as exc:
            self.respond({"ok": False, "message": str(exc)}, 502)
        except Exception:
            self.respond({"ok": False, "message": "服务暂时不可用"}, 500)

    def handle_api(self, method: str, parsed):
        action = parse_qs(parsed.query).get("action", [""])[0]
        try:
            if method == "GET" and action == "status":
                configured = CONFIG_FILE.exists()
                self.respond({
                    "ok": True,
                    "configured": configured,
                    "authenticated": self.is_authenticated(),
                    "canWriteModels": os.access(MODELS_FILE, os.W_OK) or (not MODELS_FILE.exists() and os.access(BASE_DIR, os.W_OK)),
                    "canWriteConfig": os.access(CONFIG_FILE, os.W_OK) if CONFIG_FILE.exists() else os.access(BASE_DIR, os.W_OK),
                })
                return

            if method == "GET" and action == "load":
                if not MODELS_FILE.exists():
                    self.respond({"ok": True, "catalog": default_catalog()})
                    return
                with MODELS_FILE.open("r", encoding="utf-8") as fh:
                    self.respond({"ok": True, "catalog": json.load(fh)})
                return

            if method != "POST":
                self.respond({"ok": False, "message": "不支持的请求"}, 405)
                return

            body = self.read_json_body()

            if action == "setup":
                if CONFIG_FILE.exists():
                    self.respond({"ok": False, "message": "管理员密码已经设置"}, 409)
                    return
                password = str(body.get("password") or "")
                if len(password) < 8:
                    self.respond({"ok": False, "message": "密码至少 8 位"}, 422)
                    return
                salt = secrets.token_hex(16)
                config = {
                    "password_salt": salt,
                    "password_hash": password_hash(password, salt),
                    "session_secret": secrets.token_hex(32),
                }
                write_config(config)
                self.respond({"ok": True, "message": "管理员密码已设置"}, extra_headers=self.set_session(config))
                return

            if action == "login":
                config = read_config()
                if not config:
                    self.respond({"ok": False, "message": "请先设置管理员密码"}, 428)
                    return
                if not verify_password(str(body.get("password") or ""), config):
                    self.respond({"ok": False, "message": "密码不正确"}, 401)
                    return
                self.respond({"ok": True, "message": "登录成功"}, extra_headers=self.set_session(config))
                return

            if action == "logout":
                self.respond({"ok": True, "message": "已退出"}, extra_headers=self.clear_session())
                return

            if action == "save":
                if not self.require_login():
                    return
                catalog = normalize_catalog(body.get("catalog") or {})
                atomic_write_text(MODELS_FILE, json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
                self.respond({"ok": True, "message": "保存成功", "catalog": catalog})
                return

            self.respond({"ok": False, "message": "未知操作"}, 404)
        except json.JSONDecodeError:
            return
        except ValueError as exc:
            self.respond({"ok": False, "message": str(exc)}, 422)
        except Exception as exc:
            self.respond({"ok": False, "message": str(exc)}, 500)


def main():
    parser = argparse.ArgumentParser(description="Run the model list admin site.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()

    os.chdir(str(BASE_DIR))
    mimetypes.add_type("application/json; charset=utf-8", ".json")
    server = ThreadingHTTPServer((args.host, args.port), ModelAdminHandler)
    print(f"Model admin server running at http://{args.host}:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
