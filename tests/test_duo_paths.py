"""«Dos personas» is drawn the same way everywhere (the lesson of E-01): the export, the library thumbnail, the library
hover preview, the library download, the live sessions and the editor's canvas all take the same two crops."""
import json, re, shutil, subprocess, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import tracking

ROOT = Path(__file__).resolve().parents[1]
W, H, START, END = 1920, 1080, 1.0, 5.0


def frame(path, t, w=180, h=320):
    """One grey frame at t seconds (t None: an image), scaled to w x h."""
    run = subprocess.run(['ffmpeg', '-v', 'error'] + ([] if t is None else ['-ss', f'{t:.3f}']) + ['-i', str(path), '-frames:v', '1', '-vf', f'scale={w}:{h}:flags=area',
                          '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True)
    assert run.returncode == 0 and len(run.stdout) == w * h, run.stderr[-300:]
    return np.frombuffer(run.stdout, np.uint8).reshape(h, w).astype(float)


def fake_tracking():
    """Two people; the one on the left walks a little to the right, so the top crop moves with time."""
    n = int((END - START) * tracking.SAMPLE_FPS); samples = []
    for k in range(n):
        lx = (.20 + .10 * k / (n - 1)) * W
        faces = [dict(id=1, x=lx - 60, y=330, w=120, h=150, act=0, front=1), dict(id=2, x=.75 * W - 60, y=360, w=120, h=150, act=0, front=1)]
        samples.append(dict(t=k / tracking.SAMPLE_FPS, speech=True, active=2, faces=faces))
    return dict(samples=samples, cuts=[], width=W, height=H, persons=[], status='ready', start=START, end=END)


class DuoEverywhereTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.app = app
        cls.tmp = tempfile.TemporaryDirectory(); data = Path(cls.tmp.name)
        cls.ident = 'd' * 32; folder = data / cls.ident; folder.mkdir()
        # a still, detailed picture: any difference between two drawings is a different crop, not motion
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=size={W}x{H}', '-frames:v', '1', str(data / 'still.png')], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-loop', '1', '-i', str(data / 'still.png'), '-t', '6', '-r', '30', '-pix_fmt', 'yuv420p',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-qp', '0', '-f', 'mp4', str(folder / 'source')], check=True)
        cache = folder / f'tracking-{tracking.key(START, END)}.json'; cache.write_text(json.dumps(fake_tracking()), encoding='utf-8')
        cls.job = dict(id=cls.ident, name='podcast.mp4', duration=6.0, fps=30, status='ready', transcript=[],
                       clips=[dict(id='c1', start=START, end=END, title='', text='')], clip_settings=dict(app.CLIP_DEFAULTS, framing='duo'))
        cls.record = dict(id=f'job:{cls.ident}:c1', project_id=cls.ident, clip_ref='c1', title='', user_title='', start=START, end=END,
                          origin='video', file=None, session_id=None, duration=END - START)
        cls.patches = [patch.object(app, 'DATA', data), patch.dict(app.JOBS, {cls.ident: cls.job}, clear=True),
                       patch.object(app.LIBRARY, 'get', lambda cid: cls.record if cid == cls.record['id'] else None)]
        for p in cls.patches: p.start()
        from fastapi.testclient import TestClient
        r = TestClient(app.app).post(f'/api/jobs/{cls.ident}/export', json=dict(start=START, end=END, title='', subtitles='', framing='duo',
                                                                                 show_subtitles=False, preview=True))
        assert r.status_code == 200, r.text[:300]
        cls.note = r.headers.get('X-Clip-Note'); cls.mp4 = data / 'export.mp4'; cls.mp4.write_bytes(r.content)
        cls.path = tracking.duo_path(fake_tracking(), tracking.duo_plan(fake_tracking())[0])

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches): p.stop()
        cls.tmp.cleanup()

    def test_the_export_is_split_with_no_note(self):
        self.assertIsNone(self.note)
        out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(self.mp4)],
                             capture_output=True, text=True).stdout.strip()
        self.assertEqual(out, '1080,1920')

    def test_the_thumbnail_shows_the_exports_crop(self):
        target = self.app.clip_thumb(self.record['id'])
        self.assertTrue(target and target.exists())
        t = max(.5, (END - START) * .35)                          # thumb_spec's moment, relative to the clip
        thumb, export = frame(target, None), frame(self.mp4, t)
        self.assertLess(np.abs(thumb - export).mean(), 6)
        # and the comparison can tell a different crop: the panels swapped is far off
        swapped = np.vstack([export[160:], export[:160]])
        self.assertGreater(np.abs(thumb - swapped).mean(), 15)

    def test_the_library_preview_follows_the_same_crops(self):
        response = self.app.library_preview(self.record['id'])
        for t in (.5, 2.0, 3.5):
            with self.subTest(t=t):
                self.assertLess(np.abs(frame(response.path, t) - frame(self.mp4, t)).mean(), 6)

    def test_the_library_download_exports_as_duo_with_subtitles_at_86(self):
        seen = {}
        with patch.object(self.app, 'export', side_effect=lambda ident, opts: seen.update(ident=ident, opts=opts) or 'ok'):
            self.app.library_export(self.record['id'], self.app.LibraryExport())
        self.assertEqual((seen['ident'], seen['opts'].framing, seen['opts'].caption_y), (self.ident, 'duo', 86))
        self.assertFalse(seen['opts'].auto_follow)

    def test_the_editors_canvas_uses_the_same_positions(self):
        """static/app.js duoAt (what the canvas draws) gives the crops of tracking.duo_at (what FFmpeg crops)."""
        js = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
        body = re.search(r'function duoAt\(P,t\)\{.*?\n\}', js, re.S).group(0)
        times = [0, .2, 1.234, 2.5, 3.99, 4.5]
        script = body + f'\nconst P={json.dumps(self.path)};console.log(JSON.stringify({json.dumps(times)}.map(t=>duoAt(P,t))));'
        run = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        for t, got in zip(times, json.loads(run.stdout)):
            want = tracking.duo_at(self.path, t)
            self.assertEqual((got['top'], got['bottom']), (list(want['top']), list(want['bottom'])), t)

    def test_the_editor_gets_the_exports_path(self):
        from fastapi.testclient import TestClient
        out = TestClient(self.app.app).post(f'/api/jobs/{self.ident}/duo/path', json=dict(start=START, end=END)).json()
        self.assertTrue(out['split']); self.assertEqual(out['path'], json.loads(json.dumps(self.path)))

    def test_live_sessions_prepare_the_tracking_for_duo(self):
        import live
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'm1.mp4').write_bytes(b'x')
            fake = types.SimpleNamespace(clip_settings=dict(framing='duo', tracking=False), clips=Path(tmp), id='s1')
            with patch.object(tracking, 'analyze', return_value=fake_tracking()) as analyze:
                live.LiveSession._prepare_follow(fake, dict(id='m1', start=10, end=14, file_start=7))
            analyze.assert_called_once()
            self.assertTrue(list(Path(tmp).glob('m1.tracking-*.json')))

    def test_a_clip_that_does_not_qualify_goes_out_with_tracking_and_says_why(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = fake_tracking()
            for s in one['samples']: s['faces'] = s['faces'][1:]
            cache = Path(tmp) / 'c.json'; cache.write_text(json.dumps(one), encoding='utf-8')
            geometry, note = self.app.duo_geometry(Path(tmp) / 'none', START, END, cache, Path(tmp) / 'x.cmd', END - START, 30)
            self.assertIn('crop@follow', geometry); self.assertIn('una persona', note); self.assertIn('seguimiento normal', note)
            geometry, note = self.app.duo_geometry(Path(tmp) / 'none', START, END, cache, Path(tmp) / 'x.cmd', END - START, 30, force=True)
            self.assertIn('crop@follow', geometry)     # forcing needs two persons: one alone is never split


class DuoSuggestion(unittest.TestCase):
    """«Este video parece un podcast de dos personas»: a suggestion (never a switch) when most checked clips qualify;
    the clip cards get each clip's reason."""
    def check(self, kinds, cached=True):
        import app
        one = fake_tracking()
        for s in one['samples']: s['faces'] = s['faces'][1:]
        with tempfile.TemporaryDirectory() as tmp:
            ident = 'e' * 32; folder = Path(tmp) / ident; folder.mkdir()
            clips = [dict(id=f'c{i}', start=float(i * 10), end=float(i * 10 + 4)) for i in range(len(kinds))]
            if cached:
                for c, k in zip(clips, kinds):
                    (folder / f'tracking-{tracking.key(c["start"], c["end"])}.json').write_text(json.dumps(fake_tracking() if k == 'duo' else one), encoding='utf-8')
            job = dict(id=ident, name='v.mp4', duration=100.0, clips=clips, clip_settings=dict(app.CLIP_DEFAULTS))
            with patch.object(app, 'DATA', Path(tmp)), patch.dict(app.JOBS, {ident: job}, clear=True), patch.object(app._duo_pool, 'submit') as submit:
                return app.duo_check(ident), submit

    def test_most_clips_of_two_people_suggest_it(self):
        out, _ = self.check(['duo', 'duo', 'duo', 'one'])
        self.assertTrue(out['suggest']); self.assertEqual((out['fit'], out['checked'], out['pending']), (3, 4, 0))
        self.assertIn('una persona', out['clips']['c3']['reason']); self.assertTrue(out['clips']['c0']['split'])

    def test_a_minority_does_not_and_missing_tracking_is_computed_in_the_background(self):
        self.assertFalse(self.check(['duo', 'one', 'one', 'one'])[0]['suggest'])
        out, submit = self.check(['duo', 'duo', 'duo'], cached=False)
        self.assertEqual(out['pending'], 3); self.assertFalse(out['suggest']); self.assertEqual(submit.call_count, 3)


class DuoNeverChosenSilently(unittest.TestCase):
    def test_a_screen_reaction_does_not_turn_duo_into_camera_and_game(self):
        import app
        overlay = dict(found=True, screen=True)
        self.assertTrue(app.reaction_stack(overlay, dict(framing='zoom')))
        self.assertFalse(app.reaction_stack(overlay, dict(framing='duo')))
        js = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("c.framing!=='fit'&&c.framing!=='duo')return 'stack'", js)

    def test_titles_sit_on_the_line_between_the_two(self):
        import app
        self.assertEqual(app.default_title_y('duo', 'balanced', None), round((tracking.DUO_PANEL_H + 3) / 19.2, 1))
        self.assertEqual(app.title_position('duo', 'balanced', None, 12, None), app.default_title_y('duo', 'balanced', None))
        self.assertIn(f"if (framing === 'duo') return {app.default_title_y('duo', 'balanced', None)};", (ROOT / 'static' / 'shell.js').read_text(encoding='utf-8'))
        self.assertEqual(app.default_title_y('duo', 'balanced', None), 49.9)


if __name__ == '__main__':
    unittest.main()
