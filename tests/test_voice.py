import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import time
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_store
spec = importlib.util.spec_from_file_location('voice', ROOT/'voice/oma_voice.py')
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)

class VoiceTests(unittest.TestCase):
    def test_follow_and_completion(self):
        previous = voice.CACHE, voice.CONFIG, voice.SESSIONS
        try:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                voice.CACHE, voice.CONFIG, voice.SESSIONS = base/'cache', base/'config.json', base/'sessions'
                voice.SESSIONS.mkdir()
                def session(text):
                    ident = str(uuid.uuid4())
                    path = voice.SESSIONS/(ident+'.jsonl')
                    path.write_text(json.dumps({'payload': {'id': ident}})+'\n'+json.dumps({'type':'event_msg','timestamp':'2026-10-13T00:00:00Z','payload': {'type':'task_complete','turn_id': str(uuid.uuid4()),'last_agent_message':text}})+'\n')
                    return ident,path
                first,old = session('Old reply')
                reader = voice.Reader()
                reader.bind(first)
                reader.config['auto'] = False
                second,new = session('New reply')
                # Appending resets the time; on a coarse clock it can tie with the older file.
                newest = lambda: os.utime(new,(old.stat().st_mtime+10,old.stat().st_mtime+10))
                newest()
                reader.poll()
                self.assertEqual(reader.config['thread'],second)
                self.assertEqual(reader.state['full'],'New reply')
                self.assertFalse(reader.state['playing'])
                with new.open('a') as f:
                    f.write(json.dumps({'type':'event_msg','payload':{'type':'task_started'}})+'\n')
                newest()
                reader.poll()
                self.assertTrue(reader.state['awaiting'])
                with new.open('a') as f:
                    f.write(json.dumps({'type':'event_msg','timestamp':'2026-10-13T00:01:00Z','payload':{'type':'task_complete','turn_id':'next','last_agent_message':'Fresh completion'}})+'\n')
                newest()
                reader.poll()
                self.assertEqual(reader.state['full'],'Fresh completion')
                self.assertFalse(reader.state['awaiting'])
                self.assertIsInstance(reader.state['reply_at'],float)
                reader.command({'action':'refresh'})
                self.assertFalse(reader.state['playing'])
                self.assertEqual(reader.state['full'],'Fresh completion')
        finally:
            voice.CACHE, voice.CONFIG, voice.SESSIONS = previous

    def test_service_rests_without_a_session_and_quits_when_no_tile_asks(self):
        previous = voice.CACHE, voice.CONFIG, voice.SESSIONS, voice.ALIVE
        try:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                voice.CACHE, voice.CONFIG, voice.SESSIONS, voice.ALIVE = base/'cache', base/'config.json', base/'sessions', base/'cache/alive'
                voice.SESSIONS.mkdir()
                reader = voice.Reader()
                state = voice.CACHE/'state.json'
                # What the service loop does on each pass with no Codex session: one write, not three.
                written = []
                with mock.patch.object(voice,'atomic_json',side_effect=lambda path,value: written.append(path)):
                    for _ in range(3):
                        self.assertRaises(ValueError,reader.poll)
                        reader.state.update(status='等待會話記錄',error='找不到 Codex 會話')
                        reader.save()
                self.assertEqual(written,[state])
                self.assertNotIn('checked_at',reader.state)
                voice.ALIVE.touch()
                self.assertFalse(reader.idle())
                os.utime(voice.ALIVE,(time.time()-voice.IDLE_EXIT-5,)*2)
                self.assertTrue(reader.idle())
                reader.state['playing'] = True
                self.assertFalse(reader.idle())
        finally:
            voice.CACHE, voice.CONFIG, voice.SESSIONS, voice.ALIVE = previous

    def test_tmux_capture_and_send_in_isolated_session(self):
        with tempfile.TemporaryDirectory() as directory:
            socket_name = 'oma-voice-test-' + uuid.uuid4().hex[:10]
            original_run = subprocess.run
            try:
                original_run(['tmux','-L',socket_name,'-f','/dev/null','new-session','-d','-s','oma-voice','bash','--noprofile','--norc'],check=True)
                def isolated(args, **kwargs):
                    if args[0] == 'tmux':
                        args = ['tmux','-L',socket_name,*args[1:]]
                    return original_run(args, **kwargs)
                with mock.patch.object(voice.subprocess,'run',side_effect=isolated):
                    pane,label,_=voice.terminal_snapshot()
                    self.assertRegex(pane,r'^%[0-9]+$')
                    voice.terminal_send(pane,'printf voice_test_ok')
                    time.sleep(.4)
                    _,_,screen=voice.terminal_snapshot()
                    self.assertIn('voice_test_ok',screen)
            finally:
                original_run(['tmux','-L',socket_name,'kill-server'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def test_ignores_nonfinal_events(self):
        self.assertIsNone(voice.completed_reply({'type':'event_msg','payload':{'type':'agent_message','message':'interim'}}))
        self.assertIsNone(voice.completed_reply({'type':'event_msg','payload':{'type':'turn_aborted'}}))

    def test_install_and_update_preserve_user_data(self):
        with tempfile.TemporaryDirectory(prefix='voice test ') as directory:
            home = Path(directory)
            config = home/'.config/omalauncher/voice.json'
            config.parent.mkdir(parents=True)
            config.write_text('{"auto":false}')
            env = dict(os.environ, HOME=directory)
            for _ in range(2):
                subprocess.run([sys.executable,str(ROOT/'install.py'),'--skip-deps'],env=env,check=True,stdout=subprocess.DEVNULL)
            self.assertEqual(config.read_text(),'{"auto":false}')
            tile = (home/'.config/omalauncher/widgets/46-speak.owl').read_text()
            self.assertNotIn('__',tile.split('"""')[0])
            self.assertNotIn(directory,tile)
            self.assertEqual((home/build_store.MARKER).read_text(),build_store.payload_id())
            self.assertTrue(os.access(home/'.local/bin/oma-voice',os.X_OK))
            self.assertTrue(list((home/'.local/share/oma-voice/install-backups').rglob('oma_voice.py')))

    def test_long_text_is_split_for_online_speech_and_fallback_is_explained(self):
        spec = importlib.util.spec_from_file_location('synthesize', ROOT/'voice/synthesize.py')
        synthesize = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(synthesize)
        text = '這是一句測試。'*900 + 'x'*3000
        parts = synthesize.pieces(text)
        self.assertEqual(''.join(parts),text)
        self.assertTrue(all(len(part) <= 1200 for part in parts))
        self.assertEqual(synthesize.pieces('短句'),['短句'])
        self.assertEqual(voice.english('正在播放 · 自然語音（線上）'),'Playing · online natural')
        self.assertEqual(voice.english('播放完成 · 離線基本語音（'+synthesize.UNREACHABLE+'）'),'Finished · offline basic (online voice unreachable)')
        for reason in (synthesize.NOT_INSTALLED,synthesize.NO_MPG123,synthesize.UNREACHABLE):
            self.assertIn(reason,voice.REASONS)

    def test_store_widgets_are_current_and_within_store_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            build_store.build(Path(directory))
            for name in ('terminal-voice','dictation'):
                built = (Path(directory)/name/'widget.owl').read_bytes()
                self.assertEqual(built,(ROOT/'store/widgets'/build_store.AUTHOR/name/'widget.owl').read_bytes(),'run python tools/build_store.py')
                self.assertLess(len(built),build_store.MAX_BYTES)
                text = built.decode()
                self.assertNotIn('\r',text)
                for personal in ('/root/','/home/','__HOME__'):
                    self.assertNotIn(personal,text)
                self.assertIn('version: "%s"'%build_store.VERSION,text)
                self.assertEqual(text.count('"""')%2,0)

    def test_setup_script_installs_the_same_files_as_the_installer(self):
        with tempfile.TemporaryDirectory(prefix='voice test ') as directory:
            home = Path(directory)
            # Leave out the venv and pip steps: they need the network.
            script = '\n'.join(line for line in build_store.setup_script().split('\n') if not line.startswith(('venv=','[ -x "$venv','"$venv','pkill')))
            subprocess.run(['bash','-c',script],env=dict(os.environ,HOME=directory),check=True)
            for file,target,executable in build_store.payload_files():
                self.assertEqual((home/target).read_text(),file.read_text())
                self.assertEqual(os.access(home/target,os.X_OK),executable)
            self.assertEqual((home/build_store.MARKER).read_text(),build_store.payload_id())
            self.assertEqual((home/'.cache/oma-voice/setup-state').read_text(),'done')

if __name__ == '__main__':
    unittest.main()
