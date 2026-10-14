#!/usr/bin/env python3
"""Prepare safe English OWL demos, then capture the launcher's actual rendering.

Run with a Python environment containing Pillow. Nothing is uploaded.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from build_store import VERSION

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/screenshots'
WIDGET_DIR = Path.home() / '.config/omalauncher/widgets'
LIMIT = 300_000  # Stricter than 300 KiB.
WIDGETS = {'46-speak.owl': 'terminal-voice', '47-voice-input.owl': 'dictation'}


def demo_name(name):
    return 'preview-en-' + name + '-3x4.owl'


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    data = dict(source='terminal', source_name='Claude', awaiting=False,
                status_ui='Terminal connected', reply_at=1791964800,
                summary='Build complete. All checks passed. Ready to review the changes.',
                full='Build complete.\nAll checks passed.\nReady to review the changes.',
                error_ui='', engine='online', mode='summary', auto=False,
                pause_minutes=10, follow_latest=True)
    for template, name in WIDGETS.items():
        text = (ROOT / 'widgets' / template).read_text()
        # Use the actual widget layout, with fixed example data and no setup payload.
        text = re.sub(r'_\("((?:[^"\\]|\\.)*)"\)', r'"\1"', text)
        text = text.replace('__VERSION__', VERSION).replace('__PAYLOAD_ID__', 'demo')
        text = text.replace('__LANGUAGE_NEXT__', '"en"').replace('__LANGUAGE_NAME__', '"English"').replace('__LANGUAGE_SHORT__', '"EN"')
        text = text.replace('run("""__SETUP_COMMAND__""")', 'copy("Preview only")')
        text = re.sub(r'run\("(?:[^"\\]|\\.)*"\)', 'copy("Preview only")', text)
        text = text.replace('sending = true; result = copy("Preview only")', 'result = ""; copy("Preview only")')
        replacements = {
            'source uiLanguage': 'let uiLanguage = "en"',
            'source installed': 'let installed = "demo"',
            'source setupState': 'let setupState = ""',
            'source service': 'let demo = true',
            'let offline': 'let offline = false',
            'source voice': 'let voice = parseJson(' + json.dumps(json.dumps(data)) + ')',
            'source latest': 'let latest = "Review the changes and suggest the next steps."',
        }
        lines = []
        for line in text.splitlines():
            for prefix, replacement in replacements.items():
                if line.strip().startswith(prefix + ' '):
                    line = '  ' + replacement
                    break
            lines.append(line)
        text = '\n'.join(lines) + '\n'
        text = re.sub(r'page: 1', 'page: 3', text, count=1)
        text = re.sub(r'order: \d+', 'order: ' + ('1' if name == 'terminal-voice' else '2'), text, count=1)
        assert not re.search(r'^\s*source\s|\brun\(', text, re.M), 'Demo must have no live sources or shell commands'
        assert '__' not in text
        target = WIDGET_DIR / demo_name(name)
        target.write_text(text)
        print(target, flush=True)
    return [WIDGET_DIR / demo_name(name) for name in WIDGETS.values()]


def capture(widgets):
    from PIL import Image, ImageDraw, ImageFont
    subprocess.run(['owl-check', *map(str, widgets)], check=True)
    manifest = []
    for widget, name in zip(widgets, WIDGETS.values()):
        source = WIDGET_DIR / '.preview' / (widget.name + '.png')
        im = Image.open(source).convert('RGB')
        target = OUT / (name + '.png')
        im.save(target, optimize=True)
        if target.stat().st_size >= LIMIT:
            im.quantize(colors=128).save(target, optimize=True)
        assert target.stat().st_size < LIMIT, f'{target} exceeds 300 KB'
        manifest.append(dict(file=target.name, bytes=target.stat().st_size,
                             pixels=list(im.size), sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        screen = WIDGET_DIR / '.preview' / (widget.name + '.screen.png')
        if screen.exists():
            details = Image.open(screen).convert('RGB')
            details_path = OUT / (name + '-details.png')
            details.save(details_path, optimize=True)
            if details_path.stat().st_size >= LIMIT:
                details.quantize(colors=128).save(details_path, optimize=True)
            assert details_path.stat().st_size < LIMIT
    # A compact local contact sheet, with original aspect ratios and no cropped text.
    canvas = Image.new('RGB', (1080, 960), '#0b0e17')
    draw = ImageDraw.Draw(canvas)
    font_path = '/usr/share/fonts/TTF/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, 27)
    small = ImageFont.truetype(font_path, 19)
    draw.text((32, 22), 'OMALAUNCHER TOOLS / ENGLISH PREVIEW', font=font, fill='#78ffa2')
    draw.text((32, 65), 'Sample data · actual launcher rendering', font=small, fill='#c0c7dc')
    for x, name in ((24, 'terminal-voice'), (552, 'dictation')):
        im = Image.open(OUT / (name + '.png')).convert('RGB')
        im.thumbnail((504, 760), Image.Resampling.LANCZOS)
        canvas.paste(im, (x + (504 - im.width) // 2, 116))
        draw.text((x + 12, 900), name + ' · ' + str((OUT / (name + '.png')).stat().st_size // 1000) + ' KB', font=small, fill='#c0c7dc')
    canvas.save(OUT / 'overview.png', optimize=True)
    assert (OUT / 'overview.png').stat().st_size < LIMIT
    for path in (OUT / 'overview.png', OUT / 'terminal-voice-details.png', OUT / 'dictation-details.png'):
        if path.exists():
            with Image.open(path) as im:
                manifest.append(dict(file=path.name, bytes=path.stat().st_size,
                                     pixels=list(im.size), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (OUT / 'index.html').write_text('''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Omalauncher Tools — English previews</title>
<style>body{background:#0b0e17;color:#dee5f2;font:16px system-ui;margin:32px auto;padding:0 20px;max-width:1100px}h1{color:#78ffa2}main{display:flex;gap:24px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:250px}img{display:block;width:100%;height:auto}figcaption{padding:16px 0;line-height:1.6}a{color:#78ffa2}</style>
<h1>Omalauncher Tools / English previews</h1>
<p>Fixed English sample data, rendered by the launcher. Each PNG is below 300 KB.</p>
<main>''' + ''.join('<figure><a href="{0}"><img src="{0}" alt="{1} English widget preview"></a><figcaption>{1} · {2:,} bytes · {3} × {4} px · <a href="{5}-details.png">Details</a></figcaption></figure>'.format(item['file'], name.replace('-', ' ').title(), item['bytes'], *item['pixels'], name) for item, name in zip(manifest, WIDGETS.values())) + '</main></html>\n')
    print(json.dumps(manifest, indent=2))


def cleanup(widgets):
    for widget in widgets:
        for path in (widget, WIDGET_DIR / '.check' / (widget.name + '.txt'),
                     WIDGET_DIR / '.check' / (widget.name + '.want'),
                     WIDGET_DIR / '.errors' / (widget.name + '.txt'),
                     WIDGET_DIR / '.preview' / (widget.name + '.png'),
                     WIDGET_DIR / '.preview' / (widget.name + '.screen.png')):
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    widgets = prepare()
    capture(widgets)
    cleanup(widgets)
