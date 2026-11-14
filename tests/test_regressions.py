"""Known errors that must never come back: one test per entry of docs/ERRORES_CONOCIDOS.md (E-xx in the name).

Rule: when an error is fixed, its entry is added to docs/ERRORES_CONOCIDOS.md and a test here (or named there) guards
it. test_every_known_error_has_a_guard checks that the list and the tests stay together.
"""
import ast, json, re, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class FakeYuNet:
    """Stands in for OpenCV's YuNet network only: make_detector itself stays the real one, so every consumer sees the
    real shape of its output (E-01: the tests replaced make_detector and never saw that shape change)."""
    def __init__(self, faces): self.faces = faces
    def detect(self, frame):
        if not self.faces: return 0, None
        rows = []
        for x, y, w, h in self.faces:
            # 15 values like YuNet: box, right eye, left eye, nose, mouth corners, score
            rows.append([x, y, w, h, x + .3 * w, y + .4 * h, x + .7 * w, y + .4 * h, x + .5 * w, y + .6 * h, x + .35 * w, y + .8 * h, x + .65 * w, y + .8 * h, .95])
        return 1, np.array(rows, dtype=np.float32)


def yunet(faces_for):
    """Patch: YuNet creation returns a fake network; faces_for(width, height) -> [(x, y, w, h)] in that frame size."""
    import cv2
    return patch.object(cv2, 'FaceDetectorYN', types.SimpleNamespace(create=lambda model, cfg, size, *a: FakeYuNet(faces_for(*size))))


class E01DetectorContract(unittest.TestCase):
    """E-01 (Nov 2026): a 6th value in make_detector's faces broke «Cámara + juego» for every clip."""
    def test_E01_make_detector_keeps_five_values_unless_asked(self):
        import tracking
        if not tracking.MODEL.exists(): self.skipTest('YuNet model not installed')
        with yunet(lambda w, h: [(10, 10, 40, 48)]):
            plain = tracking.make_detector(320, 180)(np.zeros((180, 320, 3), np.uint8))
            front = tracking.make_detector(320, 180, with_front=True)(np.zeros((180, 320, 3), np.uint8))
        self.assertEqual(len(plain[0]), 5); self.assertEqual(len(front[0]), 6)

    def test_E01_every_consumer_runs_with_the_real_detector_shape(self):
        import tracking, layout
        if not tracking.MODEL.exists(): self.skipTest('YuNet model not installed')
        from tests.test_cam_layout import make_stream, BOX
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'stream.mp4'; make_stream(source)
            # a face inside the camera box, scaled to whatever frame size each consumer asks for
            def faces(w, h):
                sx, sy = w / 1280, h / 720
                return [((BOX['x'] + BOX['w'] / 2 - 30) * sx, (BOX['y'] + 60) * sy, 60 * sx, 70 * sy)]
            with yunet(faces):
                overlay = layout.detect_overlay(source, 6, samples=12, prefer=True)        # whole frame + boxed + crop passes
                result = layout.analyze(source, 0, 5, overlay) if overlay.get('found') else None
                presence = layout.cam_presence(source, 0, 5, dict(found=True, width=1280, height=720, **BOX))
                tracked = tracking.analyze(source, 0, 2, lambda v: None)
        self.assertTrue(overlay['found']); self.assertIsNotNone(result); self.assertGreater(presence, 0)
        self.assertTrue(tracked['samples'] and 'front' in tracked['samples'][0]['faces'][0])


