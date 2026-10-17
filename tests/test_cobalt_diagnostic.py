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
