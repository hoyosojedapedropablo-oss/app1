import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app as backend
from fastapi.testclient import TestClient

URL='https://www.youtube.com/watch?v=JCcuOv5y_9g'


class ImportResumeTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.data=Path(tmp.name)
  for patcher in (patch.object(backend,'DATA',self.data),patch.dict(backend.IMPORTS,{},clear=True),patch.dict(backend.JOBS,{},clear=True)):
   patcher.start();self.addCleanup(patcher.stop)

 def test_running_download_is_recorded_on_disk(self):
  ident='a'*32;backend.IMPORTS[ident]={'status':'queued'};seen={}
  def fake_download(url,target,progress,**kwargs):
   seen.update(json.loads((target/'import.json').read_text(encoding='utf-8')));raise ValueError('stop')
  with patch('youtube_import.download',side_effect=fake_download):backend.import_youtube(ident,URL)
  self.assertEqual(seen,{'url':URL,'quality':'fast'})
  self.assertFalse((self.data/ident).exists())  # a failed import still leaves nothing to resume

 def test_queued_request_alone_leaves_no_record(self):
  with patch.object(backend.import_pool,'submit') as submit:
   state=TestClient(backend.app).post('/api/youtube',json={'url':'https://youtu.be/JCcuOv5y_9g'}).json()
  submit.assert_called_once();self.assertFalse((self.data/state['id']).exists())

 def test_interrupted_import_resumes_without_browser_session(self):
  ident='c'*32;folder=self.data/ident;folder.mkdir()
  (folder/'import.json').write_text(json.dumps({'url':URL,'quality':'fast'}),encoding='utf-8')
  (folder/'download.f299.mp4.part').write_bytes(b'partial')
  with patch.object(backend.import_pool,'submit') as submit:backend.resume_imports()
  submit.assert_called_once_with(backend.import_youtube,ident,URL,'fast','none')
  active=TestClient(backend.app).get('/api/youtube').json()
  self.assertEqual([item['id'] for item in active],[ident]);self.assertTrue(active[0]['resumed'])
  self.assertTrue((folder/'download.f299.mp4.part').exists())

 def test_finished_or_invalid_records_are_not_resumed(self):
  done=self.data/('d'*32);done.mkdir();(done/'source').write_bytes(b'x');(done/'import.json').write_text(json.dumps({'url':URL}))
  bad=self.data/('e'*32);bad.mkdir();(bad/'import.json').write_text('{"url":"https://example.com/video"}')
  with patch.object(backend.import_pool,'submit') as submit:backend.resume_imports()
  submit.assert_not_called();self.assertEqual(TestClient(backend.app).get('/api/youtube').json(),[])

 def test_successful_import_removes_its_record(self):
  ident='f'*32;folder=self.data/ident;folder.mkdir();(folder/'import.json').write_text('{}')
  backend.IMPORTS[ident]={'status':'queued'}
  def fake_download(url,target,progress,**kwargs):
   path=target/'download.mp4';path.write_bytes(b'mp4');return path,'video.mp4'
  with patch('youtube_import.download',side_effect=fake_download),patch.object(backend,'register_video',return_value={'id':ident}),patch.object(backend,'save_job'):
   backend.import_youtube(ident,URL)
  self.assertEqual(backend.IMPORTS[ident]['status'],'ready');self.assertFalse((folder/'import.json').exists())


if __name__=='__main__':
 unittest.main()
