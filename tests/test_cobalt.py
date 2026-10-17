import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import cobalt_import as service


def payload(size=10,duration=1,tunnels=None,name='../video.mp4'):
    return {'status':'local-processing','type':'merge','output':{'filename':name},
        'tunnel':tunnels or ['http://127.0.0.1:9000/tunnel?part=video','http://127.0.0.1:9000/tunnel?part=audio'],
        'source_video_id':'JCcuOv5y_9g','expected_duration':duration,'expected_media_bytes':size}


class CobaltTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'CLIP_COBALT_URL':'http://127.0.0.1:9000/', 'CLIP_COBALT_KEY':'test-key'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_download(self, handler, mode='fast'):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch.object(service.httpx, 'Client', return_value=client):
            return service.download('https://youtu.be/JCcuOv5y_9g', self.folder, lambda *a, **k:None, mode)

    def test_authentication_and_quality_contract(self):
        for mode in ('fast','original'):
            requests = []
            def handler(request):
                requests.append(request)
                if request.method == 'POST':
                    return httpx.Response(200, json=payload())
                return httpx.Response(200, content=b'video', headers={'Content-Type':'video/mp4'})
            with patch.object(service,'_merge_tracks',side_effect=lambda tracks,target:target.write_bytes(b'video')),patch.object(service,'_verify_media'):
                path, name = self.run_download(handler, mode)
            self.assertEqual(path.read_bytes(), b'video')
            self.assertEqual(name, 'video.mp4')
            self.assertEqual(requests[0].headers['Authorization'],'Api-Key test-key')
            for request in requests[1:]:self.assertNotIn('Authorization',request.headers)
            body = json.loads(requests[0].content)
            self.assertTrue(body['alwaysProxy'])
            self.assertEqual(body['localProcessing'],'forced')
            self.assertEqual(body['videoQuality'],'1080' if mode=='fast' else 'max')

    def test_rejects_foreign_tunnels_and_redirects(self):
        for url in ('https://evil.example/tunnel','http://127.0.0.1:9000/admin','http://user:pass@127.0.0.1:9000/tunnel'):
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(200,json=payload(tunnels=[url,'http://127.0.0.1:9000/tunnel?part=audio']))
            with self.assertRaises(service.CobaltFailure):self.run_download(handler)
            self.assertEqual(len(calls),1)
        def redirect(request):return httpx.Response(302,headers={'Location':'https://evil.example'})
        with self.assertRaises(service.CobaltFailure):self.run_download(redirect)

    def test_oversize_truncated_and_nonvideo_files_are_removed(self):
        for headers,content,size,limit in (({'Content-Length':'100'},b'abc',200,1000),({'Content-Type':'text/html'},b'error',10,1000),({},b'123456',12,5)):
            def handler(request):
                if request.method=='POST':return httpx.Response(200,json=payload(size=size))
                return httpx.Response(200,headers=headers,content=content)
            with patch.object(service,'MAX_BYTES',limit):
                with self.assertRaises(service.CobaltFailure):self.run_download(handler)
            self.assertFalse((self.folder/'download.mp4').exists())

    def test_errors_do_not_expose_provider_details(self):
        def handler(request):return httpx.Response(400,json={'status':'error','error':{'code':'unknown','context':'SECRET'}})
        with self.assertRaises(service.CobaltFailure) as error:self.run_download(handler)
        self.assertNotIn('SECRET',str(error.exception))

    def test_upstream_namespaced_error_codes(self):
        def handler(request):return httpx.Response(400,json={'status':'error','error':{'code':'error.api.youtube.no_session_tokens'}})
        with self.assertRaises(service.CobaltFailure) as error:self.run_download(handler)
        self.assertEqual(error.exception.code,'YT-SERVICIO-TOKEN')

    def test_configuration_requires_opt_in_and_owned_https(self):
        config = self.folder/'client.json'
        config.write_text(json.dumps({'enabled':False}))
        with patch.dict(os.environ,{'CLIP_COBALT_URL':'','CLIP_COBALT_KEY':''}),patch.object(service,'CONFIG_PATH',config):
            self.assertIsNone(service.configuration())
        for endpoint in ('http://remote.example/','https://api.cobalt.tools/','https://user:pass@example.com/'):
            with patch.dict(os.environ,{'CLIP_COBALT_URL':endpoint}):
                with self.assertRaises(service.CobaltFailure):service.configuration()

    def test_real_mp4_transferred_and_registered_for_editor(self):
        import app as backend
        from fastapi.testclient import TestClient
        sample=self.folder/'sample.mp4'
        backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=320x180:rate=2','-f','lavfi','-i','sine=frequency=440','-t','1','-c:v','libx264','-c:a','aac',str(sample)])
        video=sample.read_bytes()
        def handler(request):
            if request.method=='POST':return httpx.Response(200,json=payload(size=2*len(video),name='sample.mp4'))
            return httpx.Response(200,content=video,headers={'Content-Type':'video/mp4'})
        client=httpx.Client(transport=httpx.MockTransport(handler))
        ident='c'*32
        with patch.object(backend,'DATA',self.folder),patch.dict(backend.JOBS,{},clear=True),patch.dict(backend.IMPORTS,{ident:{'status':'queued'}},clear=True):
            with patch.object(service.httpx,'Client',return_value=client):backend.import_youtube(ident,'https://youtu.be/JCcuOv5y_9g')
            self.assertEqual(backend.IMPORTS[ident]['status'],'ready')
            self.assertAlmostEqual(backend.JOBS[ident]['duration'],1,delta=.1)
            self.assertGreater(len(TestClient(backend.app).get('/api/jobs/'+ident+'/video').content),0)
            self.assertFalse(list((self.folder/ident).glob('track-*.bin')))

    def test_activation_rejects_partial_or_different_configuration(self):
        spec=importlib.util.spec_from_file_location('cobalt_manage',Path(__file__).parents[1]/'services/cobalt/manage.py')
        manage=importlib.util.module_from_spec(spec);spec.loader.exec_module(manage)
        client=self.folder/'client.json';validation=self.folder/'validation.json'
        config={'enabled':False,'endpoint':'http://127.0.0.1:9000/','api_key':'test'}
        client.write_text(json.dumps(config))
        with patch.object(manage,'CLIENT',client),patch.object(manage,'VALIDATION',validation):
            validation.write_text(json.dumps({'config_identity':manage.identity(config),'results':[]}))
            with self.assertRaises(ValueError):manage.activate()
            records=[{'video_id':ident,'mode':mode,'success':True} for ident,mode in manage.EXPECTED]
            validation.write_text(json.dumps({'config_identity':'different','results':records}))
            with self.assertRaises(ValueError):manage.activate()
            self.assertFalse(json.loads(client.read_text())['enabled'])

    def test_fast_only_activation_blocks_original_before_network_access(self):
        config=self.folder/'client.json'
        config.write_text(json.dumps({'enabled':True,'endpoint':'http://127.0.0.1:9000/','api_key':'test','enabled_modes':['fast']}))
        with patch.dict(os.environ,{'CLIP_COBALT_URL':'','CLIP_COBALT_KEY':''}),patch.object(service,'CONFIG_PATH',config),patch.object(service.httpx,'Client') as client:
            with self.assertRaises(service.CobaltFailure) as error:
                service.download('https://youtu.be/JCcuOv5y_9g',self.folder,lambda *a,**k:None,'original')
            self.assertEqual(error.exception.code,'YT-SERVICIO-CALIDAD')
            client.assert_not_called()

    def test_64_second_mp4_cannot_pass_for_an_18_minute_source(self):
        import subprocess
        sample=self.folder/'short.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=160x90:rate=2','-f','lavfi','-i','sine=frequency=440','-t','64','-c:v','libx264','-c:a','aac',str(sample)],check=True)
        data=sample.read_bytes()
        def handler(request):
            if request.method=='POST':return httpx.Response(200,json=payload(size=len(data)*2,duration=1080))
            return httpx.Response(200,content=data,headers={'content-type':'video/mp4'})
        with self.assertRaises(service.CobaltFailure) as error:self.run_download(handler)
        self.assertEqual(error.exception.code,'YT-INCOMPLETO')
        self.assertFalse((self.folder/'download.mp4').exists())
        self.assertFalse(list(self.folder.glob('track-*.bin')))

    def test_missing_original_duration_or_wrong_video_identity_are_rejected(self):
        for change in ({'expected_duration':None},{'source_video_id':'rcPWJKs5It4'}):
            calls=[]
            def handler(request):
                calls.append(request)
                return httpx.Response(200,json={**payload(),**change})
            with self.assertRaises(service.CobaltFailure):self.run_download(handler)
            self.assertEqual(len(calls),1)
