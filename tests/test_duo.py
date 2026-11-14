"""Fase 4 «Dos personas» (docs/fase4-dos-personas.md): when a clip is split, and the two crops."""
import gzip, json, subprocess, tempfile, unittest
from pathlib import Path
import numpy as np
import tracking

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080


def face(i, cx, cy=420, h=130):
    return dict(id=i, x=cx - h * .4, y=cy - h / 2, w=h * .8, h=h, act=.0, front=1.0)


def result(frames, seconds=10):
    """A synthetic tracking result: `frames(k, n)` gives the faces of sample k of n."""
    n = int(seconds * tracking.SAMPLE_FPS)
    samples = [dict(t=k / tracking.SAMPLE_FPS, speech=True, active=None, faces=frames(k, n)) for k in range(n)]
    return dict(samples=samples, cuts=[], width=W, height=H)


class DuoPlanTests(unittest.TestCase):
    def test_thresholds_are_the_measured_ones(self):
        self.assertEqual((tracking.DUO_TOGETHER, tracking.DUO_SEP_MEDIAN, tracking.DUO_SEP_MIN, tracking.DUO_FLIPS), (.80, .30, .25, 0))
        import layout
        self.assertEqual(tracking.DUO_SEAM, layout.SEAM)
        self.assertEqual(tracking.DUO_PANEL_H + tracking.DUO_SEAM + tracking.DUO_PANEL_HB, 1920)
        self.assertTrue(tracking.DUO_PANEL_H % 2 == 0 and tracking.DUO_PANEL_HB % 2 == 0)       # yuv420p: even heights

    def test_two_people_side_by_side_are_split_left_above(self):
        plan, reason = tracking.duo_plan(result(lambda k, n: [face(7, .76 * W), face(3, .25 * W)]))
        self.assertIsNotNone(plan, reason); self.assertEqual(reason, '')
        self.assertEqual((plan['left'], plan['right']), (3, 7))          # left person = top panel
        self.assertEqual(plan['together'], 1.0); self.assertAlmostEqual(plan['sep_median'], .51, places=2)

    def test_a_person_who_leaves_halfway_is_not_split(self):
        # 60 % of the clip with both: under the 80 % needed
        plan, reason = tracking.duo_plan(result(lambda k, n: [face(1, .25 * W)] + ([face(2, .75 * W)] if k < .6 * n else [])))
        self.assertIsNone(plan); self.assertIn('60 %', reason); self.assertIn('80 %', reason)

    def test_faces_at_22_percent_are_not_split(self):
        plan, reason = tracking.duo_plan(result(lambda k, n: [face(1, .39 * W), face(2, .61 * W)]))
        self.assertIsNone(plan); self.assertIn('22 %', reason); self.assertIn('juntas', reason)

    def test_two_people_who_cross_are_not_split(self):
        # they walk past each other: the one on the left ends on the right
        def frames(k, n):
            f = k / (n - 1); return [face(1, (.15 + .7 * f) * W), face(2, (.85 - .7 * f) * W)]
        plan, reason = tracking.duo_plan(result(frames))
        self.assertIsNone(plan); self.assertIn('cambian de lado', reason)

    def test_one_or_three_people_and_nobody(self):
        self.assertIn('una persona', tracking.duo_plan(result(lambda k, n: [face(1, W / 2)]))[1])
        self.assertIn('3 personas', tracking.duo_plan(result(lambda k, n: [face(1, .2 * W), face(2, .5 * W), face(3, .8 * W)]))[1])
        self.assertIn('ninguna', tracking.duo_plan(result(lambda k, n: []))[1])
        # a small face in the background is not a main person
        self.assertIn('una persona', tracking.duo_plan(result(lambda k, n: [face(1, .3 * W, h=200), face(2, .8 * W, h=60)]))[1])

    def test_forcing_splits_two_people_and_keeps_the_reason(self):
        r = result(lambda k, n: [face(1, .39 * W), face(2, .61 * W)])
        plan, reason = tracking.duo_plan(r, force=True)
        self.assertTrue(plan['forced']); self.assertIn('juntas', reason)
        self.assertIsNone(tracking.duo_plan(result(lambda k, n: [face(1, W / 2)]), force=True)[0])   # one person: nothing to split

    def test_the_bench_of_ten_real_clips_is_decided_right(self):
        """Parte C.1: on the 10 clips of the user's projects, the 4 of two people are split and none of the other 6."""
        bench = {c['id']: c for c in json.loads((ROOT / 'tests/bench/dos_personas.json').read_text(encoding='utf-8'))['clips']}
        fixture = json.loads(gzip.decompress((ROOT / 'tests/bench/dos_personas_tracking.json.gz').read_bytes()))
        self.assertEqual(set(bench), set(fixture)); self.assertEqual(sum(c['dividir'] for c in bench.values()), 4)
        for cid, r in fixture.items():
            with self.subTest(clip=cid):
                plan, reason = tracking.duo_plan(r)
                self.assertEqual(plan is not None, bench[cid]['dividir'], reason)
                if plan is None: self.assertTrue(reason)


