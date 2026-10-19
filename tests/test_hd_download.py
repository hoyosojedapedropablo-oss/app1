import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch,MagicMock

spec=importlib.util.spec_from_file_location('hd_candidate',Path(__file__).parents[1]/'services/cobalt/test_hd_download.py')
hd=importlib.util.module_from_spec(spec);spec.loader.exec_module(hd)

class HDTests(unittest.TestCase):
 def test_real_official_plugin_reaches_provider_after_lowercasing_base_url(self):
  import yt_dlp
  from yt_dlp.extractor.youtube import YoutubeIE
  from yt_dlp.extractor.youtube.pot.provider import PoTokenRequest,PoTokenContext
  calls=[]
  server,base,counters=hd.provider_server(lambda path,body:(calls.append((path,body)) or (200,{'version':'2.0.2'} if path=='/ping' else {'poToken':'x'*160})))
  try:
   with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
    from yt_dlp_plugins.extractor.getpot_bgutil_http import BgUtilHTTPPTP
    provider=BgUtilHTTPPTP(YoutubeIE(ydl),MagicMock(),{'base_url':[base]})
    request=PoTokenRequest(context=PoTokenContext.GVS,innertube_context={'client':{'clientName':'MWEB'}},internal_client_name='mweb',visitor_data='test-visitor',video_id='JCcuOv5y_9g')
    with patch.object(provider,'_get_attestation',return_value=None):response=provider._real_request_pot(request)
    self.assertEqual(response.po_token,'x'*160)
    self.assertEqual(counters['tokens'],1)
    self.assertEqual([path for path,body in calls],['/ping','/get_pot'])
    self.assertEqual(calls[1][1]['content_binding'],'test-visitor')
    self.assertEqual(base,base.lower())
  finally:server.shutdown();server.server_close()
 def test_old_mixed_case_route_is_lowercased_by_actual_plugin(self):
  import yt_dlp
  from yt_dlp.extractor.youtube import YoutubeIE
  with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
   from yt_dlp_plugins.extractor.getpot_bgutil_http import BgUtilHTTPPTP
   provider=BgUtilHTTPPTP(YoutubeIE(ydl),MagicMock(),{'base_url':['http://127.0.0.1:1234/MixedCaseRoute']})
   self.assertEqual(provider._base_url,'http://127.0.0.1:1234/mixedcaseroute')
 def test_original_route_reproduces_403_without_reaching_the_provider(self):
  old_spec=importlib.util.spec_from_file_location('original_native_probe',Path(__file__).parents[1]/'services/cobalt/test_native_download.py')
  original=importlib.util.module_from_spec(old_spec);old_spec.loader.exec_module(original)
  import yt_dlp
  from yt_dlp.extractor.youtube import YoutubeIE
  from yt_dlp.extractor.youtube.pot.provider import PoTokenRequest,PoTokenContext,PoTokenProviderRejectedRequest
  with patch.object(original.secrets,'token_urlsafe',return_value='MixedCaseRoute'):
   server,base,counters=original.provider_server(lambda *args:(200,{'version':'2.0.2'}))
  try:
   with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
    from yt_dlp_plugins.extractor.getpot_bgutil_http import BgUtilHTTPPTP
    provider=BgUtilHTTPPTP(YoutubeIE(ydl),MagicMock(),{'base_url':[base]})
    request=PoTokenRequest(context=PoTokenContext.GVS,innertube_context={'client':{'clientName':'MWEB'}},internal_client_name='mweb',visitor_data='test')
    with self.assertRaises(PoTokenProviderRejectedRequest):provider._real_request_pot(request)
    self.assertEqual(counters['requests'],0)
  finally:server.shutdown();server.server_close()
 def test_measured_360p_is_rejected_even_if_file_claims_hd(self):
  for width,height,accepted in [(640,360,False),(1280,720,True),(1920,1080,True)]:
   result=type('Result',(),{'stdout':json.dumps({'streams':[{'width':width,'height':height,'codec_name':'h264'}]})})()
   with patch.object(hd.subprocess,'run',return_value=result):
    if accepted:self.assertEqual(hd.inspect_hd(Path('fixture.mp4'))['measured_height'],height)
    else:
     with self.assertRaisesRegex(ValueError,'HD_RESOLUTION_NOT_MET'):hd.inspect_hd(Path('fixture.mp4'))
 def test_hd_options_have_no_360p_fallback_and_do_not_touch_working_configuration(self):
  import yt_dlp
  options={}
  class Fake:
   def __init__(self,value):options.update(value)
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def extract_info(self,*a,**k):raise RuntimeError('No HD formats')
  with tempfile.TemporaryDirectory() as tmp,patch.object(yt_dlp,'YoutubeDL',Fake),patch('youtube_import.javascript_options',return_value={}):
   with self.assertRaises(RuntimeError):hd.download_one('JCcuOv5y_9g',Path(tmp),'http://127.0.0.1:1234/lowercase')
  self.assertEqual(options['format'].count('[height>=720]'),2)
  self.assertNotIn('/best[ext=mp4][height<=1080]',options['format'])
