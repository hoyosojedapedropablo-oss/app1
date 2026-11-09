import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
import app as backend
import tracking
from styling import title_bitmap


def result_with(centres, width=1920, height=1080):
 samples=[dict(t=i/8,active=0,faces=[dict(id=0,x=c-60,y=300,w=120,h=120)]) for i,c in enumerate(centres)]
 return dict(width=width,height=height,samples=samples,persons=[])


class FramingTests(unittest.TestCase):
 def test_zoom_levels_keep_proportional_black_bands(self):
  self.assertEqual(tracking.band_height('crop'),1920)
  bands=[tracking.band_height('zoom',z) for z in ('soft','balanced','close')]
  self.assertEqual(bands,sorted(bands));self.assertEqual(tracking.band_height('zoom','balanced'),1152)   # ~59% like the reference
  g=tracking.geometry(1920,1080,'zoom','balanced')
  self.assertAlmostEqual(1080/g['scale']/1920,.527,delta=.01)        # mostly a lateral crop of a 16:9 source
  self.assertLess(g['scale'],1.1)                                     # barely any upscaling: stays sharp
  self.assertIn('pad=1080:1920:0:384',tracking.static_filter('zoom','balanced',50,50))
  self.assertNotIn('pad',tracking.static_filter('crop','balanced',50,50))

 def test_static_zoom_export_has_bands_and_no_distortion(self):
  client=TestClient(backend.app)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'src.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=white:size=1280x720:rate=24','-vf','drawbox=x=590:y=310:w=100:h=100:color=red:t=fill','-t','1','-c:v','libx264',str(source)])
   with source.open('rb') as raw:ident=client.post('/api/upload',files={'file':('src.mp4',raw,'video/mp4')}).json()['id']
   response=client.post(f'/api/jobs/{ident}/export',json=dict(start=0,end=1,title='',subtitles='',framing='zoom',zoom='balanced'))
   self.assertEqual(response.status_code,200,response.text[:300])
   out=Path(tmp)/'out.mp4';out.write_bytes(response.content);frame=Path(tmp)/'f.png'
   backend.command(['ffmpeg','-v','error','-y','-ss','0.5','-i',str(out),'-frames:v','1',str(frame)])
   image=np.array(Image.open(frame).convert('RGB')).astype(int)
   self.assertLess(image[:370].max(),25);self.assertLess(image[1550:].max(),25)          # bands
   red=np.argwhere((image[:,:,0]>180)&(image[:,:,1]<80))
   h=red[:,0].max()-red[:,0].min();w=red[:,1].max()-red[:,1].min()
   self.assertAlmostEqual(w/h,1,delta=.06)                                                  # square stays square


class PathTests(unittest.TestCase):
 def test_subject_that_fits_keeps_the_camera_still(self):
  path=tracking.build_path(result_with([900+20*np.sin(i/3) for i in range(80)]),framing='zoom')
  self.assertTrue(path['static']);self.assertEqual(len(set(path['x'])),1)

 def test_small_head_motion_inside_dead_zone_does_not_move(self):
  centres=[600]*40+[1400]*40+[1420,1380]*20
  path=tracking.build_path(result_with(centres),framing='crop')
  tail=path['x'][-int(2*tracking.PATH_FPS):]
  self.assertLess(max(tail)-min(tail),.5)

 def test_motion_modes_limit_speed_and_never_jump(self):
  centres=[300]*24+[1600]*56
  g=tracking.geometry(1920,1080,'crop');visible=1080/g['scale'];extra=g['sw']-1080
  speeds={}
  for motion in ('smooth','balanced','fast'):
   x=np.array(tracking.build_path(result_with(centres),motion=motion,framing='crop')['x'])*extra/100   # scaled px
   per_second=np.abs(np.diff(x)).max()*tracking.PATH_FPS/g['scale']
   self.assertLessEqual(per_second,tracking.MOTION[motion]['speed']*visible*1.02)
   v=np.abs(np.diff(x));ramp=(np.argmax(v>=.9*v.max())-np.argmax(v>.05*v.max()))/tracking.PATH_FPS
   self.assertGreaterEqual(ramp,.5)                                                       # eased: speeds up over >=0.5 s, never a jump
   self.assertLessEqual(np.abs(np.diff(np.diff(x))).max(),v.max()/8)
   speeds[motion]=per_second
  self.assertLess(speeds['smooth'],speeds['balanced']);self.assertLess(speeds['balanced'],speeds['fast'])

 def test_export_commands_follow_the_preview_path_every_frame(self):
  result=result_with([300]*24+[1600]*56);path=tracking.build_path(result,framing='zoom',motion='balanced')
  with tempfile.TemporaryDirectory() as tmp:
   chain=tracking.commands(path,Path(tmp)/'c.cmd',10,60,1920,1080)
   lines=(Path(tmp)/'c.cmd').read_text().splitlines()
  self.assertEqual(len(lines),600)                                                         # one position per output frame
  g=tracking.geometry(1920,1080,'zoom');extra=g['sw']-1080
  for line in lines[::37]:
   t=float(line.split()[0]);x=int(line.split(' x ')[1].rstrip(';'))
   # The preview interpolates the same path at the same time (applyTracking in app.js).
   i=t*path['fps'];a=min(len(path['x'])-1,int(i));b=min(len(path['x'])-1,a+1)
   preview=path['x'][a]+(path['x'][b]-path['x'][a])*(i-a)
   preview=round(preview*path['extra']/200)*2                                             # app.js rounds the same way
   self.assertEqual(preview,x)
  self.assertIn('crop@follow=1080:1152',chain);self.assertIn('pad=1080:1920:0:384',chain)


