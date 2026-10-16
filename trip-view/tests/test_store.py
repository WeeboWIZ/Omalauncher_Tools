# SPDX-License-Identifier: MIT
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build_store
sys.path.insert(0, str(ROOT / 'app'))
import pixbg


class Store(unittest.TestCase):
    def run_setup(self, home, check=True):
        return subprocess.run(['bash', '-c', build_store.setup_script()],
                              env=dict(os.environ, HOME=str(home)), capture_output=True, text=True, check=check)

    def test_clean_install_update_and_agent_choice(self):
        with tempfile.TemporaryDirectory(prefix='trip-view-test-') as d:
            home = Path(d)
            self.run_setup(home)
            cache = home / '.cache/pixbg'
            app = home / '.local/share/pixbg'
            self.assertEqual([p.name for p in (app / 'lang').iterdir()], ['en.json'])
            ui = json.loads((cache / 'ui.json').read_text())
            self.assertEqual(ui['code'], 'en')
            self.assertEqual(set(ui['packs']), {'en'})
            self.assertEqual(len(json.loads((cache / 'bundle.json').read_text())['scenes']), 7)
            self.assertEqual((cache / 'store-version').read_text(), build_store.payload_id())
            self.assertEqual((app / 'pixbg.py').read_text(), build_store.payload()['.local/share/pixbg/pixbg.py'])
            env = dict(os.environ, HOME=str(home))
            for agent in ['codex', 'claude']:
                subprocess.run([sys.executable, str(app / 'pixbg.py'), 'agent', agent], env=env, check=True, capture_output=True)
                cfg = json.loads((home / '.config/pixbg/config.json').read_text())
                self.assertEqual(cfg, {'agent': agent, 'model': ''})
                self.assertEqual(json.loads((cache / 'ui.json').read_text())['agent'], agent)
            bad = subprocess.run([sys.executable, str(app / 'pixbg.py'), 'agent', 'other'], env=env, capture_output=True)
            self.assertNotEqual(bad.returncode, 0)
            generated = app / 'scenes/ai-mine.agsl'
            generated.write_text('// name: MINE\nhalf4 main(float2 p) { return half4(1.0); }\n')
            custom = app / 'lang/zh.json'
            custom.write_text((app / 'lang/en.json').read_text())
            (cache / 'lang').write_text('zh')
            old = (app / 'pixbg.py').read_text()
            (app / 'pixbg.py').write_text('# older installed program\n')
            self.run_setup(home)
            self.assertEqual((app / 'pixbg.py').read_text(), old)
            self.assertTrue(generated.exists())
            self.assertTrue(custom.exists())
            self.assertEqual((cache / 'lang').read_text(), 'zh')
            self.assertEqual(json.loads((home / '.config/pixbg/config.json').read_text())['agent'], 'claude')
            backups = list((cache / 'install-backups').glob('*/.local/share/pixbg/pixbg.py'))
            self.assertTrue(any(p.read_text() == '# older installed program\n' for p in backups))
            self.assertFalse((home / '.config/omalauncher/widgets').exists())

    def test_linked_checkout_is_not_modified(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            checkout = home / 'checkout'
            checkout.mkdir()
            (checkout / 'pixbg.py').write_text('keep me')
            share = home / '.local/share'
            share.mkdir(parents=True)
            (share / 'pixbg').symlink_to(checkout)
            result = self.run_setup(home, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((checkout / 'pixbg.py').read_text(), 'keep me')
            self.assertEqual((home / '.cache/pixbg/setup-state').read_text(), 'failed')
            self.assertFalse((home / '.cache/pixbg/store-version').exists())

    def test_reproducible_size_and_language_payload(self):
        self.assertEqual(build_store.render(), build_store.render())
        self.assertLess(len(build_store.render().encode()), 256 * 1024)
        self.assertNotIn('.local/share/pixbg/lang/zh.json', build_store.payload())
        self.assertIn('.local/share/pixbg/LICENSE', build_store.payload())


class Agents(unittest.TestCase):
    def test_provider_and_default_model_arguments(self):
        result = subprocess.CompletedProcess([], 0, '```agsl\nhalf4 main(float2 p) { return half4(1.0); }\n```', '')
        with tempfile.TemporaryDirectory() as d, patch.object(pixbg, 'CACHE', d), patch.object(pixbg.shutil, 'which', return_value='/bin/provider'), patch.object(pixbg.subprocess, 'run', return_value=result) as run:
            for agent in ['codex', 'claude']:
                code = pixbg.ask_agent('test', {'agent': agent, 'model': ''})
                args = run.call_args.args[0]
                self.assertEqual(args[0], agent)
                self.assertNotIn('--model', args)
                self.assertNotIn('-m', args)
                self.assertIn('main', code)
            pixbg.ask_agent('test', {'agent': 'codex', 'model': 'custom-model'})
            self.assertIn('custom-model', run.call_args.args[0])

    def test_missing_cli_does_not_launch(self):
        with patch.object(pixbg.shutil, 'which', return_value=None), patch.object(pixbg, 'M', side_effect=lambda key, **kw: 'Install ' + kw['agent']), patch.object(pixbg.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'Install Codex'):
                pixbg.ask_agent('test', {'agent': 'codex'})
            run.assert_not_called()
