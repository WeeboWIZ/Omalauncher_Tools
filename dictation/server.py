import hmac
import json
import os
from pathlib import Path
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CACHE = Path.home() / '.cache/oma-speak'
CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
TOKEN = secrets.token_urlsafe(32)
PORT = 18763
ORIGIN = f'http://127.0.0.1:{PORT}'
PAGE_PATH = Path(__file__).with_name('index.html')
LANG_PATH = Path.home() / '.config/omalauncher/voice-ui-language'

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, data, kind='text/plain; charset=utf-8'):
        data = data.encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{PORT}':
            return self.reply(403, 'Invalid host')
        if self.path == '/language':
            return self.reply(200, 'zh' if LANG_PATH.exists() and LANG_PATH.read_text().strip() == 'zh' else 'en')
        if self.path == '/health':
            return self.reply(200, 'oma-speak-v1')
        if self.path != '/':
            return self.reply(404, 'Not found')
        self.reply(200, PAGE_PATH.read_text(), 'text/html; charset=utf-8')

    def do_POST(self):
        if (self.path not in ('/text', '/language') or self.headers.get('Origin') != ORIGIN
                or not hmac.compare_digest(self.headers.get('X-Speak-Token', ''), TOKEN)):
            return self.reply(403, 'Forbidden')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                return self.reply(413, 'Text too long')
            body = json.loads(self.rfile.read(size))
            if self.path == '/language':
                value = body.get('language')
                if value not in ('zh', 'en'):
                    raise ValueError()
                LANG_PATH.parent.mkdir(parents=True, exist_ok=True)
                temp = LANG_PATH.with_name(LANG_PATH.name+'.tmp')
                temp.write_text(value)
                os.chmod(temp, 0o600)
                temp.replace(LANG_PATH)
                return self.reply(200, 'Language saved')
            text = body['text']
            if not isinstance(text, str) or len(text) > 16000:
                raise ValueError()
            # Keep terminal escape/control sequences out of Bash insertion.
            text = ''.join(c for c in text if c >= ' ' and c != '\x7f').strip()
            tmp = CACHE / 'latest.tmp'
            tmp.write_text(text)
            os.chmod(tmp, 0o600)
            tmp.replace(CACHE / 'latest.txt')
            self.reply(200, 'Saved. Return to the launcher and tap Send to target.')
        except (ValueError, KeyError, TypeError, UnicodeError):
            self.reply(400, 'Invalid text')

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    server.daemon_threads = True
    tokenfile = CACHE / 'token'
    tokenfile.write_text(TOKEN)
    os.chmod(tokenfile, 0o600)
    server.serve_forever()
