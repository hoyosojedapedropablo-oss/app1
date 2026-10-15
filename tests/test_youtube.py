import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import app as backend
from youtube_import import canonical_url

class YouTubeImportTests(unittest.TestCase):
 def test_canonical_links_and_playlist_removal(self):
  for url in ['https://youtu.be/BaW_jenozKc?t=10','https://www.youtube.com/watch?v=BaW_jenozKc&list=abc','https://youtube.com/shorts/BaW_jenozKc']:
   self.assertEqual(canonical_url(url),'https://www.youtube.com/watch?v=BaW_jenozKc')
 def test_reject_other_hosts_and_nonvideo_links(self):
  for url in ['http://127.0.0.1/video','https://youtube.com.evil.com/watch?v=BaW_jenozKc','file:///video','https://youtube.com/playlist?list=test','https://user:pass@youtube.com/watch?v=BaW_jenozKc']:
   with self.assertRaises(ValueError):canonical_url(url)
 def test_import_registers_real_video_ready_for_editor(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'DATA',Path(tmp)),patch.dict(backend.JOBS,{},clear=True),patch.dict(backend.IMPORTS,{},clear=True):
   ident='a'*32;backend.IMPORTS[ident]={'id':ident,'status':'queued'}
   def download(url,folder,progress,**kwargs):
    progress(50,'Descargando')
    path=folder/'download.mp4';backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=320x180:rate=1','-t','2','-c:v','libx264',str(path)])
    return path,'YouTube test.mp4'
   with patch('youtube_import.download',side_effect=download):backend.import_youtube(ident,'https://youtu.be/BaW_jenozKc')
   self.assertEqual(backend.IMPORTS[ident]['status'],'ready')
   client=TestClient(backend.app)
   self.assertEqual(client.get('/api/jobs/'+ident).json()['status'],'uploaded')
   self.assertEqual(client.get('/api/jobs/'+ident+'/video').status_code,200)
   self.assertTrue((Path(tmp)/ident/'job.json').exists())
 def test_failure_cleans_partial_files_and_is_reported(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'DATA',Path(tmp)),patch.dict(backend.IMPORTS,{},clear=True):
   ident='b'*32;backend.IMPORTS[ident]={'status':'queued'}
   with patch('youtube_import.download',side_effect=RuntimeError('sensitive provider diagnostic')):backend.import_youtube(ident,'https://youtu.be/BaW_jenozKc')
   self.assertEqual(backend.IMPORTS[ident]['status'],'error')
   self.assertNotIn('sensitive',backend.IMPORTS[ident]['message'])
   self.assertFalse((Path(tmp)/ident).exists())
 def test_api_rejects_invalid_url_and_overlapping_download(self):
  client=TestClient(backend.app)
  self.assertEqual(client.post('/api/youtube',json={'url':'https://example.com'}).status_code,400)
  with patch.dict(backend.IMPORTS,{'existing':{'status':'downloading'}},clear=True):
   self.assertEqual(client.post('/api/youtube',json={'url':'https://youtu.be/BaW_jenozKc'}).status_code,409)

class DownloadOptimizationTests(unittest.TestCase):
 def test_parallel_download_metadata_quality_and_single_extraction(self):
  import youtube_import
  for mode,limited in [('fast',True),('original',False)]:
   with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp);events=[];options={};calls=[]
    class YDL:
     def __init__(self,opts):options.update(opts)
     def __enter__(self):return self
     def __exit__(self,*args):pass
     def extract_info(self,url,download):
      calls.append('extract');self.assert_metadata=not download
      return {'title':'Mi video','channel':'Mi canal','duration':120,'requested_formats':[{'filesize':100},{'filesize':50}]}
     def process_ie_result(self,info,download):
      calls.append('download');(folder/'download.mp4').write_bytes(b'video')
      options['progress_hooks'][0]({'filename':'video','total_bytes':100,'downloaded_bytes':50,'speed':25,'eta':2})
      options['postprocessor_hooks'][0]({'status':'started'})
      return info
    with patch('yt_dlp.YoutubeDL',YDL):
     path,name=youtube_import.download('https://www.youtube.com/watch?v=BaW_jenozKc',folder,lambda value,message,**meta:events.append((value,message,meta)),mode=mode)
    self.assertEqual(calls,['extract','download'])
    self.assertEqual(options['concurrent_fragment_downloads'],8)
    self.assertEqual('[height<=1080]' in options['format'],limited)
    self.assertEqual(events[0][2]['title'],'Mi video')
    self.assertEqual(events[0][2]['thumbnail'],'https://i.ytimg.com/vi/BaW_jenozKc/hqdefault.jpg')
    self.assertEqual(events[-1][0],98)
    self.assertEqual(name,'Mi video.mp4');self.assertTrue(path.exists())
 def test_existing_video_is_reused_without_new_download(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'DATA',Path(tmp)),patch.dict(backend.JOBS,{},clear=True),patch.dict(backend.IMPORTS,{},clear=True):
   ident='c'*32;folder=Path(tmp)/ident;folder.mkdir();(folder/'source').write_bytes(b'cached')
   backend.JOBS[ident]=dict(id=ident,youtube_url='https://www.youtube.com/watch?v=BaW_jenozKc',youtube_quality='fast',youtube={'title':'Cached'})
   with patch.object(backend.import_pool,'submit',side_effect=AssertionError('No repeated download')):
    response=TestClient(backend.app).post('/api/youtube',json={'url':'https://youtu.be/BaW_jenozKc','quality':'fast'})
   self.assertEqual(response.status_code,200);self.assertEqual(response.json()['status'],'ready')
   self.assertEqual(response.json()['job']['id'],ident)
