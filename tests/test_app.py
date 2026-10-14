import tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import app, command, Export, ass_file, probe, select_clips
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
   self.assertEqual(c.post(f'/api/jobs/{ident}/analyze',json={'minimum':60,'maximum':20}).status_code,400)
 def test_selection(self):
  segments=[dict(start=i*5,end=(i+1)*5,text='Un dato increíble. ¿Sabías la verdad?') for i in range(12)]
  clips=select_clips(segments,10,20)
  self.assertTrue(clips)
  self.assertTrue(all(10<=c['end']-c['start']<=20 for c in clips))
  self.assertTrue(all(a['end']<=b['start'] for a,b in zip(clips,clips[1:])))
 def test_original_caption_timing(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'captions.ass'
   ass_file(path,Export(start=10,end=15,title='Título',subtitles='Hola mundo.'),[dict(start=11,end=13,text='Hola mundo.')])
   self.assertIn('0:00:01.00,0:00:03.00,Caption',path.read_text())

if __name__=='__main__': unittest.main()
