from contextlib import closing
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('desk_errors', Path(__file__).resolve().parents[1] / 'lib/system_errors.py')
errors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(errors)


class ErrorTests(unittest.TestCase):
    def test_levels_and_mixed_reports(self):
        self.assertEqual(errors.classify('warn: compositor does not implement fractional scaling'), 'warning')
        self.assertEqual(errors.classify('runtime: drawing takes 4 ms per frame', '/a/widgets/.errors/koi.txt'), 'info')
        self.assertEqual(errors.classify("5: expected ')', found x", '/a/widgets/.errors/desk.txt'), 'error')
        self.assertEqual(errors.classify('warn: context\nOSError: [Errno 38] Function not implemented'), 'error')
        self.assertEqual(errors.classify('2026-10-14T08:00:00 · foot exited abnormally: exit=139'), 'error')

    def test_filter_pagination_counts_and_single_report(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(errors, 'sources', return_value=[]):
            with patch.object(errors, 'ROOT', Path(directory)):
                with closing(errors.connect()) as db, db:
                    db.executemany('INSERT INTO events(time,source,text) VALUES(?,?,?)', [
                        ('now', '/terminal.log', f'error: unique-{i}') for i in range(22)
                    ] + [('now', '/foot.log', 'warn: unsupported protocol'),
                         ('now', '/widget.log', 'runtime: drawing takes 4 ms per frame')])
                result = errors.history(20, 'error')
                self.assertEqual(result['total'], 22)
                self.assertEqual(result['all_total'], 24)
                self.assertEqual(len(result['entries']), 2)
                self.assertFalse(result['more'])
                self.assertEqual(errors.history(0, 'warning')['total'], 1)
                self.assertEqual(errors.history(0, 'info')['total'], 1)
                one, two = result['entries']
                self.assertIn(one['text'], one['report'])
                self.assertIn('Source: /terminal.log', one['report'])
                with patch.object(errors, 'LANGUAGE', 'zh'):
                    self.assertIn('來源：/terminal.log', errors.history(20, 'error')['entries'][0]['report'])
                self.assertNotIn(two['text'], one['report'])
                self.assertEqual(errors.history(0, 'all')['total'], 24)

    def test_offsets_and_snapshot_recurrence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / 'service.log'
            snapshot = root / 'widget.txt'
            log.write_text('error: first\n')
            snapshot.write_text('error: widget\n')
            with patch.object(errors, 'ROOT', root), patch.object(errors, 'sources', return_value=[(log, False), (snapshot, True)]):
                self.assertEqual(errors.history()['total'], 2)
                self.assertEqual(errors.history()['total'], 2)
                with log.open('a') as stream:
                    stream.write('error: second\n')
                result = errors.history()
                self.assertEqual(result['total'], 3)
                self.assertEqual(result['entries'][0]['text'], 'error: second')
                # A pass with nothing new leaves the database file as it is.
                database = root / 'logs/system-errors.sqlite3'
                before = (database.stat().st_mtime_ns, database.read_bytes())
                errors.history()
                errors.history()
                self.assertEqual((database.stat().st_mtime_ns, database.read_bytes()), before)
                snapshot.write_text('')
                errors.history()
                snapshot.write_text('error: widget\n')
                self.assertEqual(errors.history()['total'], 4)


if __name__ == '__main__':
    unittest.main()
