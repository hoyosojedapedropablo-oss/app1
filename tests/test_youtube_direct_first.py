import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import native_import as native
import youtube_import


def engine(log,outcomes,height=1080):
 """Fake YoutubeDL: each instance pops one outcome ('ok' writes a real MP4, otherwise raises it)."""
 class Fake:
  def __init__(self,options):self.options=options;log.append(options)
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def extract_info(self,*a,**k):return {'id':'JCcuOv5y_9g','duration':2,'title':'Example','height':height,'requested_formats':[{'filesize':600,'height':height},{'filesize':400}]}
  def process_ie_result(self,*a,**k):
   outcome=outcomes.pop(0)
   if outcome!='ok':raise outcome
   for name,size in (('download.f299.mp4',600),('download.f140.m4a',400)):
    for done in (size//2,size):self.options['progress_hooks'][0]({'status':'downloading','filename':name,'downloaded_bytes':done,'total_bytes':size})
   path=self.options['outtmpl'].replace('%(ext)s','mp4')
   subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=size=1920x{height}:rate=5','-f','lavfi','-i','sine=frequency=440','-t','2','-c:v','libx264','-c:a','aac',path],capture_output=True,check=True)
 return Fake


class DirectFirstTests(unittest.TestCase):
 def run_download(self,outcomes,relay=(200,{'version':'2.0.2'}),progress=None):
  import yt_dlp
  log=[]
  relay_mock=dict(side_effect=relay) if isinstance(relay,Exception) else dict(return_value=relay)
  with tempfile.TemporaryDirectory() as tmp,patch.object(native,'configuration',return_value={'minimum_height':720}),patch.object(native,'version',return_value='2.0.2'),patch.object(native,'provider_server',return_value=(None,'http://127.0.0.1:1234/test',{})),patch.object(native,'relay_request',**relay_mock) as ping,patch('youtube_import.javascript_options',return_value={}),patch.object(yt_dlp,'YoutubeDL',engine(log,outcomes)):
   try:result=native.download('https://youtu.be/JCcuOv5y_9g',Path(tmp),progress or (lambda *a,**k:None))
   except Exception as error:result=error
   leftovers=list(Path(tmp).glob('download.*'))
  return result,log,ping,leftovers

 def test_default_clients_are_tried_first_without_docker(self):
  result,log,ping,_=self.run_download(['ok'])
  self.assertEqual(result[0].name,'download.mp4')
  self.assertEqual(len(log),1);self.assertNotIn('extractor_args',log[0])
  self.assertEqual(log[0]['http_chunk_size'],10*1024*1024)
  ping.assert_not_called()

 def test_403_on_default_clients_falls_back_to_mweb_with_po_token(self):
  forbidden=Exception('ERROR: unable to download video data: HTTP Error 403: Forbidden')
  result,log,ping,_=self.run_download([forbidden,'ok'])
  self.assertEqual(result[0].name,'download.mp4')
  self.assertEqual(log[1]['extractor_args']['youtube']['player_client'],['mweb'])
  self.assertEqual(log[1]['http_chunk_size'],1024*1024)
  ping.assert_called_once()

 def test_docker_down_reports_docker_not_javascript(self):
  forbidden=Exception('HTTP Error 403: Forbidden')
  stopped=subprocess.CalledProcessError(1,['docker','exec','-i','x','deno','eval','Deno.exit(2)'])
  with patch.object(native.subprocess,'run',side_effect=stopped):
   result,log,_,leftovers=self.run_download([forbidden],relay=native.CobaltFailure('YT-DOCKER',native.DOCKER_MESSAGE))
  self.assertIsInstance(result,native.CobaltFailure);self.assertEqual(result.code,'YT-DOCKER')
  self.assertIn('YT-403',result.safe_message);self.assertIn('Docker Desktop',result.safe_message)
  self.assertEqual(youtube_import.diagnose_error(result)[0],'YT-DOCKER')
  self.assertEqual(leftovers,[])

 def test_relay_request_converts_stopped_docker_to_clear_failure(self):
  for failure in (subprocess.CalledProcessError(1,['docker','exec','deno','eval','Deno.stdin']),
                  subprocess.TimeoutExpired(['docker','deno'],60),FileNotFoundError('docker')):
   with patch.object(native.subprocess,'run',side_effect=failure):
    with self.assertRaises(native.CobaltFailure) as caught:native.relay_request('/ping',{})
   self.assertEqual(caught.exception.code,'YT-DOCKER')

 def test_raw_subprocess_command_is_never_read_as_javascript(self):
  stopped=subprocess.CalledProcessError(1,['docker','exec','deno','eval','Deno.exit(2)'],stderr='Cannot connect to the Docker daemon')
  self.assertNotEqual(youtube_import.diagnose_error(stopped)[0],'YT-JAVASCRIPT')

 def test_size_limit_on_direct_attempt_is_final(self):
  too_big=native.CobaltFailure('YT-VALIDACION','El video supera 12 GB.')
  result,log,ping,_=self.run_download([too_big])
  self.assertEqual(result.code,'YT-VALIDACION');self.assertEqual(len(log),1);ping.assert_not_called()

 def test_progress_covers_video_and_audio_without_restarting(self):
  values=[]
  result,*_=self.run_download(['ok'],progress=lambda value,message,**meta:values.append(value) if message=='Descargando video completo…' and 'downloaded_bytes' in meta else None)
  self.assertEqual(result[0].name,'download.mp4')
  self.assertEqual(values,sorted(values));self.assertEqual(values[-1],90)

 def test_safe_log_hides_urls_and_tokens(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(youtube_import,'LOG_PATH',Path(tmp)/'logs'/'y.log'):
   youtube_import.SafeLog('test').error('HTTP Error 403 https://rr1.googlevideo.com/videoplayback?sig=abc pot=' + 'A'*60)
   text=(Path(tmp)/'logs'/'y.log').read_text(encoding='utf-8')
  self.assertIn('HTTP Error 403',text);self.assertNotIn('googlevideo',text);self.assertNotIn('A'*60,text)


if __name__=='__main__':
 unittest.main()
