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


GAME = "drawbox=x='mod(t*160\\,1100)':y=420:w=90:h=90:color=0x10C010:t=fill"


def camera_graph(game, box, border, person, fill='0xC01010'):
    """[0] the game; a camera box drawn over it with a person that moves inside (a real camera is never still; this
    FFmpeg's drawbox does not animate, overlay does) and its border on top. Output [v]."""
    (px, py, ax, ay, pw, ph) = person
    return (f"[0]{game},drawbox=x={box['x']}:y={box['y']}:w={box['w']}:h={box['h']}:color={fill}:t=fill[b];"
            f"color=c=0xe0a888:s={pw}x{ph}:r=30[p];[b][p]overlay=x='{px}+{ax}*sin(t*5)':y='{py}+{ay}*sin(t*4)':shortest=1,"
            f"drawbox=x={box['x']}:y={box['y']}:w={box['w']}:h={box['h']}:color=white:t={border}[v]")


def make_stream(path, seconds=6, size='1280x720', cam=True):
    inputs = ['-f', 'lavfi', '-i', f'gradients=s={size}:c0=0x1a3d5c:c1=0x5c8a3d:nb_colors=2:seed=7:speed=0.08:rate=30', '-f', 'lavfi', '-i', 'sine=f=440:sample_rate=48000']
    video = ['-filter_complex', camera_graph(GAME, BOX, 6, (1045, 105, 50, 30, 40, 50)), '-map', '[v]', '-map', '1:a'] if cam else ['-vf', GAME]
    backend.command(['ffmpeg', '-v', 'error', '-y', *inputs, *video, '-t', str(seconds), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-shortest', str(path)])


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

    def test_a_one_camera_stream_is_not_camera_plus_game(self):
        """NaimDarrechi (IRL, Nov 2026): a face always in the middle of a moving picture, no fixed edges: normal framing."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'irl.mp4'; make_stream(source, cam=False)
            with patch('tracking.make_detector', fake_detector((290, 90, 60, 80, .9))):
                o = layout.detect_overlay(source, 6, samples=16)
        self.assertFalse(o['found']); self.assertIn(o['kind'], ('single', 'none'))

    def test_no_face_means_no_overlay(self):
        with patch('tracking.make_detector', fake_detector(None)):
            self.assertFalse(layout.detect_overlay(self.source, 6, samples=8)['found'])

    def test_a_camera_filling_the_screen_is_not_an_overlay(self):
        with patch('tracking.make_detector', fake_detector((200, 40, 220, 260, .9))):
            o = layout.detect_overlay(self.source, 6, samples=8)
        self.assertFalse(o['found']); self.assertEqual(o['kind'], 'fullcam')


class BannerFaceTests(unittest.TestCase):
    """MrStivenTc (Free Fire, Nov 2026): the photo of his face on a banner under the camera was taken for the camera."""
    def test_a_face_that_never_changes_is_a_picture_not_the_camera(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'banner.mp4'
            banner = "drawbox=x='mod(t*160\\,1100)':y=200:w=90:h=90:color=0x10C010:t=fill,drawbox=x=60:y=380:w=300:h=300:color=0x2040c0:t=fill,drawbox=x=150:y=440:w=110:h=130:color=0xe0b090:t=fill"   # banner photo
            backend.command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=1280x720:c0=0x1a3d5c:c1=0x5c8a3d:nb_colors=2:seed=7:speed=0.08:rate=30',
                             '-filter_complex', camera_graph(banner, BOX, 6, (BOX['x'] + 125, BOX['y'] + 70, 45, 25, 40, 50), fill='0x553322'), '-map', '[v]', '-t', '6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)])
            banner_face = (150 / 2 + 5, 440 / 2 + 5, 45, 55, .95)                      # bigger and steadier than the real one
            cam_face = ((BOX['x'] + 120) / 2 + 2, (BOX['y'] + 60) / 2 + 2, 42, 52, .9)
            with patch('tracking.make_detector', lambda w, h: (lambda frame: [banner_face, cam_face])):
                o = layout.detect_overlay(source, 6, samples=16)
        self.assertTrue(o['found'])
        self.assertGreater(o['x'], 600, o)                                             # the camera at the top right, not the banner


class SmallCornerCameraTests(unittest.TestCase):
    """Westcol (Cuphead, Nov 2026): a small camera in the top-left corner whose two people were too small for the face
    detector on the whole frame, so the clips came out without the camera even with «Cámara + juego» chosen."""
    CORNER = dict(x=0, y=0, w=384, h=216)

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.source = Path(cls.tmp.name) / 'corner.mp4'; c = cls.CORNER
        backend.command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=1280x720:c0=0x1a3d5c:c1=0x5c8a3d:nb_colors=2:seed=7:speed=0.08:rate=30',
                         '-filter_complex', camera_graph(GAME, c, 4, (165, 60, 40, 25, 36, 44)), '-map', '[v]', '-t', '6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.source)])

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_found_by_its_edges_and_confirmed_by_a_face_inside_at_full_resolution(self):
        crop_only = lambda width, height: (lambda frame: [(420, 160, 70, 80, .9)] if width == 960 else [])   # face only in the crop
        with patch('tracking.make_detector', crop_only):
            o = layout.detect_overlay(self.source, 6, samples=16)
        self.assertTrue(o['found']); self.assertEqual(o['kind'], 'overlay')
        for k in ('x', 'y', 'w', 'h'): self.assertAlmostEqual(o[k], self.CORNER[k], delta=12, msg=k)
        self.assertEqual(o['content'], dict(x=0, y=0, w=1280, h=720))        # the game is the whole frame under the camera
        self.assertTrue(0 <= o['face']['x'] <= o['w'] and 0 <= o['face']['y'] <= o['h'])

    def test_without_any_face_only_when_the_user_chose_camera_plus_game(self):
        with patch('tracking.make_detector', fake_detector(None)):
            self.assertFalse(layout.detect_overlay(self.source, 6, samples=12)['found'])
            o = layout.detect_overlay(self.source, 6, samples=12, prefer=True)
        self.assertTrue(o['found']); self.assertAlmostEqual(o['w'], self.CORNER['w'], delta=12)

    def test_a_still_room_with_people_seen_outside_the_corner_is_not_a_camera(self):
        """NaimDarrechi in a restaurant (tripod): table and wall lines close a corner, but the people are big and outside it."""
        person = (430, 120, 70, 80, .9)                       # seen on the whole frame, outside the corner box
        with patch('tracking.make_detector', fake_detector(person)):
            self.assertFalse(layout.detect_overlay(self.source, 6, samples=12)['found'])
        big = lambda width, height: (lambda frame: [(300, 60, 260, 300, .9)] if width == 960 else [])   # huge face in the crop
        with patch('tracking.make_detector', big):
            self.assertFalse(layout.detect_overlay(self.source, 6, samples=12)['found'])

    def test_a_stream_without_a_camera_box_stays_normal_even_when_chosen(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'irl.mp4'; make_stream(source, cam=False)
            with patch('tracking.make_detector', fake_detector(None)):
                self.assertFalse(layout.detect_overlay(source, 6, samples=12, prefer=True)['found'])


class WideCameraTests(unittest.TestCase):
    def test_static_room_edges_inside_a_wide_camera_are_not_its_border(self):
        """Spreen (Minecraft, Nov 2026): the shelf behind the streamer never moves either; the old search took it
        for the camera border and cut the camera to 248 px of its 560."""
        box = dict(x=30, y=250, w=560, h=310)
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'wide.mp4'
            game = "drawbox=x='mod(t*300\\,1800)':y=700:w=120:h=120:color=0x10C010:t=fill"
            shelf = f",drawbox=x={box['x'] + 150}:y={box['y']}:w=6:h={box['h']}:color=0xe0c080:t=fill"     # the shelf edge
            graph = camera_graph(game, box, 4, (box['x'] + 410, box['y'] + 120, 50, 30, 40, 50), fill='0x3a2a1a').replace('[b];', shelf + '[b];', 1)
            graph = graph.replace('color=white:t=4[v]', 'color=0x202020:t=4[v]')
            backend.command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=1920x1080:c0=0x1a3d5c:c1=0x5c8a3d:nb_colors=2:seed=3:speed=0.2:rate=30',
                             '-filter_complex', graph, '-map', '[v]', '-t', '8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)])
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
                # E-31: the game panel is centred by default and the corner of the camera it shows is blurred (gblur that
                # fades over BLUR_FEATHER px on the inner sides): the centre of that zone keeps less than half its variance.
                blur = client.post(f'/api/jobs/{ident}/layout/path', json=dict(start=0, end=4, follow=False)).json()['game']['blur']
                self.assertIsNotNone(blur)
                f = blur['feather'] + 10; side = lambda key: f if blur['fade'][key] else 10
                y0 = int((path['top'] + path['seam']) * k)
                rows = slice(y0 + int((blur['y'] + side('t')) * k), y0 + int((blur['y'] + blur['h'] - side('b')) * k))
                cols = slice(int((blur['x'] + side('l')) * k), int((blur['x'] + blur['w'] - side('r')) * k))
                blurred = np.array(Image.open(frame).convert('L')).astype(float)[rows, cols]
                with patch('layout.camera_blur', return_value=None):
                    sharp_r = client.post(f'/api/jobs/{ident}/export', json=dict(start=0, end=4, title='', subtitles='', framing='stack', resolution=resolution))
                sharp_out = Path(tmp) / f'sharp{resolution}.mp4'; sharp_out.write_bytes(sharp_r.content); sharp_frame = Path(tmp) / f's{resolution}.png'
                backend.command(['ffmpeg', '-v', 'error', '-y', '-ss', '2', '-i', str(sharp_out), '-frames:v', '1', str(sharp_frame)])
                sharp = np.array(Image.open(sharp_frame).convert('L')).astype(float)[rows, cols]
                self.assertLess(blurred.var(), .5 * sharp.var(), (resolution, blurred.var(), sharp.var()))
            # «Seguir la acción del juego» on: the game crop keeps clear of the camera, as before.
            r = client.post(f'/api/jobs/{ident}/export', json=dict(start=0, end=4, title='', subtitles='', framing='stack', game_follow=True))
            out = Path(tmp) / 'follow.mp4'; out.write_bytes(r.content); frame = Path(tmp) / 'follow.png'
            backend.command(['ffmpeg', '-v', 'error', '-y', '-ss', '2', '-i', str(out), '-frames:v', '1', str(frame)])
            image = np.array(Image.open(frame).convert('RGB')).astype(int); game = image[path['top'] + 20:]
            self.assertLess(((game[:, :, 0] > 150) & (game[:, :, 1] < 70)).mean(), .01)   # the camera is not repeated below
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
            # «Cámara + juego» chosen: only then is the layout prepared (another format chosen is used as it is)
            s = live.LiveSession(Path(tmp) / 'live', 'https://kick.com/canal', minimum=10, maximum=30, clip_settings=dict(backend.CLIP_DEFAULTS, framing='stack'))
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


class ScreenReactionTests(unittest.TestCase):
    """A reaction on a screen capture: camera in the corner, a video player, the chat (moving text) and still UI."""
    def maps(self):
        sh, sw = 360, 640
        var = np.zeros((sh, sw), np.float32); texty = np.zeros((sh, sw), np.float32)
        var[0:108, 0:192] = 30                       # the streamer's camera (moving room)
        var[60:260, 0:440] = 1.0                     # the player: dark, mostly still...
        var[120:220, 160:300] = 25                   # ...with someone moving in it, and no text
        var[20:330, 450:590] = 20; texty[20:330, 450:590] = .9      # the chat: moving text
        texty[0:20, :] = .5; texty[280:360, :450] = .6               # browser bar, title, description, taskbar (still text)
        return var, texty

    def test_player_found_and_chat_left_out(self):
        var, texty = self.maps()
        box = layout._screen_region(var, texty, (0, 0, 192, 108))
        self.assertIsNotNone(box)
        x0, y0, x1, y1 = (v * layout.SCREEN_CELL for v in box)
        self.assertLessEqual(x1, 452)                # stops before the chat
        self.assertGreaterEqual(y0, 16); self.assertLessEqual(y1, 290)   # no browser bar, no title or taskbar

    def test_game_is_not_a_screen_capture(self):
        rng = np.random.default_rng(1)
        var = (8 + 20 * rng.random((360, 640))).astype(np.float32)          # a game: everything moves
        texty = (.2 * rng.random((360, 640))).astype(np.float32)
        self.assertIsNone(layout._screen_region(var, texty, (0, 0, 192, 108)))

    def test_camera_border_gives_the_real_width(self):
        ey = np.zeros((360, 640), np.float32); ey[107, 0:192] = .9
        self.assertEqual(layout._border_end(ey, (0, 0, 138, 106)), 192)
        self.assertIsNone(layout._border_end(ey, (0, 0, 192, 106)))      # already right: nothing to change

    def test_reaction_uses_camera_and_video_unless_turned_off(self):
        ov = dict(found=True, screen=True)
        self.assertTrue(backend.reaction_stack(ov, dict(framing='crop', auto_stack=True)))
        self.assertTrue(backend.reaction_stack(ov, dict(framing='zoom')))
        self.assertFalse(backend.reaction_stack(ov, dict(framing='crop', auto_stack=False)))
        self.assertFalse(backend.reaction_stack(dict(found=True, screen=False), dict(framing='crop', auto_stack=True)))
        self.assertFalse(backend.reaction_stack(None, dict(framing='crop')))


class FullScreenTitleTests(unittest.TestCase):
    def test_full_screen_title_sits_below_the_top_bar(self):
        self.assertEqual(backend.default_title_y('crop', 'balanced', None), backend.FULL_TITLE_Y)
        self.assertEqual(backend.title_position('crop', 'balanced', None, 12, None), backend.FULL_TITLE_Y)   # old automatic place moves
        self.assertEqual(backend.title_position('crop', 'balanced', None, 30, '1'), 30)                    # moved by hand: stays
class FollowEverywhereTests(unittest.TestCase):
    def test_saved_face_tracking_applies_outside_the_editor(self):
        on = dict(tracking=True)
        self.assertTrue(backend.wants_follow('crop', {}, on))                      # never opened: the project's setting
        self.assertTrue(backend.wants_follow('zoom', {}, on))
        self.assertFalse(backend.wants_follow('crop', {'auto_follow': False}, on)) # turned off for this clip
        self.assertTrue(backend.wants_follow('crop', {'auto_follow': True}, dict(tracking=False)))
        self.assertFalse(backend.wants_follow('stack', {}, on))                    # camera + game follows the game instead
        self.assertFalse(backend.wants_follow('fit', {}, on))

    def test_cached_tracking_is_reused_without_computing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'tracking.json'
            self.assertIsNone(backend.tracking_result(Path(tmp) / 'none.mp4', 0, 5, cache, compute=False))
            cache.write_text('{"samples": [], "width": 1920, "height": 1080}', encoding='utf-8')
            self.assertEqual(backend.tracking_result(Path(tmp) / 'none.mp4', 0, 5, cache)['width'], 1920)
