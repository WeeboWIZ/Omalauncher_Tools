# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
'''Trip View checks: every scene passes the offline shader check, the widget passes the uniforms
every shader declares, the language packs match, sprites stay under the Canvas limit, and the
installer keeps generated scenes.

  python -m unittest discover trip-view/tests
'''
import glob
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app'
sys.path.insert(0, str(APP))
import agslcheck  # noqa: E402
import pixbg  # noqa: E402

HEADER = (APP / 'header.agsl').read_text()
SCENES = sorted(glob.glob(str(APP / 'scenes' / '*.agsl')))
WIDGET = (ROOT / 'widgets' / '30-trip-view.owl').read_text()


class Scenes(unittest.TestCase):
    @unittest.skipUnless(shutil.which('glslangValidator'), 'needs glslang')
    def test_every_scene_passes_the_offline_check(self):
        for path in SCENES:
            errs, cost = agslcheck.check(HEADER, Path(path).read_text())
            self.assertEqual(errs, [], f'{os.path.basename(path)}: {errs}')
            self.assertLessEqual(cost, agslcheck.BUDGET)

    @unittest.skipUnless(shutil.which('glslangValidator'), 'needs glslang')
    def test_broken_or_heavy_shaders_are_rejected(self):
        errs, _ = agslcheck.check(HEADER, 'half4 main(float2 p) { return half4(bar2, 1.0); }')
        self.assertTrue(any('bar2' in e for e in errs))
        heavy = 'half4 main(float2 p) { float a = 0.0; for (int i = 0; i < 16; i++) { for (int j = 0; j < 16; j++) { a += sin(p.x + float(i * j)); } } return half4(a); }'
        errs, cost = agslcheck.check(HEADER, heavy)
        self.assertGreater(cost, agslcheck.BUDGET)
        self.assertTrue(errs)
        self.assertTrue(agslcheck.rules('half4 main(float2 p) { while (true) {} return half4(1.0); }'))

    def test_every_scene_has_a_name_mascot_and_five_palettes(self):
        for path in SCENES:
            src = Path(path).read_text()
            self.assertTrue(pixbg.meta(src, 'name'), path)
            self.assertIn(pixbg.meta(src, 'mascot'), pixbg.MASCOTS, path)
            pal = pixbg.palettes(src)
            self.assertEqual(len(pal), 5, path)
            for z in pal:
                self.assertTrue({'bg', 'c0', 'c1', 'c2', 'ac', 'ink', 'lite', 'fg'} <= set(z), path)

    def test_names_split_into_english_and_chinese(self):
        self.assertEqual(pixbg.split_name('NEON RAMEN 霓虹拉麵'), ('NEON RAMEN', '霓虹拉麵'))
        self.assertEqual(pixbg.split_name('CYBER CANYON 賽博峽谷'), ('CYBER CANYON', '賽博峽谷'))
        self.assertEqual(pixbg.split_name('霓虹雨'), ('霓虹雨', '霓虹雨'))
        self.assertEqual(pixbg.split_name('NEON RAIN'), ('NEON RAIN', 'NEON RAIN'))


class Widget(unittest.TestCase):
    def test_every_shader_node_passes_the_header_uniforms(self):
        # Passing a uniform a shader doesn't declare fails in native code, so every Shader node passes
        # exactly what header.agsl declares, and the fallback shaders declare it too.
        declared = re.findall(r'^uniform float (\w+);', HEADER, re.M)
        self.assertEqual(declared, ['zone', 'speed', 'cellpx'])
        nodes = re.findall(r'Shader \{[^\n]*uniforms: \{([^}]*)\}', WIDGET)
        self.assertGreaterEqual(len(nodes), 2)
        for u in nodes:
            self.assertEqual(sorted(k.split(':')[0].strip() for k in u.split(',')), sorted(declared))
        for name in ('blank', 'probe'):
            code = re.search(r'let %s = "([^"]*)"' % name, WIDGET).group(1)
            for d in declared:
                self.assertIn(f'uniform float {d};', code, name)

    def test_store_rules(self):
        meta = re.search(r'meta \{([^}]*)\}', WIDGET).group(1)
        desc = re.search(r'description: "([^"]*)"', meta).group(1)
        self.assertTrue(10 <= len(desc) <= 200)
        self.assertIn('license: "GPL-3.0-or-later"', meta)
        self.assertLess(len(WIDGET.encode()), 256 * 1024)
        self.assertNotIn('/root/', WIDGET)


