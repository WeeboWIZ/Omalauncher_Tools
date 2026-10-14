'''Local Linux error history. Does not access Android logs or terminal contents.'''
from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import json
import os
import platform
import re
import urllib.parse
from pathlib import Path
import sqlite3
from contextlib import closing

ROOT = Path.home() / 'oma-devlogs'
CONFIG = Path.home() / '.config/omalauncher'
TERMINALS = ROOT / 'logs/terminals'
LANGUAGE = 'en'
# Reports go to the Omalauncher author; the person opening the issue still reviews and submits it.
ISSUES = 'https://github.com/SimonSchubert/omalauncher/issues/new'
# Android browsers handle links up to about 8 KB; GitHub rejects much longer ones.
URL_LIMIT = 7000
SECRETS = [
    (re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})'), '[redacted]'),
    (re.compile(r'(?i)\b(authorization|bearer|token|api[_-]?key|secret|password|passwd)\b(\s*[:=]\s*|\s+)(["\']?)[^\s"\']{6,}'), r'\1\2\3[redacted]'),
    (re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'), '[email]'),
    (re.compile(r'\b[0-9a-fA-F]{32,}\b|\b(?=[A-Za-z0-9+_-]*\d)(?=[A-Za-z0-9+_-]*[A-Za-z])[A-Za-z0-9+_-]{40,}={0,2}'), '[redacted]'),
]


def sources():
    for path in sorted((CONFIG / 'widgets/.errors').glob('*.txt')):
        yield path, True
    yield CONFIG / 'style/errors.txt', True
    for path in sorted(Path('/tmp').glob('.guest-shell-err-*')):
        yield path, False
    for path in sorted(TERMINALS.glob('*.log')):
        yield path, False
    for name in ('oma-voice/daemon.log', 'oma-speak/server.log', 'pixel-console/bridge.log'):
        yield Path.home() / '.cache' / name, False


def connect():
    directory = ROOT / 'logs'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    dbpath = directory / 'system-errors.sqlite3'
    db = sqlite3.connect(dbpath, timeout=5)
    db.execute('CREATE TABLE IF NOT EXISTS cursors (path TEXT PRIMARY KEY, inode INTEGER, offset INTEGER, signature TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time TEXT, source TEXT, text TEXT)')
    if dbpath.stat().st_mode & 0o777 != 0o600:
        dbpath.chmod(0o600)
    return db


def collect(db):
    # One transaction protects offsets against simultaneous refreshes.
    # A pass that finds nothing new changes no row, so the database file is not written.
    db.execute('BEGIN IMMEDIATE')
    added = False
    try:
        for path, snapshot in sources():
            key = str(path)
            old = db.execute('SELECT inode, offset, signature FROM cursors WHERE path=?', (key,)).fetchone()
            try:
                with path.open('rb') as stream:
                    stat = os.fstat(stream.fileno())
                    start = 0 if snapshot or not old or old[0] != stat.st_ino or stat.st_size < old[1] else old[1]
                    # Keep newest context, bounded even when a source is noisy.
                    stream.seek(max(start, stat.st_size - 32768))
                    raw = stream.read(32768)
                    end = stream.tell()
            except (OSError, ValueError):
                continue
            signature = hashlib.sha256(raw).hexdigest() if snapshot else ''
            text = raw.decode('utf-8', errors='replace').strip()
            if text and (not snapshot or not old or old[2] != signature):
                # Service files may include routine messages: only retain error contexts.
                service = '/.cache/' in key
                if not service or any(word in text.lower() for word in ('error', 'exception', 'traceback', 'fatal', 'failed', 'panic', 'segfault')):
                    now = dt.datetime.now().astimezone().isoformat(timespec='seconds')
                    db.execute('INSERT INTO events(time,source,text) VALUES(?,?,?)', (now, key, text))
                    added = True
            if old != (stat.st_ino, end, signature):
                db.execute('INSERT OR REPLACE INTO cursors VALUES(?,?,?,?)', (key, stat.st_ino, end, signature))
        # Missing snapshot files represent cleared errors; allow future recurrences.
        for (key,) in db.execute('SELECT path FROM cursors').fetchall():
            if key.startswith(str(CONFIG)) and not Path(key).exists():
                db.execute('DELETE FROM cursors WHERE path=?', (key,))
        if added:
            db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 500)')
        db.commit()
    except BaseException:
        db.rollback()
        raise


def t(zh, en):
    return zh if LANGUAGE == 'zh' else en


def single_report(entry):
    return (t('# Omalauncher Linux 系統錯誤\n\n時間為收集時間；來源檔內容可能早於此時間。\n\n',
              '# Omalauncher Linux system error\n\nThe time is when it was collected; the source file may be older.\n\n') +
            f"## {entry['time']}\n\n{t('來源：', 'Source: ')}{entry['source']}\n\n" +
            ''.join('    ' + line + '\n' for line in entry['text'].splitlines()))


def redact(text):
    '''Hide the home path, user name, e-mail addresses and anything shaped like a key before sharing.'''
    home = str(Path.home())
    if home not in ('/', ''):
        text = text.replace(home, '~')
    text = re.sub(r'/home/[^/\s]+', '/home/[user]', text)
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = ''
    if len(user) >= 3 and user not in ('root', 'user'):
        text = re.sub(r'\b' + re.escape(user) + r'\b', '[user]', text)
    for pattern, replacement in SECRETS:
        text = pattern.sub(replacement, text)
    return text


