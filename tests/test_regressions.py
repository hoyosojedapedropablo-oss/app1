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
