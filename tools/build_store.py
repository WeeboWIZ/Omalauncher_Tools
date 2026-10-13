#!/usr/bin/env python3
"""Render widgets/*.owl with the helper programs embedded; write the widget store folders."""
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
VERSION = '3.1'
AUTHOR = 'weebowiz'
# template -> store folder. Each folder's preview.png and README.md are kept by hand.
WIDGETS = {'46-speak.owl': 'terminal-voice', '47-voice-input.owl': 'dictation'}
# repo folder -> (folder under $HOME, executable)
PAYLOAD = [('voice', '.local/share/oma-voice', False), ('dictation', '.local/share/oma-speak', False), ('bin', '.local/bin', True)]
MARKER = '.local/share/oma-voice/store-version'
MAX_BYTES = 256 * 1024
# Whole command lines of the running voice service and dictation page, as pkill -f patterns.
SERVICES = [r'^[^ ]*python[0-9.]* .*/oma_voice\.py daemon$', r'^[^ ]*python[0-9.]* .*/oma-speak/server\.py$']


def payload_files():
    for folder, destination, executable in PAYLOAD:
        for file in sorted((ROOT/folder).iterdir()):
            if file.is_file():
                yield file, destination+'/'+file.name, executable


def requirement():
    return (ROOT/'requirements.txt').read_text().strip()


def payload_id():
    digest = hashlib.sha256(requirement().encode())
    for file, target, _ in payload_files():
        digest.update(target.encode()+b'\0'+file.read_bytes().replace(b'\r\n', b'\n')+b'\0')
    return VERSION+'-'+digest.hexdigest()[:8]


def setup_script():
    lines = [
        '# Writes the voice and dictation programs kept in this widget into ~/.local, then',
        '# makes a Python environment for edge-tts (online speech). Log: ~/.cache/oma-voice/setup.log',
        'set -u',
        'umask 077',
        'share="$HOME/.local/share"',
        'cache="$HOME/.cache/oma-voice"',
        'mkdir -p "$share/oma-voice" "$share/oma-speak" "$HOME/.local/bin" "$cache"',
        'exec >>"$cache/setup.log" 2>&1',
        'say() { printf \'%s\' "$1" > "$cache/setup-state"; }',
        '# Written beside the old file and moved over it, so a running copy is never half written.',
        'put() { cat > "$1.new" && mv -f "$1.new" "$1" || { say failed; exit 1; }; }',
        'say installing',
    ]
    executables = []
    for number, (file, target, executable) in enumerate(payload_files()):
        text = file.read_text().replace('\r\n', '\n')
        end = 'OMA_VOICE_FILE_%d_END' % number
        if '"""' in text or end in text:
            sys.exit('%s contains text the widget file cannot hold (\'"""\' or %s)' % (file, end))
        lines += ['put "$HOME/%s" <<\'%s\'' % (target, end), text.rstrip('\n'), end]
        if executable:
            executables.append('"$HOME/%s"' % target)
    lines += [
        'chmod u+x '+' '.join(executables),
        'venv="$share/oma-voice/venv"',
        '[ -x "$venv/bin/python" ] || python -m venv "$venv" || { say failed; exit 1; }',
        '# Without the network this fails and speech stays offline (espeak-ng) until the next setup.',
        '"$venv/bin/python" -m pip install --quiet --disable-pip-version-check %s || echo "edge-tts was not installed"' % requirement(),
        '# Stop the old voice service and dictation page; the widget starts the new ones.',
        # No -u: under proot id says 0 while the processes keep the app's real user, so it matched nothing.
        *('pkill -f \'%s\' || true' % pattern for pattern in SERVICES),
        'printf \'%%s\' \'%s\' > "$HOME/%s"' % (payload_id(), MARKER),
        'say done',
    ]
    script = '\n'.join(lines)
    # pkill -f must not match the shell running this script, whose command line holds all of the above.
    if any(re.search(pattern, wrapper+script) for pattern in SERVICES for wrapper in ('bash -c ', 'sh -c ', '')):
        sys.exit('the setup script would stop itself')
    return script


def render(template):
    """The widget as installed: the same text for install.py and the store."""
    text = template.replace('\r\n', '\n')
    text = text.replace('__VERSION__', VERSION).replace('__PAYLOAD_ID__', payload_id())
    text = text.replace('__SETUP_COMMAND__', '\n'+setup_script()+'\n')
    if '__' in re.sub(r'__(file|name|doc|main)__', '', text.split('"""')[0]):
        sys.exit('a placeholder was left in the widget')
    return text


def build(out=ROOT/'store'/'widgets'/AUTHOR):
    written = {}
    for template, name in WIDGETS.items():
        folder = out/name
        folder.mkdir(parents=True, exist_ok=True)
        data = render((ROOT/'widgets'/template).read_text()).encode()
        if len(data) > MAX_BYTES:
            sys.exit('%s is %d KB; the store limit is %d KB' % (name, len(data)//1024, MAX_BYTES//1024))
        (folder/'widget.owl').write_bytes(data)
        written[name] = len(data)
    return written


if __name__ == '__main__':
    for name, size in build().items():
        print('store/widgets/%s/%s/widget.owl  %d KB  payload %s' % (AUTHOR, name, size//1024, payload_id()))
