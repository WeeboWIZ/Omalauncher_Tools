#!/usr/bin/env python3
'''Voice reader and dictation bridge for Codex logs or a tmux terminal.'''
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from language import CHOICE, LANGUAGES, SPOKEN, chosen, local, spoken


def english(text):
    return local(text, 'en')


HOME = Path.home()
CACHE = HOME / '.cache/oma-voice'
SOCKET = CACHE / 'control.sock'
CONFIG = HOME / '.config/omalauncher/voice.json'
SESSIONS = HOME / '.codex/sessions'
TMUX_SESSION = 'oma-voice'
# ensure() touches this. The service quits once neither it nor the Codex log has changed
# for the 'pause_minutes' setting (0 = never), and ensure() starts it again.
ALIVE = CACHE / 'alive'
PAUSE_MINUTES = 10
# Seconds between looks for a Codex session or tmux pane while there is none.
RETRY = 15


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(path)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def chinese(text):
    return any('㐀' <= c <= '鿿' for c in text)


def clean_text(text):
    # Spoken notes are in the language of the reply, or the wrong voice would be picked for it.
    notes = SPOKEN[spoken(text)]
    text = re.sub(r'```.*?```', notes[2], text, flags=re.S)
    text = re.sub(r'!?\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', notes[3], text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)', '', text)
    text = text.replace('`', '').replace('**', '').replace('__', '')
    return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127)).strip()


