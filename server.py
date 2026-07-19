import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass


SITE_DIR = Path(__file__).resolve().parent
MEDIA_DIR = SITE_DIR.parent
THUMB_DIR = SITE_DIR / "thumbs"
DATA_DIR = SITE_DIR / "data"
DB_PATH = DATA_DIR / "lanshi_store.db"
SESSION_COOKIE = "lanshi_session"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".mpg", ".mpeg"}

PRICE_CENTS = 100
PAYMENT_MODE = os.environ.get("WECHAT_PAY_MODE", "manual").lower()
PAY_IMAGE_FILE = os.environ.get("WECHAT_PAY_IMAGE", "pay.jpg")
ADMIN_TOKEN = os.environ.get("LANSHI_ADMIN_TOKEN", "lanshi-local-admin")
WECHAT_API_HOST = os.environ.get("WECHAT_API_HOST", "https://api.mch.weixin.qq.com")
WECHAT_APPID = os.environ.get("WECHAT_APPID", "")
WECHAT_MCHID = os.environ.get("WECHAT_MCHID", "")
WECHAT_SERIAL_NO = os.environ.get("WECHAT_SERIAL_NO", "")
WECHAT_PRIVATE_KEY_PATH = os.environ.get("WECHAT_PRIVATE_KEY_PATH", "")
WECHAT_NOTIFY_URL = os.environ.get("WECHAT_NOTIFY_URL", "")


def find_binary(name, known_paths=None):
    found = shutil.which(name)
    if found:
        return found
    for path in known_paths or []:
        if path and Path(path).exists():
            return str(path)
    return None


FFMPEG = find_binary("ffmpeg", [r"E:\Software\data\ChimeraX\ChimeraX\bin\ffmpeg.exe"])
OPENSSL = find_binary("openssl", [r"E:\Software\data\Anaconda\openssl.exe"])


def now():
    return int(time.time())


def normalize_spaces(value):
    return re.sub(r"\s+", " ", value).strip()


def video_id(file_name):
    return hashlib.sha1(file_name.encode("utf-8", "ignore")).hexdigest()[:16]


def clean_title(stem):
    value = stem.replace("_", " ").replace("+", " ")
    value = re.sub(r"\b20\d{10,14}\b", "", value)
    value = re.sub(r"(?i)A{3,}\b", "", value)
    value = normalize_spaces(value).strip(" -_.")
    return value or stem


def infer_series(title):
    patterns = [
        "Black Bird",
        "Darkwing",
        "Dark Wondra",
        "DarkWondra",
        "Dark Canary",
        "Dark Widow",
        "Catwarrior",
        "Supernova Prime",
        "Supernova",
        "Ultrawoman",
        "White Angel",
        "WhiteAngel",
        "Wondra",
        "Wonderkick",
        "TeenBat",
        "Teenwing",
        "TeenWing",
        "Sexy Spies",
        "Scotland Yard",
        "SYCC",
        "UKSG",
        "Athena",
        "Spider-Warrior",
        "Spider Warrior",
        "Stellar",
        "The Amazon",
    ]
    lower = title.lower()
    for pattern in patterns:
        if pattern.lower() in lower:
            return pattern.replace("DarkWondra", "Dark Wondra").replace("WhiteAngel", "White Angel")
    return title.split(" ")[0] if title else "Other"


def size_label(size):
    if size >= 1024 ** 3:
        return "%.1f GB" % (size / 1024 ** 3)
    return "%.0f MB" % (size / 1024 ** 2)


def price_label(cents):
    return "¥%.2f" % (cents / 100)


def payment_image_path():
    configured = Path(PAY_IMAGE_FILE)
    candidates = [configured] if configured.is_absolute() else [SITE_DIR / configured, MEDIA_DIR / configured]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def payment_image_url():
    return "/pay.jpg" if payment_image_path() else None


