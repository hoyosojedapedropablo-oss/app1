import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
import app as backend
import tracking
from styling import title_layout

def face(ident,cx,h,act=0.0,front=.9,y=300):
 return dict(id=ident,x=cx-h/2,y=y,w=h,h=h,act=act,front=front)

class SpeakerChoiceTests(unittest.TestCase):
 """v3: who the camera follows (1920x1080 source, 8 samples/s)."""
 def choose(self,frames,cuts=()):
  samples=[dict(t=i/8,active=None,speech=True,faces=f) for i,f in enumerate(frames)]
  changes=tracking.choose_speakers(samples,list(cuts),1920,1080)
  return [s['active'] for s in samples],changes
 def test_clip_starts_on_the_speaker_not_on_the_biggest_face(self):
  # Real case: a bigger face at the bottom right edge, looking down and silent; the speaker is in the middle.
  frames=[[face(0,1800,210,act=.01,front=0,y=850),face(1,1130,200,act=.0 if i<6 else .2,front=.8)] for i in range(40)]
  active,changes=self.choose(frames)
  self.assertEqual(active[0],1);self.assertEqual(changes,0)
 def test_without_speech_the_central_frontal_face_near_the_camera_is_chosen(self):
  frames=[[face(0,300,200),face(1,980,190),face(2,1500,90)] for i in range(24)]
  active,_=self.choose(frames)
  self.assertEqual(set(active),{1})
 def test_background_talkers_never_take_the_camera(self):
  frames=[[face(0,800,200,act=.05),face(1,1150,195,act=.04),face(2,1600,80,act=.4,front=1)] for i in range(64)]
  active,_=self.choose(frames)
  self.assertNotIn(2,active)
 def test_moving_without_talking_does_not_pull_the_camera(self):
  frames=[[face(0,900,200,act=.12),face(1,300+40*i,200,act=0,front=1)] for i in range(32)]
  active,changes=self.choose(frames)
  self.assertEqual(set(active),{0});self.assertEqual(changes,0)
 def test_conversation_side_by_side_switches_when_the_other_starts_talking(self):
  talk=lambda i,who:.25 if (i//24)%2==who else .01      # 3 s each: 0, 1, 0, 1
  frames=[[face(0,750,190,act=talk(i,0)),face(1,1150,190,act=talk(i,1))] for i in range(96)]
  active,changes=self.choose(frames)
  self.assertEqual(active[0],0);self.assertEqual(changes,3)
  for onset in (24,48,72):                                # each switch lands within 0.5 s of the new speaker starting
   switch=next(i for i in range(onset-8,96) if active[i]!=active[onset-9])
   self.assertLessEqual(abs(switch-onset),4)
 def test_each_shot_is_decided_on_its_own(self):
  frames=[[face(0,500,200,act=.2)] for i in range(16)]+[[face(5,1400,200,act=.2)] for i in range(16)]
  active,_=self.choose(frames,cuts=[2.0])
  self.assertEqual(active[0],0);self.assertEqual(active[-1],5)
 def test_followed_face_stays_near_the_centre(self):
  # Two people 0.5 of the visible width apart taking turns: the camera centres each speaker instead of a fixed middle.
  samples=[dict(t=i/8,active=0 if i<40 else 1,faces=[dict(id=0,x=700,y=300,w=150,h=150),dict(id=1,x=1000,y=300,w=150,h=150)]) for i in range(80)]
  r=dict(width=1920,height=1080,samples=samples,cuts=[])
  path=tracking.build_path(r,framing='crop');g=tracking.geometry(1920,1080,'crop');extra=g['sw']-1080
  centre=lambda k:(path['x'][k]*extra/100+540)/g['scale']
  self.assertAlmostEqual(centre(int(3*tracking.PATH_FPS)),775,delta=20)
  self.assertAlmostEqual(centre(len(path['x'])-1),1075,delta=20)

class EmptyDetector:
 def empty(self):return False
 def detectMultiScale(self,*args,**kwargs):return []

class TrackingTests(unittest.TestCase):
 def test_face_coordinates_clamp_to_subject_not_middle(self):
  self.assertEqual(tracking.position(100,270,960,540)[0],0)
  self.assertEqual(tracking.position(860,270,960,540)[0],100)
  self.assertAlmostEqual(tracking.position(480,270,960,540)[0],50,delta=.01)
  self.assertNotEqual(tracking.key(0,10),tracking.key(1,11))
 def test_balanced_two_line_title_stays_compact(self):
  title,size=title_layout('Westcol promete que su boxeo superará a todos','Montserrat',48,two_lines=True)
  self.assertEqual(title.count('\n'),1);self.assertLessEqual(size,48)
  self.assertTrue(all(len(line.split())>=2 for line in title.split('\n')))
 def moving_result(self,width=960,height=540,seconds=3,switch=1.0):
  samples=[dict(t=i/8,active=0,faces=[dict(id=0,x=(110 if i/8<switch else 750),y=200,w=100,h=100)]) for i in range(int(seconds*8))]
  return dict(status='ready',width=width,height=height,samples=samples,persons=[dict(id=0,label='Persona 1',presence=1)],points=[])
 def test_dynamic_crop_moves_in_real_export_and_requires_matching_cache(self):
  client=TestClient(backend.app)
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);source=folder/'source.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=red:size=960x540:rate=24','-vf','drawbox=x=0:y=0:w=320:h=540:color=lime:t=fill,drawbox=x=640:y=0:w=320:h=540:color=blue:t=fill','-t','3','-c:v','libx264',str(source)])
   with source.open('rb') as raw:ident=client.post('/api/upload',files={'file':('source.mp4',raw,'video/mp4')}).json()['id']
   opts=dict(start=0,end=3,title='',subtitles='',auto_follow=True,framing='crop',tracking_motion='fast')
   self.assertEqual(client.post(f'/api/jobs/{ident}/export',json=opts).status_code,400)
   (backend.DATA/ident/f'tracking-{tracking.key(0,3)}.json').write_text(json.dumps(self.moving_result()))
   self.assertEqual(client.post(f'/api/jobs/{ident}/tracking',json={'start':0,'end':3}).json()['status'],'ready')
   for framing,probe_y in (('crop',960),('zoom',960)):
    response=client.post(f'/api/jobs/{ident}/export',json=dict(opts,framing=framing))
    self.assertEqual(response.status_code,200,response.text[:500])
    out=folder/f'{framing}.mp4';out.write_bytes(response.content)
    for t,channel in [(.2,1),(2.6,2)]:
     frame=folder/'frame.png';backend.command(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(out),'-frames:v','1',str(frame)])
     image=Image.open(frame).convert('RGB');pixel=image.getpixel((540,probe_y));self.assertGreater(pixel[channel],200,(framing,t,pixel))
     if framing=='zoom':self.assertLess(max(image.getpixel((540,60))),20)   # black band above the video
   self.assertEqual(client.post(f'/api/jobs/{ident}/export',json=dict(opts,start=.1)).status_code,400)
 def test_empty_scene_does_not_claim_a_detected_speaker(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=640x360:rate=8','-t','1','-c:v','libx264',str(source)])
   with self.assertRaisesRegex(ValueError,'No se detectaron rostros'):tracking.analyze(source,0,1,lambda p:None)
 def test_detected_face_generates_a_path_and_voice_presence_is_used(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=640x360:rate=8','-f','lavfi','-i','sine=frequency=220','-t','1','-c:v','libx264','-c:a','aac',str(source)])
   with patch.object(tracking,'make_detector',return_value=lambda frame:[(20,60,100,100,.9)]),patch('faster_whisper.vad.get_speech_timestamps',return_value=[dict(start=0,end=16000)]) as vad:
    result=tracking.analyze(source,0,1,lambda p:None)
   self.assertTrue(vad.called);self.assertEqual(result['face_frames'],8);self.assertEqual(result['speaking_frames'],8)
   self.assertEqual(len(result['persons']),1)
   self.assertTrue(all(p['x']==0 for p in result['points']))
 def test_mouth_motion_switches_only_when_voice_is_present(self):
  import cv2,numpy as np
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'speakers.mp4'
   writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),8,(640,360))
   texture=np.random.default_rng(1).integers(50,190,(100,100,3),dtype=np.uint8)
   for i in range(32):
    frame=np.full((360,640,3),80,np.uint8)
    frame[60:160,40:140]=texture;frame[60:160,460:560]=texture
    left=255 if i<10 and i%2 else 0
    right=255 if i>=12 and i%2 else 0
    frame[122:150,60:122]=left;frame[122:150,480:542]=right
    writer.write(frame)
   writer.release()
   audio=Path(tmp)/'audio.mp4'
   backend.command(['ffmpeg','-v','error','-y','-i',str(source),'-f','lavfi','-i','sine=frequency=220','-t','4','-c:v','copy','-c:a','aac',str(audio)])
   detector=lambda frame:[(40,60,100,100,.9),(460,60,100,100,.9)]
   with patch.object(tracking,'make_detector',return_value=detector),patch('faster_whisper.vad.get_speech_timestamps',return_value=[dict(start=0,end=64000)]):
    spoken=tracking.analyze(audio,0,4,lambda p:None)
   with patch.object(tracking,'make_detector',return_value=detector),patch('faster_whisper.vad.get_speech_timestamps',return_value=[]):
    silent=tracking.analyze(audio,0,4,lambda p:None)
   self.assertGreater(spoken['speaker_changes'],0)
   self.assertGreater(tracking.build_path(spoken,motion='fast')['x'][-1],80)
   self.assertEqual(silent['speaker_changes'],0)
   silent_x=tracking.build_path(silent)['x'];self.assertEqual(len(set(silent_x)),1)   # nobody speaks: one person, camera still
   self.assertEqual([p['label'].split(' · ')[1] for p in spoken['persons']],['izquierda','derecha'])
   # Choosing a person follows that person even while the other one speaks.
   self.assertEqual(tracking.build_path(spoken,person=str(spoken['persons'][0]['id']))['x'][-1],0)

 def test_title_refresh_uses_only_selected_clip_and_saved_context(self):
  job=dict(id='test',duration=120,analysis_options=dict(engine='cloud',speaker='Westcol',context='Su evento de boxeo'),transcript=[dict(start=0,end=30,text='Hablamos de otra cosa.'),dict(start=50,end=80,text='Voy a hacer el mejor evento de boxeo. Será superior al anterior.')])
  payloads=[]
  def complete(payload):
   payloads.append(payload)
   return {'clips':[dict(id='clip',titles=['Westcol promete superar su anterior evento de boxeo','Westcol quiere llevar su boxeo a otro nivel'])]}
  with patch.dict(backend.JOBS,{'test':job},clear=True),patch('cloud_ai.complete',side_effect=complete):
   response=TestClient(backend.app).post('/api/jobs/test/titles',json=dict(start=50,end=80))
  self.assertEqual(response.status_code,200,response.text)
  self.assertEqual(len(response.json()['titles']),2)
  self.assertNotIn('otra cosa',payloads[0]['clips'][0]['text'])
  self.assertEqual(payloads[0]['hablante_identificado'],'Westcol')
 def test_title_refresh_rejects_copying_transcript(self):
  text='Westcol comenta su próximo evento de boxeo'
  with patch.dict(backend.JOBS,{'test':dict(duration=30,analysis_options={'engine':'cloud'})},clear=True),patch('cloud_ai.complete',return_value={'clips':[dict(id='clip',titles=[text])]}):
   response=TestClient(backend.app).post('/api/jobs/test/titles',json=dict(start=0,end=20,text=text))
  self.assertEqual(response.status_code,400)

 def test_user_title_style_accepts_a_specific_longer_sentence(self):
  from intelligence import clean_title
  title='Westcol aclara que su evento de boxeo será de lejos el mejor'
  self.assertEqual(clean_title(title,'Este año quiero que sea el mejor evento de boxeo.'),title)
  text,point=title_layout(title,'Montserrat',48,two_lines=True)
  self.assertEqual(text.count('\n'),1);self.assertGreaterEqual(point,28)
