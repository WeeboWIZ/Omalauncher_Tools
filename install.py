#!/usr/bin/env python3
"""Install/update per-user files; never copy conversations or personal config."""
import argparse
import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'tools'))
import build_store

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-deps', action='store_true', help='Dependencies already installed')
    args = parser.parse_args()
    home = Path.home()
    if not args.skip_deps:
        if not shutil.which('pacman'):
            sys.exit('Requires Omalauncher Arch Linux. Install Python, curl, util-linux, espeak-ng, libpulse first, then --skip-deps.')
        cmd = ['pacman', '-S', '--needed', '--noconfirm', 'python', 'curl', 'util-linux', 'espeak-ng', 'libpulse', 'mpg123', 'tmux']
        if os.geteuid() != 0:
            cmd.insert(0, 'sudo')
        subprocess.run(cmd, check=True)
    venv = home / '.local/share/oma-voice/venv'
    if not args.skip_deps:
        if not (venv/'bin/python').exists():
            subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
        subprocess.run([str(venv/'bin/python'), '-m', 'pip', 'install', '-r', str(ROOT/'requirements.txt')], check=True)
    backup = home / '.local/share/oma-voice/install-backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    installed = []
    def write(relative, data, executable=False):
        target = home / relative
        if target.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name+'.install-tmp')
        temp.write_bytes(data)
        temp.chmod(0o700 if executable else 0o600)
        temp.replace(target)
        installed.append(relative)
    # English became the default in 3.3: an earlier install that never chose a language stays Chinese.
    language = home / '.config/omalauncher/voice-ui-language'
    marker = home / build_store.MARKER
    before = marker.read_text().split('-')[0] if marker.exists() else ''
    earlier = before in ('3.0', '3.1', '3.2') or not before and (home / '.local/share/oma-voice/oma_voice.py').exists()
    if earlier and not language.exists():
        language.parent.mkdir(parents=True, exist_ok=True)
        language.write_text('zh')
    for folder, destination in [('voice', '.local/share/oma-voice'), ('dictation', '.local/share/oma-speak'), ('bin', '.local/bin')]:
        for file in sorted((ROOT/folder).iterdir()):
            if file.is_file():
                write(destination+'/'+file.name, file.read_bytes(), folder=='bin')
    if os.uname().machine == 'aarch64':
        subprocess.run([sys.executable, str(home/'.local/share/oma-voice/install_matcha.py')], check=False)
    for file in sorted((ROOT/'widgets').glob('*.owl')):
        write('.config/omalauncher/widgets/'+file.name, build_store.render(file.read_text()).encode())
    # The widgets show their own setup button until this names the programs they were built with.
    write(build_store.MARKER, build_store.payload_id().encode())
    print('Installed Terminal Voice and Dictation. Personal settings and conversation data were preserved.')
    print('Updated files backed up at:', backup)
    print('After updating an already-running version, restart Linux once to reload its voice service.')
    print('Open Details to choose Codex chat or a tmux terminal, then tap Sync.')
    print('Online voice sends reply text to Microsoft Edge TTS. Choose Voice: offline for local Matcha Chinese/English or espeak-ng fallback.')
    checker = shutil.which('owl-check')
    if checker and not args.skip_deps:
        for name in ('46-speak.owl', '47-voice-input.owl'):
            subprocess.run([checker, str(home/'.config/omalauncher/widgets'/name)], check=True)

if __name__ == '__main__':
    main()