def db_connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                series TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime INTEGER NOT NULL,
                ext TEXT NOT NULL,
                thumb TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                price_cents INTEGER NOT NULL DEFAULT 100
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                status TEXT NOT NULL,
                payment_mode TEXT NOT NULL,
                code_url TEXT,
                created_at INTEGER NOT NULL,
                paid_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at INTEGER NOT NULL,
                body TEXT NOT NULL
            )
            """
        )


def scan_videos():
    videos = []
    for path in MEDIA_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        stat = path.stat()
        title = clean_title(path.stem)
        vid = video_id(path.name)
        videos.append(
            {
                "id": vid,
                "file_name": path.name,
                "title": title,
                "series": infer_series(title),
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "ext": path.suffix.lower(),
                "thumb": "/thumbs/%s.jpg" % vid,
                "price_cents": PRICE_CENTS,
            }
        )
    videos.sort(key=lambda item: (item["series"].lower(), item["title"].lower()))
    return videos


def sync_videos():
    current = scan_videos()
    ids = set(item["id"] for item in current)
    with db_connect() as conn:
        for item in current:
            params = (
                item["file_name"],
                item["title"],
                item["series"],
                item["size"],
                item["mtime"],
                item["ext"],
                item["thumb"],
                item["price_cents"],
                item["id"],
            )
            updated = conn.execute(
                """
                UPDATE videos SET
                    file_name=?,
                    title=?,
                    series=?,
                    size=?,
                    mtime=?,
                    ext=?,
                    thumb=?,
                    active=1,
                    price_cents=?
                WHERE id=?
                """,
                params,
            )
            if updated.rowcount:
                continue
            conn.execute(
                """
                INSERT INTO videos (
                    id, file_name, title, series, size, mtime, ext, thumb, active, price_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    item["id"],
                    item["file_name"],
                    item["title"],
                    item["series"],
                    item["size"],
                    item["mtime"],
                    item["ext"],
                    item["thumb"],
                    item["price_cents"],
                ),
            )
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute("UPDATE videos SET active=0 WHERE id NOT IN (%s)" % placeholders, tuple(ids))
        else:
            conn.execute("UPDATE videos SET active=0")


def video_path(row):
    path = MEDIA_DIR / row["file_name"]
    try:
        resolved = path.resolve()
        media_root = MEDIA_DIR.resolve()
    except OSError:
        return None
    if not str(resolved).startswith(str(media_root)) or not resolved.exists():
        return None
    return resolved


