# live.py
import os
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

FRAMES = {}
AUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "live_audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

def attach(handler_cls):
    orig_get = handler_cls.do_GET
    orig_post = handler_cls.do_POST

    def do_get(self):
        p = urlparse(self.path)
        if p.path == "/live/frame":
            if not self.check_auth():
                return self.send_resp(HTTPStatus.UNAUTHORIZED, b'{"error":"unauth"}\n', "application/json")
            dev = parse_qs(p.query).get("dev", ["default"])[0]
            buf = FRAMES.get(dev)
            if not buf:
                return self.send_resp(HTTPStatus.NO_CONTENT, b"")
            return self.send_resp(HTTPStatus.OK, buf, "image/jpeg")
        return orig_get(self)

    def do_post(self):
        p = urlparse(self.path)
        if p.path in ("/live/frame", "/live/audio"):
            if not self.check_auth():
                return self.send_resp(HTTPStatus.UNAUTHORIZED, b'{"error":"unauth"}\n', "application/json")
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            dev = self.headers.get("X-Device-Id", "default").strip() or "default"
            if p.path == "/live/frame":
                FRAMES[dev] = body
                return self.send_resp(HTTPStatus.OK, b'{"status":"ok"}\n', "application/json")
            with open(os.path.join(AUDIO_DIR, f"{dev}.m4a"), "ab") as f:
                f.write(body)
            return self.send_resp(HTTPStatus.OK, b'{"status":"ok"}\n', "application/json")
        return orig_post(self)

    handler_cls.do_GET = do_get
    handler_cls.do_POST = do_post
