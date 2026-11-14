"""«Cámara + juego» in a live session uses the camera the session agrees on, and the game panel is centred (E-31).
Measured on Epidemic77 (31 moments): 3 moments found no camera and came out with black bands although «Cámara + juego»
was chosen; 8 had another box (one 450 px tall instead of 376: a strip of game and two dividing lines in the top panel);
and the game panel was moved aside, leaving the character at its edge."""
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import layout, live

CAM = dict(found=True, kind='overlay', detector=6, width=1920, height=1080, x=28, y=24, w=516, h=376,
           face=dict(x=280, y=200, w=120, h=160), screen=False)


def box(**over): return {**CAM, **over}


class ConsensusTests(unittest.TestCase):
    def test_E31_the_box_most_moments_agree_on_wins(self):
        seen = [box(), box(w=520), box(), box(x=24, w=486, h=450, content=dict(x=714, y=0, w=1206, h=1080)),
                box(x=136, w=412), dict(found=False), box(h=378), box()]
        agreed = layout.consensus_camera(seen)
        self.assertEqual((agreed['x'], agreed['y'], agreed['w'], agreed['h']), (28, 24, 516, 376))
        self.assertTrue(agreed['consensus']); self.assertNotIn('content', agreed)        # a stray sidebar is ignored

    def test_no_consensus_with_too_few_or_scattered_moments(self):
        self.assertIsNone(layout.consensus_camera([box(), box()]))
        self.assertIsNone(layout.consensus_camera([box(), box(x=900), box(x=1400, y=600), dict(found=False)]))

    def test_E31_the_camera_a_centred_game_panel_shows_is_blurred(self):
        o = box(); result = dict(overlay=o, panels=layout.panels(o), motion=dict(xs=[960.0] * 40))
        with tempfile.TemporaryDirectory() as tmp:
            still = layout.filter_graph(result, Path(tmp) / 'p.cmd', 1, 25, follow=False)
            moving = layout.filter_graph(result, Path(tmp) / 'p.cmd', 1, 25, follow=True)
        self.assertIn('gblur', still); self.assertIn('alphamerge', still); self.assertNotIn('gblur', moving)
        blur = layout.preview_path(result, follow=False)['game']['blur']
        self.assertTrue(blur and blur['x'] == 0 and blur['w'] > 8)                      # the camera is on the left
        self.assertIsNone(layout.preview_path(result, follow=True)['game']['blur'])

    def test_E31_the_blur_fades_into_the_game_without_a_cut(self):
        """Just inside the blurred zone's inner edge the game keeps most of its detail (the mask fades from 0), so there is
        no rectangle: measured 0.75 of the detail just outside with the 24 px fade, 0.06 with a hard edge."""
        import subprocess
        import numpy as np
        from PIL import Image
        lap = lambda z: np.abs(z[1:-1, 1:-1] * 4 - z[:-2, 1:-1] - z[2:, 1:-1] - z[1:-1, :-2] - z[1:-1, 2:]).mean()
        o = box(); result = dict(overlay=o, panels=layout.panels(o), motion=dict(xs=[960.0] * 40))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            "nullsrc=size=1920x1080:rate=25,geq=lum='128+90*sin(X/7)*cos(Y/5)+30*random(1)':cb=128:cr=128", '-t', '0.2',
                            '-vf', 'drawbox=x=28:y=24:w=516:h=376:color=0xC01010:t=fill', '-c:v', 'libx264', '-crf', '8', 'src.mp4'], cwd=tmp, check=True)
            graph = layout.filter_graph(result, tmp / 'p.cmd', .2, 25, follow=False)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', 'src.mp4', '-frames:v', '1', '-filter_complex', f'[0:v]{graph}[o]', '-map', '[o]', 'f.png'],
                           cwd=tmp, check=True)
            a = np.asarray(Image.open(tmp / 'f.png').convert('L')).astype(float)
        b = layout.preview_path(result, follow=False)['game']['blur']; y0 = result['panels']['top'] + layout.SEAM
        self.assertTrue(b['fade']['r']); self.assertFalse(b['fade']['l'])               # the camera is on the panel's left edge
        x1 = b['x'] + b['w']; rows = slice(y0 + b['y'] + 30, y0 + b['y'] + b['h'] - 40)
        self.assertGreater(lap(a[rows, x1 - 9: x1 - 1]) / lap(a[rows, x1 + 1: x1 + 9]), .5)
        centre = a[y0 + b['y'] + 10: y0 + b['y'] + b['h'] - b['feather'] - 10, b['x'] + 10: x1 - b['feather'] - 10]
        self.assertLess(lap(centre), .2 * lap(a[rows, x1 + 1: x1 + 9]))                    # the camera itself is well blurred

    def test_E31_the_game_panel_is_centred_unless_following_the_action(self):
        o = box(); result = dict(overlay=o, panels=layout.panels(o), motion=dict(xs=[1500.0] * 40))
        still = layout.game_path(result, 'balanced', follow=False)
        self.assertAlmostEqual(still['left'][0] + still['window'] / 2, 960, delta=1)   # the character in the middle
        moving = layout.game_path(result, 'balanced', follow=True)
        self.assertGreater(moving['left'][-1], still['left'][-1])                       # following still follows


