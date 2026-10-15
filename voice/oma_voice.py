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
from language import CHOICE, LANGUAGES, SPOKEN, changed_at, chosen, local, spoken
import codex_queue


HOME = Path.home()
CACHE = HOME / '.cache/oma-voice'
SOCKET = CACHE / 'control.sock'
CONFIG = HOME / '.config/omalauncher/voice.json'
SESSIONS = HOME / '.codex/sessions'
# Claude Code keeps one transcript per conversation here, whatever terminal it runs in.
CLAUDE_PROJECTS = HOME / '.claude/projects'
SOURCES = ('codex', 'claude', 'terminal')
TMUX_SESSION = 'oma-voice'
# ensure() touches this. The service quits once neither it nor the Codex log has changed
# for the 'pause_minutes' setting (0 = never), and ensure() starts it again.
ALIVE = CACHE / 'alive'
PAUSE_MINUTES = 10
# Seconds between looks for a Codex session or tmux pane while there is none.
RETRY = 15


def sweep(keep=''):
    '''Remove audio from earlier readings. Some Android file systems refuse to delete a file the
    player still holds, so what one reading leaves behind goes when the next one starts.'''
    for old in CACHE.glob('speech-*'):
        if keep and old.name.startswith(keep):
            continue
        try:
            old.unlink()
        except OSError:
            pass


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


