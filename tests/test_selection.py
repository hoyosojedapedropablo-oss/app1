import unittest
from intelligence import accept_proposals
from cloud_ai import select_cloud

class SelectionRegression(unittest.TestCase):
 def moment(self,**changes):
  return dict(dict(first=0,last=0,category='Humor',hook=4,payoff=4,novelty=1,emotion=4,discussion=1,coherent=True,reason='La sorpresa termina en una broma',evidence='¡Pensé que era mi cuarto!',titles=['Una habitación idéntica provoca una reacción inesperada']),**changes)
 def test_humor_does_not_require_novelty_and_discussion(self):
  phrases=[dict(start=0,end=25,text='Entré y me quedé sorprendido. Pensé que era mi cuarto. Hasta copiaron la silla y la mancha de la pared.')]
  self.assertEqual(len(accept_proposals({'moments':[self.moment()]},phrases,phrases,20,60)),1)
  for changes in [dict(coherent=False),dict(hook=1),dict(evidence='Una pelea inexistente')]:
   self.assertFalse(accept_proposals({'moments':[self.moment(**changes)]},phrases,phrases,20,60))
 def test_invalid_cut_is_repaired_and_logged(self):
  transcript=[dict(start=i*5,end=(i+1)*5,text='Pensé que era mi cuarto.' if i==0 else f'Copiaron el detalle número {i} de la habitación.') for i in range(14)]
  requests=[];diagnostics=[]
  def completion(payload,**kwargs):
   requests.append(payload)
   return {'moments':[self.moment(last=4 if 'revision' in payload else 13)]}
  clips=select_cloud(transcript,20,60,70,completion=completion,diagnostics=diagnostics)
  self.assertEqual(len(clips),1);self.assertEqual(clips[0]['duration'],25)
  self.assertEqual(len(requests),2);self.assertIn('duración',diagnostics[0]['rejections'][0])
 def test_filler_is_not_forced_into_clips(self):
  transcript=[dict(start=0,end=25,text='Voy a conectar el cable y ajustar el micrófono.')]
  calls=[]
  def completion(payload,**kwargs):calls.append(payload);return {'moments':[]}
  self.assertFalse(select_cloud(transcript,20,60,25,completion=completion))
  self.assertEqual(len(calls),2)
