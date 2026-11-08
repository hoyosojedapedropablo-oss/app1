import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import live


def make_segment(path, seconds=10, loud=False):
 tone='sine=frequency=440:sample_rate=16000'
 volume='volume=1.0' if loud else 'volume=0.05'
 subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'testsrc2=size=320x180:rate=10','-f','lavfi','-i',tone,'-t',str(seconds),
                 '-af',volume,'-c:v','libx264','-preset','ultrafast','-c:a','aac','-f','mpegts',str(path)],check=True,capture_output=True)


class FakeWord:
 def __init__(self,start,end,word):self.start,self.end,self.word=start,end,word
class FakeSegment:
 def __init__(self,start,end,text):
  self.start,self.end,self.text=start,end,text
  words=text.split();step=(end-start)/max(1,len(words))
  self.words=[FakeWord(start+i*step,start+(i+1)*step,w) for i,w in enumerate(words)]
class FakeWhisper:
 def __init__(self):self.calls=0
 def transcribe(self,audio,**kw):
  self.calls+=1
  return iter([FakeSegment(0.5,4.5,f'Frase {self.calls} uno dos tres cuatro.'),FakeSegment(5,9.5,f'Respuesta {self.calls} cinco seis siete ocho.')]),None


class LiveUnitTests(unittest.TestCase):
 def test_url_validation(self):
  self.assertEqual(live.validate_url('https://kick.com/destiny/'),('kick','https://kick.com/destiny'))
  self.assertEqual(live.validate_url('https://www.youtube.com/@DWEspanol/live')[0],'youtube')
  for bad in ('https://twitch.tv/x','ftp://kick.com/a','https://user:pw@kick.com/a','https://kick.com/'):
   with self.assertRaises(live.LiveError):live.validate_url(bad)

 def test_resolve_reports_offline_and_restricted_streams_clearly(self):
  def factory(message):
   class Y:
    def __init__(self,options):pass
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def extract_info(self,*a,**k):raise Exception(message)
   return Y
  with patch('youtube_import.javascript_options',return_value={}):
   with self.assertRaisesRegex(live.LiveError,'no está transmitiendo'):live.resolve('https://kick.com/a',ydl_factory=factory('ERROR: [kick:live] a: The channel is not currently live'))
   with self.assertRaisesRegex(live.LiveError,'no evita restricciones'):live.resolve('https://youtube.com/x',ydl_factory=factory('Sign in to confirm your age'))

 def test_capture_command_maps_separate_youtube_audio(self):
  stream={'parts':[{'url':'https://v/video.m3u8','headers':{'User-Agent':'x'}},{'url':'https://v/audio.m3u8','headers':{}}]}
  cmd=live.ffmpeg_capture_command(stream,Path('seg'),42)
  self.assertEqual(cmd.count('-i'),2);self.assertIn('1:a:0?',cmd);self.assertIn('42',cmd);self.assertIn('-reconnect',cmd)

 def test_loudness_and_peaks(self):
  quiet=np.full(16000*40,.01,dtype='float32');loud=np.full(16000*4,.5,dtype='float32')
  levels=live.loudness(np.concatenate([quiet[:16000*20],loud,quiet[:16000*16]]))
  peaks=live.audio_peaks([(float(i),db) for i,db in enumerate(levels)],0,40)
  self.assertEqual(len(peaks),1);self.assertEqual((peaks[0]['start'],peaks[0]['end']),(20.0,24.0));self.assertGreater(peaks[0]['db'],20)

 def test_peak_moment_uses_whole_phrases_and_keeps_tail_context(self):
  phrases=[{'start':s,'end':s+4.5,'text':'x'} for s in range(0,120,5)]
  spot=live.peak_moment({'start':50,'end':53,'db':15},phrases,20,60,0,120)
  self.assertTrue(20<=spot['end']-spot['start']<=60);self.assertIn(spot['start'],[p['start'] for p in phrases]);self.assertLessEqual(spot['start'],50)
  self.assertIsNone(live.peak_moment({'start':110,'end':114,'db':15},phrases,20,60,0,118))

 def test_duplicates(self):
  self.assertTrue(live.overlaps({'start':10,'end':40},{'start':20,'end':50}))
  self.assertFalse(live.overlaps({'start':10,'end':40},{'start':38,'end':70}))
  self.assertTrue(live.similar_text('Esto fue increíble de verdad','esto fue increible de verdad'))


class LiveSessionTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)

 def session(self):
  s=live.LiveSession(self.root,'https://kick.com/canal',minimum=10,maximum=30,buffer_minutes=10)
  s.segments.mkdir(parents=True);s.clips.mkdir(parents=True);s._model=FakeWhisper();s.transcription_device='CPU'
  return s

 def test_ingest_builds_absolute_timeline_and_renders_moment(self):
  s=self.session()
  for i in range(4):make_segment(s.segments/f'seg{i:06d}.ts',loud=(i==2))
  for p in s._closed_segments():s._ingest(p)
  self.assertAlmostEqual(s.media_s,40,delta=.5);self.assertEqual(s.processed_index,3)
  self.assertAlmostEqual(s.transcript[2]['start'],10.5,delta=.2)   # second segment's first phrase, absolute time
  self.assertGreater(max(db for t,db in s.levels if 20<=t<30),max(db for t,db in s.levels if t<10)+15)
  s._add_moment({'start':12,'end':28,'title':'Prueba','text':'Frase','score':80,'source':'IA local'})
  m=s.moments[0];self.assertEqual(m['status'],'draft')
  out=s.clips/f'{m["id"]}.mp4';self.assertGreater(live.probe_duration(out),21)   # 16 s + 3 s padding each side
  shifted=s.moment_transcript(m);self.assertTrue(all(seg['start']>-1 for seg in shifted))

 def test_detection_falls_back_to_audio_peaks_without_ai(self):
  s=self.session()
  for i in range(18):make_segment(s.segments/f'seg{i:06d}.ts',loud=(i==9))
  for p in s._closed_segments():s._ingest(p)
  with patch.object(s,'_ai_candidates',side_effect=RuntimeError('sin IA')):s._detect(s.media_s)
  self.assertEqual(len(s.moments),1);m=s.moments[0]
  self.assertEqual(m['source'],'Señal de audio');self.assertTrue(m['start']<=92 and m['end']>=90)
  self.assertNotIn('?',m['title']);self.assertEqual(m['status'],'draft')
  with patch.object(s,'_ai_candidates',side_effect=RuntimeError('sin IA')):s._detect(s.media_s)
  self.assertEqual(len(s.moments),1)   # same peak is not proposed twice

 def test_ai_candidates_are_shifted_back_to_session_time(self):
  s=self.session();s.transcript=[{'start':400.0+i*5,'end':404.0+i*5,'text':'hola mundo.','words':[{'start':400.0+i*5,'end':404.0+i*5,'text':'hola'}]} for i in range(60)]
  s.media_s=700
  def fake_select(transcript,minimum,maximum,duration,**kw):
   self.assertGreaterEqual(transcript[0]['start'],0);self.assertLessEqual(duration,live.WINDOW_S)
   return [{'start':10.0,'end':30.0,'title':'Un título'}]
  with patch('gpu_ai.status',return_value={'available':True,'model_ready':True}),patch('gpu_ai.select_gpu',side_effect=fake_select):
   result,topics=s._ai_candidates([x for x in s.transcript if x['start']>=520],520,700)
  self.assertEqual((result[0]['start'],result[0]['end']),(530.0,550.0));self.assertEqual(topics,[])

 def test_state_survives_restart_as_interrupted(self):
  s=self.session();s.status='live';s.media_s=125.5;s.moments=[{'id':'m1','status':'draft','start':1,'end':20,'title':'t'}];s.segment_times={3:[30,40]};s.save(force=True)
  loaded=live.LiveSession.load(s.root)
  self.assertEqual(loaded.status,'interrupted');self.assertEqual(loaded.media_s,125.5);self.assertEqual(loaded.segment_times,{3:[30,40]});self.assertEqual(loaded.moments[0]['id'],'m1')

 def test_eviction_keeps_only_the_buffer(self):
  s=self.session();s.buffer_s=60
  for i in range(10):(s.segments/f'seg{i:06d}.ts').write_bytes(b'x');s.segment_times[i]=[i*10,i*10+10]
  s.media_s=100;s._evict()
  self.assertEqual(sorted(int(p.stem[3:]) for p in s.segments.glob('*.ts')),[3,4,5,6,7,8,9])

 def test_supervisor_reconnects_then_ends_when_stream_finishes(self):
  s=self.session();calls=[]
  def resolver(url,height):
   calls.append(1)
   if len(calls)==1:return {'title':'Directo','channel':'Canal','parts':[{'url':'x','headers':{}}]}
   if len(calls)==2:raise live.LiveError('No se pudo conectar con el directo.')
   raise live.LiveError('El canal no está transmitiendo en vivo en este momento.')
  class Proc:
   def __init__(self,*a,**k):s.media_s=50;self.n=0
   def poll(self):self.n+=1;return None if self.n<2 else 1
   def terminate(self):pass
   def wait(self,*a):return 0
  with patch.object(live.subprocess,'Popen',Proc),patch.object(s,'_wait_retry',lambda *a:None),patch.object(s,'_final_detection'):
   s._capture(resolver)
   for _ in range(50):
    if s.status=='ended':break
    time.sleep(.1)
  self.assertEqual(s.status,'ended');self.assertEqual(len(calls),3);self.assertEqual(s.reconnects,1);self.assertFalse(s.segments.exists())


class LiveApiTests(unittest.TestCase):
 def test_open_moment_creates_editable_job(self):
  import app as backend
  from fastapi.testclient import TestClient
  with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'DATA',Path(tmp)),patch.dict(backend.JOBS,{},clear=True),patch.dict(backend.LIVE,{},clear=True):
   s=live.LiveSession(Path(tmp)/'live','https://kick.com/canal',minimum=10,maximum=30);s.segments.mkdir(parents=True);s.clips.mkdir(parents=True)
   s._model=FakeWhisper();s.channel='Canal'
   for i in range(3):make_segment(s.segments/f'seg{i:06d}.ts')
   for p in s._closed_segments():s._ingest(p)
   s._add_moment({'start':10.5,'end':24.5,'title':'Momento','text':'Frase 2 uno dos','score':70,'source':'IA local'})
   backend.LIVE[s.id]=s;client=TestClient(backend.app);mid=s.moments[0]['id']
   job=client.post(f'/api/live/{s.id}/moments/{mid}/open').json()
   self.assertEqual(job['status'],'ready');self.assertEqual(len(job['clips']),1);clip=job['clips'][0]
   self.assertAlmostEqual(clip['start'],3.0,delta=.1);self.assertAlmostEqual(clip['end']-clip['start'],14,delta=.1)
   self.assertTrue(clip['captions']);self.assertEqual(client.get(f'/api/jobs/{job["id"]}/video').status_code,200)
   self.assertEqual(client.post(f'/api/live/{s.id}/moments/{mid}/open').json()['id'],job['id'])   # opening twice reuses the job
   self.assertEqual(client.get(f'/api/live/{s.id}').json()['moments'][0]['status'],'opened')
   self.assertEqual(client.post('/api/live',json={'url':'https://twitch.tv/x'}).status_code,400)


if __name__=='__main__':
 unittest.main()
