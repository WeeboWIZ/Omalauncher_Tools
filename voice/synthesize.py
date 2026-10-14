'''Edge TTS without API keys; local Matcha or espeak-ng fallback. Reads text on stdin.'''
import asyncio
import json
import os
import re
import subprocess
import shutil
from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from language import spoken

# The voice for each language a text can be spoken in: (Microsoft Edge online, espeak-ng offline).
SPEAKERS = {
    'en': ('en-US-AriaNeural', 'en-us'), 'zh': ('zh-CN-XiaoxiaoNeural', 'cmn'), 'es': ('es-ES-ElviraNeural', 'es'),
    'de': ('de-DE-KatjaNeural', 'de'), 'fr': ('fr-FR-DeniseNeural', 'fr'), 'ja': ('ja-JP-NanamiNeural', 'ja'),
    'ko': ('ko-KR-SunHiNeural', 'ko'),
}

# Why online speech was skipped, shown beside the offline voice's name.
NOT_INSTALLED = '線上語音未安裝'
NO_MPG123 = '缺少 mpg123'
UNREACHABLE = '線上語音無回應'

def offline(text, output, reason=''):
    note = '（'+reason+'）' if reason else ''
    runtime = ROOT / 'tts/sherpa-onnx-v1.13.8-linux-aarch64-shared-cpu/bin/sherpa-onnx-offline-tts'
    model = ROOT / 'tts/matcha-icefall-zh-en'
    if spoken(text) in ('zh', 'en') and runtime.exists() and (model / 'model-steps-3.onnx').exists() and (model / 'vocos-16khz-univ.onnx').exists():
        Path(str(output)+'.backend').write_text('離線神經語音'+note)
        os.execv(str(runtime), [str(runtime), '--matcha-acoustic-model='+str(model/'model-steps-3.onnx'),
                 '--matcha-vocoder='+str(model/'vocos-16khz-univ.onnx'),
                 '--matcha-tokens='+str(model/'tokens.txt'), '--matcha-lexicon='+str(model/'lexicon.txt'),
                 '--matcha-data-dir='+str(model/'espeak-ng-data'), '--num-threads=2',
                 '--tts-rule-fsts='+','.join(str(model/name) for name in ('phone-zh.fst','date-zh.fst','number-zh.fst')),
                 '--output-filename='+str(output), '--', text])
    Path(str(output)+'.backend').write_text('離線基本語音'+note)
    os.execvp('espeak-ng', ['espeak-ng', '-v', SPEAKERS[spoken(text)][1], '-s', '175', '-w', str(output), '--', text])

def pieces(text, limit=1200):
    # One request per piece: a long reply in one request ran past the time limit and fell back to espeak-ng.
    parts, current = [], ''
    for sentence in re.findall(r'[^。！？!?；;\n]*[。！？!?；;\n]+|[^。！？!?；;\n]+', text):
        while len(sentence) > limit:
            parts.append(current+sentence[:limit-len(current)])
            sentence, current = sentence[limit-len(current):], ''
        if len(current)+len(sentence) > limit:
            parts.append(current)
            current = ''
        current += sentence
    return [part for part in parts+[current] if part.strip()]

async def fetch(edge_tts, text, voice):
    audio = b''
    async for chunk in edge_tts.Communicate(text, voice=voice, rate='-5%').stream():
        if chunk['type'] == 'audio':
            audio += chunk['data']
    if not audio:
        raise RuntimeError('no audio')
    return audio

async def online(text, output):
    import edge_tts
    if not shutil.which('mpg123'):
        raise FileNotFoundError('mpg123')
    mp3 = output.with_suffix('.mp3')
    try:
        voice = SPEAKERS[spoken(text)][0]
        with mp3.open('wb') as audio:
            for part in pieces(text):
                for attempt in range(3):
                    try:
                        audio.write(await asyncio.wait_for(fetch(edge_tts, part, voice), timeout=30))
                        break
                    except Exception:
                        # A dropped connection is common on a phone; espeak-ng is the last resort.
                        if attempt == 2:
                            raise
                        await asyncio.sleep(1)
        subprocess.run(['mpg123', '-q', '-w', str(output), str(mp3)], check=True, timeout=120)
        Path(str(output)+'.backend').write_text('自然語音（線上）')
    finally:
        mp3.unlink(missing_ok=True)

if __name__ == '__main__':
    output = Path(sys.argv[1])
    text = sys.stdin.read().strip()
    if not text:
        raise SystemExit('沒有可播放的文字')
    config = json.loads((Path.home()/'.config/omalauncher/voice.json').read_text())
    reason = ''
    if config.get('engine') != 'offline':
        try:
            asyncio.run(online(text, output))
            raise SystemExit(0)
        except Exception as error:
            reason = NOT_INSTALLED if isinstance(error, ImportError) else NO_MPG123 if isinstance(error, FileNotFoundError) else UNREACHABLE
            print('線上語音不可用，改用離線：'+type(error).__name__+' '+str(error)[:200], file=sys.stderr)
            output.unlink(missing_ok=True)
    offline(text, output, reason)
