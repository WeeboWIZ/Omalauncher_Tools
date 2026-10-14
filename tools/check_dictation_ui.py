#!/usr/bin/env python3
"""Check the dictation UI with isolated browser fixtures.

Requires Playwright and Chromium. No microphone or actual drafts are used.
"""
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.cache/ui-checks'
PAGE = (ROOT / 'dictation/index.html').read_text()
MOCK = '''
window.__sessions=[];
class SpeechFixture {
 start(){window.__sessions.push(this);queueMicrotask(()=>this.onstart?.());}
 stop(){queueMicrotask(()=>this.onend?.());}
 abort(){queueMicrotask(()=>this.onend?.());}
}
window.SpeechRecognition=SpeechFixture;
Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{window.__copied=value;}}});
'''


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
        for code in ('en', 'zh', 'es', 'de', 'fr', 'ja', 'ko'):
            context = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2)
            context.add_init_script(MOCK)
            page = context.new_page()
            errors, saves = [], []
            selected = [code]
            page.on('pageerror', lambda error: errors.append(str(error)))
            def route(request):
                path = urlparse(request.request.url).path
                if path == '/language':
                    if request.request.method == 'POST':
                        selected[0] = request.request.post_data_json['language']
                    request.fulfill(status=200, body=selected[0], content_type='text/plain')
                elif path == '/text':
                    saves.append(request.request.post_data_json['text'])
                    request.fulfill(status=200, body='Saved')
                elif path == '/':
                    request.fulfill(status=200, body=PAGE, content_type='text/html; charset=utf-8')
                else:
                    request.fulfill(status=404, body='Not found')
            page.route('**/*', route)
            page.goto('http://127.0.0.1:18763/#preview-only')
            page.wait_for_function('(code)=>document.documentElement.lang === (code === "zh" ? "zh-Hant" : code)', arg=code)
            for width in (320, 360, 390, 640):
                page.set_viewport_size({'width': width, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (code, width)
                assert page.evaluate('[...document.querySelectorAll("button,select")].every(e=>e.scrollWidth <= e.clientWidth + 1)'), (code, width, 'clipped control')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert 'OMALAUNCHER' not in page.locator('main').inner_text()
            page.locator('#start').click()
            page.wait_for_function('document.body.dataset.listening === "true"')
            page.evaluate('''()=>{const r=window.__sessions.at(-1);const result=[{transcript:"Review the changes and suggest the next steps."},{transcript:"Review the changes."}];result.isFinal=true;r.onresult({results:[result]});}''')
            page.locator('#stop').click()
            page.wait_for_function('document.body.dataset.listening === "false"')
            assert page.locator('#text').input_value() == 'Review the changes and suggest the next steps.'
            assert page.locator('#alternatives button').count() == 2
            page.locator('#text').fill('Review the changes and suggest the next steps.')
            page.locator('#copy').click()
            assert page.evaluate('window.__copied') == page.locator('#text').input_value()
            with page.expect_response(lambda response: response.url.endswith('/text') and response.request.method == 'POST') as response:
                page.locator('#save').click()
            assert response.value.status == 200
            page.wait_for_function('document.getElementById("status").textContent === localize("已保存至首頁")')
            assert saves == ['Review the changes and suggest the next steps.'], (code, saves)
            # Editing while listening stops the recognizer and keeps the draft.
            page.locator('#start').click()
            page.locator('#text').focus()
            page.wait_for_function('document.body.dataset.listening === "false"')
            draft = page.locator('#text').input_value()
            page.reload()
            assert page.locator('#text').input_value() == draft
            page.locator('#clear').click()
            assert page.locator('#text').input_value() == ''
            assert page.evaluate('localStorage.getItem("oma-speak-draft")') == ''
            page.select_option('#ui-language', 'zh' if code == 'en' else 'en')
            page.wait_for_function('(value)=>document.documentElement.lang === value', arg='zh-Hant' if code == 'en' else 'en')
            assert not errors, (code, errors)
            report.append({'language': code, 'widths': [320, 360, 390, 640], 'flows': 'record, stop, edit, copy, save, restore, clear, language switch'})
            context.close()
        browser.close()
    (OUT / 'dictation-ui-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