def environment():
    version = Path.home() / '.local/share/oma-devlogs/store-version'
    try:
        devlogs = version.read_text().strip().split('-')[0]
    except OSError:
        devlogs = 'unknown'
    return f'Linux {platform.release()} {platform.machine()} · Python {platform.python_version()} · DEV LOGS {devlogs}'


def issue_url(entry, analysis=None):
    '''A prefilled GitHub issue in English for the author; nothing is sent until it is submitted there.'''
    title = redact(f"[DEV LOGS] {entry['name']}: {entry['summary']}")[:120]
    head = f'Reported from the DEV LOGS widget.\n\n**Environment:** {environment()}\n**Collected:** {entry["time"]}\n**Source:** `{redact(entry["source"])}`\n\n'
    if analysis:
        head += '## Agent analysis\n\n' + redact(str(analysis.get('summary', ''))) + '\n\n'
        for cause in analysis.get('causes') or []:
            head += f"- {redact(str(cause.get('text', '')))} ({cause.get('confidence', '?')})\n"
        head += '\n'
    log = redact(entry['text'])
    def link(body):
        return ISSUES + '?' + urllib.parse.urlencode({'title': title, 'body': body}, quote_via=urllib.parse.quote)
    fenced = head + '## Log\n\n```\n' + log + '\n```\n'
    url = link(fenced)
    while len(url) > URL_LIMIT and log:
        # Keep the end of the log, where the failure usually is.
        log = log[len(log) // 4 + 1:]
        url = link(head + '## Log (truncated; the full report can be pasted from DEV LOGS)\n\n```\n…' + log + '\n```\n')
    return url


def classify(text, source=''):
    '''Classify known diagnostics; unknown messages stay informational.'''
    if re.search(r'\b(?:error|exception|traceback|fatal|failed|panic|segfault|segmentation fault|enosys)\b|function not implemented|exited abnormally|異常退出|錯誤|失敗', text, re.I):
        return 'error'
    if re.search(r'\b(?:warn|warning)\b|警告', text, re.I):
        return 'warning'
    if text.strip().startswith('runtime: drawing takes'):
        return 'info'
    if '/widgets/.errors/' in source or source.endswith('/style/errors.txt'):
        return 'error'
    return 'info'


def summarize(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    relevant = [line for line in lines if any(word in line.lower() for word in ('error', 'exception', 'fatal', 'failed', 'exited abnormally', '異常退出')) and not line.startswith(('File ', 'During '))]
    return (relevant[-1] if relevant else (lines[0] if lines else ''))[:180]


def history(offset=0, level='all'):
    offset = max(0, int(offset))
    if level not in ('all', 'error', 'warning', 'info'):
        raise ValueError('Unknown error filter')
    with closing(connect()) as db:
        collect(db)
        rows = [dict(zip(('id', 'time', 'source', 'text'), row)) for row in db.execute(
            'SELECT id,time,source,text FROM events ORDER BY id DESC')]
    for row in rows:
        row['level'] = classify(row['text'], row['source'])
    counts = {kind: sum(row['level'] == kind for row in rows) for kind in ('error', 'warning', 'info')}
    filtered = [row for row in rows if level == 'all' or row['level'] == level]
    total = len(filtered)
    entries = filtered[offset:offset + 20]
    for entry in entries:
        entry['summary'] = summarize(entry['text'])
        entry['name'] = Path(entry['source']).name
        entry['report'] = single_report(entry)
        entry['shared'] = redact(entry['report'])
        entry['issue'] = issue_url(entry)
    return {'total': total, 'all_total': len(rows), 'error_total': counts['error'],
            'counts': counts, 'level': level, 'entries': entries, 'offset': offset, 'more': offset + 20 < total}


def record(event_id):
    '''One stored event with the same fields as a history entry, or None.'''
    with closing(connect()) as db:
        row = db.execute('SELECT id,time,source,text FROM events WHERE id=?', (int(event_id),)).fetchone()
    if not row:
        return None
    entry = dict(zip(('id', 'time', 'source', 'text'), row))
    entry['level'] = classify(entry['text'], entry['source'])
    entry['summary'] = summarize(entry['text'])
    entry['name'] = Path(entry['source']).name
    return entry


def report():
    with closing(connect()) as db:
        collect(db)
        rows = db.execute('SELECT time,source,text FROM events ORDER BY id DESC LIMIT 100').fetchall()
    text = t('# Omalauncher Linux 系統錯誤\n\n時間為收集時間；來源檔內容可能早於此時間。以下為最近 100 筆本機紀錄。\n\n'
             '終端紀錄只包含 stderr 與非零退出碼，無法判斷所有視窗關閉原因。\n\n',
             '# Omalauncher Linux system errors\n\nTimes are when each was collected; the source file may be older. The newest 100 local records follow.\n\n'
             'Terminal records hold only stderr and a non-zero exit code, so they cannot explain every closed window.\n\n')
    for time, source, body in rows:
        text += f"## {time}\n\n{t('來源：', 'Source: ')}{source}\n\n"
        text += ''.join('    ' + line + '\n' for line in body.splitlines()) + '\n'
    return text



if __name__ == '__main__':
    import sys
    # system_errors.py [offset] [level] [en|zh], or: system_errors.py report [en|zh]
    if len(sys.argv) > 1 and sys.argv[1] == 'report':
        LANGUAGE = 'zh' if sys.argv[2:3] == ['zh'] else 'en'
        print(report())
    else:
        LANGUAGE = 'zh' if sys.argv[3:4] == ['zh'] else 'en'
        print(json.dumps(history(sys.argv[1] if len(sys.argv) > 1 else 0,
                                 sys.argv[2] if len(sys.argv) > 2 else 'all'), ensure_ascii=False))