class E01NeverSilent(unittest.TestCase):
    """E-01: the crash was hidden by `except Exception: pass`; now it is recorded, kept and retried."""
    def test_E01_failed_camera_preparation_is_recorded_not_swallowed(self):
        import live, incidents
        with tempfile.TemporaryDirectory() as tmp:
            fake = types.SimpleNamespace(clip_settings=dict(framing='stack'), clips=Path(tmp), id='s1')
            moment = dict(id='m1', start=10, end=30, file_start=7)
            with patch.object(incidents, 'FILE', Path(tmp) / 'incidents.jsonl'), patch('layout.detect_overlay', side_effect=ValueError('too many values to unpack (expected 5)')):
                live.LiveSession._prepare_layout(fake, moment)
                groups = incidents.recent()
        self.assertIn('layout_error', moment)
        self.assertEqual(groups[0]['step'], 'layout'); self.assertIn('unpack', groups[0]['message'])

    def test_E01_unexpected_error_in_face_tracking_is_recorded_but_no_faces_is_not(self):
        import live, incidents, tracking
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'm1.mp4').write_bytes(b'x')
            fake = types.SimpleNamespace(clip_settings=dict(framing='zoom', tracking=True), clips=Path(tmp), id='s1')
            moment = dict(id='m1', start=10, end=30, file_start=7)
            with patch.object(incidents, 'FILE', Path(tmp) / 'incidents.jsonl'):
                with patch.object(tracking, 'analyze', side_effect=ValueError('No se detectaron rostros en este clip.')):
                    live.LiveSession._prepare_follow(fake, moment)
                self.assertEqual(incidents.recent(), [])
                with patch.object(tracking, 'analyze', side_effect=ValueError('too many values to unpack')):
                    live.LiveSession._prepare_follow(fake, moment)
                self.assertEqual(incidents.recent()[0]['step'], 'follow')

    def test_E01_no_silent_handlers_in_the_steps_that_decide_the_format(self):
        """`except Exception: pass` is forbidden in the functions that prepare how a clip looks."""
        watched = {'live.py': {'_prepare_layout', '_prepare_follow', 'refresh_layouts', '_add_moment'},
                   'app.py': {'detect_job_overlay', 'prepare_layouts', 'refresh_live_layouts', 'queue_live_layout', 'clip_thumb'}}
        for name, functions in watched.items():
            tree = ast.parse((ROOT / name).read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in functions:
                    for handler in ast.walk(node):
                        if isinstance(handler, ast.ExceptHandler) and (handler.type is None or getattr(handler.type, 'id', '') == 'Exception'):
                            silent = all(isinstance(b, ast.Pass) for b in handler.body)
                            self.assertFalse(silent, f'{name}:{node.name} line {handler.lineno} hides errors')


class E02ChosenFormatThreshold(unittest.TestCase):
    """E-02 (Nov 2026, MrStivenTc): the streamer's face in 29-33 % of the samples; at a fixed 30 % the camera was found
    or lost by chance. With «Cámara + juego» chosen, 20 % is enough."""
    def test_E02_chosen_stack_accepts_a_camera_seen_in_a_fifth_of_the_samples(self):
        src = (ROOT / 'layout.py').read_text(encoding='utf-8')
        self.assertIn("if presence < (.2 if prefer else .3)", src)


class E12ScriptNames(unittest.TestCase):
    """E-12 (Nov 2026, Kick VODs): a second top-level `const ago` in shell.js stopped the whole script: every button died."""
    def test_E12_no_duplicate_top_level_names_in_the_page_scripts(self):
        for name in ('shell.js', 'app.js'):
            seen = {}
            for n, line in enumerate((ROOT / 'static' / name).read_text(encoding='utf-8').splitlines(), 1):
                m = re.match(r'(?:async\s+)?(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)', line)
                if not m: continue
                self.assertNotIn(m.group(1), seen, f'{name}: «{m.group(1)}» declared on lines {seen.get(m.group(1))} and {n}')
                seen[m.group(1)] = n


class E19ResumedSessionGap(unittest.TestCase):
    """E-19 (Nov 2026, HotSpanish Vlogs): stopped and resumed without ever losing the signal (next_index still 0), the
    resume left no gap; the first detection proposed minute 15 whose video was deleted at the stop -> render failed."""
    def session(self, tmp):
        import live
        s = live.LiveSession(Path(tmp), 'https://kick.com/canal'); s.segments.mkdir(parents=True); s.clips.mkdir(parents=True)
        return s

    def test_E19_resuming_a_stopped_session_marks_a_gap_even_without_reconnections(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self.session(tmp); s.next_index = 0; s.media_s = 1005.1
            s._mark_restart(); s._mark_restart()                     # once per restart point
            self.assertEqual(s.gaps, [1005.1])
            self.assertGreaterEqual(s._window(1300)[0], 1005.1)       # detection never looks before the resume

    def test_E19_detection_only_looks_at_video_still_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self.session(tmp)
            for i in range(100):
                s.segment_times[i] = [i * 10.0, i * 10.0 + 10]
                if i >= 90: (s.segments / f'seg{i:06d}.ts').write_bytes(b'x')   # 0-89 were deleted
            s.media_s = 1000
            self.assertEqual(s._window(1000)[0], 900.0)

    def test_E19_a_moment_whose_video_is_gone_is_discarded_not_left_broken(self):
        import live, incidents
        with tempfile.TemporaryDirectory() as tmp, patch.object(incidents, 'FILE', Path(tmp) / 'i.jsonl'):
            s = self.session(tmp)
            s._add_moment(dict(start=930, end=955, title='Momento'))
            self.assertEqual(s.moments[0]['status'], 'discarded')

    def test_E19_a_library_clip_without_video_is_not_reported_as_a_failure(self):
        import app, incidents
        from fastapi import HTTPException
        with tempfile.TemporaryDirectory() as tmp, patch.object(incidents, 'FILE', Path(tmp) / 'i.jsonl'),              patch.object(app, 'library_preview', side_effect=HTTPException(404, 'El video de este clip no está disponible.')),              patch.object(app, '_preview_pool', types.SimpleNamespace(submit=lambda f: f())):
            app._preview_queued.discard('live:x:y'); app.library_previews_warm(app.WarmInput(ids=['live:x:y']))
            self.assertEqual(incidents.recent(), [])


class E29FontsReachLibass(unittest.TestCase):
    """E-29 (Nov 2026): montserrat.ttf kept the names «Montserrat Thin» of its variable source and libass drew every
    Montserrat subtitle in Arial; and a project copied static/fonts only on its first export, so new faces never reached it."""
    HEAD = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, '
            'PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, '
            'Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n')
    EVENT = ('[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
             'Dialogue: 0,0:00:00.00,0:00:01.00,C,,0,0,0,,Hola\n')

    def test_E29_every_offered_face_is_drawn_with_its_own_file(self):
        import subprocess, shutil, styling
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(ROOT / 'static' / 'fonts', Path(tmp) / 'fonts')
            for family, file in styling.FONTS.items():
                style = f'Style: C,{family},64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,0,2,10,10,10,1\n'
                (Path(tmp) / 'c.ass').write_text(self.HEAD + style + self.EVENT, encoding='utf-8')
                log = subprocess.run(['ffmpeg', '-v', 'verbose', '-y', '-f', 'lavfi', '-i', 'color=size=320x180:d=0.1', '-frames:v', '1',
                                      '-vf', 'ass=c.ass:fontsdir=fonts', 'o.png'], cwd=tmp, capture_output=True, text=True).stderr
                chosen = next((l.split('->')[1] for l in log.splitlines() if 'fontselect:' in l), '')
                self.assertTrue(chosen, f'{family}: no font selected')
                self.assertNotIn('Arial', chosen, f'{family} ({file}) falls back: {chosen}')

    def test_E29_an_old_project_gets_the_new_faces(self):
        import app
        with tempfile.TemporaryDirectory() as tmp:
            fonts = Path(tmp) / 'fonts'; fonts.mkdir()
            (fonts / 'montserrat.ttf').write_bytes(b'old')                                  # an old copy, different
            app.sync_fonts(fonts)
            for p in (ROOT / 'static' / 'fonts').glob('*.ttf'):
                self.assertEqual((fonts / p.name).read_bytes(), p.read_bytes(), p.name)


class RegistryTests(unittest.TestCase):
    def test_every_known_error_has_a_guard(self):
        """Each E-xx of docs/ERRORES_CONOCIDOS.md names a test that exists."""
        doc = (ROOT / 'docs' / 'ERRORES_CONOCIDOS.md').read_text(encoding='utf-8')
        entries = re.findall(r'^## (E-\d+)', doc, re.M)
        self.assertGreaterEqual(len(entries), 10)
        code = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'tests').glob('test_*.py'))
        for block in [b for b in re.split(r'^## ', doc, flags=re.M)[1:] if b.startswith('E-')]:
            ident = block.split()[0]
            guards = re.findall(r'`(test_\w+)`', block)
            self.assertTrue(guards, f'{ident} names no test')
            for g in guards: self.assertIn(f'def {g}', code, f'{ident}: {g} does not exist')


if __name__ == '__main__':
    unittest.main()
