import tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import app, command, Export, ass_file, probe, JOBS
from intelligence import accept_proposals, diverse_selection
from timeline import make_cues
from app import decode_audio
import numpy as np
from PIL import Image

class Workflow(unittest.TestCase):
 def test_decode_audio_without_pyav(self):
  from unittest.mock import patch
  from faster_whisper.feature_extractor import FeatureExtractor
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'stereo.wav'
   command(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-ac','2','-t','1',str(source)])
   with patch('av.open',side_effect=AssertionError('PyAV must not decode input')):
    audio=decode_audio(source)
    features=FeatureExtractor()(audio)
   self.assertEqual(audio.dtype,np.float32)
   self.assertEqual(audio.shape,(16000,))
   self.assertGreater(float(np.max(np.abs(audio))),0)
   self.assertEqual(features.shape[0],80)

 def test_vertical_crop_keeps_selected_subject_without_bands(self):
  c=TestClient(app)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'landscape.mp4'
   command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=red:size=960x540:rate=10','-vf','drawbox=x=0:y=0:w=320:h=540:color=lime:t=fill,drawbox=x=640:y=0:w=320:h=540:color=blue:t=fill','-t','1','-c:v','libx264',str(source)])
   with source.open('rb') as f: ident=c.post('/api/upload',files={'file':('video.mp4',f,'video/mp4')}).json()['id']
   for position,channel in [(0,1),(100,2)]:
    r=c.post(f'/api/jobs/{ident}/export',json=dict(start=0,end=0.5,title='',subtitles='',focus_x=position))
    self.assertEqual(r.status_code,200,r.text)
    out=Path(tmp)/'clip.mp4';out.write_bytes(r.content)
    frame=Path(tmp)/'frame.png'
    command(['ffmpeg','-v','error','-y','-i',str(out),'-frames:v','1',str(frame)])
    im=Image.open(frame)
    self.assertEqual(im.size,(1080,1920))
    for point in [(100,100),(540,960),(100,1800)]:
     pixel=im.getpixel(point)
     self.assertGreater(pixel[channel],200)
     self.assertLess(sum(pixel)-pixel[channel],40)

 def test_upload_export_and_ranges(self):
  c=TestClient(app)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.mp4'
   command(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=12','-f','lavfi','-i','sine=frequency=440','-t','2','-c:v','libx264','-c:a','aac',str(source)])
   with source.open('rb') as f: r=c.post('/api/upload',files={'file':('sample.mp4',f,'video/mp4')})
   self.assertEqual(r.status_code,200,r.text); ident=r.json()['id']
   opts=dict(start=0,end=1,title='Un dato curioso',subtitles='Subtítulos de prueba',style='bold',font='DejaVu Sans',logo='none',framing='crop')
   r=c.post(f'/api/jobs/{ident}/export',json=opts)
   self.assertEqual(r.status_code,200,r.text)
   output=Path(tmp)/'out.mp4'; output.write_bytes(r.content)
   video=next(s for s in probe(output)['streams'] if s['codec_type']=='video')
   self.assertEqual((video['width'],video['height']),(1080,1920))
   opts['end']=10
   self.assertEqual(c.post(f'/api/jobs/{ident}/export',json=opts).status_code,400)
   self.assertEqual(c.post(f'/api/jobs/{ident}/analyze',json={'minimum':60,'maximum':20}).status_code,422)
 def test_selection_range_and_coverage(self):
  candidates=[dict(id=str(i),start=i*30,end=i*30+25,score=90-i,text=f'Información concreta número {i} y tema {i}') for i in range(20)]
  chosen=diverse_selection(candidates,600,20,60,10)
  self.assertTrue(chosen)
  self.assertTrue(all(20<=c['end']-c['start']<=60 for c in chosen))
  self.assertLessEqual(sum(c['end']-c['start'] for c in chosen),180)
  self.assertLessEqual(len(chosen),10)
  self.assertFalse(diverse_selection([dict(candidates[0],end=120)],600,20,60))

 def test_caption_progression_and_silence(self):
  transcript=[dict(start=0,end=60,text='uno dos tres cuatro cinco seis siete ocho',words=[dict(text=str(i),start=i*4,end=i*4+.5) for i in range(12)])]
  cues=make_cues(transcript,0,50)
  self.assertGreater(len(cues),10)
  self.assertTrue(all(c['end']-c['start']<1 for c in cues))
  self.assertTrue(all(a['end']<=b['start'] for a,b in zip(cues,cues[1:])))
  self.assertNotEqual(cues[0]['text'],cues[-1]['text'])
  self.assertTrue(all(0<=c['start']<c['end']<=50 for c in cues))

 def test_interpreted_titles_and_evidence(self):
  phrases=[dict(start=0,end=25,text='Antes dormía cuatro horas. Ahora hago menos directos para cuidar mi salud.')]
  data={'moments':[dict(first=0,last=0,category='Emoción',hook=5,payoff=4,novelty=4,emotion=5,discussion=4,coherent=True,reason='Contrasta dinero y salud',evidence='dormía cuatro horas',titles=['Westcol explica por qué hace menos directos'])]}
  clips=accept_proposals(data,phrases,phrases,20,60,'Westcol')
  self.assertEqual(len(clips),1)
  self.assertLessEqual(len(clips[0]['title']),64)
  data['moments'][0]['evidence']='Una pelea que nunca ocurrió'
  self.assertFalse(accept_proposals(data,phrases,phrases,20,60))

 def test_original_caption_timing(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'captions.ass'
   ass_file(path,Export(start=10,end=15,title='Título',subtitles='Hola mundo.'),[dict(start=11,end=13,text='Hola mundo.')])
   self.assertIn('0:00:01.00,0:00:02.00,Caption',path.read_text())
   self.assertIn('0:00:02.00,0:00:03.08,Caption',path.read_text())

if __name__=='__main__': unittest.main()
