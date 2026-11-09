import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image
import app as backend
import layout

# Synthetic stream: a smooth moving background (the game, fixed blue/green colours so it is never mistaken for the red camera) and a fixed camera overlay at the top right with a 6 px border.
BOX = dict(x=900, y=20, w=340, h=260)


def make_stream(path, seconds=6, size='1280x720', cam=True):
    draw = (f",drawbox=x={BOX['x']}:y={BOX['y']}:w={BOX['w']}:h={BOX['h']}:color=0xC01010:t=fill"
            f",drawbox=x={BOX['x']}:y={BOX['y']}:w={BOX['w']}:h={BOX['h']}:color=white:t=6") if cam else ''
    backend.command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s={size}:c0=0x1a3d5c:c1=0x5c8a3d:nb_colors=2:seed=7:speed=0.08:rate=30', '-f', 'lavfi', '-i', 'sine=f=440:sample_rate=48000',
                     '-vf', f"drawbox=x='mod(t*160\\,1100)':y=420:w=90:h=90:color=0x10C010:t=fill{draw}", '-t', str(seconds), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-shortest', str(path)])


def fake_detector(face):
    """YuNet stand-in: one face, in 640-wide sample coordinates."""
    return lambda width, height: (lambda frame: [face] if face else [])


CAM_FACE = ((BOX['x'] + BOX['w'] / 2) / 2 - 30, (BOX['y'] + BOX['h'] * .45) / 2 - 35, 60, 70, .9)


class DetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.source = Path(cls.tmp.name) / 'stream.mp4'; make_stream(cls.source)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_overlay_rectangle_comes_from_the_border_that_never_moves(self):
        with patch('tracking.make_detector', fake_detector(CAM_FACE)):
            o = layout.detect_overlay(self.source, 6, samples=16)
        self.assertTrue(o['found']); self.assertEqual(o['kind'], 'overlay')
        for k in ('x', 'y', 'w', 'h'): self.assertAlmostEqual(o[k], BOX[k], delta=10, msg=k)
        self.assertTrue(all(o[k] % 2 == 0 for k in ('x', 'y', 'w', 'h')))

    def test_clip_without_the_streamer_in_the_camera_is_flagged(self):
        o = dict(found=True, width=1280, height=720, **BOX)
        with patch('tracking.make_detector', fake_detector(CAM_FACE)):
            self.assertEqual(layout.cam_presence(self.source, 0, 5, o), 1)
        with patch('tracking.make_detector', fake_detector((40, 200, 60, 70, .9))):     # a face, but in the game
            self.assertEqual(layout.cam_presence(self.source, 0, 5, o), 0)

    def test_no_face_means_no_overlay(self):
        with patch('tracking.make_detector', fake_detector(None)):
            self.assertFalse(layout.detect_overlay(self.source, 6, samples=8)['found'])

    def test_a_camera_filling_the_screen_is_not_an_overlay(self):
        with patch('tracking.make_detector', fake_detector((200, 40, 220, 260, .9))):
            o = layout.detect_overlay(self.source, 6, samples=8)
        self.assertFalse(o['found']); self.assertEqual(o['kind'], 'fullcam')


class WideCameraTests(unittest.TestCase):
    def test_static_room_edges_inside_a_wide_camera_are_not_its_border(self):
        """Spreen (Minecraft, Nov 2026): the shelf behind the streamer never moves either; the old search took it
        for the camera border and cut the camera to 248 px of its 560."""
        box = dict(x=30, y=250, w=560, h=310)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'wide.mp4'
            room = (f"drawbox=x={box['x']}:y={box['y']}:w={box['w']}:h={box['h']}:color=0x3a2a1a:t=fill,"
                    f"drawbox=x={box['x'] + 150}:y={box['y']}:w=6:h={box['h']}:color=0xe0c080:t=fill,"     # the shelf edge
                    f"drawbox=x={box['x']}:y={box['y']}:w={box['w']}:h={box['h']}:color=0x202020:t=4")
            backend.command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=1920x1080:c0=0x1a3d5c:c1=0x5c8a3d:nb_colors=2:seed=3:speed=0.2:rate=30',
                             '-vf', "drawbox=x='mod(t*300\,1800)':y=700:w=120:h=120:color=0x10C010:t=fill," + room, '-t', '8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)])
            face = ((box['x'] + 430) / 3 - 15, (box['y'] + 140) / 3 - 18, 30, 36, .9)      # on the right, 4.8 face widths from the left border (Spreen: 4.7)
            with patch('tracking.make_detector', fake_detector(face)):
                o = layout.detect_overlay(source, 8, samples=16)
        self.assertTrue(o['found'])
        for k in ('x', 'y', 'w', 'h'): self.assertAlmostEqual(o[k], box[k], delta=16, msg=(k, o))


