"""The video analysis keeps the moments the AI found (E-21): on two real videos 0 of 24 proposals survived, all for
their length (remates de 4-11 s en Ibai, historias de 72-188 s en un podcast), and every clip came from coverage."""
import re, unittest
from pathlib import Path
import intelligence

ROOT = Path(__file__).resolve().parents[1]


def story(n=30, length=5.):
    texts = [f'Frase {i} de la historia con detalles del barrio.' for i in range(n)]
    texts[22] = 'Y ahí fue cuando me dijeron que me iban a cobrar la deuda con la vida.'
    phrases = [{'start': i * length, 'end': i * length + length - .4, 'text': t} for i, t in enumerate(texts)]
    transcript = [{'start': p['start'], 'end': p['end'], 'text': p['text'],
                   'words': [{'start': p['start'] + j * .3, 'end': p['start'] + j * .3 + .25, 'text': w} for j, w in enumerate(p['text'].split())]}
                  for p in phrases]
    return phrases, transcript


def proposal(first, last, evidence):
    return {'moments': [{'first': first, 'last': last, 'category': 'Relato', 'hook': 4, 'payoff': 4, 'novelty': 4, 'emotion': 4,
                         'discussion': 3, 'coherent': True, 'reason': 'r', 'evidence': evidence,
                         'titles': ['Le dijeron que le cobrarían la deuda con la vida']}]}


class RepairTests(unittest.TestCase):
    def test_E21_video_analysis_repairs_cuts_instead_of_dropping(self):
        code = (ROOT / 'app.py').read_text(encoding='utf-8')
        calls = re.findall(r'(?:cloud_ai\.select_cloud|gpu_ai\.select_gpu)\(transcript,[^\n]*', code)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all('repair=True' in c for c in calls), calls)

    def test_E21_a_long_story_is_cut_around_its_quote(self):
        phrases, transcript = story()
        data = proposal(2, 29, 'me dijeron que me iban a cobrar la deuda con la vida')    # 148 s, quote at phrase 22
        self.assertEqual(intelligence.accept_proposals(data, phrases, transcript, 20, 60), [])   # without repair: dropped
        clip = intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True)[0]
        self.assertTrue(20 <= clip['end'] - clip['start'] <= 60)
        self.assertLessEqual(clip['start'], phrases[22]['start']); self.assertGreaterEqual(clip['end'], phrases[22]['end'])
        self.assertGreater(clip['start'], phrases[2]['start'])           # not the first 60 s of the story

    def test_E21_a_short_punchline_grows_to_the_minimum(self):
        phrases, transcript = story()
        data = proposal(22, 22, 'me dijeron que me iban a cobrar la deuda con la vida')    # 4.6 s
        clip = intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True)[0]
        self.assertTrue(20 <= clip['end'] - clip['start'] <= 60)
        self.assertIn('cobrar la deuda', clip['text'])

    def test_quote_too_long_for_the_range_is_still_dropped(self):
        phrases = [{'start': 0., 'end': 70., 'text': 'una sola frase enorme sin cortes que dura setenta segundos'}]
        self.assertIsNone(intelligence.fit_around(phrases, 0, 0, (0, 0), 20, 60))


if __name__ == '__main__':
    unittest.main()
