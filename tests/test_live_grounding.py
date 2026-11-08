import unittest
import intelligence


def phrases_and_transcript():
 texts=['Hoy hablamos de aves.','Son ornitólogos aficionados, en la jerga moderna, pajareros.','Miembros de una comunidad que crece.','Cada sábado salen al campo.',
        'Una app reconoce los cantos.','Así identifican especies.','Contaron sesenta y cuatro especies.','En un solo día de observación.']
 phrases=[{'start':i*6.0,'end':i*6.0+5.5,'text':t} for i,t in enumerate(texts)]
 transcript=[{'start':p['start'],'end':p['end'],'text':p['text'],'words':[{'start':p['start']+j*.5,'end':p['start']+j*.5+.4,'text':w} for j,w in enumerate(p['text'].split())]} for p in phrases]
 return phrases,transcript


def proposal(first,last,evidence):
 return {'moments':[{'first':first,'last':last,'category':'Datos','hook':4,'payoff':4,'novelty':4,'emotion':3,'discussion':3,'coherent':True,
                     'reason':'r','evidence':evidence,'titles':['Pajareros cuentan 64 especies en un día']}]}


class GroundingTests(unittest.TestCase):
 def test_near_verbatim_quote_only_with_repair(self):
  text='son ornitólogos aficionados en la jerga moderna pajareros'
  self.assertTrue(intelligence.grounded('son ornitologos aficionados en la jerga moderna',text,repair=True))
  self.assertFalse(intelligence.grounded('son ornitologos aficionados en la jerga moderna',text))
  self.assertFalse(intelligence.grounded('les gusta mirar pájaros los fines de semana',text,repair=True))   # paraphrase

 def test_fit_duration(self):
  phrases=[{'start':s,'end':s+4} for s in range(0,100,5)]
  self.assertEqual(intelligence.fit_duration(phrases,2,3,20,60),(2,6))
  first,last=intelligence.fit_duration(phrases,0,19,20,60);self.assertLessEqual(phrases[last]['end']-phrases[first]['start'],60)
  self.assertIsNone(intelligence.fit_duration(phrases[:2],0,1,20,60))

 def test_repair_extends_span_to_include_real_quote_and_fixes_duration(self):
  phrases,transcript=phrases_and_transcript()
  data=proposal(3,4,'Son ornitólogos aficionados, en la jerga moderna, pajareros')   # quote is in phrase 1, outside 3–4
  self.assertEqual(intelligence.accept_proposals(data,phrases,transcript,20,60),[])                 # video analysis: unchanged
  clip=intelligence.accept_proposals(data,phrases,transcript,20,60,repair=True)[0]
  self.assertLessEqual(clip['start'],phrases[1]['start']);self.assertTrue(20<=clip['end']-clip['start']<=60)
  self.assertIn('pajareros',clip['text'].lower())

 def test_repair_still_rejects_invented_quotes(self):
  phrases,transcript=phrases_and_transcript()
  self.assertEqual(intelligence.accept_proposals(proposal(1,4,'Los pájaros votaron en las elecciones municipales'),phrases,transcript,20,60,repair=True),[])


if __name__=='__main__':
 unittest.main()