def summarize(text, limit=360):
    '''Extract sentences verbatim; retain an explicit failure/limitation if present.'''
    text = clean_text(text)
    if len(text) <= limit:
        return text
    sentences = [s.strip() for s in re.split(r'(?<=[。！？.!?])\s*|\n+', text) if s.strip()]
    selected = []
    important = re.compile(r'未完成|尚未|無法|不能|失敗|限制|需要你|待.*確認|未.*驗證|未.*測試|not tested|failed|unable|cannot|limitation', re.I)
    warning = next((s for s in sentences if important.search(s)), '')
    # Reserve room for a caveat even when it appears at the end of a long answer.
    budget = limit - min(len(warning), limit // 2) - (8 if warning else 0)
    used = 0
    for s in sentences:
        if s == warning:
            continue
        if used + len(s) > budget:
            if not selected:
                selected.append(s[:budget].rstrip() + '…')
            break
        selected.append(s)
        used += len(s) + 1
    if warning:
        selected.append(warning[:limit // 2])
    notes = SPOKEN[spoken(text)]
    return notes[0] + ' '.join(selected) + notes[1]


def completed_reply(event):
    '''Ignore commentary, tool output, subagent logs and aborted turns.'''
    if event.get('type') != 'event_msg':
        return None
    payload = event.get('payload', {})
    if payload.get('type') != 'task_complete':
        return None
    text = payload.get('last_agent_message')
    if not isinstance(text, str) or not text.strip():
        return None
    return payload.get('turn_id') or payload.get('root_turn_id') or event.get('timestamp'), text


def find_session(thread):
    # Session IDs are data, never shell expressions or path components.
    thread = str(uuid.UUID(thread))
    return next(SESSIONS.rglob('*' + thread + '.jsonl'), None)


def latest_session():
    files = list(SESSIONS.rglob('*.jsonl'))
    if not files:
        raise ValueError('找不到 Codex 會話')
    path = max(files, key=lambda p: p.stat().st_mtime)
    with path.open() as f:
        meta = json.loads(f.readline()).get('payload', {})
    return str(uuid.UUID(meta.get('id') or meta.get('session_id')))


def terminal_snapshot():
    '''Read only the current pane of the dedicated, user-entered tmux session.'''
    if not shutil.which('tmux'):
        raise ValueError('需要 tmux / tmux is required')
    pane = subprocess.run(['tmux', 'display-message', '-p', '-t', TMUX_SESSION, '#{pane_id}'],
                          capture_output=True, text=True, timeout=3)
    if pane.returncode or not re.fullmatch(r'%[0-9]+', pane.stdout.strip()):
        raise ValueError('請在現有終端執行 tmux new -A -s oma-voice')
    pane_id = pane.stdout.strip()
    command = subprocess.run(['tmux', 'display-message', '-p', '-t', pane_id, '#{pane_current_command}'],
                             capture_output=True, text=True, timeout=3).stdout.strip()
    output = subprocess.run(['tmux', 'capture-pane', '-p', '-t', pane_id, '-S', '-80'],
                            capture_output=True, text=True, timeout=3)
    if output.returncode:
        raise ValueError('無法讀取終端畫面')
    clean = ''.join(ch for ch in output.stdout if ch in '\n\t' or ord(ch) >= 32)
    clean = '\n'.join(line.rstrip() for line in clean.splitlines()).strip()
    label = 'Claude' if 'claude' in command.lower() else 'Codex' if 'codex' in command.lower() else (command or 'Terminal')
    return pane_id, label, clean[-6000:]


def terminal_send(pane_id, text):
    '''Submit one explicit user action to the already selected tmux pane.'''
    if not re.fullmatch(r'%[0-9]+', pane_id):
        raise ValueError('無效的終端窗格')
    text = ' '.join(text.splitlines()).strip()
    for keys in (['-l', text], ['Enter']):
        result = subprocess.run(['tmux', 'send-keys', '-t', pane_id, *keys],
                                capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise ValueError(result.stderr.strip() or '終端輸入失敗')


class Reader:
    def __init__(self):
        self.config = read_json(CONFIG, {})
        self.config.setdefault('auto', True)
        self.config.setdefault('mode', 'summary')
        self.config.setdefault('language', 'cmn')
        self.config.setdefault('rate', 175)
        self.config.setdefault('engine', 'online')
        if not self.config.get('thread'):
            try:
                self.config['thread'] = latest_session()
            except ValueError:
                self.config['thread'] = None
        self.config.setdefault('follow_latest', True)
        self.config.setdefault('source', 'codex')
        self.config.setdefault('pause_minutes', PAUSE_MINUTES)
        self.term_last = None
        self.checked_session = 0
        self.next_terminal = 0
        self.retry_at = 0
        self.saved = None
        atomic_json(CONFIG, self.config)
        self.state = read_json(CACHE / 'state.json', {})
        self.state.update(status='已連接，等待回覆', playing=False, error='')
        self.process = None
        self.player_lock = threading.RLock()
        self.generation = 0
        self.path = None
        self.offset = 0
        self.pending = b''
        self.last_turn = None
        self.save()

    def save(self):
        # The tiles show these; 'status' and 'error' stay as written, for the next change of language.
        language = chosen()
        self.state['status_ui'] = local(self.state.get('status', ''), language)
        self.state['error_ui'] = local(self.state.get('error', ''), language)
        for old in ('status_en', 'error_en', 'checked_at'):
            self.state.pop(old, None)
        stamp = self.state.get('reply_at')
        if isinstance(stamp, str):
            try:
                self.state['reply_at'] = datetime.datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
            except ValueError:
                self.state['reply_at'] = None
        self.state.update(auto=self.config['auto'], mode=self.config['mode'], thread=self.config['thread'], engine=self.config['engine'], follow_latest=self.config['follow_latest'], source=self.config['source'], pause_minutes=self.config['pause_minutes'], source_name=self.state.get('source_name','Codex'))
        # The tiles redraw on every write, so write only what changed.
        if self.state != self.saved:
            atomic_json(CACHE / 'state.json', self.state)
            self.saved = dict(self.state)

    def bind(self, thread):
        path = find_session(thread)
        if path is None:
            raise ValueError('找不到指定會話')
        self.config['thread'] = str(uuid.UUID(thread))
        self.path = path
        # Seed replay, but never automatically speak historical answers on startup.
        self.pending = b''
        self.last_turn = None
        self.state.update(full='', summary='', last_turn='', reply_at=None, awaiting=False, status='已連接，等待回覆')
        with path.open('rb') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    reply = completed_reply(event)
                    kind = event.get('payload', {}).get('type')
                    if kind == 'task_started':
                        self.state['awaiting'] = True
                    elif kind in ('task_complete', 'turn_aborted'):
                        self.state['awaiting'] = False
                except ValueError:
                    continue
                if reply:
                    self.last_turn, full = reply
                    self.state.update(full=full, summary=summarize(full), last_turn=self.last_turn, reply_at=event.get('timestamp'))
            self.offset = f.tell()
        self.state['status'] = 'Codex 正在回覆…' if self.state['awaiting'] else ('已同步最近回覆' if self.state['full'] else '已連接，等待回覆')
        atomic_json(CONFIG, self.config)
        self.save()

    def poll(self):
        if self.config['source'] == 'terminal':
            return self.poll_terminal()
        if not self.config['thread']:
            self.config['thread'] = latest_session()
        if time.monotonic() - self.checked_session >= RETRY:
            self.checked_session = time.monotonic()
            if self.config['follow_latest']:
                thread = latest_session()
                if thread != self.config['thread']:
                    self.stop()
                    self.bind(thread)
        if self.path is None:
            self.bind(self.config['thread'])
        size = self.path.stat().st_size
        if size == self.offset:
            return
        if size < self.offset:
            self.bind(self.config['thread'])
        with self.path.open('rb') as f:
            f.seek(self.offset)
            data = f.read(4 * 1024 * 1024)
            self.offset = f.tell()
        lines = (self.pending + data).split(b'\n')
        self.pending = lines.pop()
        for line in lines:
            try:
                event = json.loads(line)
                reply = completed_reply(event)
                kind = event.get('payload', {}).get('type')
                if kind == 'task_started':
                    self.state.update(awaiting=True, status='Codex 正在回覆…', error='')
                    self.save()
                elif kind in ('task_complete', 'turn_aborted'):
                    self.state['awaiting'] = False
            except (ValueError, UnicodeError):
                continue
            if not reply or reply[0] == self.last_turn:
                continue
            self.last_turn, full = reply
            self.state.update(full=full, summary=summarize(full), last_turn=self.last_turn,
                              status='收到新回覆', error='', awaiting=False, reply_at=event.get('timestamp'))
            self.save()
            if self.config['auto']:
                self.play(self.state[self.config['mode']])

    def poll_terminal(self):
        if time.monotonic() < self.next_terminal:
            return
        self.next_terminal = time.monotonic() + 3
        try:
            pane, label, full = terminal_snapshot()
        except ValueError as exc:
            self.next_terminal = time.monotonic() + RETRY
            self.state.update(source_name='Terminal', term_pane='', status=str(exc),
                              full='', summary='', error='', reply_at=None, awaiting=False)
            self.save()
            return
        self.state.update(source_name=label, term_pane=pane, status='已連接終端 · 點播放讀取畫面',
                          error='', awaiting=False)
        if full != self.term_last:
            self.term_last = full
            self.state.update(full=full, summary=clean_text(full)[-360:], reply_at=time.time() if full else None)
        self.save()

    def idle(self):
        '''Nothing is being spoken, and no tile, command or Codex activity for the chosen time.'''
        limit = self.config['pause_minutes'] * 60
        if not limit or self.state.get('playing'):
            return False
        # Codex still writing its log counts, so a long task is read aloud with the screen off.
        seen = [ALIVE] + ([self.path] if self.path and self.config['source'] == 'codex' else [])
        try:
            return time.time() - max(path.stat().st_mtime for path in seen) >= limit
        except OSError:
            return False

    def stop(self):
        with self.player_lock:
            self.generation += 1
            if self.process is not None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                self.process = None
            self.state.update(playing=False, status='已停止')
            self.save()

    def play(self, text):
        if not text.strip():
            raise ValueError('還沒有可播放的回覆')
        self.stop()
        with self.player_lock:
            generation = self.generation
            self.state.update(playing=True, status='正在播放', error='')
            self.save()

        def worker():
            wav = CACHE / ('speech-' + uuid.uuid4().hex + '.wav')
            try:
                with self.player_lock:
                    if generation != self.generation:
                        return
                if not shutil.which('espeak-ng') or not shutil.which('paplay'):
                    raise ValueError('需要 espeak-ng 和 paplay')
                commands = [
                    ([str(Path(__file__).parent / 'venv/bin/python'),
                      str(Path(__file__).parent / 'synthesize.py'), str(wav)], clean_text(text).encode()),
                    (['paplay', str(wav)], None),
                ]
                for args, data in commands:
                    if data is None:
                        with self.player_lock:
                            if generation == self.generation:
                                backend = Path(str(wav) + '.backend')
                                self.state['status'] = '正在播放 · ' + (backend.read_text() if backend.exists() else '語音')
                                self.save()
                    with self.player_lock:
                        if generation != self.generation:
                            return
                        proc = subprocess.Popen(args, stdin=subprocess.PIPE if data else subprocess.DEVNULL,
                                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                        self.process = proc
                    try:
                        _, err = proc.communicate(data, timeout=300)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.communicate()
                        raise ValueError('播放逾時')
                    if proc.returncode and generation == self.generation:
                        raise ValueError(err.decode(errors='replace')[-400:] or '播放失敗')
                with self.player_lock:
                    if generation == self.generation:
                        self.process = None
                        # Keep the reason on screen when the natural voice was not the one heard.
                        used = Path(str(wav) + '.backend')
                        used = used.read_text() if used.exists() else ''
                        self.state.update(playing=False, status='播放完成 · '+used if '離線' in used and '（' in used else '播放完成')
                        self.save()
            except Exception as exc:
                with self.player_lock:
                    if generation == self.generation:
                        self.state.update(playing=False, status='播放失敗', error=str(exc))
                        self.save()
            finally:
                wav.unlink(missing_ok=True)
                Path(str(wav) + '.backend').unlink(missing_ok=True)
        threading.Thread(target=worker, daemon=True).start()

    def command(self, request):
        action = request.get('action')
        if action != 'status':
            self.retry_at = 0
        if action in ('replay', 'send'):
            if self.config['source'] == 'terminal':
                self.next_terminal = 0
            self.poll()
        if action == 'status':
            # Also how a change of interface language reaches the tiles: save() writes only what changed.
            self.save()
            return self.state
        if action == 'replay':
            self.play(self.state.get('full' if request.get('full') else 'summary', ''))
        elif action == 'test':
            self.play(SPOKEN[chosen()][4])
        elif action == 'stop':
            self.stop()
        elif action == 'auto':
            value = request.get('value', 'toggle')
            self.config['auto'] = not self.config['auto'] if value == 'toggle' else value == 'on'
            if not self.config['auto']:
                self.stop()
            self.state['status'] = '自動播報已開啟' if self.config['auto'] else '自動播報已關閉'
            atomic_json(CONFIG, self.config)
            self.save()
        elif action == 'engine':
            value = request.get('value', 'toggle')
            if value == 'toggle':
                value = 'offline' if self.config['engine'] == 'online' else 'online'
            if value not in ('online', 'offline'):
                raise ValueError('請選 online 或 offline')
            self.stop()
            self.config['engine'] = value
            atomic_json(CONFIG, self.config)
            self.state['status'] = '已切換線上自然語音' if value == 'online' else '已切換離線神經語音'
            self.save()
        elif action == 'pause':
            value = str(request.get('value', 'toggle')).strip().lower()
            if value == 'toggle':
                value = '0' if self.config['pause_minutes'] else str(PAUSE_MINUTES)
            if value == 'off':
                value = '0'
            if not value.isascii() or not value.isdigit() or int(value) > 1440:
                raise ValueError('請輸入 1 到 1440 的分鐘數，或 off')
            self.config['pause_minutes'] = int(value)
            atomic_json(CONFIG, self.config)
            self.state['status'] = '已更新閒置暫停時間' if int(value) else '閒置後不再暫停'
            self.save()
        elif action == 'refresh':
            self.stop()
            if self.config['source'] == 'terminal':
                self.next_terminal = 0
                self.poll_terminal()
            else:
                self.bind(latest_session() if self.config['follow_latest'] else self.config['thread'])
        elif action == 'source':
            value = request.get('value')
            if value not in ('codex', 'terminal'):
                raise ValueError('請選 Codex 或 Terminal')
            self.stop()
            self.config['source'] = value
            self.state.update(full='', summary='', reply_at=None, source_name='Codex' if value == 'codex' else 'Terminal')
            atomic_json(CONFIG, self.config)
            if value == 'terminal':
                self.next_terminal = 0
                self.term_last = None
                self.poll_terminal()
            else:
                self.bind(latest_session() if self.config['follow_latest'] else self.config['thread'])
        elif action == 'follow':
            self.config['follow_latest'] = not self.config['follow_latest']
            if self.config['follow_latest']:
                self.stop()
                self.bind(latest_session())
            atomic_json(CONFIG, self.config)
            self.save()
        elif action == 'bind':
            self.stop()
            self.config['follow_latest'] = False
            self.bind(request['thread'])
        elif action == 'send':
            text = request.get('text', '').strip()
            if not text or len(text) > 16000:
                raise ValueError('請先輸入內容（最多 16000 字）')
            if any(ord(c) < 32 and c not in '\n\t' for c in text):
                raise ValueError('文字含有控制字元')
            self.stop()
            if self.config['source'] == 'terminal':
                pane, label, _ = terminal_snapshot()
                terminal_send(pane, text)
                self.state.update(status='已送到終端 · '+label, error='')
            else:
                result = subprocess.run(['codex', 'queue', '--thread', self.config['thread'], '--message', text],
                                        capture_output=True, text=True, timeout=20)
                if result.returncode:
                    raise ValueError(result.stderr[-500:] or result.stdout[-500:] or '送出失敗')
                self.state.update(status='已送到這個 Codex 會話的佇列', error='')
            self.save()
        else:
            raise ValueError('未知命令')
        return {'ok': True, 'status': self.state['status']}


def serve():
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (CACHE / 'daemon.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        ALIVE.touch()
        reader = Reader()
        if reader.config['source'] == 'terminal':
            reader.poll_terminal()
        elif reader.config['thread']:
            reader.bind(reader.config['thread'])
        SOCKET.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(SOCKET))
            SOCKET.chmod(0o600)
            server.listen(4)
            while not reader.idle():
                if time.monotonic() >= reader.retry_at:
                    try:
                        reader.poll()
                    except (OSError, ValueError) as exc:
                        reader.state.update(status='等待會話記錄', error=str(exc))
                        reader.save()
                        reader.retry_at = time.monotonic() + RETRY
                if not select.select([server], [], [], 0.5)[0]:
                    continue
                conn, _ = server.accept()
                with conn:
                    conn.settimeout(5)
                    try:
                        data = b''
                        while b'\n' not in data and len(data) <= 70000:
                            part = conn.recv(8192)
                            if not part:
                                break
                            data += part
                        if len(data) > 70000:
                            raise ValueError('請求太大')
                        response = reader.command(json.loads(data))
                    except Exception as exc:
                        response = {'ok': False, 'error': str(exc), 'error_ui': local(str(exc))}
                    try:
                        conn.sendall((json.dumps(response, ensure_ascii=False) + '\n').encode())
                    except OSError:
                        pass


def request(value):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(25)
        client.connect(str(SOCKET))
        client.sendall((json.dumps(value, ensure_ascii=False) + '\n').encode())
        data = b''
        while b'\n' not in data:
            part = client.recv(8192)
            if not part:
                break
            data += part
        return json.loads(data)


def ensure():
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    ALIVE.touch()
    try:
        request({'action': 'status'})
        return
    except (OSError, ValueError):
        pass
    with (CACHE / 'daemon.log').open('ab') as log:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'daemon'],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(30):
        try:
            request({'action': 'status'})
            return
        except (OSError, ValueError):
            time.sleep(0.1)
    raise ValueError('語音服務未啟動，請查看 ~/.cache/oma-voice/daemon.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['daemon', 'ensure', 'status', 'replay', 'stop', 'auto', 'bind', 'send', 'test', 'engine', 'refresh', 'follow', 'language', 'source', 'pause'])
    parser.add_argument('value', nargs='?')
    parser.add_argument('--text')
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.action == 'language':
        if args.value not in LANGUAGES:
            raise ValueError(local('請選擇介面語言：')+' '.join(LANGUAGES))
        path = CHOICE
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        temp.write_text(args.value)
        temp.chmod(0o600)
        temp.replace(path)
        try:
            request({'action': 'status'})
        except (OSError, ValueError):
            pass
        return
    if args.action == 'daemon':
        serve()
        return
    ensure()
    if args.action == 'ensure':
        return
    result = request({'action': args.action, 'value': args.value or 'toggle',
                      'thread': args.value, 'text': args.text or '', 'full': args.full})
    result['request_id'] = uuid.uuid4().hex
    if result.get('ok') is not False and 'status' in result:
        result['status_ui'] = local(result['status'])
    print(json.dumps(result, ensure_ascii=False) if args.action == 'status' or args.json else
          result.get('error_ui') or local(result.get('status', '完成')))
    if result.get('ok') is False:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError) as error:
        print(local(str(error)), file=sys.stderr)
        sys.exit(1)