class GeometryTests(unittest.TestCase):
    def overlay(self, x, y, w, h, W=1920, H=1080):
        return dict(found=True, width=W, height=H, x=x, y=y, w=w, h=h, face=dict(x=x + w / 2, y=y + h * .45, w=w / 4, h=h / 3))

    def test_camera_panel_takes_40_to_50_percent_and_keeps_its_shape(self):
        wide = layout.panels(self.overlay(1444, 12, 460, 368))           # TheDonato: 1.25:1
        self.assertEqual(wide['top'], 864); self.assertEqual(wide['cam'], dict(x=1444, y=12, w=460, h=368))
        square = layout.panels(self.overlay(20, 12, 300, 300))           # square camera: panel 50 %, top/bottom trimmed
        self.assertEqual(square['top'], 960); self.assertEqual(square['cam']['w'], 300)
        self.assertAlmostEqual(square['cam']['w'] / square['cam']['h'], 1080 / 960, delta=.02)
        flat = layout.panels(self.overlay(0, 0, 640, 240))               # very wide camera: panel 40 %, sides trimmed
        self.assertEqual(flat['top'], 768); self.assertAlmostEqual(flat['cam']['w'] / flat['cam']['h'], 1080 / 768, delta=.02)
        for p in (wide, square, flat): self.assertEqual(p['top'] + layout.SEAM + p['bottom'], 1920)

    def test_game_crop_never_shows_the_camera_again_and_moves_smoothly(self):
        o = self.overlay(1444, 12, 460, 368)
        xs = [400.0] * 20 + [1500.0] * 40                                   # action jumps to the right side (under the camera)
        result = dict(overlay=o, panels=layout.panels(o), motion=dict(xs=xs))
        path = layout.game_path(result, 'balanced')
        left = np.array(path['left']); window = path['window']
        self.assertLessEqual(left.max() + window, 1444 + .5)               # right edge of the game crop stays left of the camera
        step = np.abs(np.diff(left)).max() * layout.PATH_FPS
        self.assertLessEqual(step, layout.MOTION['balanced']['speed'] * window * 1.02)
        still = layout.game_path(result, 'balanced', follow=False)
        self.assertTrue(still['static'])

    def test_motion_modes_differ_in_speed(self):
        o = self.overlay(20, 12, 300, 300)
        result = dict(overlay=o, panels=layout.panels(o), motion=dict(xs=[500.0] * 12 + [1800.0] * 60))
        speed = {m: np.abs(np.diff(layout.game_path(result, m)['left'])).max() for m in ('smooth', 'balanced', 'fast')}
        self.assertLess(speed['smooth'], speed['balanced']); self.assertLess(speed['balanced'], speed['fast'])


