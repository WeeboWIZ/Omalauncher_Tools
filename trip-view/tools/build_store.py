#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WeeboWIZ
'''Build the English-only, self-contained Trip View store widget.'''
import ast
import base64
import sys
import io
import tokenize
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT.parent / 'store/widgets/weebowiz/trip-view'
VERSION = '1.1'
# The tile before the local tools exist, and so the store's previews (a fresh 4×2 tile): Neon Ramen in
# palette 3 (the default) with TRIP VIEW on its sign, 4 px per cell (about 6 KB).
COVER = ROOT / 'store/cover.png'


def runtime_text(path):
    text = path.read_text()
    if path.suffix == '.agsl' and path.parent.name == 'scenes':
        # Scenes: drop indentation and comments (AGSL has no strings, so // always starts one),
        # but keep the metadata lines pixbg reads (name, prompt, mascot, tag) and the license header.
        out = []
        for line in text.splitlines():
            meta = re.match(r'\s*//\s*(name|prompt|mascot|tag|thumb|SPDX|Copyright)\b', line)
            line = line.strip() if meta else line.split('//', 1)[0].strip()
            if line:
                out.append(line)
        return '\n'.join(out) + '\n'
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
        # Outside multi-line strings (the agent prompts stay byte for byte): drop the blank lines that removed
        # docstrings and comments leave, and indent with one space per level instead of four.
        inside = set()
        for t in tokenize.generate_tokens(io.StringIO(text).readline):
            if t.type == tokenize.STRING and t.start[0] != t.end[0]:
                inside.update(range(t.start[0] + 1, t.end[0] + 1))
        out = []
        for n, line in enumerate(text.splitlines(), 1):
            if n in inside:
                out.append(line)
            elif line.strip():
                pad = len(line) - len(line.lstrip(' '))
                out.append(' ' * (pad // 4) + line.lstrip(' '))
        text = '\n'.join(out) + '\n'
        ast.parse(text)
    return text


def builtin():
    """What the widget needs before the local tools exist: the five scenes as the bundle lists them (with
    their shader bodies), the shader header and the English pack. Setup writes the same files from here,
    so the widget carries them once."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('pixbg_build', ROOT / 'app/pixbg.py')
    pixbg = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / 'app'))
    spec.loader.exec_module(pixbg)
    pixbg.DATA, pixbg.SCENES = str(ROOT / 'app'), str(ROOT / 'app/scenes')
    scenes = []
    for sc in pixbg.scenes():
        if sc['kind'] != 'preset':
            continue
        body = runtime_text(Path(sc['path']))
        e = pixbg.entry(sc, body)
        del e['code']
        e.update(body=body, thumb=None, tile=None)
        scenes.append(e)
    return {'header': runtime_text(ROOT / 'app/header.agsl'), 'scenes': scenes,
            'lang': json.loads(runtime_text(ROOT / 'app/lang/en.json'))}


def builtin_json():
    text = json.dumps(builtin(), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    if '"""' in text or '${' in text:
        raise ValueError('Built-in data would end or interpolate the OWL string')
    return text


def payload():
    paths = [ROOT / 'app' / n for n in ('pixbg.py', 'agslcheck.py', 'sfx.py')]
    result = {'.local/share/pixbg/' + p.relative_to(ROOT / 'app').as_posix(): runtime_text(p) for p in paths}
    result['.local/share/pixbg/LICENSE'] = (ROOT / 'LICENSE').read_text()
    return result


def payload_id():
    content = (ROOT / 'tools/store_setup.py').read_text() + repr(payload()) + builtin_json()
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
    q = '"' * 3

    def swap(old, new, count=1):
        nonlocal text
        if text.count(old) != count:
            raise ValueError(f'Expected {count} of {old!r} in the widget, found {text.count(old)}')
        text = text.replace(old, new)

    # Everything works right after install: the scenes, the shader header and the English pack are built in.
    # The local tools (pixbg: the agent, wallpapers, the tile's stills, card previews, the full-bleed page)
    # are installed in the background on the first tap, with the reviewed command below.
    swap('  source ui = file("~/.cache/pixbg/ui.json") json\n',
         '  source ui = file("~/.cache/pixbg/ui.json") json\n'
         '  asset tripCover = base64"__COVER__"\n'
         '  let tripBuiltin = parseJson(' + q + '__BUILTIN__' + q + ')\n'
         '  source installed = file("~/.cache/pixbg/store-version")\n'
         '  source setupState = file("~/.cache/pixbg/setup-state")\n'
         '  let ready = installed == "__PAYLOAD_ID__" && len(bundle.scenes ?? []) >= 5\n')
    swap('  let list = bundle.scenes ?? []', '  let list = ready ? bundle.scenes : tripBuiltin.scenes')
    # Until this version's tools are installed (a new install, or right after an update), the built-in pack is
    # the one that matches the widget's strings.
    swap('let LP = get(ui.packs ?? {}, lc, null) ?? get(ui.packs ?? {}, "en", {})',
         'let LP = !ready ? tripBuiltin.lang : get(ui.packs ?? {}, lc, null) ?? get(ui.packs ?? {}, "en", null) ?? tripBuiltin.lang')
    swap('cur.code ?? blank', 'cur.code ?? (cur.body != null ? tripBuiltin.header + cur.body : blank)')
    # Until pixbg has taken the tile's still, Neon Ramen rests on the built-in picture (TRIP VIEW on its sign).
    swap('else if (cur.tile ?? cur.thumb) != null',
         'else if (cur.tile ?? cur.thumb ?? (cur.id == "05-ramen" ? tripCover : null)) != null')
    swap('Image { src: cur.tile ?? cur.thumb; fill: true; fit: cover }',
         'Image { src: cur.tile ?? cur.thumb ?? tripCover; fill: true; fit: cover }')
    # Opening the page counts as a tap on the tile, so it starts the background install too.
    swap('onTap: { openedAt = now; panel = true; screen();', 'onTap: { liveAt = now; openedAt = now; panel = true; screen();', 2)
    marker = '  onTap: { liveAt = now; openedAt = now; panel = true; screen(); run(probeStale ? "~/.local/bin/pixbg agents" : "true") }'
    swap(marker,
         '  // The first tap installs the local tools in the background (about 2 s, nothing in the way);\n'
         '  // a failed install is retried on the next tap.\n'
         '  on liveAt { run(ready || setupState == "installing" ? "true" : ' + q + '__SETUP_COMMAND__' + q + ') }\n'
         + marker)
    # While the tools install, a line says so above the scene (the current scene's card stays at the bottom).
    spacer = '            Spacer { weight: 1 }   // 場景在這裡露出來\n'
    swap(spacer,
         '            if !ready {\n'
         '              Text { text: setupState == "failed" ? "Couldn\'t install the local tools (see ~/.cache/pixbg/setup.log). '
         'Close and reopen this page to try again." : "Getting the local tools ready for the agent, wallpapers and previews…"; '
         'style: small; color: setupState == "failed" ? "#ff6a6a" : soft; maxLines: 3; padding: [16, 0] }\n'
         '            }\n' + spacer)
    text = (text.replace('__COVER__', base64.b64encode(COVER.read_bytes()).decode())
            .replace('__BUILTIN__', builtin_json()).replace('__PAYLOAD_ID__', payload_id())
            .replace('__SETUP_COMMAND__', setup_script()))
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
