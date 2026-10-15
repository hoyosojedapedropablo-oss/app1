import threading,unittest
from coverage import plan,covered,complete_coverage
from cloud_ai import AnalysisCancelled

class CoverageTests(unittest.TestCase):
 def test_unique_coverage_and_range_even_with_no_highlights(self):
  for duration,minimum,maximum in [(1080,20,60),(7200,20,60),(125,60,60),(25,20,60),(7200,5,5)]:
   clips=plan([],[],duration,minimum,maximum)
   self.assertGreaterEqual(covered(clips)+1e-6,.75*duration)
   self.assertTrue(all(minimum-1e-6<=c['duration']<=maximum+1e-6 for c in clips))
   self.assertTrue(all(0<=c['start']<c['end']<=duration for c in clips))
   self.assertTrue(all(not c['potential'] for c in clips))
 def test_overlap_is_not_counted_twice_and_highlight_kept(self):
  highlight=dict(id='highlight',start=15,end=55,duration=40,title='Una reacción inesperada',score=90)
  clips=plan([highlight],[],200,20,60)
  self.assertEqual(next(c for c in clips if c['id']=='highlight')['potential'],True)
  self.assertGreaterEqual(covered(clips),150)
  self.assertEqual(covered([dict(start=0,end=60),dict(start=20,end=70)]),70)
 def test_every_review_clip_gets_editorial_titles(self):
  calls=[]
  def completion(payload,**kwargs):
   calls.append(payload)
   return {'clips':[dict(id=c['id'],titles=['Una sorpresa transforma la conversación']) for c in payload['clips']]}
  clips=complete_coverage([],[],1080,20,60,completion)
  self.assertGreater(len(clips),10)
  self.assertTrue(all(c['title'] and c['titles'] for c in clips))
  self.assertTrue(all(len(p['clips'])<=6 for p in calls))
 def test_cancellation_and_short_video_are_explicit(self):
  with self.assertRaisesRegex(ValueError,'más corto'):plan([],[],10,20,60)
  event=threading.Event();event.set()
  with self.assertRaises(AnalysisCancelled):complete_coverage([],[],100,20,60,lambda *a,**k:self.fail('No inference after cancel'),cancel=event)
