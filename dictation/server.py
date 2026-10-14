import hmac
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CACHE = Path.home() / '.cache/oma-speak'
CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
TOKEN = secrets.token_urlsafe(32)
PORT = 18763
ORIGIN = f'http://127.0.0.1:{PORT}'
PAGE_PATH = Path(__file__).with_name('index.html')
LANG_PATH = Path.home() / '.config/omalauncher/voice-ui-language'
LANGUAGES = ('en', 'zh', 'es', 'de', 'fr', 'ja', 'ko')

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
            value = LANG_PATH.read_text().strip() if LANG_PATH.exists() else ''
            return self.reply(200, value if value in LANGUAGES else LANGUAGES[0])
        if self.path == '/health':
            return self.reply(200, 'oma-speak-v1')
        if self.path == '/target':
            if not hmac.compare_digest(self.headers.get('X-Speak-Token', ''), TOKEN):
                return self.reply(403, 'Forbidden')
            try:
                current = json.loads((Path.home()/'.cache/oma-voice/state.json').read_text())
            except (OSError, ValueError):
                current = {}
            target = {'source': current.get('source', 'codex'),
                      'source_name': str(current.get('source_name', 'Terminal'))[:80]}
            return self.reply(200, json.dumps(target, ensure_ascii=False), 'application/json; charset=utf-8')
        if self.path == '/refine-status':
            if not hmac.compare_digest(self.headers.get('X-Speak-Token', ''), TOKEN):
                return self.reply(403, 'Forbidden')
            try:
                value = json.loads((CACHE/'refine-status.json').read_text())
            except (OSError, ValueError):
                value = {'phase': 'idle'}
            if value.get('phase') == 'ready':
                try:
                    raw = (CACHE/'latest.txt').read_text().strip()
                    if hashlib.sha256(raw.encode()).hexdigest() != value.get('source_hash'):
                        value = {'phase': 'idle'}
                    else:
                        value['text'] = (CACHE/'refined.txt').read_text()
                except OSError:
                    value = {'phase': 'idle'}
            return self.reply(200, json.dumps(value, ensure_ascii=False), 'application/json; charset=utf-8')
        if self.path != '/':
            return self.reply(404, 'Not found')
        self.reply(200, PAGE_PATH.read_text(), 'text/html; charset=utf-8')

    def do_POST(self):
        if (self.path not in ('/text', '/language', '/refine', '/send') or self.headers.get('Origin') != ORIGIN
                or not hmac.compare_digest(self.headers.get('X-Speak-Token', ''), TOKEN)):
            return self.reply(403, 'Forbidden')
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 65536:
                return self.reply(413, 'Text too long')
            body = json.loads(self.rfile.read(size))
            if self.path == '/language':
                value = body.get('language')
                if value not in LANGUAGES:
                    raise ValueError()
                LANG_PATH.parent.mkdir(parents=True, exist_ok=True)
                temp = LANG_PATH.with_name(LANG_PATH.name+'.tmp')
                temp.write_text(value)
                os.chmod(temp, 0o600)
                temp.replace(LANG_PATH)
                return self.reply(200, 'Language saved')
            if self.path == '/send':
                version = body.get('version')
                if version not in ('original', 'refined'):
                    raise ValueError()
                command = [sys.executable, str(Path.home()/'.local/bin/oma-send-dictation')]
                if version == 'refined':
                    command.append('--refined')
                result = subprocess.run(command, capture_output=True, text=True, timeout=28)
                output = json.loads(result.stdout.splitlines()[-1])
                code = 200 if output.get('ok') is True else 400
                return self.reply(code, json.dumps(output, ensure_ascii=False), 'application/json; charset=utf-8')
            text = body['text']
            if not isinstance(text, str) or len(text) > 16000:
                raise ValueError()
            # Keep terminal escape/control sequences out of Bash insertion.
            text = ''.join(c for c in text if c >= ' ' and c != '\x7f').strip()
            if not text:
                raise ValueError()
            try:
                previous = (CACHE/'latest.txt').read_text()
            except OSError:
                previous = None
            tmp = CACHE / 'latest.tmp'
            tmp.write_text(text)
            os.chmod(tmp, 0o600)
            tmp.replace(CACHE / 'latest.txt')
            status = CACHE / 'send-status.json'
            status_tmp = CACHE / 'send-status.tmp'
            status_tmp.write_text(json.dumps({'phase': 'saved'}))
            os.chmod(status_tmp, 0o600)
            status_tmp.replace(status)
            if self.path == '/refine' or previous != text:
                (CACHE/'refined.txt').unlink(missing_ok=True)
                (CACHE/'refine-status.json').unlink(missing_ok=True)
            if self.path == '/refine':
                subprocess.run([sys.executable, str(Path.home()/'.local/bin/oma-refine-dictation'), '--start'],
                               check=True, timeout=5)
                return self.reply(200, json.dumps({'phase': 'refining'}), 'application/json; charset=utf-8')
            self.reply(200, 'Saved. Return to the launcher and tap Send to target.')
        except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
            self.reply(400, 'Invalid text')
        except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            self.reply(503, 'Action unavailable')

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    server.daemon_threads = True
    tokenfile = CACHE / 'token'
    tokenfile.write_text(TOKEN)
    os.chmod(tokenfile, 0o600)
    server.serve_forever()