class Languages(unittest.TestCase):
    def test_packs_have_the_same_strings(self):
        packs = {Path(p).stem: json.loads(Path(p).read_text()) for p in glob.glob(str(APP / 'lang' / '*.json'))}
        self.assertIn('zh', packs)
        self.assertIn('en', packs)
        for code, d in packs.items():
            self.assertEqual(set(d['T']), set(packs['zh']['T']), code)
            self.assertEqual(set(d['msg']), set(packs['zh']['msg']), code)
            self.assertEqual(len(d['wd']), 7, code)
            self.assertIn(d['names'], ('en', 'zh'), code)

    def test_widget_only_uses_known_strings(self):
        keys = set(json.loads((APP / 'lang' / 'zh.json').read_text())['T'])
        used = set(re.findall(r'\bT\.(\w+)', WIDGET)) | set(re.findall(r'get\(T, "(\w+)"', WIDGET))
        self.assertEqual(sorted(used - keys), [])


class Actors(unittest.TestCase):
    def test_sprites_stay_under_the_canvas_limit(self):
        # The launcher draws at most 2000 Canvas calls a frame, and each run of a sprite row counts.
        def runs(rows):
            return sum(1 for r in rows for i, ch in enumerate(r) if ch != '.' and (i == 0 or r[i - 1] != ch))
        for path in glob.glob(str(APP / 'scenes' / '*.actors.json')):
            data = json.loads(Path(path).read_text())
            art = data['art']
            for zone in range(5):
                toys = [a['toy'] for a in data['acts'] if zone in a.get('zones', [zone])]
                worst = sum(max(runs(f) for f in art[t]['frames']) for t in toys)
                self.assertLess(worst, 1800, f'{os.path.basename(path)} act {zone}: {worst} runs')


class Install(unittest.TestCase):
    def test_install_keeps_generated_scenes(self):
        with tempfile.TemporaryDirectory() as home:
            scenes = Path(home) / '.local/share/pixbg/scenes'
            scenes.mkdir(parents=True)
            (scenes / 'ai-20260101-000000.agsl').write_text('// name: MINE 我的\nhalf4 main(float2 p) { return half4(1.0); }\n')
            (scenes / 'ai-20260101-000001.agsl').write_text('// name: BROKEN 壞的\nhalf4 main(float2 p) { return half4(bar2, 1.0); }\n')
            env = dict(os.environ, HOME=home)
            subprocess.run([sys.executable, str(ROOT / 'install.py'), '--skip-deps', '--no-check'], check=True, env=env, capture_output=True)
            self.assertTrue((scenes / 'ai-20260101-000000.agsl').exists())
            self.assertTrue((scenes / 'ai-20260101-000001.agsl').exists())
            self.assertTrue((scenes / '05-ramen.agsl').exists())
            self.assertTrue((Path(home) / '.local/bin/pixbg').is_symlink())
            self.assertTrue((Path(home) / '.config/omalauncher/widgets/30-trip-view.owl').exists())
            bundle = json.loads((Path(home) / '.cache/pixbg/bundle.json').read_text())
            ids = [s['id'] for s in bundle['scenes']]
            self.assertEqual(ids[0], '05-ramen')
            self.assertIn('ai-20260101-000000', ids)
            self.assertNotIn('ai-20260101-000001', ids)   # it doesn't compile, so it never reaches the phone


if __name__ == '__main__':
    unittest.main()
