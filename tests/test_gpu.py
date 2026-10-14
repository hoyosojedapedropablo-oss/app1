import json,threading,unittest
from unittest.mock import patch
import httpx
import gpu_ai,cloud_ai

class GPUAnalysis(unittest.TestCase):
 def transport(self,gpu_bytes=5_000_000_000,model=True):
  def respond(request):
   self.assertEqual(request.url.host,'127.0.0.1')
   if request.url.path=='/api/version':return httpx.Response(200,json={'version':'0.12.0'})
   if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':gpu_ai.MODEL}] if model else []})
   if request.url.path=='/api/ps':return httpx.Response(200,json={'models':[{'name':gpu_ai.MODEL,'size_vram':gpu_bytes}]})
   if request.url.path=='/api/chat':
    body=json.loads(request.content)
    self.assertNotIn('Authorization',request.headers)
    if body['messages'][0]['role']=='user':return httpx.Response(200,json={'message':{'content':'OK'},'done':True})
    self.assertIsInstance(body['format'],dict)
    payload=json.loads(body['messages'][1]['content'])
    if payload.get('task')=='coverage_titles':
     content={'clips':[dict(id=c['id'],titles=['Una sorpresa transforma la conversación']) for c in payload['clips']]}
     return httpx.Response(200,json={'message':{'content':json.dumps(content)},'done':True,'done_reason':'stop'})
    moment=dict(first=0,last=len(payload['frases'])-1,category='Emoción',hook=5,payoff=5,novelty=4,emotion=5,discussion=4,coherent=True,reason='Prioriza salud sobre más directos',evidence='Gané menos dinero pero recuperé mi salud.',titles=['Westcol reduce los directos para cuidar su salud'])
    return httpx.Response(200,json={'message':{'content':json.dumps({'moments':[moment]})},'done':True,'done_reason':'stop'})
   if request.url.path=='/api/generate':return httpx.Response(200,json={'done':True})
   return httpx.Response(404)
  return httpx.MockTransport(respond)
 def test_actual_gpu_memory_required_not_just_installed(self):
  with self.assertRaisesRegex(ValueError,'sin memoria GPU'):gpu_ai.warmup(self.transport(gpu_bytes=0))
  info=gpu_ai.warmup(self.transport())
  self.assertTrue(info['gpu_loaded']);self.assertGreater(info['gpu_bytes'],0)
 def test_missing_model_is_actionable(self):
  with self.assertRaisesRegex(ValueError,'INSTALAR_GPU_WINDOWS'):gpu_ai.warmup(self.transport(model=False))
 def test_local_gpu_never_calls_cloud_or_cpu_llama(self):
  transcript=[dict(start=0,end=8,text='Antes hacía directos todos los días y apenas dormía.'),dict(start=8,end=16,text='Decidí reducir los directos para recuperar mi salud.'),dict(start=16,end=24,text='Gané menos dinero pero recuperé mi salud.')]
  with patch('cloud_ai.complete',side_effect=AssertionError('No paid API')),patch('intelligence.local_model',side_effect=AssertionError('No CPU llama')):
   clips=gpu_ai.select_gpu(transcript,20,60,25,speaker='Westcol',transport=self.transport())
  self.assertEqual(len(clips),1)
  self.assertTrue(20<=clips[0]['duration']<=60)
  self.assertIn('local GPU',clips[0]['source'])
 def test_gpu_title_schema_for_every_coverage_clip(self):
  from coverage import complete_coverage,covered
  clips=complete_coverage([],[],180,20,60,lambda payload,**kwargs:gpu_ai.complete(payload,transport=self.transport(),**kwargs))
  self.assertGreaterEqual(covered(clips),135)
  self.assertTrue(all(c['title'] for c in clips))
 def test_cancellation_does_not_send_new_gpu_request(self):
  event=threading.Event();event.set()
  with self.assertRaises(cloud_ai.AnalysisCancelled):gpu_ai.complete({},transport=self.transport(),cancel=event)

if __name__=='__main__':unittest.main()
