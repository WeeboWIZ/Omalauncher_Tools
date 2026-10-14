from contextlib import redirect_stdout
import datetime as dt
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('devdesk', str(Path(__file__).resolve().parents[1] / 'bin/oma-devlogs'))
spec = importlib.util.spec_from_loader(loader.name, loader)
desk = importlib.util.module_from_spec(spec)
loader.exec_module(desk)


class MonthlyJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in [('ROOT', root), ('JOURNAL', root / 'journal'), ('NOTES', root / 'notes')]:
            p = patch.object(desk, name, value)
            p.start()
            self.addCleanup(p.stop)
        desk.ensure_dirs()

    def history(self, day='', offset=0, project=''):
        output = io.StringIO()
        with redirect_stdout(output):
            desk.history(day, offset, project)
        return json.loads(output.getvalue())

    def test_daily_views_and_pagination_from_monthly_file(self):
        lines = ['- 2026-10-13 09:00 · 舊日紀錄']
        lines += [f'- 2026-10-14 10:{i:02} · 紀錄 {i}' for i in range(45)]
        (desk.JOURNAL / '2026-10.md').write_text('# 開發日誌\n\n' + '\n'.join(lines))
        latest = self.history()
        self.assertEqual(latest['days'], ['2026-10-14', '2026-10-13'])
        self.assertEqual(latest['day'], '2026-10-14')
        self.assertEqual(latest['total'], 45)
        self.assertEqual(len(latest['entries']), 40)
        self.assertTrue(latest['more'])
        self.assertEqual(latest['entries'][0]['text'], '10:44 · 紀錄 44')
        self.assertEqual(len(self.history('2026-10-14', 40)['entries']), 5)
        self.assertEqual([e['text'] for e in self.history('2026-10-13')['entries']], ['09:00 · 舊日紀錄'])

    def test_legacy_daily_files_and_month_boundaries(self):
        (desk.JOURNAL / '2026-09-30.md').write_text('# daily\n- 23:00 · 舊格式\n')
        (desk.JOURNAL / '2026-10.md').write_text('# monthly\n- 2026-10-01 08:00 · 新格式\n')
        self.assertEqual(self.history()['days'], ['2026-10-01', '2026-09-30'])
        self.assertEqual([e['text'] for e in self.history('2026-09-30')['entries']], ['23:00 · 舊格式'])
        self.assertEqual(desk.read_latest(), ('2026-10-01', '08:00 · 新格式'))

    def test_log_writes_monthly_file_with_full_timestamp(self):
        output = io.StringIO()
        with patch.object(desk, 'refresh_widget'), patch.object(desk, 'LANGUAGE', 'zh'), redirect_stdout(output):
            desk.log_entry('專案：功能完成；驗證通過。')
            desk.log_entry('另一個重要變更。')
        self.assertTrue(output.getvalue().startswith('已儲存 → journal/'))
        now = dt.datetime.now().astimezone()
        files = list(desk.JOURNAL.glob('*.md'))
        self.assertEqual([p.name for p in files], [now.strftime('%Y-%m.md')])
        content = files[0].read_text()
        self.assertEqual(content.count('# 開發日誌'), 1)
        self.assertIn('- ' + now.date().isoformat() + ' ', content)
        self.assertEqual(self.history(now.date().isoformat())['total'], 2)

    def test_messages_follow_the_language(self):
        for language, saved, empty in (('en', 'Saved → ', 'Write something to log.'), ('zh', '已儲存 → ', '請輸入日誌內容。')):
            output = io.StringIO()
            with patch.object(desk, 'refresh_widget'), patch.object(desk, 'LANGUAGE', language), redirect_stdout(output):
                desk.log_entry('Sample App: checks passed.')
                with self.assertRaises(SystemExit) as raised:
                    desk.log_entry('   ')
            self.assertTrue(output.getvalue().startswith(saved))
            self.assertEqual(str(raised.exception), empty)

    def test_edit_keeps_the_timestamp_and_delete_keeps_a_copy(self):
        path = desk.JOURNAL / '2026-10.md'
        path.write_text('# Dev log\n\n- 2026-10-14 09:00 · First\n- 2026-10-14 10:00 · Second\n')
        home = Path(self.temp.name) / 'home'
        with patch.object(Path, 'home', return_value=home):
            first, second = reversed(self.history('2026-10-14')['entries'])
            desk.edit_log(first['id'], '  Edited   text ')
            self.assertIn('- 2026-10-14 09:00 · Edited text\n', path.read_text())
            # The id names the old line: refused once the line changed.
            with self.assertRaises(ValueError):
                desk.edit_log(first['id'], 'Again')
            with self.assertRaises(ValueError):
                desk.edit_log(second['id'], '   ')
            desk.delete_log(second['id'])
            self.assertNotIn('Second', path.read_text())
            saved = json.loads(next((home / '.local/share/oma-devlogs/trash').glob('log-*.json')).read_text())
            self.assertEqual(saved['line'], '- 2026-10-14 10:00 · Second')
            self.assertEqual([e['text'] for e in self.history('2026-10-14')['entries']], ['09:00 · Edited text'])
            for bad in ('../x:1:abcdef0123', '2026-10:99:abcdef0123'):
                with self.assertRaises(ValueError):
                    desk.delete_log(bad)

    def test_legacy_daily_lines_can_be_edited(self):
        path = desk.JOURNAL / '2026-09-30.md'
        path.write_text('# daily\n- 23:00 · Old\n')
        desk.edit_log(self.history('2026-09-30')['entries'][0]['id'], 'New')
        self.assertEqual(path.read_text(), '# daily\n- 23:00 · New\n')

    def test_projects_are_tagged_detected_and_filtered(self):
        (desk.JOURNAL / '2026-10.md').write_text('# Dev log\n\n- 2026-10-13 09:00 · Untagged\n'
                                                 '- 2026-10-13 10:00 · [Alpha] Older alpha\n- 2026-10-14 11:00 · [Beta] Beta work\n')
        everything = self.history()
        self.assertEqual(everything['projects'], [{'name': 'Beta', 'count': 1}, {'name': 'Alpha', 'count': 1}])
        self.assertEqual(everything['unassigned'], 1)
        self.assertEqual(everything['entries'], [{'id': everything['entries'][0]['id'], 'text': '11:00 · Beta work', 'project': 'Beta'}])
        alpha = self.history('', 0, 'Alpha')
        self.assertEqual((alpha['days'], alpha['day'], alpha['matching']), (['2026-10-13'], '2026-10-13', 1))
        self.assertEqual([e['text'] for e in alpha['entries']], ['10:00 · Older alpha'])
        self.assertEqual([e['text'] for e in self.history('', 0, '-')['entries']], ['09:00 · Untagged'])
        # Editing keeps the tag.
        desk.edit_log(alpha['entries'][0]['id'], 'Renamed')
        self.assertIn('- 2026-10-13 10:00 · [Alpha] Renamed\n', (desk.JOURNAL / '2026-10.md').read_text())

    def test_log_project_from_flag_git_or_projects_folder(self):
        home = Path(self.temp.name) / 'home'
        repo = home / 'code' / 'my-app'
        (repo / 'src').mkdir(parents=True)
        (home / 'projects' / 'plain' / 'docs').mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        with patch.object(Path, 'home', return_value=home), patch.object(desk, 'refresh_widget'), redirect_stdout(io.StringIO()):
            os.chdir(repo / 'src')
            desk.log_entry('From git')
            desk.log_entry('Flag wins', ' [Other] ')
            os.chdir(home / 'projects' / 'plain' / 'docs')
            desk.log_entry('From folder')
            os.chdir(home)
            desk.log_entry('No project')
        content = next(desk.JOURNAL.glob('*.md')).read_text()
        for line in ('· [my-app] From git', '· [Other] Flag wins', '· [plain] From folder', ' · No project'):
            self.assertIn(line, content)

    def test_invalid_dates_and_empty_days(self):
        self.assertEqual(self.history('2026-10-12')['entries'], [])
        for day in ('../README', '2026-10', '2026-02-30'):
            with self.assertRaises(SystemExit):
                self.history(day)


if __name__ == '__main__':
    unittest.main()