class DuoPathTests(unittest.TestCase):
    def setUp(self):
        def frames(k, n):          # two people, the right one nods and drifts a little; the left one vanishes for 1 s
            right = face(2, .74 * W + 40 * np.sin(k / 9), 430 + 15 * np.sin(k / 5))
            return ([] if 30 <= k < 38 else [face(1, .26 * W)]) + [right]
        self.r = result(frames, 12)
        self.plan, _ = tracking.duo_plan(self.r)
        self.path = tracking.duo_path(self.r, self.plan)

    def test_each_panel_frames_its_person_inside_the_picture(self):
        p = self.path
        for key, cx, ph in (('top', .26 * W, tracking.DUO_PANEL_H), ('bottom', .74 * W, tracking.DUO_PANEL_HB)):
            panel = p[key]
            self.assertAlmostEqual(panel['w'] / panel['h'], tracking.DUO_PANEL_W / ph, places=2)
            self.assertAlmostEqual(130 / panel['h'], tracking.DUO_FACE, places=1)                       # face ~35 % of the panel
            self.assertTrue(all(0 <= x <= W - panel['w'] for x in panel['x']) and all(0 <= y <= H - panel['h'] for y in panel['y']))
            centre = np.array(panel['x']) + panel['w'] / 2
            self.assertLess(np.max(np.abs(centre - cx)), 80)                                              # on its own person
        self.assertEqual((p['top']['id'], p['bottom']['id']), (1, 2))

    def test_panels_hold_still_when_a_person_vanishes_and_never_move_too_fast(self):
        top = np.array(self.path['top']['x'])
        self.assertLess(np.ptp(top), 1.0)                                                                # held, never jumps
        m = tracking.MOTION['balanced']
        for key in ('top', 'bottom'):
            for axis, size in (('x', 'w'), ('y', 'h')):
                v = np.array(self.path[key][axis]); limit = m['speed'] * self.path[key][size] / tracking.PATH_FPS
                self.assertLessEqual(np.max(np.abs(np.diff(v))), limit + .01, (key, axis))

    def test_ffmpeg_draws_the_two_panels_at_1080x1920(self):
        with tempfile.TemporaryDirectory() as tmp:
            graph = tracking.duo_commands(self.path, Path(tmp) / 'duo.cmd', 2.0, 30)
            run = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={W}x{H}:rate=30:duration=2', '-filter_complex',
                                  f'[0:v]{graph}[o]', '-map', '[o]', '-f', 'rawvideo', '-pix_fmt', 'gray', '-frames:v', '3', '-'],
                                 capture_output=True, cwd=tmp)
            self.assertEqual(run.returncode, 0, run.stderr[-400:]); self.assertEqual(len(run.stdout), 3 * 1080 * 1920)
            still = tracking.duo_still(self.path, 1.0)
            self.assertNotIn('sendcmd', still); self.assertIn('vstack', still)

    def test_positions_are_even_and_match_the_still(self):
        at = tracking.duo_at(self.path, 1.234)
        self.assertTrue(all(v % 2 == 0 for xy in at.values() for v in xy))
        self.assertIn(f'crop@dtop={self.path["top"]["w"]}:{self.path["top"]["h"]}:{at["top"][0]}:{at["top"][1]}', tracking.duo_still(self.path, 1.234))



class DuoKnownErrors(unittest.TestCase):
    def test_E37_panels_have_even_heights_and_fill_1920(self):
        """yuv420p needs even heights: two panels of 957 px gave a 1080x1919 video."""
        self.assertEqual((tracking.DUO_PANEL_H, tracking.DUO_SEAM, tracking.DUO_PANEL_HB), (956, 6, 958))

    @unittest.expectedFailure
    def test_E36_open_active_follows_the_left_person_when_her_mouth_wins(self):
        """ABIERTO (E-36): in the TOPBOY wide shot the left person's mouth moves more in 7 of the 27 one-second windows with
        voice, but `active` never follows her. To be fixed in another phase; when it is, this test passes (an
        «unexpected success» fails the suite) and the entry is closed."""
        r = json.loads(gzip.decompress((ROOT / 'tests/bench/dos_personas_tracking.json.gz').read_bytes()))['duo-topboy']
        plan, _ = tracking.duo_plan(r); left, right = plan['left'], plan['right']; S = r['samples']; k = tracking.SAMPLE_FPS
        wins = followed = 0
        for i in range(0, len(S) - k + 1, k):
            part = [s for s in S[i:i + k] if s['speech']]
            if len(part) < k / 2: continue
            act = {p: np.mean([next((f['act'] for f in s['faces'] if f['id'] == p), 0) for s in part]) for p in (left, right)}
            if act[left] > act[right]:
                wins += 1; followed += any(s['active'] == left for s in S[i:i + k])
        self.assertGreaterEqual(wins, 5)               # the measurement of Parte A
        self.assertGreater(followed, 0)                # today 0: active never goes to her


if __name__ == '__main__':
    unittest.main()
