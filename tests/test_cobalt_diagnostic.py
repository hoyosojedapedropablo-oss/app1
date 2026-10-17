import importlib.util
from pathlib import Path
import unittest
import httpx

spec=importlib.util.spec_from_file_location('cobalt_diagnose',Path(__file__).parents[1]/'services/cobalt/diagnose.py')
diag=importlib.util.module_from_spec(spec);spec.loader.exec_module(diag)

class DiagnosticTests(unittest.TestCase):
    def test_distinguishes_empty_merge_from_flowing_tracks_without_secrets(self):
        import json
        def handler(request):
            if request.method=='POST':
                body=json.loads(request.content)
                if body['localProcessing']=='disabled':return httpx.Response(200,json={'status':'tunnel','url':'http://localhost:9000/tunnel?token=private&part=merge'})
                return httpx.Response(200,json={'status':'local-processing','tunnel':['http://localhost:9000/tunnel?token=private&part=video','http://localhost:9000/tunnel?token=private&part=audio']})
            self.assertNotIn('Authorization',request.headers)
            return httpx.Response(200,content=b'' if request.url.params['part']=='merge' else b'x'*70000)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=diag.inspect_paths(client,'http://localhost:9000/','private-key')
        self.assertEqual(result[0]['streams'][0]['sample_bytes'],0)
        self.assertEqual([s['sample_bytes'] for s in result[1]['streams']],[65536,65536])
        self.assertNotIn('private',json.dumps(result))

    def test_foreign_url_never_requested_and_safe_errors_only(self):
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(200,json={'status':'tunnel','url':'https://evil.example/tunnel?secret=private'})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=diag.inspect_paths(client,'http://localhost:9000/','key')
        self.assertEqual(len(calls),2)
        self.assertTrue(all(r['error_code']=='YT-SERVICIO-RESPUESTA' for r in result))
        self.assertNotIn('private',str(result))

    def test_upstream_probe_preserves_head_get_evidence_and_redacts_urls(self):
        import json
        import subprocess
        script=diag.UPSTREAM_PROBE
        script=script.replace("const {fetch,EnvHttpProxyAgent} = await import('undici');", "const EnvHttpProxyAgent=class {}; const fetch=async (url,options)=>{if(options.method==='HEAD')return new Response(null,{status:403});return url.searchParams.get('track')==='video'?new Response(new Uint8Array(70000),{status:206,headers:{'Content-Type':'video/mp4'}}):new Response('private error detail',{status:403});};")
        script=script.replace("const {default:extract} = await import('./src/processing/services/youtube.js');", "const extract=async()=>({urls:['https://media.googlevideo.com/video?track=video&secret=PRIVATE','https://media.googlevideo.com/video?track=audio&secret=PRIVATE']});")
        script=script.replace("const {getHeaders} = await import('./src/stream/shared.js');", "const getHeaders=()=>({});")
        output=subprocess.run(['node','--input-type=module'],input=script,capture_output=True,text=True,timeout=5,check=True)
        self.assertNotIn('PRIVATE',output.stdout+output.stderr)
        self.assertNotIn('private error detail',output.stdout+output.stderr)
        report=json.loads(output.stdout.strip().removeprefix('CLIP_PROBE_JSON:'))
        self.assertEqual(report['tracks'][0]['head']['http_status'],403)
        self.assertEqual(report['tracks'][0]['get']['http_status'],206)
        self.assertEqual(report['tracks'][0]['get']['sample_bytes'],65536)
        self.assertEqual(report['tracks'][1]['get']['http_status'],403)
        self.assertEqual(report['tracks'][1]['get']['sample_bytes'],0)
