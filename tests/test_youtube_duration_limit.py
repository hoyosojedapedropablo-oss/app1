"""YouTube duration boundaries; local uploads and transfer budgets stay unchanged."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import app as backend
import cobalt_import
import native_import
import youtube_import

URL='https://www.youtube.com/watch?v=JCcuOv5y_9g'
CASES=(7201,11999,12000,12000.001,12001)


def engine(duration,options,processed):
 class Engine:
  def __init__(self,value):options.update(value)
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def extract_info(self,*args,**kwargs):
   return {'id':'JCcuOv5y_9g','duration':duration,'title':'Duration boundary','height':1080}
  def process_ie_result(self,info,download):
   processed.append(info['duration'])
   Path(options['outtmpl'].replace('%(ext)s','mp4')).write_bytes(b'media fixture')
   return info
 return Engine


class YouTubeDurationTests(unittest.TestCase):
 def test_native_filter_and_source_guard_accept_200_minutes_and_reject_any_excess(self):
  for duration in CASES:
   with self.subTest(duration=duration),tempfile.TemporaryDirectory() as tmp:
    options={};processed=[]
    with patch.object(native_import,'configuration',return_value={'minimum_height':720}),patch.object(native_import,'version',return_value='2.0.2'),patch.object(native_import,'provider_server',return_value=(None,'http://127.0.0.1:1234/test',{})),patch.object(native_import,'relay_request',return_value=(200,{'version':'2.0.2'})),patch('youtube_import.javascript_options',return_value={}),patch('yt_dlp.YoutubeDL',engine(duration,options,processed)),patch.object(native_import,'_verify_media') as verify,patch.object(native_import,'inspect_resolution',return_value={'video_width':1920,'video_height':1080}):
     run=lambda:native_import.download(URL,Path(tmp),lambda *args,**kwargs:None)
     if duration<=12000:
      path,_=run();self.assertTrue(path.exists());self.assertEqual(processed,[duration]);verify.assert_called_once_with(path,float(duration))
      self.assertIsNone(options['match_filter']({'duration':duration}))
     else:
      with self.assertRaises(cobalt_import.CobaltFailure):run()
      self.assertEqual(processed,[]);verify.assert_not_called()
      self.assertIn('200 minutos',options['match_filter']({'duration':duration}))

 def test_legacy_download_duration_filter_uses_same_boundary(self):
  for duration in CASES:
   with self.subTest(duration=duration),tempfile.TemporaryDirectory() as tmp:
    options={};processed=[]
    with patch('youtube_import.javascript_options',return_value={}),patch('yt_dlp.YoutubeDL',engine(duration,options,processed)):
     run=lambda:youtube_import._download_attempt(URL,Path(tmp),lambda *args,**kwargs:None)
     if duration<=12000:
      path,_=run();self.assertTrue(path.exists());self.assertEqual(processed,[duration])
     else:
      with self.assertRaisesRegex(ValueError,'200 minutos'):run()
      self.assertEqual(processed,[])

 def test_youtube_final_registration_accepts_exactly_200_minutes(self):
  for duration in CASES:
   with self.subTest(duration=duration),tempfile.TemporaryDirectory() as tmp,patch.object(backend,'DATA',Path(tmp)),patch.dict(backend.JOBS,{},clear=True),patch.dict(backend.IMPORTS,{},clear=True):
    ident='d'*32;backend.IMPORTS[ident]={'status':'queued'}
    def download(url,folder,progress,**kwargs):
     path=folder/'download.mp4';path.write_bytes(b'media fixture');return path,'video.mp4'
    media={'format':{'duration':str(duration)},'streams':[{'codec_type':'video','avg_frame_rate':'30/1'}]}
    with patch('youtube_import.download',side_effect=download),patch.object(backend,'probe',return_value=media):backend.import_youtube(ident,URL)
    state=backend.IMPORTS[ident]
    if duration<=12000:
     self.assertEqual(state['status'],'ready');self.assertEqual(state['job']['duration'],duration)
    else:
     self.assertEqual(state['status'],'error');self.assertIn('200 minutos',state['message']);self.assertFalse((Path(tmp)/ident).exists())

 def test_local_upload_retains_120_minute_limit(self):
  for duration in (7200,7200.001,12000):
   with self.subTest(duration=duration),patch.dict(backend.JOBS,{},clear=True),patch.object(backend,'save_job'),patch.object(backend,'probe',return_value={'format':{'duration':duration},'streams':[{'codec_type':'video'}]}):
    if duration<=7200:self.assertEqual(backend.register_video('local',Path('file'),'video.mp4')['duration'],duration)
    else:
     with self.assertRaisesRegex(ValueError,'120 minutos'):backend.register_video('local',Path('file'),'video.mp4')

 def test_native_saved_file_duration_uses_200_minute_boundary(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(native_import,'ROOT',Path(tmp)),patch.object(native_import,'_verify_media') as verify:
   path=Path(tmp)/'data/cobalt/native-validation/proof/download.mp4';path.parent.mkdir(parents=True);path.write_bytes(b'media')
   for duration in CASES:
    record={'video_id':'JCcuOv5y_9g','success':True,'expected_duration':duration,'path':str(path.relative_to(tmp)),'bytes':5}
    verify.reset_mock();result=native_import.cached_source(record,'JCcuOv5y_9g')
    self.assertEqual(result is not None,duration<=12000)
    self.assertEqual(verify.call_count,1 if duration<=12000 else 0)

 def test_cobalt_source_metadata_uses_same_boundary(self):
  for duration in CASES:
   with self.subTest(duration=duration):
    payload={'source_video_id':'JCcuOv5y_9g','expected_duration':duration,'expected_media_bytes':10}
    if duration<=12000:self.assertEqual(cobalt_import._source_metadata(payload,URL),(duration,10))
    else:
     with self.assertRaises(cobalt_import.CobaltFailure):cobalt_import._source_metadata(payload,URL)

 def test_cobalt_inspection_and_verified_records_use_same_boundary(self):
  spec=importlib.util.spec_from_file_location('duration_manage',Path(__file__).parents[1]/'services/cobalt/manage.py')
  manage=importlib.util.module_from_spec(spec);spec.loader.exec_module(manage)
  import json
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'video.mp4';path.write_bytes(b'media')
   for duration in CASES:
    record={'verification_version':2,'success':True,'expected_duration':duration,'duration':duration,'audio_packets':1,'video_packets':1}
    self.assertEqual(manage.verified_record(record),duration<=12000)
    video={'codec_type':'video','codec_name':'h264','height':1080,'width':1920,'nb_read_packets':'1'}
    audio={'codec_type':'audio','codec_name':'aac','nb_read_packets':'1'}
    media={'format':{'duration':duration},'streams':[video,audio]}
    with patch.object(manage.subprocess,'run',return_value=SimpleNamespace(stdout=json.dumps(media))):
     if duration<=12000:self.assertEqual(manage.inspect_media(path,'fast')['duration'],duration)
     else:
      with self.assertRaises(ValueError):manage.inspect_media(path,'fast')

 def test_native_transfer_timeout_remains_two_hours(self):
  with tempfile.TemporaryDirectory() as tmp:
   options={};processed=[];Original=engine(12000,options,processed)
   class SlowEngine(Original):
    def process_ie_result(self,*args,**kwargs):options['progress_hooks'][0]({'status':'downloading'})
   with patch.object(native_import,'configuration',return_value={}),patch.object(native_import,'version',return_value='2.0.2'),patch.object(native_import,'provider_server',return_value=(None,'http://127.0.0.1:1234/test',{})),patch.object(native_import,'relay_request',return_value=(200,{'version':'2.0.2'})),patch('youtube_import.javascript_options',return_value={}),patch('yt_dlp.YoutubeDL',SlowEngine),patch.object(native_import.time,'monotonic',side_effect=[0,7201]):
    with self.assertRaises(cobalt_import.CobaltFailure) as error:native_import.download(URL,Path(tmp),lambda *args,**kwargs:None)
    self.assertEqual(error.exception.code,'YT-TIEMPO')
