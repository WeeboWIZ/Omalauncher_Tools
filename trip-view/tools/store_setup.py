# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WeeboWIZ
'''Install the reviewed text payload without downloading code or replacing user scenes.'''
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


def builtin_files(home, version):
    '''The five scenes, the shader header and the English pack, which the widget carries for use before
    setup (`let tripBuiltin`). Read from the installed widget file of this version and returned as files.'''
    quotes = '"' * 3          # spelled out: three quotes in a row would end the OWL string carrying this program
    start = '  let tripBuiltin = parseJson(' + quotes
    for owl in sorted((home / '.config/omalauncher/widgets').glob('*.owl')):
        text = owl.read_text(errors='replace')
        if start in text and 'installed == "' + version + '"' in text:
            data = json.loads(text.split(start, 1)[1].split(quotes + ')', 1)[0])
            break
    else:
        raise RuntimeError('The Trip View widget file was not found in ~/.config/omalauncher/widgets.')
    app = '.local/share/pixbg/'
    files = {app + 'header.agsl': data['header'],
             app + 'lang/en.json': json.dumps(data['lang'], ensure_ascii=False, indent=2) + '\n'}
    for scene in data['scenes']:
        if not re.fullmatch(r'[0-9a-z-]+', scene['id']):
            raise RuntimeError('Unexpected scene id: ' + scene['id'])
        files[app + 'scenes/' + scene['id'] + '.agsl'] = scene['body']
        if scene.get('actors') is not None:
            files[app + 'scenes/' + scene['id'] + '.actors.json'] = json.dumps(scene['actors'], ensure_ascii=False, separators=(',', ':'))
    return files


def install_files(files, version):
    home = Path.home()
    cache = home / '.cache/pixbg'
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / 'setup.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Setup is already running.')
            return
        state = cache / 'setup-state'
        state.write_text('installing')
        backup = cache / 'install-backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        try:
            files = dict(files, **builtin_files(home, version))
            # Do not follow developer checkouts or other redirected installation paths.
            targets = [home / name for name in files]
            targets += [home / '.local/bin' / name for name in ('pixbg', 'tripview')]
            for target in targets:
                for parent in target.parents:
                    if parent == home:
                        break
                    if parent.is_symlink():
                        raise RuntimeError('Setup found a linked directory: ' + str(parent) + '. Use your existing checkout to update it.')
            for relative, text in files.items():
                target = home / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    saved = backup / relative
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved, follow_symlinks=False)
                temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.install-tmp')
                try:
                    temporary.write_text(text, encoding='utf-8')
                    temporary.chmod(0o700 if target.name == 'pixbg.py' else 0o600)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
            tool = home / '.local/share/pixbg/pixbg.py'
            for name in ('pixbg', 'tripview'):
                target = home / '.local/bin' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    saved = backup / '.local/bin' / name
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved, follow_symlinks=False)
                temp = target.with_name(name + '.' + uuid.uuid4().hex + '.install-tmp')
                temp.symlink_to(tool)
                temp.replace(target)
            # English is the only bundled language. Never remove custom language packs.
            language = cache / 'lang'
            if not language.exists():
                language.write_text('en')
            subprocess.run([sys.executable, str(tool), 'bundle'], check=True, timeout=120)
            bundle = json.loads((cache / 'bundle.json').read_text())
            expected = {Path(p).stem for p in files if p.endswith('.agsl') and '/scenes/' in p}
            actual = {scene['id'] for scene in bundle['scenes']}
            if not expected <= actual:
                raise RuntimeError('Some built-in animations failed validation. Check setup.log.')
            (cache / 'store-version').write_text(version)
            state.write_text('done')
            print('Trip View is ready. Existing animations, languages and settings were preserved.')
            # The home tile's still (Neon Ramen for a new install), taken in the background. Taking it also
            # reloads the widget, so the tile leaves the setup screen even if the launcher missed the state file.
            if not os.environ.get('TRIP_VIEW_NO_BACKGROUND'):   # set by the tests, which have no launcher
                subprocess.run([sys.executable, str(tool), 'tile', '--cards'], check=False, timeout=30)
                # Which agent CLIs are installed and signed in, for the generator card.
                subprocess.Popen([sys.executable, str(tool), 'agents'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception:
            state.write_text('failed')
            raise
