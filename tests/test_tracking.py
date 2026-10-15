import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
import app as backend
import tracking
from styling import title_layout

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
 def test_dynamic_crop_moves_in_real_export_and_requires_matching_cache(self):
  client=TestClient(backend.app)
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);source=folder/'source.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=red:size=960x540:rate=24','-vf','drawbox=x=0:y=0:w=320:h=540:color=lime:t=fill,drawbox=x=640:y=0:w=320:h=540:color=blue:t=fill','-t','3','-c:v','libx264',str(source)])
   with source.open('rb') as raw:ident=client.post('/api/upload',files={'file':('source.mp4',raw,'video/mp4')}).json()['id']
   opts=dict(start=0,end=3,title='',subtitles='',auto_follow=True)
   self.assertEqual(client.post(f'/api/jobs/{ident}/export',json=opts).status_code,400)
   result=dict(status='ready',start=0,end=3,width=960,height=540,points=[dict(time=0,x=0,y=50),dict(time=1,x=0,y=50),dict(time=1.5,x=100,y=50),dict(time=3,x=100,y=50)])
   (backend.DATA/ident/f'tracking-{tracking.key(0,3)}.json').write_text(json.dumps(result))
   self.assertEqual(client.post(f'/api/jobs/{ident}/tracking',json={'start':0,'end':3}).json()['status'],'ready')
   response=client.post(f'/api/jobs/{ident}/export',json=opts)
   self.assertEqual(response.status_code,200,response.text[:500])
   out=folder/'out.mp4';out.write_bytes(response.content)
   for t,channel in [(.4,1),(2.5,2)]:
    frame=folder/'frame.png';backend.command(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(out),'-frames:v','1',str(frame)])
    pixel=Image.open(frame).getpixel((540,960));self.assertGreater(pixel[channel],200)
   self.assertEqual(client.post(f'/api/jobs/{ident}/export',json=dict(opts,start=.1)).status_code,400)
 def test_empty_scene_does_not_claim_a_detected_speaker(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=640x360:rate=4','-t','1','-c:v','libx264',str(source)])
   with self.assertRaisesRegex(ValueError,'No se detectaron rostros'):tracking.analyze(source,0,1,lambda p:None)
 def test_detected_face_generates_a_path_and_voice_presence_is_used(self):
  import numpy as np
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'source.mp4'
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=640x360:rate=4','-f','lavfi','-i','sine=frequency=220','-t','1','-c:v','libx264','-c:a','aac',str(source)])
   class Detector:
    def empty(self):return False
    def detectMultiScale(self,*args,**kwargs):return np.array([[30,60,100,100]])
   with patch('cv2.CascadeClassifier',side_effect=lambda path:Detector() if 'frontal' in path else EmptyDetector()),patch('faster_whisper.vad.get_speech_timestamps',return_value=[dict(start=0,end=16000)]) as vad:
    result=tracking.analyze(source,0,1,lambda p:None)
   self.assertTrue(vad.called);self.assertEqual(result['face_frames'],4)
   self.assertEqual(result['speaking_frames'],4)
   self.assertTrue(all(p['x']==0 for p in result['points']))

 def test_mouth_motion_switches_only_when_voice_is_present(self):
  import cv2,numpy as np
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'speakers.mp4'
   writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'mp4v'),4,(640,360))
   texture=np.random.default_rng(1).integers(50,190,(100,100,3),dtype=np.uint8)
   for i in range(16):
    frame=np.full((360,640,3),80,np.uint8)
    frame[60:160,40:140]=texture;frame[60:160,460:560]=texture
    left=255 if i<5 and i%2 else 0
    right=255 if i>=6 and i%2 else 0
    frame[122:150,60:122]=left;frame[122:150,480:542]=right
    writer.write(frame)
   writer.release()
   # Add audio so the production speech detector path is exercised (speech labels mocked).
   audio=Path(tmp)/'audio.mp4'
   backend.command(['ffmpeg','-v','error','-y','-i',str(source),'-f','lavfi','-i','sine=frequency=220','-t','4','-c:v','copy','-c:a','aac',str(audio)])
   class Detector:
    def empty(self):return False
    def detectMultiScale(self,*args,**kwargs):return np.array([[40,60,100,100],[460,60,100,100]])
   with patch('cv2.CascadeClassifier',side_effect=lambda path:Detector() if 'frontal' in path else EmptyDetector()),patch('faster_whisper.vad.get_speech_timestamps',return_value=[dict(start=0,end=64000)]):
    spoken=tracking.analyze(audio,0,4,lambda p:None)
   with patch('cv2.CascadeClassifier',side_effect=lambda path:Detector() if 'frontal' in path else EmptyDetector()),patch('faster_whisper.vad.get_speech_timestamps',return_value=[]):
    silent=tracking.analyze(audio,0,4,lambda p:None)
   self.assertGreater(spoken['speaker_changes'],0)
   self.assertGreater(spoken['points'][-1]['x'],80)
   self.assertEqual(silent['speaker_changes'],0)
   self.assertEqual(silent['points'][-1]['x'],0)

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
