import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import urllib.request
from urllib.error import HTTPError
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('native_probe',Path(__file__).parents[1]/'services/cobalt/test_native_download.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

class NativeTests(unittest.TestCase):
    def test_loopback_relay_preserves_binding_and_rejects_browser_origin_and_tls_disable(self):
        calls=[]
        def relay(path,body):calls.append((path,body));return 200,{'poToken':'PRIVATE'}
        server,base,counters=probe.provider_server(relay)
        try:
            body={'content_binding':'correct-video-binding','challenge':{'challenge':'PRIVATE'},'disable_tls_verification':False}
            with urllib.request.urlopen(urllib.request.Request(base+'/get_pot',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=3) as response:
                self.assertEqual(json.load(response),{'poToken':'PRIVATE'})
            self.assertEqual(calls,[('/get_pot',body)])
            for url,headers,value in [(base+'/get_pot',{'Origin':'https://evil.example'},{}),(base+'/get_pot',{}, {'disable_tls_verification':True}),(base.rsplit('/',1)[0]+'/get_pot',{}, {})]:
                with self.assertRaises(HTTPError):urllib.request.urlopen(urllib.request.Request(url,data=json.dumps(value).encode(),headers=headers),timeout=3)
            self.assertEqual(len(calls),1)
            self.assertEqual(counters['tokens'],1)
        finally:server.shutdown();server.server_close()

    def test_provider_errors_never_return_raw_diagnostic_or_tokens(self):
        result=SimpleNamespace(stdout=json.dumps({'status':503,'body':{'error':'PRIVATE'}}))
        with patch.object(probe.subprocess,'run',return_value=result):
            self.assertEqual(probe.relay_request('/get_pot',{}),(503,{'error':'PROVIDER_UNAVAILABLE'}))
        with self.assertRaises(ValueError):probe.relay_request('/get_pot',{'disable_tls_verification':True})

    def test_relay_forwards_body_via_stdin_and_fixed_docker_target(self):
        calls=[]
        def run(command,**kwargs):calls.append((command,kwargs));return SimpleNamespace(stdout=json.dumps({'status':200,'body':{'poToken':'x'*160}}))
        with patch.object(probe.subprocess,'run',side_effect=run):
            status,payload=probe.relay_request('/get_pot',{'content_binding':'PRIVATE'})
        self.assertEqual(status,200)
        self.assertIn('clipstudio-download-pot-provider-1',calls[0][0])
        self.assertNotIn('PRIVATE',' '.join(calls[0][0]))
        self.assertEqual(json.loads(calls[0][1]['input'])['body']['content_binding'],'PRIVATE')

    def test_invalid_source_metadata_never_starts_download(self):
        import yt_dlp
        for info in [{'id':'wrong','duration':3624},{'id':'JCcuOv5y_9g','duration':float('nan')},{'id':'JCcuOv5y_9g','duration':7201}]:
            class Fake:
                def __init__(self,options):pass
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def extract_info(self,*args,**kwargs):return info
                def process_ie_result(self,*args,**kwargs):raise AssertionError('must not download')
            with tempfile.TemporaryDirectory() as tmp,patch.object(yt_dlp,'YoutubeDL',Fake),patch('youtube_import.javascript_options',return_value={}):
                with self.assertRaisesRegex(ValueError,'SOURCE_METADATA'):probe.download_one('JCcuOv5y_9g',Path(tmp),'http://127.0.0.1:1234/secret')

    def test_full_download_does_not_accept_partial_duration(self):
        import yt_dlp
        from cobalt_import import CobaltFailure
        class Fake:
            def __init__(self,options):
                self.options=options
                assert options['extractor_args']['youtube']['player_client']==['mweb']
                assert 'cookiesfrombrowser' not in options
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def extract_info(self,*args,**kwargs):return {'id':'JCcuOv5y_9g','duration':3624}
            def process_ie_result(self,*args,**kwargs):Path(self.options['outtmpl'].replace('%(ext)s','mp4')).write_bytes(b'partial')
        with tempfile.TemporaryDirectory() as tmp,patch.object(yt_dlp,'YoutubeDL',Fake),patch('youtube_import.javascript_options',return_value={}),patch('cobalt_import._verify_media',side_effect=CobaltFailure('YT-INCOMPLETO','partial')) as verify:
            with self.assertRaises(CobaltFailure):probe.download_one('JCcuOv5y_9g',Path(tmp),'http://127.0.0.1:1234/secret')
            self.assertEqual(verify.call_args.args[1],3624.)

    def test_plugin_checksum_failure_cannot_install(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return b'corrupt'
        with patch.object(probe,'version',side_effect=probe.PackageNotFoundError()),patch.object(probe.urllib.request,'urlopen',return_value=Response()),patch.object(probe.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'PLUGIN_CHECKSUM'):probe.install_plugin()
            run.assert_not_called()
