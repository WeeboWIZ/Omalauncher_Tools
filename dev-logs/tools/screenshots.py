#!/usr/bin/env python3
'''Capture the real launcher layout with fixed English examples, never user data.

Requires Pillow only for PNG compression. Temporary demo widgets are removed.
'''
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from build_store import ROOT, STORE, VERSION

OUT = ROOT / 'docs/screenshots'
WIDGETS = Path.home() / '.config/omalauncher/widgets'
LIMIT = 300_000


def literal(value):
    return 'parseJson(' + json.dumps(json.dumps(value, ensure_ascii=False), ensure_ascii=False) + ')'


def inert_handlers(text):
    pattern = re.compile(r'\b(?:onTap|onChange|onSubmit):\s*')
    cursor = 0
    result = ''
    while found := pattern.search(text, cursor):
        result += text[cursor:found.end()] + '{}'
        start = i = found.end()
        block = text[start] == '{'
        depth = 0
        while i < len(text):
            if text[i] == '"':
                quote = '"""' if text.startswith('"""', i) else '"'
                i += len(quote)
                while i < len(text):
                    if text[i] == '\\':
                        i += 2
                    elif text.startswith(quote, i):
                        i += len(quote)
                        break
                    else:
                        i += 1
                continue
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                if depth == 0:
                    break
                depth -= 1
                if block and depth == 0:
                    i += 1
                    break
            elif not block and depth == 0 and text[i] in ';\n':
                break
            i += 1
        cursor = i
    return result + text[cursor:]


def fixture():
    logs = [
        dict(id='1', project='Sample App', text='14:20 · Added daily journal browsing over monthly Markdown files. Date switching and pagination checks passed.'),
        dict(id='2', project='Sample App', text='11:05 · Added per-report copying and error filters. Verified that warnings remain available under All.'),
        dict(id='3', project='Notes Site', text='09:10 · Added Markdown editing and trash recovery. File-operation checks passed; device review remains pending.'),
    ]
    entry = dict(id=1, time='2026-10-01T14:15:00+00:00', name='sample-app.log',
                 source='/home/demo/oma-devlogs/logs/terminals/sample-app.log', level='error',
                 summary='Example: command exited with code 1',
                 text='Example diagnostic\nCommand exited with code 1.\nCheck the local configuration and retry.',
                 report='Example report only')
    return {
        'installed': '"demo"', 'setupState': '""',
        'snapshot': literal(dict(ok=True, out=dict(notes=4, entries=8, latest='14:20 · Sample App: daily logs added; checks passed.', updated='14:20:00',
                                                 home='/home/demo', projects='/home/demo/projects', root='/home/demo/oma-devlogs'))),
        'archive': literal(dict(ok=True, out=dict(days=['2026-10-01', '2026-09-30'], day='2026-10-01', entries=logs, total=3, more=False,
                                                all=8, unassigned=0, projects=[dict(name='Sample App', count=5), dict(name='Notes Site', count=3)]))),
        'directory': literal(dict(ok=True, out=dict(path='/home/demo/projects', parent='/home/demo', total=6, more=False,
            crumbs=[dict(name='~', path='/home/demo'), dict(name='projects', path='/home/demo/projects')], items=[
            dict(name='sample-app', path='/home/demo/projects/sample-app', dir=True, size=0, count=12, kind='folder'),
            dict(name='notes-site', path='/home/demo/projects/notes-site', dir=True, size=0, count=7, kind='folder'),
            dict(name='archive', path='/home/demo/projects/archive', dir=True, size=0, count=0, kind='folder'),
            dict(name='architecture.md', path='/home/demo/projects/architecture.md', dir=False, size=1850, link=False, kind='md'),
            dict(name='release-checklist.md', path='/home/demo/projects/release-checklist.md', dir=False, size=940, link=False, kind='md'),
            dict(name='build.sh', path='/home/demo/projects/build.sh', dir=False, size=420, link=False, kind='code'),
        ]))),
        'found': literal(dict(ok=True, out={})),
        'agentInfo': literal(dict(installed=True, name='Claude Code', batch=True)),
        'agentState': literal({}),
        'systemErrors': literal(dict(ok=True, out=dict(total=1, all_total=3, error_total=1, counts=dict(error=1, warning=1, info=1), entries=[entry], more=False))),
    }


def prepare(name, tab='logs'):
    text = (ROOT / 'widgets/65-dev-logs.owl').read_text()
    text = text.replace('__VERSION__', VERSION).replace('__PAYLOAD_ID__', 'demo').replace('__SETUP_COMMAND__', 'true')
    for source, expression in fixture().items():
        text = re.sub(r'^\s*source ' + source + r' = .*$', lambda _: '  let ' + source + ' = ' + expression, text, flags=re.M)
    text = text.replace('state tab = "logs"', 'state tab = ' + json.dumps(tab))
    if tab == 'errors':
        text = text.replace('state expandedError = 0', 'state expandedError = 1')
    text = text.replace('page: 2', 'page: 3')
    text = inert_handlers(text)
    assert not re.search(r'^\s*source\s|\b(?:run|terminal|app)\(', text, re.M)
    path = WIDGETS / ('preview-en-dev-logs-' + name + '.owl')
    path.write_text(text)
    return path


def capture(path, name, screen=True):
    from PIL import Image
    subprocess.run(['owl-check', str(path)], check=True)
    source = WIDGETS / '.preview' / (path.name + ('.screen.png' if screen else '.png'))
    # The first off-screen composition can precede the font/layout settling.
    # Request a fresh render after the initial check and wait for its actual PNG.
    time.sleep(2)
    check = WIDGETS / '.check' / (path.name + '.txt')
    previous_check = check.stat().st_mtime_ns
    (WIDGETS / '.check' / (path.name + '.want')).write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    for _ in range(200):
        time.sleep(0.1)
        if check.stat().st_mtime_ns != previous_check:
            break
    else:
        raise RuntimeError('Timed out waiting for refreshed preview: ' + path.name)
    target = OUT / (name + '.png')
    with Image.open(source) as image:
        image = image.convert('RGB')
        image.save(target, optimize=True)
        if target.stat().st_size >= LIMIT:
            image.quantize(colors=128).save(target, optimize=True)
        pixels = list(image.size)
    if target.stat().st_size >= LIMIT:
        raise ValueError(f'{target} exceeds 300 KB')
    return dict(file=target.name, bytes=target.stat().st_size, pixels=pixels,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest())


def cleanup(path):
    for relative in (path.name, '.check/' + path.name + '.txt', '.check/' + path.name + '.want',
                     '.errors/' + path.name + '.txt', '.preview/' + path.name + '.png', '.preview/' + path.name + '.screen.png'):
        (WIDGETS / relative).unlink(missing_ok=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, tab in [('logs', 'logs'), ('files', 'files'), ('errors', 'errors'), ('settings', 'settings')]:
        path = prepare(name, tab)
        try:
            subprocess.run(['owl-check', str(path)], check=True)
            subprocess.run(['owl-send', str(path), 'set', 'tab', tab], check=True)
            if tab == 'errors':
                subprocess.run(['owl-send', str(path), 'set', 'expandedError', '1'], check=True)
            if name == 'logs':
                manifest.append(capture(path, 'dev-logs', screen=False))
            manifest.append(capture(path, name))
        finally:
            cleanup(path)
    STORE.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT / 'dev-logs.png', STORE / 'preview.png')
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
