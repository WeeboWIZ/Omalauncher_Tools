# SPDX-License-Identifier: MIT
import importlib.util
import json
import re
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
# The program's own read-only data (shader header, language packs) comes from this checkout, not an installed copy.
pixbg.DATA, pixbg.LANGS = str(ROOT / 'app'), str(ROOT / 'app/lang')


class Store(unittest.TestCase):
    def run_setup(self, home, check=True):
        # Setup reads the built-in scenes from the installed widget file, as on a phone.
        widgets = home / '.config/omalauncher/widgets'
        widgets.mkdir(parents=True, exist_ok=True)
        (widgets / 'market-weebowiz-trip-view.owl').write_text(build_store.render())
        return subprocess.run(['bash', '-c', build_store.setup_script()],
                              env=dict(os.environ, HOME=str(home), TRIP_VIEW_NO_BACKGROUND='1'),
                              capture_output=True, text=True, check=check)

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
            self.assertEqual(len(json.loads((cache / 'bundle.json').read_text())['scenes']), 5)
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
            self.assertEqual([p.name for p in (home / '.config/omalauncher/widgets').iterdir()], ['market-weebowiz-trip-view.owl'])

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
    # Fake CLIs that speak each agent's streaming format and record their arguments.
    SHADER = '```agsl\\\\nhalf4 main(float2 p) { return half4(1.0); }\\\\n```'
    FAKE = {
        'claude': "echo '{\"type\":\"system\",\"subtype\":\"init\",\"model\":\"claude-test\"}'\n"
                  "echo '{\"type\":\"stream_event\",\"event\":{\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"%s\"}}}'\n"
                  "echo '{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"result\":\"%s\"}'" % (SHADER, SHADER),
        'codex': "echo '{\"type\":\"thread.started\"}'\n"
                 "echo '{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"%s\"}}'" % SHADER,
    }

    def fake(self, d, agent, body):
        path = Path(d) / agent
        path.write_text(f'#!/bin/sh\necho "$@" > "{d}/{agent}.args"\ncat > /dev/null\n{body}\n')
        path.chmod(0o755)
        return str(path)

    def test_provider_and_default_model_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            exes = {a: self.fake(d, a, body) for a, body in self.FAKE.items()}
            with patch.object(pixbg, 'find_cli', side_effect=lambda a: exes[a]), patch.object(pixbg, 'AGENT_CWD', d), \
                    patch.object(pixbg, 'MODELS', d + '/models.json'):
                for agent in ['codex', 'claude']:
                    seen = []
                    code = pixbg.ask_agent('test', {'agent': agent, 'model': ''}, lambda kind, **kw: seen.append(kind))
                    args = (Path(d) / f'{agent}.args').read_text().split()
                    self.assertNotIn('--model', args)
                    self.assertNotIn('-m', args)
                    self.assertIn('main', code)
                    self.assertIn('connected', seen)
                    self.assertIn('writing', seen)
                self.assertIn('--no-session-persistence', (Path(d) / 'claude.args').read_text())
                pixbg.ask_agent('test', {'agent': 'codex', 'model': 'custom-model'})
                self.assertIn('custom-model', (Path(d) / 'codex.args').read_text())

    def test_agent_errors_are_explained(self):
        with tempfile.TemporaryDirectory() as d:
            exe = self.fake(d, 'claude', "echo '{\"type\":\"result\",\"is_error\":true,\"result\":\"Invalid API key. Please run /login\"}'")
            with patch.object(pixbg, 'find_cli', return_value=exe), patch.object(pixbg, 'AGENT_CWD', d), patch.object(pixbg, 'MODELS', d + '/models.json'):
                with self.assertRaises(pixbg.AgentError) as e:
                    pixbg.ask_agent('test', {'agent': 'claude', 'model': ''})
                self.assertEqual(e.exception.kind, 'login')
                self.assertEqual(e.exception.fix, 'claude auth login')
        e = pixbg.explain('codex', 'You have hit your usage limit. Try again at 10:54 PM.')
        self.assertEqual(e.kind, 'busy')
        self.assertIn('10:54 PM', str(e))

    def test_stalled_agent_is_stopped(self):
        with tempfile.TemporaryDirectory() as d:
            exe = self.fake(d, 'claude', 'sleep 30')
            with patch.object(pixbg, 'find_cli', return_value=exe), patch.object(pixbg, 'AGENT_CWD', d), patch.object(pixbg, 'STALL', 1), patch.object(pixbg, 'MODELS', d + '/models.json'):
                with self.assertRaises(pixbg.AgentError):
                    pixbg.ask_agent('test', {'agent': 'claude', 'model': ''})

    def test_missing_cli_does_not_launch(self):
        with patch.object(pixbg, 'find_cli', return_value=None), patch.object(pixbg, 'M', side_effect=lambda key, **kw: 'Install ' + kw['agent']), patch.object(pixbg.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, 'Install Codex'):
                pixbg.ask_agent('test', {'agent': 'codex'})
            popen.assert_not_called()

    def test_model_names(self):
        self.assertEqual(pixbg.model_label('claude-opus-5-5', 'claude'), 'Opus 5.5')
        self.assertEqual(pixbg.model_label('claude-opus-5-5[1m]', 'claude'), 'Opus 5.5')
        self.assertEqual(pixbg.model_label('sonnet', 'claude'), 'Sonnet')
        self.assertEqual(pixbg.model_label('', 'codex'), 'Codex')
        with tempfile.TemporaryDirectory() as d, patch.object(pixbg, 'HOME', d), patch.object(pixbg, 'CONFIG', d + '/config.json'), \
                patch.object(pixbg, 'MODELS', d + '/models.json'), patch.dict(os.environ, {'ANTHROPIC_MODEL': ''}):
            os.makedirs(d + '/.codex')
            Path(d + '/.codex/config.toml').write_text('model = "gpt-test"\n')
            Path(d + '/.codex/models_cache.json').write_text(json.dumps({'models': [{'slug': 'gpt-test', 'display_name': 'GPT-Test'}]}))
            self.assertEqual(pixbg.model_label(pixbg.agent_model('codex'), 'codex'), 'GPT-Test')
            self.assertEqual(pixbg.agent_model('claude'), '')
            pixbg.write_json(d + '/models.json', {'claude': 'claude-sonnet-5-5'})
            self.assertEqual(pixbg.agent_model('claude'), 'claude-sonnet-5-5')
            pixbg.write_json(d + '/config.json', {'agent': 'claude', 'model': 'opus'})
            self.assertEqual(pixbg.agent_model('claude'), 'opus')

    def test_edit_keeps_name_prompt_and_old_version(self):
        base = (ROOT / 'app/scenes/10-void.agsl').read_text()
        scene = '// name: CHIANG MAI 清邁晴山\n// prompt: mountains\n// edit: more clouds\n// mascot: star\n' + base
        reply = '// name: SOMETHING ELSE\n// mascot: ufo\n' + base     # ask_agent returns the code without the fence
        with tempfile.TemporaryDirectory() as d:
            scenes, cache = Path(d) / 'scenes', Path(d) / 'cache'
            scenes.mkdir()
            cache.mkdir()
            (scenes / 'ai-1.agsl').write_text(scene)
            (scenes / '10-void.agsl').write_text(base)
            seen = {}
            def agent(prompt, cfg, on=None):
                seen['prompt'] = prompt
                return reply
            with patch.object(pixbg, 'SCENES', str(scenes)), patch.object(pixbg, 'CACHE', str(cache)), \
                    patch.object(pixbg, 'STATUS', str(cache / 'status.json')), patch.object(pixbg, 'HISTORY', str(cache / 'history')), \
                    patch.object(pixbg, 'ready_agent', return_value=({'agent': 'claude', 'model': ''}, '')), \
                    patch.object(pixbg, 'agent_model', return_value=''), patch.object(pixbg, 'ask_agent', side_effect=agent), \
                    patch.object(pixbg, 'build_bundle'), patch.object(pixbg, 'notify_sel'), patch.object(pixbg, 'make_thumbs'), \
                    patch.object(pixbg, 'make_tiles'), patch.object(pixbg.signal, 'signal'):
                pixbg.gen('add a moon', 'ai-1')
            self.assertIn('add a moon', seen['prompt'])
            self.assertIn('mountains', seen['prompt'])
            edited = (scenes / 'ai-1.agsl').read_text()
            self.assertEqual(pixbg.meta(edited, 'name'), 'CHIANG MAI 清邁晴山')
            self.assertEqual(pixbg.meta(edited, 'prompt'), 'mountains')
            self.assertEqual(pixbg.meta(edited, 'mascot'), 'star')
            self.assertEqual(re.findall(r'^// edit: (.+)$', edited, re.M), ['more clouds', 'add a moon'])
            self.assertEqual([p.read_text() for p in (cache / 'history').iterdir()], [scene])
            status = json.loads((cache / 'status.json').read_text())
            self.assertEqual((status['state'], status['job'], status['edit']), ('done', 'edit', 'ai-1'))

