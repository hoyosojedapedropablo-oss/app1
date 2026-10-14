import io,json,tempfile,unittest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app import app,command,probe,JOBS,Export,ass_file
from timeline import make_cues

class Editor(unittest.TestCase):
 def setUp(self):self.c=TestClient(app)
 def upload(self,source):
  with source.open('rb') as f:r=self.c.post('/api/upload',files={'file':('sample.mp4',f,'video/mp4')})
  self.assertEqual(r.status_code,200,r.text)
  return r.json()['id']
 def test_logo_interval_and_position_in_real_export(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);source=folder/'source.mp4'
   command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=lime:size=320x180:rate=4','-t','6','-c:v','libx264',str(source)])
   ident=self.upload(source)
   raw=io.BytesIO();Image.new('RGBA',(40,20),(255,0,0,255)).save(raw,format='PNG')
   r=self.c.post('/api/logos/custom',files={'file':('mi-logo.png',raw.getvalue(),'image/png')})
   self.assertEqual(r.status_code,200);logo=r.json()['id']
   r=self.c.post(f'/api/jobs/{ident}/export',json=dict(start=0,end=5,title='',subtitles='',logo=logo,logo_start=1,logo_end=3,logo_width=10,logo_x=0,logo_y=0))
   self.assertEqual(r.status_code,200,r.text)
   output=folder/'out.mp4';output.write_bytes(r.content)
   self.assertAlmostEqual(float(probe(output)['format']['duration']),5,delta=.25)
   for t,present in [(0.5,False),(1.5,True),(3.5,False)]:
    frame=folder/'frame.png';command(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(output),'-frames:v','1',str(frame)])
    pixel=Image.open(frame).getpixel((10,10))
    self.assertGreater(pixel[0 if present else 1],200)
    self.assertLess(pixel[1 if present else 0],40)
   r=self.c.post(f'/api/jobs/{ident}/export',json=dict(start=0,end=5,title='',subtitles='',logo=logo,logo_start=2,logo_end=8))
   self.assertEqual(r.status_code,400)
 def test_duration_is_enforced_on_export(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.mp4'
   command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=gray:size=320x180:rate=1','-t','130','-c:v','libx264',str(source)])
   ident=self.upload(source);JOBS[ident]['analysis_range']={'minimum':20,'maximum':60}
   for end in [15,125]:
    r=self.c.post(f'/api/jobs/{ident}/export',json=dict(start=5,end=end,title='',subtitles='',clip_id='candidate'))
    self.assertEqual(r.status_code,400,r.text)
   r=self.c.post(f'/api/jobs/{ident}/export',json=dict(start=5,end=25,title='',subtitles='',clip_id='candidate'))
   self.assertEqual(r.status_code,200,r.text)
   output=Path(tmp)/'out.mp4';output.write_bytes(r.content)
   self.assertAlmostEqual(float(probe(output)['format']['duration']),20,delta=.15)
 def test_title_compact_and_coordinates_and_outline(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'captions.ass'
   opts=Export(start=0,end=20,title='Westcol explica por qué prioriza su salud sobre los directos',subtitles='',title_x=35,title_y=20,caption_x=60,caption_y=75,caption_color='#FF0000',outline_color='#0000FF',outline_width=6,captions=[dict(start=2,end=3,text='Un subtítulo de prueba')])
   ass_file(path,opts)
   text=path.read_text(encoding='utf-8')
   self.assertIn(r'\pos(378.0,384.0)',text)
   self.assertIn(r'\pos(648.0,1440.0)',text)
   self.assertIn('&H000000FF',text)
   self.assertIn('&H00FF0000',text)
   title_line=next(line for line in text.splitlines() if ',Title,,' in line)
   self.assertLessEqual(title_line.count(r'\N'),1)
   self.assertIn('0:00:06.00',title_line)
 def test_clip_relative_captions_progress_through_middle_of_video(self):
  transcript=[dict(start=100,end=140,text=' '.join(str(i) for i in range(40)),words=[dict(start=100+i,end=100+i+.45,text=str(i)) for i in range(40)])]
  cues=make_cues(transcript,110,130)
  self.assertEqual(cues[0]['text'],'10')
  self.assertTrue(any('28' in c['text'] for c in cues))
  self.assertTrue(all(0<=c['start']<c['end']<=20 for c in cues))
  self.assertFalse(any(c['end']-c['start']>1.8 for c in cues))

if __name__=='__main__':unittest.main()
