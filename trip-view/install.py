#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
'''Install Trip View independently of the other tools: the pixbg program, its scenes and the home-screen widget.'''
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PACKAGES = ['python', 'python-pillow', 'glslang', 'libpulse']
WIDGET = '30-trip-view.owl'


def install_app(home, link=False):
    '''Put app/ at ~/.local/share/pixbg. Scenes the user generated (scenes/ai-*.agsl) are kept.'''
    target = home / '.local/share/pixbg'
    if link:
        if target.is_symlink() or not target.exists():
            target.unlink(missing_ok=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(ROOT / 'app')
            return target
        sys.exit(f'{target} is a folder; move it away before --link')
    if target.is_symlink():
        target.unlink()
    shutil.copytree(ROOT / 'app', target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-deps', action='store_true', help='Required Arch packages are already installed')
    parser.add_argument('--link', action='store_true', help='Link ~/.local/share/pixbg to this checkout instead of copying (for development)')
    parser.add_argument('--no-check', action='store_true', help="Don't run owl-check after installing the widget")
    args = parser.parse_args()
    home = Path.home()
    if not args.skip_deps:
        if not shutil.which('pacman'):
            parser.error('Requires Omalauncher Arch Linux; use --skip-deps only if dependencies are present.')
        cmd = ['pacman', '-S', '--needed', '--noconfirm'] + PACKAGES
        if os.geteuid() != 0:
            cmd.insert(0, 'sudo')
        subprocess.run(cmd, check=True)

    app = install_app(home, args.link)
    tool = app / 'pixbg.py'
    tool.chmod(0o755)
    bin_dir = home / '.local/bin'
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in ('pixbg', 'tripview'):
        link = bin_dir / name
        link.unlink(missing_ok=True)
        link.symlink_to(tool)

    # Every scene is checked offline (compile, AGSL rules, GPU cost) while it is bundled.
    subprocess.run([sys.executable, str(tool), 'bundle'], check=True)

    widgets = home / '.config/omalauncher/widgets'
    widgets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'widgets' / WIDGET, widgets / WIDGET)
    print('Trip View is on page 3 of the home screen. Tap it for the full-screen page; "Set wallpaper" there also measures the screen for scene previews.')

    checker = shutil.which('owl-check')
    if checker and not args.no_check:
        subprocess.run([checker, str(widgets / WIDGET)], check=True)
        # Scene card previews need the screen measured once (it happens on the first "Set wallpaper").
        if (home / '.cache/pixbg/screen-box.json').exists():
            subprocess.run([sys.executable, str(tool), 'thumbs'], check=False)


if __name__ == '__main__':
    main()
