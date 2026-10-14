'''The one dictation waiting in a Codex chat's queue. Codex reloads its SQLite queue when a row
changes, so a newer dictation replaces the waiting one instead of piling up behind it.'''
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import uuid

HOME = Path.home()
DB = Path(os.environ.get('CODEX_HOME') or HOME/'.codex')/'queue_1.sqlite'
PENDING = HOME/'.cache/oma-voice/queued.json'


@contextmanager
def _connect():
    if not DB.exists():
        raise OSError('no Codex queue')
    connection = sqlite3.connect(str(DB), timeout=3)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _text(payload):
    try:
        content = json.loads(payload)['UserInput']['content']
        return ''.join(part.get('text', '') for part in content if part.get('type') == 'text')
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def items(thread):
    '''(id, text) of every message waiting in this chat, oldest first.'''
    with _connect() as connection:
        rows = connection.execute('SELECT id, payload_json FROM queued_items WHERE thread_id = ? ORDER BY queue_order',
                                  (thread,)).fetchall()
    return [(row[0], _text(row[1])) for row in rows]


def remove(thread, ids):
    if not ids:
        return 0
    with _connect() as connection:
        return sum(connection.execute('DELETE FROM queued_items WHERE thread_id = ? AND id = ?',
                                      (thread, item)).rowcount for item in ids)


def pending():
    '''The waiting dictation message, or None once Codex has taken it or it was removed.'''
    try:
        value = json.loads(PENDING.read_text())
    except (OSError, ValueError):
        return None
    try:
        waiting = any(item == value.get('id') for item, _ in items(value.get('thread', '')))
    except (OSError, sqlite3.Error):
        return value
    if not waiting:
        PENDING.unlink(missing_ok=True)
        return None
    return value


def forget(thread, text):
    '''Before queueing text: drop the earlier waiting dictation and copies of this text.'''
    ids = []
    earlier = pending()
    if earlier and earlier.get('thread') == thread:
        ids.append(earlier['id'])
    try:
        ids += [item for item, queued in items(thread) if queued == text and item not in ids]
        removed = remove(thread, ids)
    except (OSError, sqlite3.Error):
        removed = 0
    PENDING.unlink(missing_ok=True)
    return removed


def remember(thread, text):
    '''After `codex queue`: note the newest matching row, if it is still waiting.'''
    try:
        found = [item for item, queued in items(thread) if queued == text]
    except (OSError, sqlite3.Error):
        found = []
    if not found:
        return None
    value = {'thread': thread, 'id': found[-1], 'text': text}
    PENDING.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = PENDING.with_name(PENDING.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False))
    temporary.chmod(0o600)
    temporary.replace(PENDING)
    return value


def cancel():
    value = pending()
    if value is None:
        return None
    remove(value['thread'], [value['id']])
    PENDING.unlink(missing_ok=True)
    return value
