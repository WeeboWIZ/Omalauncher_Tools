import importlib.util
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import time
from unittest import mock
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import build_store
spec = importlib.util.spec_from_file_location('voice', ROOT/'voice/oma_voice.py')
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)

def chinese(text):
    return any('㐀' <= c <= '鿿' for c in text)


class VoiceTests(unittest.TestCase):
    def test_claude_transcript_gives_only_final_replies(self):
        sys.path.insert(0, str(ROOT/'voice'))
        import oma_voice
        prompt = {'type': 'user', 'message': {'role': 'user', 'content': 'Fix it'}}
        tool_result = {'type': 'user', 'message': {'role': 'user', 'content': [{'type': 'tool_result', 'content': 'ok'}]}}
        working = {'type': 'assistant', 'requestId': 'r1', 'message': {'stop_reason': 'tool_use', 'content': [{'type': 'text', 'text': 'Looking'}]}}
        thinking = {'type': 'assistant', 'requestId': 'r2', 'message': {'stop_reason': 'end_turn', 'content': [{'type': 'thinking', 'thinking': 'x'}]}}
        final = {'type': 'assistant', 'requestId': 'r2', 'message': {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Done.'}]}}
        subagent = dict(final, isSidechain=True)
        self.assertEqual(oma_voice.claude_event(prompt), ('start', None))
        for event in (tool_result, working, thinking, subagent):
            self.assertIsNone(oma_voice.claude_event(event))
        self.assertEqual(oma_voice.claude_event(final), ('reply', ('r2', 'Done.')))

    def test_refine_uses_the_agent_of_the_current_source(self):
        from importlib.machinery import SourceFileLoader
        refine = SourceFileLoader('refine_under_test', str(ROOT/'bin/oma-refine-dictation')).load_module()
        with tempfile.TemporaryDirectory() as directory:
            refine.VOICE_STATE = Path(directory)/'state.json'
            with mock.patch.object(refine.shutil, 'which', lambda name: '/usr/bin/'+name):
                for state, first in (({'source': 'claude'}, 'claude'), ({'source': 'codex'}, 'codex'),
                                     ({'source': 'terminal', 'source_name': 'Claude'}, 'claude'), ({}, 'codex')):
                    refine.VOICE_STATE.write_text(json.dumps(state))
                    self.assertEqual([name for name, _ in refine.agents()], [first, {'claude': 'codex', 'codex': 'claude'}[first]])
            with mock.patch.object(refine.shutil, 'which', lambda name: '/usr/bin/claude' if name == 'claude' else None):
                refine.VOICE_STATE.write_text(json.dumps({'source': 'codex'}))
                self.assertEqual([name for name, _ in refine.agents()], ['claude'])
        command = refine.claude_command()
        self.assertIn('haiku', command)
        self.assertIn('--no-session-persistence', command)

    def test_leftover_audio_is_removed_by_the_next_reading(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(voice, 'CACHE', Path(directory)):
            for name in ('speech-old.wav', 'speech-old.wav.backend', 'speech-old.mp3', 'speech-new.wav', 'state.json'):
                (Path(directory)/name).write_text('x')
            voice.sweep(keep='speech-new')
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['speech-new.wav', 'state.json'])

    def test_dictation_open_button_reports_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            cache = home/'.cache/oma-speak'
            bin_dir = home/'bin'
            cache.mkdir(parents=True)
            bin_dir.mkdir()
            (cache/'token').write_text('test-token')
            for name, body in [('curl', 'printf "oma-speak-v1\\n"'), ('xdg-open', 'exit 0')]:
                command = bin_dir/name
                command.write_text('#!/bin/sh\n'+body+'\n')
                command.chmod(0o700)
            env = dict(os.environ, HOME=directory, PATH=str(bin_dir)+os.pathsep+os.environ.get('PATH',''))
            run = lambda: subprocess.run(['bash',str(ROOT/'bin/speak'),'--json'],env=env,
                                         capture_output=True,text=True,timeout=5)
            self.assertTrue(json.loads(run().stdout)['ok'])
            (bin_dir/'xdg-open').write_text('#!/bin/sh\nexit 1\n')
            self.assertFalse(json.loads(run().stdout)['ok'])

    def test_dictation_send_reports_progress_and_failure_without_live_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            share = home/'.local/share/oma-voice'
            bin_dir = home/'.local/bin'
            cache = home/'.cache/oma-speak'
            share.mkdir(parents=True)
            bin_dir.mkdir(parents=True)
            cache.mkdir(parents=True)
            (share/'language.py').write_text('def local(text): return text\n')
            (cache/'latest.txt').write_text('Test message')
            target = bin_dir/'oma-voice'
            target.write_text('#!/usr/bin/python\nimport json\nprint(json.dumps({"ok": True, "status": "queued"}))\n')
            target.chmod(0o700)
            env = dict(os.environ, HOME=str(home))
            run = lambda: subprocess.run([sys.executable, str(ROOT/'bin/oma-send-dictation')],
                                         env=env, capture_output=True, text=True, timeout=10)
            result = run()
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads((cache/'send-status.json').read_text())['phase'], 'sent')
            self.assertEqual(json.loads(result.stdout.splitlines()[-1])['status'], 'queued')
            one_line = subprocess.run([sys.executable, str(ROOT/'bin/oma-send-dictation'), '--json'],
                                      env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(len(one_line.stdout.splitlines()), 1)
            self.assertEqual(json.loads(one_line.stdout)['phase'], 'sent')
            with (cache/'send.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                busy = subprocess.run([sys.executable, str(ROOT/'bin/oma-send-dictation'), '--json'],
                                      env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(json.loads(busy.stdout)['phase'], 'busy')
            target.write_text('#!/usr/bin/python\nimport json, sys\nprint(json.dumps({"ok": False, "error": "rejected"}))\nsys.exit(1)\n')
            result = run()
            self.assertEqual(json.loads((cache/'send-status.json').read_text())['phase'], 'failed')
            self.assertIn('rejected', result.stdout)
            failed = subprocess.run([sys.executable, str(ROOT/'bin/oma-send-dictation'), '--json'],
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(len(failed.stdout.splitlines()), 1)
            self.assertFalse(json.loads(failed.stdout)['ok'])

    def test_refined_dictation_is_reviewable_and_cannot_send_stale_text(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            share = home/'.local/share/oma-voice'
            bin_dir = home/'.local/bin'
            cache = home/'.cache/oma-speak'
            share.mkdir(parents=True)
            bin_dir.mkdir(parents=True)
            cache.mkdir(parents=True)
            (share/'language.py').write_text('def local(text): return text\n')
            (cache/'latest.txt').write_text('Please fix thing thing')
            codex = bin_dir/'codex'
            codex.write_text('#!/usr/bin/python\nimport sys\nsys.stdin.read()\nprint("Please fix the issue.")\n')
            codex.chmod(0o700)
            target = bin_dir/'oma-voice'
            target.write_text('#!/usr/bin/python\nimport json, sys\nprint(json.dumps({"ok": True, "status": sys.argv[-1]}))\n')
            target.chmod(0o700)
            env = dict(os.environ, HOME=str(home), PATH=str(bin_dir)+os.pathsep+os.environ.get('PATH',''))
            started = subprocess.run([sys.executable,str(ROOT/'bin/oma-refine-dictation'),'--start','--json'],
                                     env=env,check=True,capture_output=True,text=True)
            self.assertEqual(len(started.stdout.splitlines()), 1)
            self.assertTrue(json.loads(started.stdout)['ok'])
            deadline = time.monotonic()+5
            while time.monotonic()<deadline:
                state = json.loads((cache/'refine-status.json').read_text())
                if state['phase'] != 'refining':
                    break
                time.sleep(.05)
            self.assertEqual(state['phase'],'ready')
            self.assertEqual((cache/'refined.txt').read_text(),'Please fix the issue.')
            send = lambda: subprocess.run([sys.executable,str(ROOT/'bin/oma-send-dictation'),'--refined'],
                                          env=env,capture_output=True,text=True,timeout=10)
            self.assertEqual(json.loads(send().stdout.splitlines()[-1])['status'],'Please fix the issue.')
            (cache/'latest.txt').write_text('Different request')
            self.assertFalse(json.loads(send().stdout.splitlines()[-1])['ok'])

    def test_dictation_page_refine_and_send_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            share = home/'.local/share/oma-voice'
            bin_dir = home/'.local/bin'
            share.mkdir(parents=True)
            bin_dir.mkdir(parents=True)
            (share/'language.py').write_text('def local(text): return text\n')
            (share/'oma_voice.py').write_text(
                'import json,sys\nfrom pathlib import Path\n'
                'path=Path.home()/".cache/oma-voice/state.json"\n'
                'source=sys.argv[2]\n'
                'path.write_text(json.dumps({"source":source,"source_name":"tmux test" if source=="terminal" else "Codex",'
                '"term_pane":"%1" if source=="terminal" else ""}))\n'
                'print(json.dumps({"ok":True}))\n')
            for name in ('oma-refine-dictation','oma-send-dictation'):
                (bin_dir/name).write_bytes((ROOT/'bin'/name).read_bytes())
            codex = bin_dir/'codex'
            codex.write_text('#!/usr/bin/python\nimport sys\nsys.stdin.read()\nprint("Polished request.")\n')
            codex.chmod(0o700)
            target = bin_dir/'oma-voice'
            target.write_text('#!/usr/bin/python\nimport json,sys\nprint(json.dumps({"ok": True, "status": sys.argv[-1]}))\n')
            target.chmod(0o700)
            env = {'HOME': directory, 'PATH': str(bin_dir)+os.pathsep+os.environ.get('PATH','')}
            with mock.patch.dict(os.environ, env):
                spec = importlib.util.spec_from_file_location('dictation_server',ROOT/'dictation/server.py')
                server = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(server)
                httpd = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
                server.PORT = httpd.server_port
                server.ORIGIN = 'http://127.0.0.1:'+str(server.PORT)
                thread = threading.Thread(target=httpd.serve_forever,daemon=True)
                thread.start()
                def request(path, body=None):
                    headers={'X-Speak-Token': server.TOKEN}
                    data=None if body is None else json.dumps(body).encode()
                    if data is not None:
                        headers.update(Origin=server.ORIGIN,**{'Content-Type':'application/json'})
                    with urllib.request.urlopen(urllib.request.Request(server.ORIGIN+path,data=data,headers=headers),timeout=5) as response:
                        payload = response.read().decode()
                        try:
                            return json.loads(payload)
                        except ValueError:
                            return payload
                try:
                    voice_state = home/'.cache/oma-voice/state.json'
                    voice_state.parent.mkdir(parents=True)
                    voice_state.write_text(json.dumps({'source':'terminal','source_name':'tmux test'}))
                    self.assertEqual(request('/target')['source_name'],'tmux test')
                    self.assertFalse(request('/target')['connected'])
                    self.assertEqual(request('/target',{'source':'codex'})['source'],'codex')
                    self.assertEqual(request('/target',{'source':'terminal'})['source'],'terminal')
                    self.assertTrue(request('/target')['connected'])
                    self.assertEqual(request('/refine',{'text':'Please fix thing thing'})['phase'],'refining')
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        state=request('/refine-status')
                        if state['phase']!='refining':
                            break
                        time.sleep(.05)
                    self.assertEqual(state['text'],'Polished request.')
                    request('/text',{'text':'Please fix thing thing'})
                    self.assertEqual(request('/refine-status')['phase'],'ready')
                    self.assertEqual(request('/send',{'version':'refined'})['status'],'Polished request.')
                finally:
                    httpd.shutdown()
                    httpd.server_close()

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

    def test_send_follows_new_chat_without_waiting_for_background_retry(self):
        previous = voice.CACHE, voice.CONFIG, voice.SESSIONS
        try:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                voice.CACHE, voice.CONFIG, voice.SESSIONS = base/'cache', base/'config.json', base/'sessions'
                voice.SESSIONS.mkdir()
                first = str(uuid.uuid4())
                old = voice.SESSIONS/(first+'.jsonl')
                old.write_text(json.dumps({'payload': {'id': first}})+'\n')
                reader = voice.Reader()
                reader.bind(first)
                reader.checked_session = time.monotonic()
                second = str(uuid.uuid4())
                new = voice.SESSIONS/(second+'.jsonl')
                new.write_text(json.dumps({'payload': {'id': second}})+'\n')
                os.utime(new,(old.stat().st_mtime+10,old.stat().st_mtime+10))
                with mock.patch.object(voice.subprocess,'run',return_value=mock.Mock(returncode=0)) as queued:
                    result = reader.command({'action':'send','text':'Hello'})
                self.assertTrue(result['ok'])
                self.assertEqual(reader.config['thread'],second)
                self.assertEqual(queued.call_args.args[0][3],second)
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
                # A change of interface language reaches the tiles through the state file.
                choice = base/'language'
                with mock.patch.object(sys.modules['language'],'CHOICE',choice):
                    for code,text in (('ko','채팅 기록 대기 중'),('zh','等待會話記錄'),('nonsense','Waiting for chat log')):
                        choice.write_text(code)
                        self.assertEqual(reader.command({'action':'status'})['status_ui'],text)
                        self.assertEqual(json.loads(state.read_text())['status_ui'],text)
                    # Written by something else, as the dictation page does: the service notices by the file's time.
                    self.assertEqual(sys.modules['language'].changed_at(),reader.language_at)
                    choice.write_text('fr')
                    os.utime(choice,ns=(1,reader.language_at+1))
                    self.assertNotEqual(sys.modules['language'].changed_at(),reader.language_at)
                voice.ALIVE.touch()
                self.assertEqual(reader.state['pause_minutes'],10)
                self.assertFalse(reader.idle())
                os.utime(voice.ALIVE,(time.time()-601,)*2)
                self.assertTrue(reader.idle())
                reader.state['playing'] = True
                self.assertFalse(reader.idle())
                reader.state['playing'] = False
                # Codex still writing its log keeps the service for a task that outlasts the screen.
                log = voice.SESSIONS/'log.jsonl'
                log.write_text('')
                reader.path = log
                self.assertFalse(reader.idle())
                os.utime(log,(time.time()-601,)*2)
                self.assertTrue(reader.idle())
                reader.command({'action':'pause','value':'45'})
                self.assertFalse(reader.idle())
                os.utime(voice.ALIVE,(time.time()-2701,)*2)
                os.utime(log,(time.time()-2701,)*2)
                self.assertTrue(reader.idle())
                reader.command({'action':'pause','value':'off'})
                self.assertFalse(reader.idle())
                self.assertEqual(voice.read_json(voice.CONFIG)['pause_minutes'],0)
                reader.command({'action':'pause','value':'toggle'})
                self.assertEqual(reader.state['pause_minutes'],10)
                for bad in ('-1','1441','ten','1.5',''):
                    self.assertRaises(ValueError,reader.command,{'action':'pause','value':bad})
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

    def test_every_language_has_every_text_and_keeps_the_live_parts(self):
        import re
        import ui_strings
        language = sys.modules['language']
        self.assertEqual(tuple(ui_strings.LANGUAGES),language.LANGUAGES)
        self.assertEqual(set(ui_strings.NAMES),set(language.LANGUAGES))
        self.assertEqual(set(ui_strings.SHORT),set(language.LANGUAGES))
        for english,others in ui_strings.STRINGS.items():
            self.assertEqual(len(others),len(language.LANGUAGES)-1,english)
            for text in others:
                self.assertTrue(text.strip(),english)
                # ${...} is an OWL expression: only quoted words inside it may differ.
                live = lambda value: [re.sub(r"'[^']*'","''",part) for part in re.findall(r'\$\{.*\}',value)]
                self.assertEqual(live(text),live(english),english)
        for table in (language.MESSAGES,language.PREFIXES,language.VOICES,language.REASONS):
            for chinese,others in table.items():
                self.assertEqual(len(others),len(language.LANGUAGES)-1,chinese)
                self.assertTrue(all(text.strip() for text in others),chinese)
        self.assertEqual(language.local('已停止','zh'),'已停止')
        self.assertEqual(language.local('已停止','de'),'Gestoppt')
        self.assertEqual(language.local('已送到終端 · Claude','fr'),'Envoyé au terminal · Claude')
        self.assertEqual(language.local('not a known message','ja'),'not a known message')
        page = (ROOT/'dictation/index.html').read_text()
        table = json.loads(next(line for line in page.split('\n') if line.startswith('const UI_STRINGS = '))[len('const UI_STRINGS = '):].rstrip(';'))
        # The page is in Chinese or English only: every other interface language sees English.
        for chinese,texts in table.items():
            self.assertEqual(set(texts),{'en'},chinese)
        # The one language picker lists spoken languages; each interface language has one.
        speech = json.loads(re.sub(r'(\w+):', r'"\1":', next(line for line in page.split('\n') if line.startswith('const SPEECH='))[len('const SPEECH='):].rstrip(';')).replace("'", '"'))
        for code in language.LANGUAGES:
            self.assertIn('<option value="%s">'%speech[code],page)
            self.assertIn("'%s'"%code,(ROOT/'dictation/server.py').read_text())

    def test_replies_are_read_in_their_own_language(self):
        language = sys.modules['language']
        samples = {
            'en':'The build is done and all of the tests are passing for this change.',
            'es':'He terminado la tarea y los cambios que pediste ya están en la rama principal.',
            'de':'Die Aufgabe ist fertig und die Änderungen sind nicht mehr auf dem alten Zweig.',
            'fr':"J'ai terminé la tâche et les changements sont dans la branche pour que vous puissiez les voir.",
            'ja':'タスクが完了しました。変更をご確認ください。',
            'ko':'작업이 완료되었습니다. 변경 사항을 확인하세요.',
            'zh':'已完成今天的工作摘要。',
        }
        for code,text in samples.items():
            for interface in language.LANGUAGES:
                self.assertEqual(language.spoken(text,interface),code,(code,interface))
            long = voice.summarize((text+' ')*40)
            self.assertTrue(long.startswith(language.SPOKEN[code][0]),long[:40])
            self.assertEqual(language.spoken(long,'en'),code)
        # Too little to tell: the interface language decides, and a language without a voice of its own is English.
        self.assertEqual(language.spoken('OK','de'),'de')
        self.assertEqual(language.spoken('OK','ja'),'en')
        spec = importlib.util.spec_from_file_location('synthesize', ROOT/'voice/synthesize.py')
        synthesize = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(synthesize)
        self.assertEqual(set(synthesize.SPEAKERS),set(language.LANGUAGES))

    def test_ignores_nonfinal_events(self):
        self.assertIsNone(voice.codex_event({'type':'event_msg','payload':{'type':'agent_message','message':'interim'}}))
        self.assertEqual(voice.codex_event({'type':'event_msg','payload':{'type':'turn_aborted'}}),('end',None))

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
            # A new install is English; one from before 3.3 that never chose a language stays Chinese.
            language = home/'.config/omalauncher/voice-ui-language'
            self.assertFalse(language.exists())
            (home/build_store.MARKER).write_text('3.2-00000000')
            subprocess.run([sys.executable,str(ROOT/'install.py'),'--skip-deps'],env=env,check=True,stdout=subprocess.DEVNULL)
            self.assertEqual(language.read_text(),'zh')
            tile = (home/'.config/omalauncher/widgets/46-speak.owl').read_text()
            self.assertNotIn('__',tile.split('"""')[0])
            self.assertNotIn(directory,tile)
            self.assertEqual((home/build_store.MARKER).read_text(),build_store.payload_id())
            for marker in build_store.WIDGET_MARKERS.values():
                self.assertEqual((home/marker).read_text(),build_store.payload_id())
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
        # Notes added to English text are English, so the English voice is the one chosen for it.
        english = voice.summarize('This sentence is part of a long reply. '*30+'See https://example.com and\n```\ncode\n```')
        self.assertTrue(english.startswith('Excerpt. '))
        self.assertFalse(chinese(english))
        self.assertFalse(chinese(voice.clean_text('See https://example.com and\n```\ncode\n```')))
        self.assertTrue(voice.summarize('這是一句很長的回覆。'*80).startswith('回覆節錄。'))
        self.assertEqual(voice.local('正在播放 · 自然語音（線上）','en'),'Playing · online natural')
        self.assertEqual(voice.local('播放完成 · 離線基本語音（'+synthesize.UNREACHABLE+'）','en'),'Finished · offline basic (online voice unreachable)')
        for reason in (synthesize.NOT_INSTALLED,synthesize.NO_MPG123,synthesize.UNREACHABLE):
            self.assertIn(reason,sys.modules['language'].REASONS)

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
                # The store shows the name, the description and the preview as they are: English.
                head = text.split('requires')[0]
                self.assertFalse(chinese(head.split('source uiLanguage')[0]),head)
                self.assertEqual(text.count('"""')%2,0)
                # The store's reviewer reads these as a request for root; a translation must not look like one.
                import re
                self.assertIsNone(re.search(r'\bsudo\b|\bsu\s',text))

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
            self.assertEqual((home/build_store.WIDGET_MARKERS['terminal-voice']).read_text(),build_store.payload_id())
            self.assertEqual((home/'.cache/oma-voice/setup-state').read_text(),'done')
            language = home/'.config/omalauncher/voice-ui-language'
            subprocess.run(['bash','-c',script],env=dict(os.environ,HOME=directory),check=True)
            self.assertFalse(language.exists())
            (home/build_store.MARKER).write_text('3.2-00000000')
            subprocess.run(['bash','-c',script],env=dict(os.environ,HOME=directory),check=True)
            self.assertEqual(language.read_text(),'zh')
            language.write_text('en')
            (home/build_store.MARKER).write_text('3.1-00000000')
            subprocess.run(['bash','-c',script],env=dict(os.environ,HOME=directory),check=True)
            self.assertEqual(language.read_text(),'en')
            # Installing an older store tile must not overwrite newer shared programs.
            newer = '99.0-aabbccdd'
            (home/build_store.MARKER).write_text(newer)
            program = home/'.local/share/oma-voice/oma_voice.py'
            program.write_text('newer program')
            subprocess.run(['bash','-c',script],env=dict(os.environ,HOME=directory),check=True)
            self.assertEqual((home/build_store.MARKER).read_text(),newer)
            self.assertEqual(program.read_text(),'newer program')
            self.assertEqual((home/build_store.WIDGET_MARKERS['terminal-voice']).read_text(),build_store.payload_id())

    def test_installer_updates_the_active_store_dictation_tile(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            tile = home/'.config/omalauncher/widgets/market-weebowiz-dictation.owl'
            tile.parent.mkdir(parents=True)
            tile.write_text('old store tile')
            subprocess.run([sys.executable,str(ROOT/'install.py'),'--skip-deps'],
                           env=dict(os.environ,HOME=directory),check=True,stdout=subprocess.DEVNULL)
            self.assertEqual(tile.read_text(),build_store.render((ROOT/'widgets/47-voice-input.owl').read_text()))
            self.assertFalse((tile.parent/'47-voice-input.owl').exists())

if __name__ == '__main__':
    unittest.main()
