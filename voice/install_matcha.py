'''Download the pinned sherpa-onnx runtime and Matcha zh-en model on ARM64.'''
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
TTS = ROOT / 'tts'
RUNTIME = 'sherpa-onnx-v1.13.8-linux-aarch64-shared-cpu'
MODEL = 'matcha-icefall-zh-en'
FILES = (
    ('https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/' + RUNTIME + '.tar.bz2',
     '4e3734f82bc1379fd91f219f5869c7e9d03b7a4f7561907d8abca4849c51a789', RUNTIME + '.tar.bz2'),
    ('https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/' + MODEL + '.tar.bz2',
     '271b804af570400d3bcdcb53bf6e53cc9f75180ee763b9f13eb5eaf2b0d086ef', MODEL + '.tar.bz2'),
    ('https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/vocos-16khz-univ.onnx',
     'b599142a1fb8ff03de3e84ac35ff537c619e56f4267a6fe894851a42844acf9e', 'vocos-16khz-univ.onnx'),
)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def download(url, path, expected):
    request = urllib.request.Request(url, headers={'User-Agent': 'Omalauncher-Terminal-Voice'})
    with urllib.request.urlopen(request, timeout=60) as response, path.open('wb') as output:
        shutil.copyfileobj(response, output)
    if digest(path) != expected:
        path.unlink(missing_ok=True)
        raise ValueError('SHA-256 mismatch for ' + url)


def extract(archive, destination):
    destination.mkdir(parents=True)
    subprocess.run(['tar', '-xjf', str(archive), '--no-same-owner', '--strip-components=1', '-C', str(destination)], check=True)


def install():
    if os.uname().machine != 'aarch64':
        print('Matcha is available on ARM64; other architectures keep the espeak-ng fallback.')
        return
    runtime = TTS / RUNTIME
    model = TTS / MODEL
    if (runtime / 'bin/sherpa-onnx-offline-tts').is_file() and (model / 'model-steps-3.onnx').is_file() and (model / 'vocos-16khz-univ.onnx').is_file():
        print('Matcha and sherpa-onnx are already installed.')
        return

    TTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.matcha-', dir=TTS) as temporary:
        temporary = Path(temporary)
        runtime_archive, model_archive, vocoder_archive = (temporary / name for _, _, name in FILES)
        for (url, expected, _), path in zip(FILES, (runtime_archive, model_archive, vocoder_archive)):
            print('Downloading ' + url.rsplit('/', 1)[-1])
            download(url, path, expected)
        runtime_stage, model_stage = temporary / 'runtime', temporary / 'model'
        extract(runtime_archive, runtime_stage)
        extract(model_archive, model_stage)
        shutil.copy2(vocoder_archive, model_stage / 'vocos-16khz-univ.onnx')
        required = ('model-steps-3.onnx', 'vocos-16khz-univ.onnx', 'lexicon.txt', 'tokens.txt', 'espeak-ng-data')
        if not (runtime_stage / 'bin/sherpa-onnx-offline-tts').is_file() or any(not (model_stage / name).exists() for name in required):
            raise RuntimeError('Downloaded Matcha files are incomplete')
        for source, target in ((runtime_stage, runtime), (model_stage, model)):
            old = target.with_name(target.name + '.old')
            shutil.rmtree(old, ignore_errors=True)
            if target.exists():
                target.replace(old)
            source.replace(target)
            shutil.rmtree(old, ignore_errors=True)
    print('Installed Matcha ' + MODEL + ' with the Vocos 16 kHz vocoder.')


if __name__ == '__main__':
    try:
        install()
    except Exception as error:
        print('Could not install offline Matcha: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