class TitleAndSettingsTests(unittest.TestCase):
 def test_rounded_title_corners_are_transparent_and_square_is_default_for_old_projects(self):
  rounded=title_bitmap('Un título de prueba','Montserrat',48,20,10,'#FFEB00','#000000',corners='rounded')
  square=title_bitmap('Un título de prueba','Montserrat',48,20,10,'#FFEB00','#000000')
  self.assertEqual(rounded.size,square.size)
  self.assertEqual(rounded.getpixel((0,0))[3],0);self.assertEqual(square.getpixel((0,0))[3],255)
  self.assertEqual(rounded.getpixel((rounded.width//2,2))[3],255)

 def test_without_subtitles_the_export_has_no_caption_pixels(self):
  client=TestClient(backend.app)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'src.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=black:size=1280x720:rate=24','-t','2','-c:v','libx264',str(source)])
   with source.open('rb') as raw:ident=client.post('/api/upload',files={'file':('src.mp4',raw,'video/mp4')}).json()['id']
   base=dict(start=0,end=2,title='',subtitles='TEXTO DE PRUEBA',captions=[dict(start=0,end=2,text='TEXTO DE PRUEBA')],framing='crop')
   bright={}
   for show in (True,False):
    out=Path(tmp)/f'{show}.mp4';out.write_bytes(client.post(f'/api/jobs/{ident}/export',json=dict(base,show_subtitles=show)).content)
    frame=Path(tmp)/'f.png';backend.command(['ffmpeg','-v','error','-y','-ss','1','-i',str(out),'-frames:v','1',str(frame)])
    bright[show]=int((np.array(Image.open(frame).convert('L'))>200).sum())
   self.assertGreater(bright[True],500);self.assertEqual(bright[False],0)

 def test_new_projects_get_new_defaults_and_old_ones_keep_theirs(self):
  client=TestClient(backend.app)
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'src.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=320x180:rate=8','-t','1','-c:v','libx264',str(source)])
   with source.open('rb') as raw:ident=client.post('/api/upload',files={'file':('src.mp4',raw,'video/mp4')}).json()['id']
   settings=client.get(f'/api/jobs/{ident}').json()['clip_settings']
   self.assertEqual((settings['framing'],settings['zoom'],settings['tracking'],settings['subtitles'],settings['title_corners']),('zoom','balanced',True,True,'rounded'))
   saved=client.put(f'/api/jobs/{ident}/clip-settings',json=dict(settings,subtitles=False,framing='crop')).json()
   self.assertEqual((saved['subtitles'],saved['framing']),(False,'crop'))
   self.assertFalse(json.loads((backend.DATA/ident/'job.json').read_text(encoding='utf-8'))['clip_settings']['subtitles'])
   old=dict(backend.JOBS[ident]);old.pop('clip_settings')
   self.assertEqual(backend.clip_settings(old)['framing'],'crop');self.assertEqual(backend.clip_settings(old)['title_corners'],'square')
   self.assertTrue(backend.clip_settings(old)['legacy'])
   self.assertEqual(client.put(f'/api/jobs/{ident}/clip-settings',json=dict(settings,zoom='giant')).status_code,422)


if __name__=='__main__':
 unittest.main()


class SceneCutTests(unittest.TestCase):
 def test_camera_jumps_at_a_scene_cut_and_moves_smoothly_inside_shots(self):

  r=result_with([400]*40+[1500]*40);r['cuts']=[5.0]
  x=np.array(tracking.build_path(r,framing='crop')['x'])
  i=int(5*tracking.PATH_FPS)
  self.assertGreater(abs(x[i]-x[i-1]),40)                                   # instant reposition at the cut
  self.assertLess(np.abs(np.diff(x[:i-1])).max(),.01);self.assertLess(np.abs(np.diff(x[i+1:])).max(),.01)


class ChosenPersonTests(unittest.TestCase):
 def test_absent_chosen_person_falls_back_to_the_speaker(self):
  samples=[dict(t=i/8,active=0,faces=[dict(id=0,x=200,y=300,w=120,h=120)]+([dict(id=1,x=1500,y=300,w=120,h=120)] if i<40 else [])) for i in range(80)]
  r=dict(width=1920,height=1080,samples=samples,persons=[],cuts=[5.0])
  x=np.array(tracking.build_path(r,person='1',framing='crop')['x'])
  self.assertGreater(x[int(2*tracking.PATH_FPS)],80)        # follows person 1 while visible (right side)
  self.assertLess(x[-1],10)                                   # after the cut person 1 is gone: frames the speaker (left)