class ExportTests(unittest.TestCase):
    def test_stacked_export_puts_the_camera_on_top_and_the_game_below(self):
        client = TestClient(backend.app)
        with tempfile.TemporaryDirectory() as tmp, patch('tracking.make_detector', fake_detector(CAM_FACE)):
            source = Path(tmp) / 'stream.mp4'; make_stream(source)
            with source.open('rb') as raw: ident = client.post('/api/upload', files={'file': ('stream.mp4', raw, 'video/mp4')}).json()['id']
            state = client.post(f'/api/jobs/{ident}/overlay').json()
            for _ in range(100):
                if state.get('status') in ('ready', 'error'): break
                import time; time.sleep(.2); state = client.get(f'/api/jobs/{ident}/overlay').json()
            self.assertTrue(state['found'], state)
            path = client.post(f'/api/jobs/{ident}/layout/path', json=dict(start=0, end=4)).json()
            self.assertTrue(path['found']); self.assertEqual(path['top'] + path['seam'] + path['bottom'], 1920)
            for resolution, size in ((1080, (1080, 1920)), (1440, (1440, 2560))):
                r = client.post(f'/api/jobs/{ident}/export', json=dict(start=0, end=4, title='', subtitles='', framing='stack', resolution=resolution))
                self.assertEqual(r.status_code, 200, r.text[:300])
                out = Path(tmp) / f'out{resolution}.mp4'; out.write_bytes(r.content); frame = Path(tmp) / f'f{resolution}.png'
                backend.command(['ffmpeg', '-v', 'error', '-y', '-ss', '2', '-i', str(out), '-frames:v', '1', str(frame)])
                image = np.array(Image.open(frame).convert('RGB')).astype(int)
                self.assertEqual(image.shape[1::-1], size)
                k = size[0] / 1080; top = int(path['top'] * k)
                cam = image[int(40 * k):top - int(40 * k), int(60 * k):-int(60 * k)]
                red = (cam[:, :, 0] > 150) & (cam[:, :, 1] < 70)
                self.assertGreater(red.mean(), .9)                              # the camera fills the top panel
                game = image[top + int(20 * k):]
                self.assertLess(((game[:, :, 0] > 150) & (game[:, :, 1] < 70)).mean(), .01)   # and is not repeated below
            # A manual rectangle replaces the detected one and the layout follows it.
            fixed = client.put(f'/api/jobs/{ident}/overlay', json=dict(x=880, y=10, w=380, h=290)).json()
            self.assertTrue(fixed['manual']); self.assertEqual((fixed['x'], fixed['w']), (880, 380))
            self.assertEqual(client.post(f'/api/jobs/{ident}/layout/path', json=dict(start=0, end=4)).json()['cam']['x'], 880)
            self.assertEqual(client.put(f'/api/jobs/{ident}/overlay', json=dict(x=1200, y=10, w=380, h=290)).status_code, 400)

    def test_old_automatic_detections_are_redone_but_manual_ones_are_kept(self):
        import json
        with tempfile.TemporaryDirectory() as tmp, patch.object(backend, 'DATA', Path(tmp)):
            (Path(tmp) / 'job').mkdir()
            backend.write_overlay('job', dict(found=True, x=1, y=1, w=50, h=50))                 # saved by detector 1
            self.assertIsNone(backend.read_overlay('job'))
            backend.write_overlay('job', dict(found=True, manual=True, x=1, y=1, w=50, h=50))
            self.assertEqual(backend.read_overlay('job')['w'], 50)
            backend.write_overlay('job', dict(found=True, detector=layout.DETECTOR_VERSION, x=2, y=2, w=60, h=60))
            self.assertEqual(backend.read_overlay('job')['w'], 60)

    def test_stack_without_a_camera_explains_what_to_do(self):
        client = TestClient(backend.app)
        with tempfile.TemporaryDirectory() as tmp, patch('tracking.make_detector', fake_detector(None)):
            source = Path(tmp) / 'plain.mp4'; make_stream(source, seconds=3, cam=False)
            with source.open('rb') as raw: ident = client.post('/api/upload', files={'file': ('plain.mp4', raw, 'video/mp4')}).json()['id']
            r = client.post(f'/api/jobs/{ident}/export', json=dict(start=0, end=2, title='', subtitles='', framing='stack'))
            self.assertEqual(r.status_code, 400); self.assertIn('cámara', r.json()['detail'])
            self.assertFalse(client.post(f'/api/jobs/{ident}/layout/path', json=dict(start=0, end=2)).json()['found'])

    def test_project_settings_accept_the_new_options_and_old_projects_keep_theirs(self):
        self.assertEqual(backend.ClipSettings(framing='stack', resolution=1440).framing, 'stack')
        self.assertTrue(backend.CLIP_DEFAULTS['auto_stack']); self.assertFalse(backend.LEGACY_CLIP_SETTINGS['auto_stack'])
        self.assertEqual(backend.clip_settings({})['framing'], 'crop')


