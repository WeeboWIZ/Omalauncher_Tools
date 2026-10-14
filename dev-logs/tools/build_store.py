#!/usr/bin/env python3
'''Build a self-contained DEV LOGS widget for GitHub and the widget store.'''
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2.0'
STORE = ROOT.parent / 'store/widgets/weebowiz/dev-logs'
PAYLOAD = {
    'bin/oma-devlogs': ('.local/bin/oma-devlogs', True),
    'bin/oma-devlogs-terminal': ('.local/bin/oma-devlogs-terminal', True),
    'lib/system_errors.py': ('.local/share/oma-devlogs/system_errors.py', False),
    'lib/agent_help.py': ('.local/share/oma-devlogs/agent_help.py', False),
}


def payload():
    return {target: ((ROOT / source).read_text(), executable)
            for source, (target, executable) in PAYLOAD.items()}


def payload_id():
    digest = hashlib.sha256((ROOT / 'lib/setup.py').read_bytes())
    for source in PAYLOAD:
        digest.update(source.encode() + b'\0' + (ROOT / source).read_bytes())
    return VERSION + '-' + digest.hexdigest()[:12]


def setup_script():
    code = (ROOT / 'lib/setup.py').read_text() + '\ninstall_files(' + repr(payload()) + ', ' + repr(payload_id()) + ')\n'
    if '"""' in code or '\nOMA_DESK_SETUP\n' in code:
        raise ValueError('Payload cannot contain OWL or heredoc delimiters')
    return ('set -eu\numask 077\nmkdir -p "$HOME/.cache/oma-devlogs"\n'
            'exec >>"$HOME/.cache/oma-devlogs/setup.log" 2>&1\n'
            "python - <<'OMA_DESK_SETUP'\n" + code + 'OMA_DESK_SETUP')


def render():
    text = (ROOT / 'widgets/65-dev-logs.owl').read_text()
    text = text.replace('__VERSION__', VERSION).replace('__PAYLOAD_ID__', payload_id())
    text = text.replace('__SETUP_COMMAND__', setup_script())
    if len(text.encode()) > 256 * 1024:
        raise ValueError('Widget exceeds the store limit of 256 KiB')
    return text


def build():
    STORE.mkdir(parents=True, exist_ok=True)
    target = STORE / 'widget.owl'
    target.write_text(render())
    target.chmod(0o644)
    print(f'{target.relative_to(ROOT.parent)}: {target.stat().st_size} bytes; payload {payload_id()}')
    return target


if __name__ == '__main__':
    build()
