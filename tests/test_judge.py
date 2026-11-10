import unittest
from unittest.mock import patch

import judge
import viral


def answers(**over):
    base = {'quien': 'Spreen', 'a_quien': 'Carrera', 'que_pasa': 'lo acusa de hacer trampa', 'por_que': 'perdió la final',
            'despues': 'Carrera responde furioso', 'tiene_sentido': True, 'se_entiende_solo': True, 'tipo': 'conflicto',
            'gancho': 8, 'desenlace': 8, 'humor': 2, 'suspenso': 4, 'polemica': 9, 'emocion': 6, 'conflicto': 9,
            'relleno': False, 'veredicto': 'subir_ya', 'motivo': 'Acusación directa con respuesta.'}
    return {**base, **over}


class ScoreTests(unittest.TestCase):
    def test_strong_conflict_is_on_fire(self):
        self.assertGreaterEqual(judge.score(answers()), 85)

    def test_scores_spread_instead_of_clustering(self):
        notes = {judge.score(answers()),
                 judge.score(answers(gancho=6, desenlace=6, polemica=3, conflicto=2, humor=7, veredicto='bueno')),
                 judge.score(answers(gancho=4, desenlace=2, polemica=2, conflicto=1, humor=2, emocion=3, suspenso=2, veredicto='flojo')),
                 judge.score(answers(gancho=1, desenlace=1, polemica=0, conflicto=0, humor=1, emocion=1, suspenso=0, relleno=True, veredicto='descartar'))}
        self.assertEqual(len(notes), 4)
        self.assertGreater(max(notes) - min(notes), 50)

    def test_verdict_keeps_the_number_honest(self):
        # High marks but a «flojo» verdict never reads as a great clip; filler stays under the live cut.
        self.assertLessEqual(judge.score(answers(veredicto='flojo')), 64)
        self.assertLess(judge.score(answers(relleno=True, veredicto='descartar')), judge.DROP_BELOW)

    def test_not_understood_alone_costs_points(self):
        self.assertLess(judge.score(answers(veredicto='bueno', se_entiende_solo=False)), judge.score(answers(veredicto='bueno')))

    def test_bad_values_are_clamped(self):
        self.assertTrue(0 <= judge.score({'gancho': 99, 'desenlace': -4, 'humor': None, 'veredicto': 'raro'}) <= 100)


class JudgeTests(unittest.TestCase):
    def test_judge_returns_analysis_and_marks(self):
        seen = {}
        def complete(payload, cancel=None):
            seen.update(payload); return answers()
        r = judge.judge('Te robaste el torneo, hermano', speaker='Spreen', context='Final', names=['Carrera'], complete=complete)
        self.assertEqual(r['verdict'], 'subir_ya'); self.assertEqual(r['kind'], 'conflicto')
        self.assertEqual(r['analysis']['a_quien'], 'Carrera'); self.assertEqual(r['marks']['polemica'], 9)
        self.assertEqual(seen['nombres_del_directo'], ['Carrera'])

    def test_no_judge_when_ai_fails_or_text_is_empty(self):
        def broken(payload, cancel=None): raise RuntimeError('ollama off')
        self.assertIsNone(judge.judge('algo dicho', complete=broken))
        self.assertIsNone(judge.judge('   ', complete=lambda p, c=None: answers()))
        self.assertIsNone(judge.judge('algo', complete=lambda p, c=None: {'nada': 1}))

    def test_title_writer_receives_the_analysis(self):
        seen = {}
        def complete(payload, cancel=None):
            seen.update(payload); return {'titulos': []}
        viral.generate('Te robaste el torneo', speaker='Spreen', complete=complete, analysis={'a_quien': 'Carrera', 'motivo': ''})
        self.assertEqual(seen.get('analisis_del_editor'), {'a_quien': 'Carrera'})


class LiveJudgeTests(unittest.TestCase):
    def run_detect(self, verdict):
        import tempfile, live
        from pathlib import Path
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        s = live.LiveSession(Path(tmp.name), 'https://kick.com/canal', minimum=10, maximum=30, buffer_minutes=10)
        s.segments.mkdir(parents=True); s.clips.mkdir(parents=True)
        palabras = 'te robaste el torneo hermano y todos lo vimos en directo no me vengas con cuentos'.split()
        words = [{'start': i * .4, 'end': i * .4 + .35, 'text': palabras[i % len(palabras)]} for i in range(400)]
        s.transcript = [{'start': w['start'], 'end': w['end'], 'text': w['text'], 'words': [w]} for w in words]
        s.media_s = 160
        cand = [{'start': 20.0, 'end': 44.0, 'title': 'Te robaste el torneo', 'titles': [], 'score': 73}]
        with patch.object(s, '_ai_candidates', return_value=(cand, [])), patch('judge.judge', return_value=verdict), \
             patch.object(s, '_viral_title', return_value={}), patch.object(s, '_render_moment', create=True), \
             patch('live.topic_still_open', return_value=False):
            s._detect(160, final=True)
        return s

    def test_live_drops_filler(self):
        s = self.run_detect({'score': 20, 'verdict': 'descartar', 'kind': 'relleno', 'analysis': {'motivo': 'Sin contenido.'}, 'marks': {}})
        self.assertEqual(s.moments, [])

    def test_live_keeps_real_note_and_analysis(self):
        s = self.run_detect({'score': 91, 'verdict': 'subir_ya', 'kind': 'polémica', 'analysis': {'a_quien': 'Carrera', 'motivo': 'Acusación.'}, 'marks': {'polemica': 9}})
        self.assertEqual(len(s.moments), 1); m = s.moments[0]
        self.assertEqual((m['score'], m['verdict'], m['viral_kind']), (91, 'subir_ya', 'polémica'))
        self.assertEqual(m['analysis']['a_quien'], 'Carrera')

    def test_live_keeps_moment_when_judge_unavailable(self):
        s = self.run_detect(None)
        self.assertEqual(len(s.moments), 1); self.assertEqual(s.moments[0]['score'], 73)


if __name__ == '__main__':
    unittest.main()