class ReadyOnOpenTests(unittest.TestCase):
    """Clips must open already in «Cámara + juego»: nothing is computed when the user opens them."""
    OVERLAY = dict(found=True, kind='overlay', detector=layout.DETECTOR_VERSION, width=1280, height=720, presence=1, content=dict(x=0, y=0, w=1280, h=720), **BOX)

    def fake_analyze(self, calls):
        def analyze(source, start, end, overlay, progress=lambda v: None):
            calls.append((round(start, 3), round(end, 3)))
            return dict(version=layout.VERSION, start=start, end=end, overlay=overlay, panels=layout.panels(overlay), cam_presence=1, motion=dict(xs=[640.0] * 8))
        return analyze

    def test_analysis_prepares_every_clip_before_it_is_opened(self):
        client = TestClient(backend.app); calls = []
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'stream.mp4'; make_stream(source, seconds=4)
            with source.open('rb') as raw: ident = client.post('/api/upload', files={'file': ('stream.mp4', raw, 'video/mp4')}).json()['id']
        job = backend.JOBS[ident]; job['clips'] = [dict(start=0.0, end=2.0), dict(start=1.0, end=3.5)]
        backend.write_overlay(ident, self.OVERLAY)
        with patch('layout.analyze', self.fake_analyze(calls)):
            backend.prepare_layouts(ident)
            self.assertEqual(calls, [(0.0, 2.0), (1.0, 3.5)]); self.assertEqual(job['layout_ready'], 2)
            path = client.post(f'/api/jobs/{ident}/layout/path', json=dict(start=1.0, end=3.5)).json()
        self.assertTrue(path['found']); self.assertEqual(len(calls), 2)          # opening the clip computed nothing new

    def test_live_moment_opens_with_its_layout_already_prepared(self):
        import sys, live
        sys.path.insert(0, str(Path(__file__).parent))
        from test_live import FakeWhisper, make_segment
        calls = []
        with tempfile.TemporaryDirectory() as tmp, patch.object(backend, 'DATA', Path(tmp)), patch.dict(backend.JOBS, {}, clear=True), patch.dict(backend.LIVE, {}, clear=True):
            s = live.LiveSession(Path(tmp) / 'live', 'https://kick.com/canal', minimum=10, maximum=30, clip_settings=dict(backend.CLIP_DEFAULTS))
            s.segments.mkdir(parents=True); s.clips.mkdir(parents=True); s._model = FakeWhisper()
            for i in range(3): make_segment(s.segments / f'seg{i:06d}.ts')
            for p in s._closed_segments(): s._ingest(p)
            with patch('layout.detect_overlay', return_value=dict(self.OVERLAY)), patch('layout.analyze', self.fake_analyze(calls)):
                s._add_moment({'start': 10.5, 'end': 24.5, 'title': 'Momento', 'text': 'Frase 2 uno dos', 'score': 70, 'source': 'IA local'})
            mid = s.moments[0]['id']
            self.assertEqual(s.moments[0]['status'], 'draft'); self.assertTrue((s.clips / f'{mid}.layout.json').exists()); self.assertEqual(len(calls), 1)
            backend.LIVE[s.id] = s; client = TestClient(backend.app)
            job = client.post(f'/api/live/{s.id}/moments/{mid}/open').json(); clip = job['clips'][0]
            self.assertTrue(backend.read_overlay(job['id'])['found'])
            with patch('layout.analyze', side_effect=AssertionError('computed again on open')):
                path = client.post(f'/api/jobs/{job["id"]}/layout/path', json=dict(start=clip['start'], end=clip['end'])).json()
            self.assertTrue(path['found'])


class QualityTests(unittest.TestCase):
    def test_gpu_export_uses_more_bitrate_than_before(self):
        args = backend.GPU_VIDEO
        self.assertEqual(args[args.index('-cq') + 1], '23'); self.assertIn('-temporal-aq', args)


if __name__ == '__main__':
    unittest.main()
