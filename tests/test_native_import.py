import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import native_import as native
import youtube_import

class NativeImportTests(unittest.TestCase):
 def fixture(self,root):
  path=root/'data/cobalt/native-validation/proof/download.mp4';path.parent.mkdir(parents=True)
  subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=320x180:rate=5','-f','lavfi','-i','sine=frequency=440','-t','2','-c:v','libx264','-c:a','aac',str(path)],capture_output=True,check=True)
  record={'video_id':'JCcuOv5y_9g','success':True,'expected_duration':2,'bytes':path.stat().st_size,'path':str(path.relative_to(root))}
  config={'enabled':True,'enabled_modes':['fast'],'verification_version':2,'verified_files':[record]}
  configpath=root/'data/youtube-native.json';configpath.write_text(json.dumps(config))
  return path,record,configpath
 def test_verified_real_video_imports_into_editor_without_download_or_docker(self):
  import app as backend
  from fastapi.testclient import TestClient
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);path,record,config=self.fixture(root);folder=root/'jobs';folder.mkdir()
   with patch.object(native,'ROOT',root),patch.object(native,'CONFIG_PATH',config),patch.object(backend,'DATA',folder),patch.dict(backend.JOBS,{},clear=True),patch.dict(backend.IMPORTS,{},clear=True),patch.object(native,'relay_request',side_effect=AssertionError('No network or Docker for verified saved file')):
    ident='e'*32;backend.IMPORTS[ident]={'status':'queued'}
    backend.import_youtube(ident,'https://www.youtube.com/watch?v=JCcuOv5y_9g')
    state=backend.IMPORTS[ident]
    self.assertEqual(state['status'],'ready');self.assertEqual(state['verification_version'],2)
    self.assertEqual(state['job']['youtube_verification_version'],2)
    self.assertEqual((folder/ident/'source').read_bytes(),path.read_bytes())
    self.assertEqual(TestClient(backend.app).get('/api/jobs/'+ident+'/video').status_code,200)
 def test_partial_duration_and_outside_cache_path_are_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);path,record,config=self.fixture(root)
   with patch.object(native,'ROOT',root):
    self.assertIsNone(native.cached_source({**record,'expected_duration':3624},record['video_id']))
    self.assertIsNone(native.cached_source({**record,'path':'../outside.mp4'},record['video_id']))
    self.assertIsNone(native.cached_source(record,'rcPWJKs5It4'))
 def test_native_route_precedes_disabled_cobalt_and_browser_alternative(self):
  with patch.object(native,'configuration',return_value={'enabled':True}),patch.object(native,'download',return_value=('file','video.mp4')) as download,patch('cobalt_import.download',side_effect=AssertionError()):
   result=youtube_import.download('url',None,lambda *a,**k:None,browser='brave')
   self.assertEqual(result,('file','video.mp4'));download.assert_called_once()
 def test_original_quality_fails_before_network(self):
  with patch.object(native,'configuration',return_value={'enabled':True}),patch.object(native,'provider_server',side_effect=AssertionError()):
   with self.assertRaisesRegex(native.CobaltFailure,'original'):native.download('https://youtu.be/JCcuOv5y_9g',Path('/tmp'),lambda *a,**k:None,mode='original')
 def test_new_link_preserves_tested_options_and_rejects_partial_output(self):
  import yt_dlp
  options={}
  class Fake:
   def __init__(self,value):options.update(value)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*a,**k):return {'id':'JCcuOv5y_9g','duration':3624,'title':'Example','height':360}
   def process_ie_result(self,*a,**k):Path(options['outtmpl'].replace('%(ext)s','mp4')).write_bytes(b'partial')
  with tempfile.TemporaryDirectory() as tmp,patch.object(native,'configuration',return_value={}),patch.object(native,'version',return_value='2.0.2'),patch.object(native,'provider_server',return_value=(None,'http://127.0.0.1:1234/test',{})),patch.object(native,'relay_request',return_value=(200,{'version':'2.0.2'})),patch('youtube_import.javascript_options',return_value={}),patch.object(yt_dlp,'YoutubeDL',Fake):
   with self.assertRaises(native.CobaltFailure):native.download('https://youtu.be/JCcuOv5y_9g',Path(tmp),lambda *a,**k:None)
   self.assertFalse((Path(tmp)/'download.mp4').exists())
   self.assertEqual(options['extractor_args']['youtube']['player_client'],['mweb'])
   self.assertEqual(options['http_chunk_size'],1024*1024)
   self.assertNotIn('cookiesfrombrowser',options)