def ensure_thumbnail(video_row):
    thumb = THUMB_DIR / ("%s.jpg" % video_row["id"])
    if thumb.exists() and thumb.stat().st_size > 0:
        return thumb
    path = video_path(video_row)
    if not path or not FFMPEG:
        return None
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = thumb.with_suffix(".tmp.jpg")
    for timestamp in ("00:00:08", "00:00:02"):
        cmd = [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            timestamp,
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-1",
            "-q:v",
            "5",
            str(tmp),
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
            if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
                tmp.replace(thumb)
                return thumb
        except Exception:
            pass
        if tmp.exists():
            tmp.unlink()
    return None


def get_session(handler):
    cookies = SimpleCookie(handler.headers.get("Cookie"))
    cookie = cookies.get(SESSION_COOKIE)
    if cookie and re.match(r"^[A-Za-z0-9_-]{24,}$", cookie.value):
        return cookie.value, None
    sid = secrets.token_urlsafe(24)
    header = "%s=%s; Path=/; SameSite=Lax; HttpOnly" % (SESSION_COOKIE, sid)
    return sid, header


def parse_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if not length:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def encode_json(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def row_to_video(row, purchased):
    return {
        "id": row["id"],
        "title": row["title"],
        "fileName": row["file_name"],
        "series": row["series"],
        "size": row["size"],
        "sizeLabel": size_label(row["size"]),
        "updatedAt": row["mtime"],
        "ext": row["ext"],
        "thumb": row["thumb"],
        "priceCents": row["price_cents"],
        "priceLabel": price_label(row["price_cents"]),
        "purchased": bool(purchased),
        "downloadUrl": "/api/videos/%s/download" % row["id"] if purchased else None,
    }


def purchased_video_ids(session_id):
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT video_id FROM orders WHERE session_id=? AND status='paid'",
            (session_id,),
        ).fetchall()
    return set(row["video_id"] for row in rows)


def video_by_id(video_id_value):
    with db_connect() as conn:
        return conn.execute("SELECT * FROM videos WHERE id=? AND active=1", (video_id_value,)).fetchone()


def admin_authorized(handler, parsed=None):
    token = handler.headers.get("X-Admin-Token", "")
    if not token and parsed is not None:
        token = parse_qs(parsed.query).get("token", [""])[0]
    return secrets.compare_digest(token, ADMIN_TOKEN)


def admin_order_payload(row):
    return {
        "orderId": row["id"],
        "videoId": row["video_id"],
        "title": row["title"],
        "fileName": row["file_name"],
        "amountCents": row["amount_cents"],
        "amountLabel": price_label(row["amount_cents"]),
        "status": row["status"],
        "paymentMode": row["payment_mode"],
        "createdAt": row["created_at"],
        "paidAt": row["paid_at"],
    }


def wechat_configured():
    return all([WECHAT_APPID, WECHAT_MCHID, WECHAT_SERIAL_NO, WECHAT_PRIVATE_KEY_PATH, WECHAT_NOTIFY_URL, OPENSSL])


def sign_wechat_message(message):
    if not OPENSSL:
        raise RuntimeError("OpenSSL is required for WeChat Pay signing")
    private_key = Path(WECHAT_PRIVATE_KEY_PATH)
    if not private_key.exists():
        raise RuntimeError("WECHAT_PRIVATE_KEY_PATH does not exist")
    with tempfile.NamedTemporaryFile("wb", delete=False) as msg_file:
        msg_file.write(message.encode("utf-8"))
        msg_path = msg_file.name
    try:
        result = subprocess.run(
            [OPENSSL, "dgst", "-sha256", "-sign", str(private_key), msg_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", "ignore"))
        return base64.b64encode(result.stdout).decode("ascii")
    finally:
        try:
            os.unlink(msg_path)
        except OSError:
            pass


def create_wechat_native_order(order_id, video_title, amount_cents):
    if not wechat_configured():
        raise RuntimeError("WeChat Pay is not configured. Use WECHAT_PAY_MODE=manual for local QR-code testing.")
    path = "/v3/pay/transactions/native"
    url = WECHAT_API_HOST.rstrip("/") + path
    payload = {
        "appid": WECHAT_APPID,
        "mchid": WECHAT_MCHID,
        "description": video_title[:120],
        "out_trade_no": order_id,
        "notify_url": WECHAT_NOTIFY_URL,
        "amount": {"total": amount_cents, "currency": "CNY"},
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(now())
    nonce = secrets.token_hex(16)
    message = "POST\n%s\n%s\n%s\n%s\n" % (path, timestamp, nonce, body)
    signature = sign_wechat_message(message)
    auth = (
        'WECHATPAY2-SHA256-RSA2048 mchid="%s",nonce_str="%s",signature="%s",'
        'timestamp="%s",serial_no="%s"'
    ) % (WECHAT_MCHID, nonce, signature, timestamp, WECHAT_SERIAL_NO)
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": auth,
            "User-Agent": "LanshiStore/1.0",
        },
        method="POST",
    )
    context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError("WeChat Pay request failed: %s" % detail)
    code_url = data.get("code_url")
    if not code_url:
        raise RuntimeError("WeChat Pay did not return code_url")
    return code_url


class StoreHandler(SimpleHTTPRequestHandler):
    server_version = "LanshiStore/0.2"

    def translate_path(self, path):
        parsed = urlparse(path)
        requested = unquote(parsed.path.lstrip("/"))
        if not requested:
            requested = "index.html"
        return str(SITE_DIR / requested)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def send_json(self, payload, status=HTTPStatus.OK, set_cookie=None):
        body = encode_json(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/pay.jpg":
            self.handle_pay_image()
            return
        if path == "/api/config":
            self.handle_config()
            return
        if path == "/api/videos":
            self.handle_videos()
            return
        if path == "/api/purchases":
            self.handle_purchases()
            return
        if path == "/api/admin/orders":
            self.handle_admin_orders(parsed)
            return
        if path.startswith("/api/orders/"):
            self.handle_order_status(path)
            return
        if path.startswith("/api/videos/") and path.endswith("/download"):
            self.handle_download(path)
            return
        if path.startswith("/thumbs/"):
            self.handle_thumbnail(path)
            return
        super().do_GET()

    def do_HEAD(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/pay.jpg":
            self.handle_pay_image(head_only=True)
            return
        if path.startswith("/api/videos/") and path.endswith("/download"):
            self.handle_download(path, head_only=True)
            return
        super().do_HEAD()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/orders":
            self.handle_create_order()
            return
        if path.startswith("/api/orders/") and path.endswith("/mock-pay"):
            self.handle_confirm_paid(path)
            return
        if path.startswith("/api/orders/") and path.endswith("/confirm-paid"):
            self.handle_confirm_paid(path)
            return
        if path.startswith("/api/admin/orders/") and path.endswith("/confirm"):
            self.handle_admin_confirm_order(path, parsed)
            return
        if path == "/api/wechat/notify":
            self.handle_wechat_notify()
            return
        if path == "/api/refresh":
            sync_videos()
            self.send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_config(self):
        self.send_json(
            {
                "priceCents": PRICE_CENTS,
                "priceLabel": price_label(PRICE_CENTS),
                "paymentMode": PAYMENT_MODE,
                "wechatConfigured": wechat_configured(),
                "manualPayImage": payment_image_url(),
                "manualPayReady": bool(payment_image_url()),
                "manualConfirmByAdmin": PAYMENT_MODE == "manual",
                "downloadAfterPurchase": True,
            }
        )

    def handle_videos(self):
        session_id, cookie = get_session(self)
        purchased = purchased_video_ids(session_id)
        with db_connect() as conn:
            rows = conn.execute("SELECT * FROM videos WHERE active=1 ORDER BY series, title").fetchall()
        videos = [row_to_video(row, row["id"] in purchased) for row in rows]
        self.send_json({"videos": videos, "total": len(videos), "priceLabel": price_label(PRICE_CENTS)}, set_cookie=cookie)

    def handle_purchases(self):
        session_id, cookie = get_session(self)
        with db_connect() as conn:
            rows = conn.execute(
                """
                SELECT orders.*, videos.title, videos.file_name
                FROM orders JOIN videos ON orders.video_id=videos.id
                WHERE orders.session_id=? AND orders.status='paid'
                ORDER BY orders.paid_at DESC
                """,
                (session_id,),
            ).fetchall()
        purchases = [
            {
                "orderId": row["id"],
                "videoId": row["video_id"],
                "title": row["title"],
                "fileName": row["file_name"],
                "paidAt": row["paid_at"],
                "downloadUrl": "/api/videos/%s/download" % row["video_id"],
            }
            for row in rows
        ]
        self.send_json({"purchases": purchases}, set_cookie=cookie)

    def handle_order_status(self, path):
        order_id = path.strip("/").split("/")[2]
        session_id, cookie = get_session(self)
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            self.send_json({"error": "订单不存在"}, HTTPStatus.NOT_FOUND, cookie)
            return
        if row["session_id"] != session_id:
            self.send_json({"error": "订单不属于当前浏览器"}, HTTPStatus.FORBIDDEN, cookie)
            return
        self.send_json(
            {
                "orderId": row["id"],
                "videoId": row["video_id"],
                "status": row["status"],
                "amountCents": row["amount_cents"],
                "amountLabel": price_label(row["amount_cents"]),
                "paidAt": row["paid_at"],
            },
            set_cookie=cookie,
        )

    def handle_create_order(self):
        session_id, cookie = get_session(self)
        try:
            body = parse_json(self)
        except Exception:
            self.send_json({"error": "请求内容不是有效 JSON"}, HTTPStatus.BAD_REQUEST, cookie)
            return
        vid = body.get("videoId")
        row = video_by_id(vid)
        if not row:
            self.send_json({"error": "视频不存在"}, HTTPStatus.NOT_FOUND, cookie)
            return
        amount = PRICE_CENTS
        order_id = "LS%s%s" % (time.strftime("%Y%m%d%H%M%S"), secrets.token_hex(4).upper())
        mode = PAYMENT_MODE
        try:
            if mode == "wechat":
                code_url = create_wechat_native_order(order_id, row["title"], amount)
            elif mode == "manual":
                code_url = payment_image_url()
                if not code_url:
                    raise RuntimeError("未找到微信收款码。请把 pay.jpg 放在 Lanshi 文件夹或视频素材目录。")
            else:
                code_url = "weixin://wxpay/bizpayurl?pr=lanshi-demo-%s" % order_id
                mode = "mock"
        except Exception as exc:
            self.send_json({"error": "微信支付下单失败", "detail": str(exc)}, HTTPStatus.BAD_GATEWAY, cookie)
            return
        with db_connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (id, video_id, session_id, amount_cents, status, payment_mode, code_url, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                """,
                (order_id, row["id"], session_id, amount, mode, code_url, now()),
            )
        self.send_json(
            {
                "orderId": order_id,
                "videoId": row["id"],
                "title": row["title"],
                "amountCents": amount,
                "amountLabel": price_label(amount),
                "status": "pending",
                "paymentMode": mode,
                "codeUrl": code_url,
            },
            HTTPStatus.CREATED,
            cookie,
        )

    def handle_admin_orders(self, parsed):
        if not admin_authorized(self, parsed):
            self.send_json({"error": "卖家确认码不正确"}, HTTPStatus.UNAUTHORIZED)
            return
        query = parse_qs(parsed.query)
        status = query.get("status", [""])[0]
        params = []
        where = ""
        if status in ("pending", "paid"):
            where = "WHERE orders.status=?"
            params.append(status)
        with db_connect() as conn:
            rows = conn.execute(
                """
                SELECT orders.*, videos.title, videos.file_name
                FROM orders JOIN videos ON orders.video_id=videos.id
                %s
                ORDER BY orders.created_at DESC
                LIMIT 200
                """
                % where,
                params,
            ).fetchall()
        self.send_json({"orders": [admin_order_payload(row) for row in rows]})

    def handle_admin_confirm_order(self, path, parsed):
        if not admin_authorized(self, parsed):
            self.send_json({"error": "卖家确认码不正确"}, HTTPStatus.UNAUTHORIZED)
            return
        order_id = path.strip("/").split("/")[3]
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                self.send_json({"error": "订单不存在"}, HTTPStatus.NOT_FOUND)
                return
            conn.execute("UPDATE orders SET status='paid', paid_at=? WHERE id=?", (now(), order_id))
        self.send_json({"ok": True, "orderId": order_id, "videoId": row["video_id"], "status": "paid"})

    def handle_confirm_paid(self, path):
        if PAYMENT_MODE not in ("mock", "wechat-mock"):
            self.send_json({"error": "收款确认请在卖家后台完成"}, HTTPStatus.FORBIDDEN)
            return
        order_id = path.strip("/").split("/")[2]
        session_id, cookie = get_session(self)
        with db_connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                self.send_json({"error": "订单不存在"}, HTTPStatus.NOT_FOUND, cookie)
                return
            if row["session_id"] != session_id:
                self.send_json({"error": "订单不属于当前浏览器"}, HTTPStatus.FORBIDDEN, cookie)
                return
            conn.execute("UPDATE orders SET status='paid', paid_at=? WHERE id=?", (now(), order_id))
        self.send_json({"ok": True, "orderId": order_id, "videoId": row["video_id"], "status": "paid"}, set_cookie=cookie)

    def handle_wechat_notify(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", "ignore") if length else ""
        with db_connect() as conn:
            conn.execute("INSERT INTO notifications (received_at, body) VALUES (?, ?)", (now(), body))
        # Full WeChat v3 callback verification/decryption should be added before production.
        self.send_json({"code": "SUCCESS", "message": "stored"})

    def handle_pay_image(self, head_only=False):
        image = payment_image_path()
        if not image:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(image))[0] or "image/jpeg"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(image.stat().st_size))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        if head_only:
            return
        with image.open("rb") as file:
            shutil.copyfileobj(file, self.wfile)

    def handle_download(self, path, head_only=False):
        parts = path.strip("/").split("/")
        vid = parts[2]
        session_id, cookie = get_session(self)
        purchased = vid in purchased_video_ids(session_id)
        if not purchased:
            self.send_json({"error": "请先完成微信支付购买"}, HTTPStatus.PAYMENT_REQUIRED, cookie)
            return
        row = video_by_id(vid)
        if not row:
            self.send_json({"error": "视频不存在"}, HTTPStatus.NOT_FOUND, cookie)
            return
        path_obj = video_path(row)
        if not path_obj:
            self.send_json({"error": "视频文件不存在"}, HTTPStatus.NOT_FOUND, cookie)
            return
        file_size = path_obj.stat().st_size
        content_type = mimetypes.guess_type(str(path_obj))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % row["file_name"].replace('"', ""))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if head_only:
            return
        with path_obj.open("rb") as file:
            shutil.copyfileobj(file, self.wfile, length=1024 * 1024)

    def handle_thumbnail(self, path):
        vid = Path(path).stem
        row = video_by_id(vid)
        if not row:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        thumb = ensure_thumbnail(row)
        if not thumb:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(thumb.stat().st_size))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        with thumb.open("rb") as file:
            shutil.copyfileobj(file, self.wfile)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))


def choose_server():
    base_port = int(os.environ.get("PORT", "8000"))
    for port in range(base_port, base_port + 50):
        try:
            return ThreadingHTTPServer(("127.0.0.1", port), StoreHandler)
        except OSError:
            continue
    raise RuntimeError("No available port found")


def main():
    init_db()
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    sync_videos()
    server = choose_server()
    host, port = server.server_address
    print("Lanshi store ready: http://%s:%s" % (host, port), flush=True)
    print("Payment mode: %s, price: %s" % (PAYMENT_MODE, price_label(PRICE_CENTS)), flush=True)
    print("Video source: %s" % MEDIA_DIR, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
