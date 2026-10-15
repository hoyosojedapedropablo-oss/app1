import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from fastapi.testclient import TestClient
from editorial import cached_completion
from coverage import plan,covered,complete_coverage
from cloud_ai import select_cloud
from app import app,Export,render_title

class EditorialTests(unittest.TestCase):
 def test_topics_do_not_get_joined_to_reach_coverage(self):
  transcript=[dict(start=0,end=30,text='Trabajar con mi pareja me enseñó a poner límites.'),dict(start=30,end=60,text='El evento de boxeo tendrá nuevos competidores.')]
  topics=[dict(start=0,end=30,label='Pareja'),dict(start=30,end=60,label='Boxeo')]
  mixed=dict(id='mixed',start=0,end=60,title='Un título que mezcla todo',score=90,text='Habla de dos cosas.')
  clips=plan([mixed],transcript,60,20,60,topics)
  self.assertTrue(clips);self.assertGreaterEqual(covered(clips),45)
  self.assertTrue(all(c['end']<=30 or c['start']>=30 for c in clips))
  self.assertNotIn('mixed',[c['id'] for c in clips])
 def test_question_and_answer_stay_together(self):
  transcript=[dict(start=0,end=10,text='¿Cómo decidiste trabajar con tu pareja?'),dict(start=10,end=30,text='Primero pusimos límites claros para respetar nuestro tiempo.'),dict(start=30,end=40,text='¿Y cómo cambió la relación?'),dict(start=40,end=60,text='Aprendimos a separar los problemas del trabajo de nuestra casa.')]
  clips=plan([],transcript,60,20,40,[dict(start=0,end=60,label='Trabajar con tu pareja')])
  self.assertEqual([(c['start'],c['end']) for c in clips],[(0,30),(30,60)])
 def test_short_topics_are_not_forced_together(self):
  transcript=[dict(start=0,end=15,text='Un tema completo.'),dict(start=15,end=30,text='Otro tema diferente.')]
  self.assertFalse(plan([],transcript,30,20,60,[dict(start=0,end=15),dict(start=15,end=30)]))
 def test_topics_are_extracted_in_existing_call_without_empty_retry(self):
  transcript=[dict(start=0,end=30,text='Antes trabajaba con mi pareja.'),dict(start=30,end=60,text='Ahora organizo un evento de boxeo.')]
  calls=[];topics=[]
  def completion(payload,**kwargs):
   calls.append(payload);return {'moments':[],'topics':[dict(first=0,last=0,label='Pareja'),dict(first=1,last=len(payload['frases'])-1,label='Boxeo')]}
  self.assertFalse(select_cloud(transcript,20,60,60,completion=completion,topic_ranges=topics))
  self.assertEqual(len(calls),1);self.assertEqual(len(topics),2)
 def test_cached_model_output_is_reused_and_context_invalidates_it(self):
  with tempfile.TemporaryDirectory() as tmp:
   calls=[]
   def completion(payload,**kwargs):calls.append(payload);return {'moments':[],'topics':[]}
   wrapped=cached_completion(Path(tmp),'gpu',completion)
   payload={'frases':[],'contexto':'pareja'}
   wrapped(payload);wrapped(payload)
   self.assertEqual(len(calls),1)
   wrapped(dict(payload,contexto='boxeo'));self.assertEqual(len(calls),2)
 def test_auto_titles_use_fewer_batches_and_read_the_full_clip(self):
  calls=[]
  def completion(payload,**kwargs):
   calls.append(payload)
   return {'clips':[dict(id=c['id'],titles=['¿Dónde está el límite al trabajar con tu pareja?']) for c in payload['clips']]}
  clips=complete_coverage([],[],1080,20,60,completion)
  self.assertEqual(len(calls),3);self.assertEqual(len(clips),14)
  self.assertIn('TODO el clip',calls[0]['instruccion'])
 def test_background_padding_is_exact_and_color_is_customizable(self):
  base=dict(start=0,end=20,title='Trabajar con tu pareja no siempre sale como esperas',subtitles='',title_padding_x=0,title_padding_y=0)
  tight=render_title(Export(**base))
  roomy=render_title(Export(**dict(base,title_padding_x=25,title_padding_y=12)))
  self.assertEqual(roomy.width-tight.width,50);self.assertEqual(roomy.height-tight.height,24)
  for color in ['#FFFFFF','#000000','#FFEB00','#FFBF00','#FF7900','#FF9EC4','#FF00AA','#FF2525']:
   opts=Export(**dict(base,title_bg_color=color,title_padding_x=4,title_padding_y=4))
   image=render_title(opts)
   self.assertEqual(image.getpixel((0,0))[:3],tuple(bytes.fromhex(color[1:])))
   response=TestClient(app).post('/api/title-preview',json=opts.model_dump())
   self.assertEqual(response.status_code,200)
   self.assertEqual(Image.open(io.BytesIO(response.content)).size,image.size)

 def test_stable_clip_ids_allow_reusing_title_batches(self):
  with tempfile.TemporaryDirectory() as tmp:
   calls=[]
   def completion(payload,**kwargs):
    calls.append(payload)
    return {'clips':[dict(id=c['id'],titles=['¿Dónde está el límite al trabajar con tu pareja?']) for c in payload['clips']]}
   wrapped=cached_completion(Path(tmp),'gpu',completion)
   first=complete_coverage([],[],1080,20,60,wrapped)
   count=len(calls)
   second=complete_coverage([],[],1080,20,60,wrapped)
   self.assertEqual(len(calls),count)
   self.assertEqual([c['id'] for c in first],[c['id'] for c in second])

 def test_full_cached_analysis_preserves_topics_and_reuses_both_model_passes(self):
  import app as backend
  with tempfile.TemporaryDirectory() as tmp,patch.object(backend,'DATA',Path(tmp)),patch.dict(backend.JOBS,{},clear=True):
   ident='e'*32;folder=Path(tmp)/ident;folder.mkdir()
   backend.command(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=160x90:rate=1','-t','60','-c:v','libx264','-f','mp4',str(folder/'source')])
   transcript=[dict(start=0,end=30,text='Trabajar con mi pareja nos obligó a poner límites.'),dict(start=30,end=60,text='Ahora prepararemos un evento de boxeo con nuevos participantes.')]
   (folder/'transcript.json').write_text(json.dumps(transcript))
   backend.JOBS[ident]=dict(id=ident,duration=60,name='sample.mp4',status='uploaded',clips=[])
   calls=[]
   def complete(payload,**kwargs):
    calls.append(payload)
    if payload.get('task')=='coverage_titles':return {'clips':[dict(id=c['id'],titles=['¿Dónde está el límite al trabajar con tu pareja?' if 'pareja' in c['text'] else 'El próximo evento de boxeo ya toma forma']) for c in payload['clips']]}
    phrases=payload['frases'];split=next(i for i,p in enumerate(phrases) if p['start']>=30)
    return {'moments':[],'topics':[dict(first=0,last=split-1,label='Pareja'),dict(first=split,last=len(phrases)-1,label='Boxeo')]}
   with patch('cloud_ai.complete',side_effect=complete),patch('app.decode_audio',side_effect=AssertionError('Cached transcript must not be decoded')):
    backend.analyze(ident,backend.Analysis(engine='cloud'))
    self.assertEqual(backend.JOBS[ident]['status'],'ready',backend.JOBS[ident].get('message'))
    ids=[c['id'] for c in backend.JOBS[ident]['clips']]
    self.assertEqual(len(calls),2)
    backend.analyze(ident,backend.Analysis(engine='cloud'))
   job=backend.JOBS[ident]
   self.assertEqual(len(calls),2);self.assertEqual(job['analysis_cache_hits'],2)
   self.assertEqual([c['id'] for c in job['clips']],ids)
   self.assertGreaterEqual(job['coverage_percent'],75)
   self.assertTrue(all(c['end']<=30 or c['start']>=30 for c in job['clips']))
