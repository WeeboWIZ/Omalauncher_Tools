#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WeeboWIZ
'''Build the English-only, self-contained Trip View store widget.'''
import ast
import io
import tokenize
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT.parent / 'store/widgets/weebowiz/trip-view'
VERSION = '1.5'


def runtime_text(path):
    text = path.read_text()
    if path.suffix == '.json':
        return json.dumps(json.loads(text), ensure_ascii=False, separators=(',', ':'))
    if path.suffix == '.py':
        # Strip documentation only, keeping executable statements and shader prompts intact.
        tree = ast.parse(text)
        lines = text.splitlines(keepends=True)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(node):
                doc = node.body[0]
                for i in range(doc.lineno - 1, doc.end_lineno):
                    lines[i] = '\n'
        text = ''.join(lines)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        text = tokenize.untokenize(t._replace(string='') if t.type == tokenize.COMMENT and 'SPDX' not in t.string and 'Copyright' not in t.string and not t.string.startswith('#!') else t for t in tokens)
        ast.parse(text)
    return text


def payload():
    paths = [ROOT / 'app' / n for n in ('pixbg.py', 'agslcheck.py', 'sfx.py', 'header.agsl', 'lang/en.json')]
    paths += sorted((ROOT / 'app/scenes').glob('*.agsl'))
    paths += sorted((ROOT / 'app/scenes').glob('*.actors.json'))
    result = {'.local/share/pixbg/' + p.relative_to(ROOT / 'app').as_posix(): runtime_text(p) for p in paths}
    result['.local/share/pixbg/LICENSE'] = (ROOT / 'LICENSE').read_text()
    return result


def payload_id():
    content = (ROOT / 'tools/store_setup.py').read_text() + repr(payload())
    return VERSION + '-' + hashlib.sha256(content.encode()).hexdigest()[:12]


def setup_script():
    # Escaping double quotes in Python string literals leaves the payload readable,
    # while keeping embedded docstrings from ending the OWL triple-quoted command.
    literal = repr(payload()).replace('"""', '\\x22\\x22\\x22')
    code = (ROOT / 'tools/store_setup.py').read_text() + '\ninstall_files(' + literal + ', ' + repr(payload_id()) + ')\n'
    if '"""' in code or '\nTRIP_VIEW_SETUP\n' in code:
        raise ValueError('Invalid setup delimiter')
    command = ('set -eu\numask 077\nmkdir -p "$HOME/.cache/pixbg"\n'
            'exec >>"$HOME/.cache/pixbg/setup.log" 2>&1\n'
            "python - <<'TRIP_VIEW_SETUP'\n" + code + 'TRIP_VIEW_SETUP')
    if len(command.encode()) > 120 * 1024:
        raise ValueError('Setup command exceeds the safe per-argument limit')
    return command


def render():
    text = (ROOT / 'widgets/30-trip-view.owl').read_text()
    text = re.sub(r'^  (page|order):.*\n', '', text, flags=re.M)
    text = text.replace('  padding: 0\n', '  padding: 0\n  requires { pacman: ["python", "python-pillow", "glslang", "libpulse", "bash", "coreutils"] }\n', 1)
    marker = '  onTap: { panel = true; screen() }'
    setup = '''  source installed = file("~/.cache/pixbg/store-version")
  source setupState = file("~/.cache/pixbg/setup-state")
  let ready = installed == "__PAYLOAD_ID__" && len(bundle.scenes ?? []) >= 7
  component Setup(compact = false) {
    Column {
      fill: width; padding: 18; gap: 12
      Text { text: "TRIP VIEW"; fontSize: compact ? 16 : 22; bold: true }
      if !compact {
      Text { text: setupState == "failed" ? "Setup failed. See ~/.cache/pixbg/setup.log, then retry." : setupState == "installing" ? "Installing and checking animations…" : "Install seven pixel animations and the local animation tools."; style: small; maxLines: 4 }
      Text { text: "Your animations and settings are preserved. No scripts are downloaded."; style: small; color: muted; maxLines: 3 }
      }
      Button { text: setupState == "installing" ? "Retry setup" : installed == "" ? "Set up" : "Update"; fill: width; onTap: run("""__SETUP_COMMAND__""") }
    }
  }

'''.replace('__PAYLOAD_ID__', payload_id()).replace('__SETUP_COMMAND__', setup_script())
    text = text.replace(marker, setup + marker, 1)
    # Wrap only the rendered content; retain the same components and behavior.
    a, b = text.split('\n  screen {', 1)
    start = a.index('\n  Box {', a.index(marker))
    a = a[:start] + '\n  if !ready { Setup { compact: tiny } } else {' + a[start:] + '\n  }\n'
    b = b.replace('    Box {', '    if !ready { Setup {} } else {\n    Box {', 1)
    tail = b.rfind('\n  }\n}')
    b = b[:tail] + '\n    }' + b[tail:]
    text = a + '\n  screen {' + b
    if len(text.encode()) > 256 * 1024:
        raise ValueError(f'Widget is too large: {len(text.encode())} bytes')
    return text


def build():
    STORE.mkdir(parents=True, exist_ok=True)
    p = STORE / 'widget.owl'
    p.write_text(render())
    p.chmod(0o644)
    print(f'{p}: {p.stat().st_size} bytes; {payload_id()}')
    return p


if __name__ == '__main__':
    build()