class SessionTests(unittest.TestCase):
    def session(self, tmp, n=4):
        s = live.LiveSession(Path(tmp), 'https://kick.com/epidemic77', minimum=10, maximum=60, buffer_minutes=10)
        s.clips.mkdir(parents=True); s.clip_settings = {'framing': 'stack', 'auto_stack': True}
        s.moments = [dict(id=f'm{i}', start=10. * i + 5, end=10. * i + 15, file_start=10. * i + 2, status='draft') for i in range(n)]
        for m in s.moments[:-1]:
            (s.clips / f"{m['id']}.layout.json").write_text(json.dumps(dict(overlay=box())), encoding='utf-8')
        return s

    def prepare(self, s, detected, presence=1.0):
        def analyze(source, start, end, overlay, progress=None):
            return dict(overlay=overlay, panels=layout.panels(overlay) if overlay.get('found') else None,
                        cam_presence=presence if overlay.get('found') else None)
        with patch('layout.detect_overlay', return_value=detected), patch('layout.analyze', side_effect=analyze):
            s._prepare_layout(s.moments[-1])
        return json.loads((s.clips / f"{s.moments[-1]['id']}.layout.json").read_text(encoding='utf-8'))['overlay']

    def test_E31_a_moment_that_missed_the_camera_uses_the_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self.session(tmp); s.moments[-1]['layout_note'] = 'No se vio la cámara…'       # from an earlier miss
            ov = self.prepare(s, dict(found=False, kind='none', width=1920, height=1080))
            self.assertTrue(ov['found']); self.assertTrue(ov['consensus']); self.assertEqual(ov['h'], 376)
            self.assertNotIn('layout_note', s.moments[-1])

    def test_E31_a_wrong_box_is_replaced_by_the_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov = self.prepare(self.session(tmp), box(x=24, w=486, h=450))
            self.assertEqual((ov['x'], ov['w'], ov['h']), (28, 516, 376)); self.assertEqual(ov['detected']['h'], 450)

    def test_E31_nobody_in_the_sessions_camera_means_no_camera(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self.session(tmp)
            ov = self.prepare(s, dict(found=False, kind='none', width=1920, height=1080), presence=0.0)
            self.assertFalse(ov['found']); self.assertIn('layout_note', s.moments[-1])

    def test_E31_saved_moments_with_a_wrong_box_are_prepared_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self.session(tmp, n=5)
            for m in s.moments: (s.clips / f"{m['id']}.mp4").write_bytes(b'x')
            (s.clips / 'm3.layout.json').write_text(json.dumps(dict(overlay=box(h=450, x=24, w=486, detector=layout.DETECTOR_VERSION))), encoding='utf-8')
            (s.clips / 'm4.layout.json').write_text(json.dumps(dict(overlay=box(detector=layout.DETECTOR_VERSION))), encoding='utf-8')
            done = []
            with patch.object(s, '_prepare_layout', side_effect=lambda m: done.append(m['id'])):
                s.refresh_layouts()
            self.assertEqual(done, ['m3'])


class OpenedProjectTests(unittest.TestCase):
    def test_E31_an_opened_project_takes_the_sessions_camera_unless_marked_by_hand(self):
        import app
        with tempfile.TemporaryDirectory() as tmp:
            s = SessionTests.session(SessionTests(), tmp, n=5)
            for m in s.moments: (s.clips / f"{m['id']}.layout.json").write_text(json.dumps(dict(overlay=box())), encoding='utf-8')
            ident = 'b' * 32; folder = Path(tmp) / 'data' / ident; folder.mkdir(parents=True)
            job = dict(id=ident, live={'session': s.id, 'moment': 'm4'})
            with patch.object(app, 'DATA', Path(tmp) / 'data'), patch.dict(app.JOBS, {ident: job}), patch.dict(app.LIVE, {s.id: s}):
                app._session_cams.clear()
                app.write_overlay(ident, box(x=24, w=486, h=450, status='ready', manual=False))
                ov = app.read_overlay(ident)
                self.assertEqual((ov['x'], ov['w'], ov['h']), (28, 516, 376)); self.assertEqual(ov['detected']['h'], 450)
                self.assertEqual(json.loads(app.overlay_file(ident).read_text(encoding='utf-8'))['h'], 376)        # saved
                app.write_overlay(ident, box(x=24, w=486, h=450, status='ready', manual=True))
                self.assertEqual(app.read_overlay(ident)['h'], 450)                                               # by hand: kept


class ExportDefaultTests(unittest.TestCase):
    def test_E31_exports_centre_the_game_by_default(self):
        import app
        self.assertFalse(app.Export(title='', subtitles='', start=0, end=5).game_follow)


if __name__ == '__main__':
    unittest.main()