def clean_text(text):
    # Spoken notes are in the language of the reply, or the wrong voice would be picked for it.
    notes = SPOKEN[spoken(text)]
    text = re.sub(r'```.*?```', notes[2], text, flags=re.S)
    text = re.sub(r'!?\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'https?://\S+', notes[3], text)
    text = re.sub(r'(?m)^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s*)', '', text)
    text = text.replace('`', '').replace('**', '').replace('__', '')
    return ''.join(c for c in text if c in '\n\t' or (ord(c) >= 32 and ord(c) != 127)).strip()


def readable(text):
    '''The reply as the detail page shows it: Markdown marks taken out, code and links kept.'''
    text = re.sub(r'(?m)^\s*```.*$', '', text or '')
    text = re.sub(r'!?\[([^\]]+)\]\(([^)]*)\)', r'\1 (\2)', text)
    text = re.sub(r'(?m)^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$\n?', '', text)
    text = re.sub(r'(?m)^\s*\|(.*)\|\s*$', lambda m: ' · '.join(c.strip() for c in m.group(1).split('|') if c.strip()), text)
    text = re.sub(r'(?m)^(\s*)#{1,6}\s+', r'\1', text)
    text = re.sub(r'(?m)^(\s*)[-*+]\s+', r'\1• ', text)
    text = re.sub(r'(?m)^>\s?', '', text)
    text = text.replace('**', '').replace('__', '').replace('`', '')
    return re.sub(r'\n{3,}', '\n\n', text).strip()


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


def codex_event(event):
    '''('start'|'end', None) or ('reply', (turn, text)); commentary, tool output and subagents are skipped.'''
    payload = event.get('payload')
    if event.get('type') != 'event_msg' or not isinstance(payload, dict):
        return None
    kind = payload.get('type')
    text = payload.get('last_agent_message')
    if kind == 'task_complete' and isinstance(text, str) and text.strip():
        return 'reply', (payload.get('turn_id') or payload.get('root_turn_id') or event.get('timestamp'), text)
    if kind == 'task_started':
        return 'start', None
    if kind in ('task_complete', 'turn_aborted'):
        return 'end', None
    return None


def claude_event(event):
    '''('start', None) when the user asks Claude something, ('reply', (id, text)) for its final answer.'''
    if event.get('isSidechain'):
        return None
    message = event.get('message')
    if not isinstance(message, dict):
        return None
    content = message.get('content')
    if event.get('type') == 'user':
        # Tool results come back as user entries too; only typed prompts start a turn.
        if isinstance(content, str) or (isinstance(content, list) and any(
                isinstance(part, dict) and part.get('type') == 'text' for part in content)):
            return 'start', None
        return None
    if event.get('type') != 'assistant' or message.get('stop_reason') != 'end_turn' or not isinstance(content, list):
        return None
    text = '\n\n'.join(part.get('text', '') for part in content
                         if isinstance(part, dict) and part.get('type') == 'text').strip()
    if not text:
        return None
    return 'reply', (event.get('requestId') or message.get('id') or event.get('uuid'), text)


def latest_claude():
    files = list(CLAUDE_PROJECTS.glob('*/*.jsonl'))
    if not files:
        raise ValueError('找不到 Claude 會話')
    return max(files, key=lambda p: p.stat().st_mtime)


def claude_pane():
    '''The oma-voice tmux pane, only if Claude runs in it: the one place a Claude chat can be typed into.'''
    try:
        pane, label, _ = terminal_snapshot()
    except ValueError:
        return None
    return pane if label == 'Claude' else None


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
        if keys == ['Enter']:
            # Codex and Claude read an Enter right after fast typing as part of a paste: a newline, not submit.
            time.sleep(0.5)
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
        self.language_at = changed_at()
        self.state['status_ui'] = local(self.state.get('status', ''), language)
        self.state['error_ui'] = local(self.state.get('error', ''), language)
        self.state['full_view'] = readable(self.state.get('full') or '')
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

    def open_log(self, path):
        '''Follow a chat log from its end; older answers are shown, never read aloud.'''
        self.path, self.pending, self.last_turn = path, b'', None
        self.state.update(full='', summary='', last_turn='', reply_at=None, awaiting=False)
        with path.open('rb') as f:
            for line in f:
                self.take(line, live=False)
            self.offset = f.tell()
        name = 'Claude' if self.config['source'] == 'claude' else 'Codex'
        self.state['status'] = name+' 正在回覆…' if self.state['awaiting'] else ('已同步最近回覆' if self.state['full'] else '已連接，等待回覆')
        self.save()

    def take(self, line, live):
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            return
        found = (claude_event if self.config['source'] == 'claude' else codex_event)(event)
        if not found:
            return
        kind, reply = found
        if kind != 'reply':
            self.state['awaiting'] = kind == 'start'
            if live and kind == 'start':
                self.state.update(status=('Claude' if self.config['source'] == 'claude' else 'Codex')+' 正在回覆…', error='')
                self.save()
            return
        if reply[0] == self.last_turn:
            return
        self.last_turn, full = reply
        self.state.update(full=full, summary=summarize(full), last_turn=self.last_turn, awaiting=False, reply_at=event.get('timestamp'))
        if live:
            self.state.update(status='收到新回覆', error='')
            self.save()
            if self.config['auto']:
                self.play(self.state[self.config['mode']])

    def bind(self, thread):
        path = find_session(thread)
        if path is None:
            raise ValueError('找不到指定會話')
        self.config['thread'] = str(uuid.UUID(thread))
        self.open_log(path)
        atomic_json(CONFIG, self.config)

    def poll(self):
        source = self.config['source']
        if source == 'terminal':
            return self.poll_terminal()
        if time.monotonic() - self.checked_session >= RETRY or self.path is None:
            self.checked_session = time.monotonic()
            if source == 'claude':
                self.state['term_pane'] = claude_pane() or ''
                latest = latest_claude()
                if latest != self.path:
                    self.stop()
                    self.open_log(latest)
                self.save()
            else:
                if not self.config['thread']:
                    self.config['thread'] = latest_session()
                if self.config['follow_latest'] and latest_session() != self.config['thread']:
                    self.stop()
                    self.bind(latest_session())
                elif self.path is None:
                    self.bind(self.config['thread'])
        size = self.path.stat().st_size
        if size < self.offset:
            return self.open_log(self.path)
        if size == self.offset:
            return
        with self.path.open('rb') as f:
            f.seek(self.offset)
            data = f.read(4 * 1024 * 1024)
            self.offset = f.tell()
        lines = (self.pending + data).split(b'\n')
        self.pending = lines.pop()
        for line in lines:
            self.take(line, live=True)

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
        seen = [ALIVE] + ([self.path] if self.path and self.config['source'] != 'terminal' else [])
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
            sweep(keep=wav.stem)
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
                # Only this reading's files: a newer reading may already be writing its own.
                for own in CACHE.glob(wav.stem + '*'):
                    try:
                        own.unlink()
                    except OSError:
                        pass
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
            elif self.config['source'] == 'claude':
                self.open_log(latest_claude())
            else:
                self.bind(latest_session() if self.config['follow_latest'] else self.config['thread'])
        elif action == 'source':
            value = request.get('value')
            if value not in SOURCES:
                raise ValueError('請選 Codex、Claude 或 Terminal')
            self.stop()
            self.config['source'] = value
            self.path = None
            # The last send result belongs to the old target; the dictation tile must not keep showing it.
            (HOME/'.cache/oma-speak/send-status.json').unlink(missing_ok=True)
            self.state.update(full='', summary='', reply_at=None, term_pane='',
                              source_name={'codex': 'Codex', 'claude': 'Claude'}.get(value, 'Terminal'))
            atomic_json(CONFIG, self.config)
            if value == 'claude':
                self.state['term_pane'] = claude_pane() or ''
                self.open_log(latest_claude())
            elif value == 'terminal':
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
            # A new chat may have appeared during the 15-second background backoff.
            # An explicit Send must use the current target immediately.
            if self.config['source'] == 'codex' and self.config['follow_latest']:
                latest = latest_session()
                if latest != self.config['thread']:
                    self.bind(latest)
            self.stop()
            if self.config['source'] == 'claude':
                pane = claude_pane()
                if pane is None:
                    raise ValueError('Claude 不在 oma-voice tmux 中，無法送出；請點「在 tmux 開啟 Claude」')
                terminal_send(pane, text)
                self.state.update(status='已送到終端 · Claude', error='', term_pane=pane)
            elif self.config['source'] == 'terminal':
                pane, label, _ = terminal_snapshot()
                terminal_send(pane, text)
                self.state.update(status='已送到終端 · '+label, error='')
            else:
                thread = self.config['thread']
                # Only the newest dictation may wait for the agent: replace, never pile up.
                replaced = codex_queue.forget(thread, text)
                result = subprocess.run(['codex', 'queue', '--thread', thread, '--message', text],
                                        capture_output=True, text=True, timeout=20)
                if result.returncode:
                    raise ValueError(result.stderr[-500:] or result.stdout[-500:] or '送出失敗')
                # An idle chat takes the message at once; a busy one keeps it until its turn ends.
                waiting = None
                for _ in range(6):
                    time.sleep(0.25)
                    waiting = codex_queue.remember(thread, text)
                    if waiting is None:
                        break
                status = '已送到 Codex 會話' if waiting is None else '已取代排隊中的上一則' if replaced else '排隊中：Codex 回覆完成後送出'
                self.state.update(status=status, error='')
                self.save()
                return {'ok': True, 'status': status, 'queued': waiting is not None, 'replaced': bool(replaced)}
            self.save()
        elif action == 'unqueue':
            cancelled = codex_queue.cancel()
            self.state.update(status='已取消排隊中的訊息' if cancelled else '沒有排隊中的訊息', error='')
            self.save()
            return {'ok': True, 'status': self.state['status'], 'text': cancelled and cancelled.get('text')}
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
        sweep()
        reader = Reader()
        if reader.config['source'] == 'terminal':
            reader.poll_terminal()
        elif reader.config['source'] == 'claude':
            try:
                reader.poll()
            except (OSError, ValueError) as exc:
                reader.state.update(status='等待會話記錄', error=str(exc))
        elif reader.config['thread']:
            reader.bind(reader.config['thread'])
        SOCKET.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(SOCKET))
            SOCKET.chmod(0o600)
            server.listen(4)
            while not reader.idle():
                # The dictation page and the setup screen write the language without telling the service.
                if changed_at() != reader.language_at:
                    reader.save()
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
    parser.add_argument('action', choices=['daemon', 'ensure', 'status', 'replay', 'stop', 'auto', 'bind', 'send', 'test', 'engine', 'refresh', 'follow', 'language', 'source', 'pause', 'unqueue'])
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
