from contextlib import redirect_stdout
import importlib.machinery
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('logs_files', str(Path(__file__).resolve().parents[1] / 'bin/oma-devlogs'))
spec = importlib.util.spec_from_loader(loader.name, loader)
logs = importlib.util.module_from_spec(spec)
loader.exec_module(logs)


class FileTests(unittest.TestCase):
    def test_creation_preserves_existing_file_and_trash_keeps_recovery_path(self):
        with tempfile.TemporaryDirectory(prefix='logs files ') as directory, patch.object(Path, 'home', return_value=Path(directory)):
            home = Path(directory)
            original = logs.create_markdown(str(home), 'Release notes')
            original.write_text('# User notes\nKeep this content.\n')
            second = logs.create_markdown(str(home), 'Release notes')
            self.assertNotEqual(original, second)
            self.assertEqual(second.name, 'Release notes-2.md')
            target = logs.trash_markdown(str(original))
            self.assertFalse(original.exists())
            self.assertIn('Keep this content.', target.read_text())
            self.assertEqual(json.loads(target.with_suffix('.json').read_text())['original'], str(original))

    def test_home_boundary_and_symlink_deletion_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            home = Path(directory)
            with patch.object(Path, 'home', return_value=home):
                with self.assertRaises(ValueError):
                    logs.create_markdown(outside, 'Outside')
                original = logs.create_markdown(str(home), 'Real')
                link = home / 'link.md'
                link.symlink_to(original)
                with self.assertRaises(ValueError):
                    logs.trash_markdown(str(link))
                self.assertTrue(original.exists())
                for name in ('../outside', 'bad/name', 'two\nlines', '.hidden'):
                    with self.assertRaises(ValueError):
                        logs.create_markdown(str(home), name)

    def test_browse_reports_counts_kinds_and_crumbs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)):
            home = Path(directory)
            project = home / 'projects' / 'app'
            (project / 'src').mkdir(parents=True)
            (project / 'src' / 'main.py').write_text('print()')
            (project / '.hidden').write_text('')
            (project / 'README.md').write_text('# App')
            (project / 'logo.png').write_bytes(b'png')
            (project / 'empty').mkdir()
            output = io.StringIO()
            with redirect_stdout(output):
                logs.browse(str(project), 0, 2)
            listing = json.loads(output.getvalue())
            self.assertEqual([c['name'] for c in listing['crumbs']], ['~', 'projects', 'app'])
            self.assertEqual([(i['name'], i['kind'], i.get('count')) for i in listing['items']], [('empty', 'folder', 0), ('src', 'folder', 1)])
            self.assertTrue(listing['more'])
            output = io.StringIO()
            with redirect_stdout(output):
                logs.browse(str(project), 2)
            self.assertEqual([i['kind'] for i in json.loads(output.getvalue())['items']], ['image', 'md'])

    def test_search_names_and_markdown_text(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)):
            home = Path(directory)
            (home / 'a' / 'node_modules').mkdir(parents=True)
            (home / 'a' / 'node_modules' / 'release.md').write_text('skip')
            (home / 'a' / 'Release-plan.md').write_text('# Plan')
            (home / 'a' / 'notes.md').write_text('line one\nthe RELEASE date\n')
            (home / 'a' / 'code.py').write_text('release = 1')
            names = logs.search(str(home), 'release')
            self.assertEqual([i['rel'] for i in names['items']], ['a/Release-plan.md'])
            both = logs.search(str(home), 'release', content=True)
            self.assertEqual({i['rel']: i['match'] for i in both['items']}, {'a/Release-plan.md': '', 'a/notes.md': 'the RELEASE date'})
            deep = home
            for level in range(8):
                deep = deep / f'd{level}'
            deep.mkdir(parents=True)
            (deep / 'release.txt').write_text('')
            self.assertNotIn('release.txt', [i['name'] for i in logs.search(str(home), 'release')['items']])
            self.assertIn('error', logs.search(str(home), '   '))
            with tempfile.TemporaryDirectory() as outside:
                self.assertIn('error', logs.search(outside, 'x'))


if __name__ == '__main__':
    unittest.main()
