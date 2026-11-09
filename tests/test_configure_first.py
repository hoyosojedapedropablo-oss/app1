import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import live


def alive(pid):
 out=subprocess.run(['tasklist','/FI',f'PID eq {pid}','/NH'],capture_output=True,text=True).stdout
 return str(pid) in out


class Info:
 def __init__(self,lang,p):self.language=lang;self.language_probability=p
class Seg:
 def __init__(self):
  class W:start=.2;end=.6;word=' hola'
  self.words=[W()];self.text=' hola';self.start=.2;self.end=.6


class LanguageTests(unittest.TestCase):
 def session(self,choice):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  s=live.LiveSession(Path(tmp.name),'https://kick.com/canal',language=choice);s.segments.mkdir(parents=True)
  return s

 def feed(self,s,detections):
  seen=[]
  class Model:
   def transcribe(self,audio,**kw):seen.append(kw['language']);lang,p=detections.pop(0);return iter([Seg()]),Info(lang,p)
  s._model=Model();audio=np.zeros(16000*6,dtype='<f4')
  with patch.object(live.subprocess,'run',return_value=type('R',(),{'stdout':audio.tobytes()})()):
   for i in range(len(detections)):s._ingest(Path(f'seg{i:06d}.ts'))
  return seen

 def test_chosen_language_is_used_from_the_first_segment(self):
  s=self.session('es');seen=self.feed(s,[('en',.99),('en',.99)])
  self.assertEqual(seen,['es','es']);self.assertEqual(s.language,'es')

 def test_one_noisy_chunk_does_not_lock_a_wrong_language(self):
  s=self.session('auto')
  seen=self.feed(s,[('en',.95),('es',.9),('es',.85),('es',.92),('es',.9)])
  self.assertEqual(s.language,'es');self.assertEqual(seen[:4],[None,None,None,None]);self.assertEqual(seen[4],'es')

 def test_low_confidence_detections_never_lock(self):
  s=self.session('auto');self.feed(s,[('en',.7),('en',.6),('en',.75),('en',.5)])
  self.assertEqual(s.language,'')

 def test_language_and_settings_survive_a_restart(self):
  s=self.session('es');s.clip_settings={'framing':'crop','subtitles':False};s.save(force=True)
  loaded=live.LiveSession.load(s.root)
  self.assertEqual((loaded.language,loaded.language_choice,loaded.clip_settings['subtitles']),('es','es',False))


@unittest.skipUnless(os.name=='nt','Windows job objects')
class CaptureLifetimeTests(unittest.TestCase):
 def test_capture_dies_when_the_app_is_killed(self):
  parent=textwrap.dedent(f'''
   import subprocess,sys,time
   sys.path.insert(0,{str(Path(live.__file__).parent)!r})
   import live
   p=subprocess.Popen(['ffmpeg','-v','error','-re','-f','lavfi','-i','testsrc=size=64x64:rate=5','-f','null','-'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   print(p.pid,live.kill_with_app(p),flush=True);time.sleep(60)
  ''')
  proc=subprocess.Popen([sys.executable,'-c',parent],stdout=subprocess.PIPE,text=True)
  pid,assigned=proc.stdout.readline().split()
  self.assertEqual(assigned,'True');self.assertTrue(alive(pid))
  proc.kill();proc.wait()                                     # a forced close, like closing the window
  for _ in range(30):
   if not alive(pid):break
   time.sleep(.2)
  self.assertFalse(alive(pid),'FFmpeg outlived ClipStudio')

 def test_orphan_captures_are_stopped_at_startup(self):
  with tempfile.TemporaryDirectory() as tmp:
   marker=str(Path(tmp)/'abc'/'segments'/'seg%06d.ts')
   orphan=subprocess.Popen(['ffmpeg','-v','error','-re','-f','lavfi','-i','testsrc=size=64x64:rate=5','-metadata',f'comment={marker}','-f','null','-'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   other=subprocess.Popen(['ffmpeg','-v','error','-re','-f','lavfi','-i','testsrc=size=64x64:rate=5','-f','null','-'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    time.sleep(.5)
    self.assertGreaterEqual(live.kill_orphan_captures(Path(tmp)),1)
    orphan.wait(timeout=10)
    self.assertIsNone(other.poll())                           # unrelated FFmpeg processes are left alone
   finally:
    for p in (orphan,other):
     if p.poll() is None:p.kill()


class ApiTests(unittest.TestCase):
 def test_live_start_keeps_language_and_clip_settings(self):
  import app as backend
  from fastapi.testclient import TestClient
  with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'LIVE_DIR',Path(tmp)),patch.dict(backend.LIVE,{},clear=True),patch.object(live.LiveSession,'start'):
   r=TestClient(backend.app).post('/api/live',json={'url':'https://kick.com/canal','minimum':15,'maximum':40,'language':'es','clip_settings':{'framing':'crop','subtitles':False}})
   self.assertEqual(r.status_code,200,r.text);s=next(iter(backend.LIVE.values()))
   self.assertEqual((s.language,s.minimum,s.maximum),('es',15,40))
   self.assertEqual((s.clip_settings['framing'],s.clip_settings['subtitles'],s.clip_settings['title_corners']),('crop',False,'rounded'))
   self.assertEqual(TestClient(backend.app).post('/api/live',json={'url':'https://kick.com/canal','clip_settings':{'zoom':'giant'}}).status_code,400)

 def test_setup_step_holds_all_questions(self):
  html=(Path(live.__file__).parent/'static'/'index.html').read_text(encoding='utf-8')
  modal=html[html.index('id="configModal"'):]
  for control in ('id="minimum"','id="maximum"','id="liveMin"','id="liveMax"','id="liveHeight"','id="liveBuffer"','id="liveLanguage"','name="cfgFraming"','name="cfgSubtitles"','id="cfgStart"'):
   self.assertIn(control,modal,control)
  self.assertEqual(html.count('id="liveMin"'),1)


if __name__=='__main__':
 unittest.main()
