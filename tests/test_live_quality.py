import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import live
import viral


class TopicTests(unittest.TestCase):
 phrases=[{'start':s,'end':s+4.5,'text':'x'} for s in range(0,120,5)]

 def test_clip_is_cut_where_the_topic_changes(self):
  topics=[{'start':0,'end':34.5,'label':'a','boundary':False},{'start':35,'end':90,'label':'b','boundary':True}]
  clip=live.cut_at_topic_change({'start':5,'end':60},topics,self.phrases,20)
  self.assertEqual(clip['end'],34.5);self.assertTrue(clip['cut_at_topic'])

 def test_too_short_first_topic_drops_the_clip(self):
  topics=[{'start':0,'end':14.5,'boundary':False},{'start':15,'end':90,'boundary':True}]
  self.assertIsNone(live.cut_at_topic_change({'start':5,'end':60},topics,self.phrases,20))

 def test_no_topics_keeps_the_clip(self):
  self.assertEqual(live.cut_at_topic_change({'start':5,'end':60},[],self.phrases,20),{'start':5,'end':60})

 def test_open_topic_waits(self):
  topics=[{'start':0,'end':40},{'start':41,'end':176}]
  self.assertTrue(live.topic_still_open({'start':120,'end':174},topics,180))
  self.assertFalse(live.topic_still_open({'start':10,'end':39},topics,180))


class ViralTitleTests(unittest.TestCase):
 text='le faltan dos semanas a la guarida nueva y ya me gasté toda la plata que tenía en los muebles'

 def fake(self,titles,best=0):
  return lambda payload,cancel=None:{'afirmacion':'le faltan dos semanas a la guarida','tipo':'confesión','titulos':titles,'mejor':best}

 def test_best_grounded_title_first_and_separators_removed(self):
  result=viral.generate(self.text,'Westcol',complete=self.fake(['Westcol muestra su casa | otra cosa','«Ya me gasté toda la plata»: Westcol y su guarida nueva','Descubre la guarida','Westcol habla','¿Cuándo estará la guarida? | x'],best=1))
  self.assertEqual(result['title'],'«Ya me gasté toda la plata»: Westcol y su guarida nueva')
  self.assertNotIn('Descubre la guarida',result['titles'])
  self.assertTrue(all('|' not in t for t in result['titles']))

 def test_invented_titles_are_rejected(self):
  result=viral.generate(self.text,'Westcol',complete=self.fake(['Westcol revela su divorcio con Karina','Westcol confirma pelea con Samulx','Westcol anuncia nuevo coche deportivo','Westcol gana millones apostando','Westcol deja Kick para siempre']))
  self.assertIsNone(result)

 def test_filler_words_are_not_names(self):
  self.assertFalse(viral.grounded_title('Broder confiesa algo','hola como estas'))


class FakeInfo:
 language='es';language_probability=.95


class TranscriptionTests(unittest.TestCase):
 def test_overlap_does_not_duplicate_words_and_language_is_fixed(self):
  calls=[]
  class Word:
   def __init__(self,start,end,word):self.start,self.end,self.word=start,end,word
  class Seg:
   def __init__(self,words):self.words=words;self.text=''.join(w.word for w in words);self.start=words[0].start;self.end=words[-1].end
  class Model:
   def transcribe(self,audio,**kw):
    calls.append(kw);n=len(audio)/16000
    # one word every second of the audio it receives, including the carried-over part
    return iter([Seg([Word(i,i+.5,f' w{i}') for i in range(int(n))])]),FakeInfo()
  with tempfile.TemporaryDirectory() as tmp:
   s=live.LiveSession(Path(tmp),'https://kick.com/canal');s.segments.mkdir(parents=True);s._model=Model()
   audio=np.zeros(16000*6,dtype='<f4')
   with patch.object(live.subprocess,'run',return_value=type('R',(),{'stdout':audio.tobytes()})()):
    s._ingest(Path('seg000000.ts'));s._ingest(Path('seg000001.ts'))
  starts=[w['start'] for seg in s.transcript for w in seg['words']]
  self.assertEqual(starts,sorted(set(starts)))                   # no duplicated words from the overlap
  self.assertEqual(starts[:7],[0,1,2,3,4,5,6.5])
  self.assertEqual(s.language,'')                                   # 'auto' needs several agreeing detections (test_configure_first)
  self.assertIsNone(calls[0]['language']);self.assertIsNone(calls[1]['language'])
  self.assertTrue(calls[1]['initial_prompt'])

 def test_missing_turbo_model_falls_back_to_small_on_cpu_without_downloading(self):
  created=[]
  class Fake:
   def __init__(self,name,**kw):created.append((name,kw['device']))
  with tempfile.TemporaryDirectory() as tmp,patch('faster_whisper.WhisperModel',Fake),patch('faster_whisper.utils.download_model',side_effect=RuntimeError('not cached')),patch('gpu_ai.status',return_value={'gpu_loaded':True}):
   s=live.LiveSession(Path(tmp),'https://kick.com/canal');s._whisper()
  self.assertEqual(created,[('small','cpu')]);self.assertIn('large-v3-turbo',s.transcription_device)

 def test_installed_turbo_runs_on_gpu_when_vram_allows(self):
  created=[]
  class Fake:
   def __init__(self,name,**kw):created.append((name,kw['device'],kw['compute_type']))
  import capabilities
  with tempfile.TemporaryDirectory() as tmp,patch('faster_whisper.WhisperModel',Fake),patch('faster_whisper.utils.download_model',return_value='x'),patch('gpu_ai.status',return_value={'gpu_loaded':True}),patch.object(capabilities,'transcription_plan',return_value=('cuda','ok')),patch.object(capabilities,'free_vram_mb',return_value=2600):
   s=live.LiveSession(Path(tmp),'https://kick.com/canal');s._whisper()
  self.assertEqual(created,[('large-v3-turbo','cuda','int8')])

 def test_defaults(self):
  self.assertEqual(live.DEFAULT_HEIGHT,1080);self.assertLessEqual(live.DETECT_EVERY_S,30);self.assertLessEqual(live.SEGMENT_S,6)


if __name__=='__main__':
 unittest.main()
