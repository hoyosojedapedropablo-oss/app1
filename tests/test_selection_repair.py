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

    def test_E22_example_titles_of_the_guide_are_never_accepted(self):
        text = 'Arriba las manos, entramos por la puerta con el ariete y Westcol no encuentra la planta'
        self.assertIsNone(intelligence.clean_title('¿Dónde está el límite cuando trabajas con tu pareja?', text))
        self.assertIsNone(intelligence.clean_title('¿Dónde está el límite al trabajar con tu pareja?', text))
        self.assertNotIn('pareja', intelligence.TITLE_GUIDE)

    def test_E23_a_described_quote_is_replaced_by_its_key_phrase(self):
        phrases, transcript = story()
        data = proposal(18, 24, 'Se menciona que le iban a cobrar una deuda')               # a description, not said
        self.assertEqual(intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True), [])
        data['moments'][0]['key'] = 22
        clip = intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True)[0]
        self.assertIn('cobrar la deuda', clip['evidence'])
        self.assertTrue(20 <= clip['end'] - clip['start'] <= 60)

    def test_E23_a_key_far_from_the_moment_does_not_rescue_it(self):
        phrases, transcript = story()
        data = proposal(2, 8, 'Se menciona que le iban a cobrar una deuda'); data['moments'][0]['key'] = 22
        self.assertEqual(intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True), [])

    def test_E23_selector_asks_for_a_copied_quote_and_its_phrase_id(self):
        self.assertIn('COPIA EXACTA', intelligence.SYSTEM)
        self.assertIn('key', intelligence.Moment.model_fields)
        self.assertIn('una broma no es una crítica', intelligence.TITLE_GUIDE)

    def test_E23_a_clip_without_valid_titles_does_not_fail_the_analysis(self):
        from coverage import complete_coverage
        def completion(payload, **kwargs):
            return {'clips': [dict(id=c['id'], titles=['¿Dónde está el límite cuando trabajas con tu pareja?']) for c in payload['clips']]}
        clips = complete_coverage([], [], 120, 20, 60, completion)
        self.assertTrue(clips)
        self.assertTrue(all(c['title_fallback'] and 'ponle título' in c['title'] for c in clips))

    def test_E24_with_repair_the_judge_decides_moments_the_model_rated_two(self):
        phrases, transcript = story()
        data = proposal(18, 24, 'me dijeron que me iban a cobrar la deuda con la vida')
        data['moments'][0].update(hook=2, payoff=2)
        self.assertEqual(intelligence.accept_proposals(data, phrases, transcript, 20, 60), [])          # strict without repair
        self.assertEqual(len(intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True)), 1)
        data['moments'][0].update(hook=1)            # E-25: even its own 1 no longer drops it with repair
        self.assertEqual(len(intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True)), 1)
        data['moments'][0].update(coherent=False)    # an idea the model itself finds incomplete still goes
        self.assertEqual(intelligence.accept_proposals(data, phrases, transcript, 20, 60, repair=True), [])

    def test_E24_titles_in_spanish_case_and_without_ellipsis(self):
        text = 'Ibai y Westcol entrenan con la Policía'
        self.assertEqual(intelligence.clean_title('Entrenamiento Intenso: ¿Qué Tan Fuertes Se Hacen?', text),
                         'Entrenamiento intenso: ¿qué tan fuertes se hacen?')
        self.assertEqual(intelligence.clean_title('Westcol Y Ibai Contra La Policía En El Asalto', text),
                         'Westcol y Ibai contra la Policía en el asalto')
        self.assertEqual(intelligence.clean_title('Así fue... la muerte del vecino del barrio', text), 'Así fue la muerte del vecino del barrio')
        self.assertEqual(intelligence.clean_title('¿Por qué Westcol no encuentra la planta?', text), '¿Por qué Westcol no encuentra la planta?')

    def test_E24_coverage_does_not_repeat_an_ai_clip(self):
        from coverage import plan
        transcript = [{'start': i * 5., 'end': i * 5. + 4.6, 'text': f'Frase número {i} del podcast.',
                       'words': [{'start': i * 5., 'end': i * 5. + 4.6, 'text': f'frase{i}.'}]} for i in range(60)]
        ai = {'id': 'ia', 'start': 15., 'end': 50., 'text': 'x', 'score': 70, 'title': 'IA'}
        clips = plan([ai], transcript, 300, 20, 60)
        for c in clips:
            if c['id'] != 'ia':
                self.assertLessEqual(min(c['end'], 50.) - max(c['start'], 15.), .25 * min(c['end'] - c['start'], 35.) + 1e-6)

    def test_E25_titles_that_say_nothing_or_name_someone_absent_are_rejected(self):
        ibai = 'Uescol, fuera de disparador. Acabas de disparar, va, va, va'
        self.assertIsNone(intelligence.clean_title('¡Va, va, va!', ibai))
        self.assertEqual(intelligence.clean_title('¿Quién controla el disparo de Westcol?', ibai), '¿Quién controla el disparo de Westcol?')
        guest = 'Juan Camilo cuenta que la vida tiene tres estaciones y que él ya pasó por la cárcel'
        self.assertIsNone(intelligence.clean_title('La reflexión de Westcol sobre las tres estaciones', guest))
        self.assertIsNone(intelligence.clean_title('Desde los 13 años: la vida delincuencial de un hablante', guest))
        self.assertEqual(intelligence.clean_title('Juan Camilo y las tres estaciones de la vida', guest), 'Juan Camilo y las tres estaciones de la vida')

    def test_E25_coverage_never_repeats_more_than_three_seconds(self):
        from coverage import overlaps_a_clip
        ai = [{'start': 420., 'end': 441.1}]
        self.assertTrue(overlaps_a_clip(436.5, 470., ai))          # 4.6 s of a 21 s clip: 22 %, but more than 3 s
        self.assertFalse(overlaps_a_clip(439., 470., ai))          # 2.1 s at the edge is fine

    def test_quote_too_long_for_the_range_is_still_dropped(self):
        phrases = [{'start': 0., 'end': 70., 'text': 'una sola frase enorme sin cortes que dura setenta segundos'}]
        self.assertIsNone(intelligence.fit_around(phrases, 0, 0, (0, 0), 20, 60))


if __name__ == '__main__':
    unittest.main()
