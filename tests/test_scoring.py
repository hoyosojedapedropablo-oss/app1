"""Clip notes that reflect the clip (E-20): clips of a whole video averaged about 40 and almost all read as «flojo»."""
import unittest

import judge
import scoring


def marks(level, verdict, **over):
    base = {'gancho': level, 'desenlace': level, 'humor': level, 'suspenso': level - 1, 'polemica': level, 'emocion': level - 1,
            'conflicto': level - 2, 'tiene_sentido': True, 'se_entiende_solo': True, 'relleno': False, 'veredicto': verdict}
    return {**base, **over}


def talk(duration, rate=3., first=.2, pause_at=None, pause=0.):
    """Words every 1/rate s from `first`, with an optional silence."""
    out, t = [], first
    while t < duration - .3:
        if pause_at is not None and pause_at <= t < pause_at + 1 / rate: t += pause
        out.append({'text': 'palabra', 'start': t, 'end': t + .8 / rate}); t += 1 / rate
    return out


def clip(i, score, start=None):
    start = i * 40. if start is None else start
    return {'id': f'c{i}', 'start': start, 'end': start + 30, 'score': score, 'text': 'algo dicho', 'marks': {'gancho': 8, 'desenlace': 7}}


class JudgeScaleTests(unittest.TestCase):
    def test_E20_a_publishable_clip_is_not_boxed_as_weak(self):
        # Marks of 5-6 used to land at about 45 («flojo»); a clip a clipper would post now reads as publishable.
        self.assertGreaterEqual(judge.score(marks(6, 'publicable')), 55)
        self.assertGreaterEqual(judge.score(marks(7, 'bueno')), 70)
        self.assertLess(judge.score(marks(9, 'flojo')), 55)                 # the verdict still keeps the number honest
        self.assertIn('publicable', judge.SCHEMA['properties']['veredicto']['enum'])

    def test_E20_judge_is_told_clips_are_preselected_not_that_most_are_weak(self):
        self.assertNotIn('la mayoría de momentos de un directo son normales', judge.SYSTEM)
        self.assertIn('preseleccionados', judge.SYSTEM)


class SignalTests(unittest.TestCase):
    def test_E20_a_clip_that_starts_talking_scores_above_one_with_dead_air(self):
        lively = scoring.signals(talk(30), 30)
        slow = scoring.signals(talk(30, rate=1., first=4., pause_at=10, pause=6), 30)
        self.assertGreater(lively['score'], slow['score'] + 25)
        self.assertGreaterEqual(lively['hook'], .8)
        self.assertGreater(slow['pauses'], .2)

    def test_no_words_gives_no_signal(self):
        self.assertEqual(scoring.signals([], 30)['score'], 0)


class RankTests(unittest.TestCase):
    def rank(self, clips):
        return scoring.rank_video(clips, lambda c: talk(c['end'] - c['start']))

    def test_E20_best_clips_first_with_rank_and_reasons(self):
        out = self.rank([clip(0, 50), clip(1, 80), clip(2, 65)])
        self.assertEqual([c['id'] for c in out], ['c1', 'c2', 'c0'])
        self.assertEqual([c['rank'] for c in out], [1, 2, 3])
        self.assertEqual(out[0]['reasons'][0], 'Top 1 de este video')
        self.assertIn('Gancho fuerte', out[0]['reasons'])
        self.assertEqual(out[0]['judge_score'], 80)

    def test_E20_filler_for_coverage_goes_to_review_not_to_the_main_list(self):
        filler = {'id': 'f', 'start': 5., 'end': 30., 'score': None, 'text': 'relleno'}
        out = self.rank([clip(1, 75), filler])
        self.assertEqual(out[-1]['id'], 'f'); self.assertEqual(out[-1]['section'], 'review')
        self.assertIsNone(out[-1]['score'])
        self.assertEqual(out[0]['section'], 'best')

    def test_E20_a_typical_video_no_longer_averages_forty(self):
        # Judge notes as the old scale gave them for one real-looking video: most in the 40s.
        out = self.rank([clip(i, s) for i, s in enumerate([44, 41, 48, 52, 39, 45, 58, 43, 47, 50])])
        notes = [c['score'] for c in out]
        self.assertGreater(sum(notes) / len(notes), 45)
        self.assertTrue(all(c['section'] == 'best' for c in out[:3]))      # the top 3 of a video are always shown
        self.assertTrue(all(0 <= n <= 99 for n in notes))

    def test_E20c_coverage_clips_are_judged_when_the_ai_marked_no_moment(self):
        coverage = [{'id': f'f{i}', 'start': i * 40., 'end': i * 40. + 30, 'score': None} for i in range(20)]
        self.assertEqual([c['id'] for c in scoring.judge_order(coverage, 40)], [f'f{i}' for i in range(20)])
        mixed = coverage[:3] + [clip(5, 60, start=500.), clip(6, 80, start=600.)]
        self.assertEqual([c['id'] for c in scoring.judge_order(mixed, 4)], ['c6', 'c5', 'f0', 'f1'])

    def test_E20c_judged_coverage_enters_the_ranking_and_filler_waits_in_review(self):
        judged = [dict(clip(i, 50 + i), category='Para revisar') for i in range(4)]
        filler = dict(clip(9, 20), verdict='descartar')
        out = self.rank(judged + [filler])
        self.assertTrue(all(c['section'] == 'best' for c in out[:3]))       # «Los mejores» is never empty
        self.assertEqual(out[-1]['id'], 'c9'); self.assertEqual(out[-1]['section'], 'review')

    def test_E20_place_in_the_video_never_turns_a_weak_clip_into_a_great_one(self):
        out = self.rank([clip(0, 30)])
        self.assertLess(out[0]['score'], scoring.POTENTIAL_FROM)


if __name__ == '__main__':
    unittest.main()
