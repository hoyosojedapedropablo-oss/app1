import json,threading,time,unittest,tempfile,uuid
from pathlib import Path
import app as backend
from unittest.mock import patch
import httpx
import cloud_ai
from intelligence import candidate_windows
from timeline import timed_sentences
from app import app
from fastapi.testclient import TestClient

class CloudAnalysis(unittest.TestCase):
 def tearDown(self):cloud_ai.configure('')
 def test_parallel_text_only_analysis_without_local_model(self):
  cloud_ai.configure('test-key-for-offline-tests')
  active=0;maximum=0;lock=threading.Lock();payloads=[];progress=[]
  transcript=[dict(start=i*10,end=(i+1)*10,text=f'Opinión concreta del tema {i}.') for i in range(110)]
  def respond(request):
   nonlocal active,maximum
   body=json.loads(request.content);payloads.append(body)
   self.assertEqual(str(request.url),'https://api.openai.com/v1/chat/completions')
   self.assertNotIn('test-key-for-offline-tests',request.content.decode())
   with lock:active+=1;maximum=max(active,maximum)
   time.sleep(.04)
   with lock:active-=1
   return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"moments": []}'}}]})
  with patch('intelligence.local_model',side_effect=AssertionError('Cloud mode must not load CPU model')):
   clips=cloud_ai.select_cloud(transcript,20,60,1100,transport=httpx.MockTransport(respond),on_progress=lambda i,total,stage:progress.append((i,total)))
  self.assertEqual(clips,[])
  self.assertEqual(maximum,3)
  self.assertEqual(progress[-1],(len(payloads),len(payloads)))
  self.assertLess(len(payloads),10)
  for body in payloads:
   payload=json.loads(body['messages'][1]['content'])
   ids=[s['id'] for s in payload['frases']]
   self.assertEqual(len(ids),len(set(ids)))
   self.assertNotIn('candidatos',payload)
 def test_recovered_transcript_skips_local_models(self):
  cloud_ai.configure('offline-cache-test-key')
  with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'DATA',Path(tmp)),patch.dict(backend.JOBS,{},clear=True):
   ident=uuid.uuid4().hex;folder=Path(tmp)/ident;folder.mkdir()
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=gray:size=160x90:rate=1','-t','25','-c:v','libx264','-f','mp4',str(folder/'source')])
   transcript=[dict(start=0,end=8,text='Antes hacía directos todos los días y apenas dormía.'),dict(start=8,end=16,text='Decidí reducir los directos para descansar y recuperar mi salud.'),dict(start=16,end=24,text='Gané menos dinero pero recuperé mi salud.')]
   cache=folder/'transcript.json';cache.write_text(json.dumps(transcript),encoding='utf-8');before=cache.stat().st_mtime_ns
   backend.recover_jobs()
   self.assertIn(ident,backend.JOBS)
   self.assertTrue(TestClient(app).get('/api/jobs').json()[0]['cached'])
   def completion(payload,**kwargs):
    return {'moments':[dict(first=0,last=len(payload['frases'])-1,category='Emoción',hook=5,payoff=5,novelty=4,emotion=5,discussion=4,coherent=True,reason='Prioriza la salud sobre hacer más directos',evidence='Gané menos dinero pero recuperé mi salud.',titles=['Westcol reduce los directos para cuidar su salud'])]}
   with patch('cloud_ai.complete',side_effect=completion),patch('app.decode_audio',side_effect=AssertionError('Do not decode cached audio')):
    backend.analyze(ident,backend.Analysis(minimum=20,maximum=60,engine='cloud',speaker='Westcol'))
   job=backend.JOBS[ident]
   self.assertEqual(job['status'],'ready',job.get('message'))
   self.assertEqual(len(job['clips']),1)
   self.assertEqual(cache.stat().st_mtime_ns,before)
   self.assertNotIn('transcript',TestClient(app).get('/api/jobs/'+ident).json())
   self.assertTrue((folder/'job.json').exists())

 def test_rate_limit_is_actionable_and_does_not_expose_key(self):
  cloud_ai.configure('private-test-token')
  transport=httpx.MockTransport(lambda r:httpx.Response(429,json={'error':{'message':'private-test-token'}}))
  with self.assertRaises(ValueError) as error:cloud_ai.complete({},transport=transport)
  self.assertIn('saldo',str(error.exception));self.assertNotIn('private-test-token',str(error.exception))
 def test_cancel_prevents_paid_requests(self):
  event=threading.Event();event.set()
  transport=httpx.MockTransport(lambda r: self.fail('No network request should be sent after cancellation'))
  with self.assertRaises(cloud_ai.AnalysisCancelled):cloud_ai.complete({},cancel=event,transport=transport)
 def test_api_key_not_returned_or_persisted(self):
  c=TestClient(app)
  with patch('cloud_ai.check_connection',return_value=True):
   response=c.post('/api/ai',json={'key':'private-key-for-testing'})
  self.assertEqual(response.status_code,200)
  self.assertNotIn('private-key-for-testing',response.text)
  self.assertNotIn('private-key-for-testing',c.get('/api/ai').text)
  self.assertTrue(c.get('/api/ai').json()['configured'])
  self.assertEqual(c.delete('/api/ai').status_code,200)
  self.assertFalse(c.get('/api/ai').json()['configured'])

if __name__=='__main__':unittest.main()
