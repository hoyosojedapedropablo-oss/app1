"""Biblioteca permanente: nothing disappears when switching streamer, restarting, opening other projects or editing."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import library


def job(ident, clips, channel=None, live=None):
    j = dict(id=ident, name=f'{ident}.mp4', duration=600, clips=[dict(id=f'c{i}', start=10.0 * i, end=10.0 * i + 30, title=f'Clip {i}', text='hola', score=70 + i) for i in range(clips)])
    if channel: j['youtube'] = dict(channel=channel)
    if live: j['live'] = live
    return j


def session(root, sid, channel, moments, url='https://kick.com/x'):
    folder = Path(root) / 'live' / sid; (folder / 'moments').mkdir(parents=True)
    state = dict(id=sid, url=url, channel=channel, created='2026-11-08T23:00:00+00:00',
                 moments=[dict(id=f'm{i}', start=100.0 + i, end=130.0 + i, duration=30, title=f'{channel} momento {i}', text='x', score=80, status='draft') for i in range(moments)])
    for m in state['moments']: (folder / 'moments' / f"{m['id']}.mp4").write_bytes(b'video')
    (folder / 'state.json').write_text(json.dumps(state), encoding='utf-8')
    return folder, state


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        (self.root / 'v1').mkdir(); (self.root / 'v1' / 'source').write_bytes(b'video'); (self.root / 'v1' / 'job.json').write_text('{}', encoding='utf-8')
        self.lib = library.Library(self.root)

    def tearDown(self):
        self.lib.db.close(); self.tmp.cleanup()

    def test_first_start_makes_a_backup_and_sync_is_additive(self):
        self.assertEqual(len(list((self.root / 'backups').glob('*.zip'))), 1)
        session(self.root, 's1', 'Spreen', 3)
        jobs = [job('v1', 2, channel='TheDonato')]
        self.assertEqual(self.lib.sync_all(jobs, self.root / 'live'), 5)
        self.assertEqual(self.lib.sync_all(jobs, self.root / 'live'), 0)          # no duplicates
        s = self.lib.summary(); self.assertEqual((s['total'], s['live'], s['video']), (5, 3, 2))
        self.assertEqual(s['channels'][0]['channel'], 'Spreen')                    # most clipped first

    def test_switching_streamer_and_restarting_keeps_every_clip(self):
        session(self.root, 's1', 'Spreen', 3); self.lib.sync_all([], self.root / 'live')
        session(self.root, 's2', 'JuanFerLaMata', 2); self.lib.sync_all([], self.root / 'live')
        self.lib.db.close(); self.lib = library.Library(self.root)                 # the app restarts
        names = sorted({c['channel'] for c in self.lib.list()})
        self.assertEqual(names, ['JuanFerLaMata', 'Spreen']); self.assertEqual(len(self.lib.list()), 5)
        self.assertEqual(len(list((self.root / 'backups').glob('*.zip'))), 1)     # backup only before the first build

    def test_user_changes_survive_a_refresh(self):
        folder, state = session(self.root, 's1', 'Spreen', 1); self.lib.sync_all([], self.root / 'live')
        cid = 'live:s1:m0'
        self.lib.update(cid, favorite=True, tags=['humor', ' top '], title='Mi título'); self.lib.mark(cid, 'edited')
        state['moments'][0]['title'] = 'Título nuevo de la IA'; (folder / 'state.json').write_text(json.dumps(state), encoding='utf-8')
        self.lib.sync_all([], self.root / 'live')
        c = self.lib.public(self.lib.get(cid))
        self.assertEqual((c['favorite'], c['tags'], c['title'], c['status']), (True, ['humor', 'top'], 'Mi título', 'edited'))
        self.lib.mark(cid, 'draft'); self.assertEqual(self.lib.get(cid)['status'], 'edited')   # status never goes back

    def test_a_clip_whose_source_disappears_stays_listed(self):
        folder, _ = session(self.root, 's1', 'Spreen', 1); self.lib.sync_all([], self.root / 'live')
        (folder / 'state.json').unlink(); (folder / 'moments' / 'm0.mp4').unlink()
        self.lib.sync_all([], self.root / 'live')
        c = self.lib.list()[0]; self.assertTrue(c['missing']); self.assertEqual(c['title'], 'Spreen momento 0')

    def test_remove_restore_and_trash_move_only_the_clips_own_files(self):
        folder, _ = session(self.root, 's1', 'Spreen', 2); self.lib.sync_all([job('v1', 1)], self.root / 'live')
        self.lib.remove('live:s1:m0')                                                # only the record
        self.assertTrue((folder / 'moments' / 'm0.mp4').exists()); self.assertEqual(len(self.lib.list()), 2)
        self.lib.restore('live:s1:m0'); self.assertEqual(len(self.lib.list()), 3)
        moved = self.lib.remove('live:s1:m1', files=True)                           # its MP4 goes to the trash
        self.assertFalse((folder / 'moments' / 'm1.mp4').exists()); self.assertTrue(Path(moved[0]['trash']).exists())
        self.lib.restore('live:s1:m1'); self.assertTrue((folder / 'moments' / 'm1.mp4').exists())
        self.lib.remove('job:v1:c0', files=True)                                    # a project video is shared: never moved
        self.assertTrue((self.root / 'v1' / 'source').exists())

    def test_old_trash_is_emptied_after_30_days_only(self):
        old = self.root / 'papelera' / '2026-09-01'; old.mkdir(parents=True); (old / 'x.mp4').write_bytes(b'v')
        new = self.root / 'papelera' / '2026-11-08'; new.mkdir(parents=True)
        os.utime(old, (0, 0))
        self.assertEqual(self.lib.empty_trash(), 1); self.assertFalse(old.exists()); self.assertTrue(new.exists())

    def test_filters_search_and_sort(self):
        session(self.root, 's1', 'Spreen', 2); self.lib.sync_all([job('v1', 3, channel='TheDonato')], self.root / 'live')
        self.assertEqual(len(self.lib.list(origin='live')), 2); self.assertEqual(len(self.lib.list(channel='TheDonato')), 3)
        self.assertEqual(len(self.lib.list(q='momento 1')), 1)
        self.lib.update('job:v1:c1', favorite=True); self.assertEqual([c['id'] for c in self.lib.list(favorite=True)], ['job:v1:c1'])
        scores = [c['score'] for c in self.lib.list(sort='score')]; self.assertEqual(scores, sorted(scores, reverse=True))


class SharedEditsTests(unittest.TestCase):
    def test_apply_to_all_clips_copies_the_look_but_keeps_each_clip_text_and_times(self):
        import app as backend
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp:
            ident = 'a' * 32; (Path(tmp) / ident).mkdir()
            j = dict(id=ident, name='v.mp4', duration=100, clips=[dict(id='c0', start=0, end=20, title='Uno', text='a'), dict(id='c1', start=30, end=55, title='Dos', text='b')],
                     clip_edits=dict(c0=dict(title='Mi título', start=1, end=21, logo='none', framing='stack', title_y=40)))
            with patch.object(backend, 'DATA', Path(tmp)), patch.dict(backend.JOBS, {ident: j}, clear=True):
                client = TestClient(backend.app)
                r = client.put(f'/api/jobs/{ident}/edits/shared', json=dict(settings=dict(logo='kick', logo_width=30, title_size=70, title_y=12, framing='zoom', start=99)))
                self.assertEqual(r.status_code, 200)
                saved = json.loads((Path(tmp) / ident / 'job.json').read_text(encoding='utf-8'))['clip_edits']
                for cid in ('c0', 'c1'): self.assertEqual((saved[cid]['logo'], saved[cid]['logo_width'], saved[cid]['title_size']), ('kick', 30, 70))
                self.assertEqual((saved['c0']['title'], saved['c0']['start'], saved['c0']['framing'], saved['c0']['title_y']), ('Mi título', 1, 'stack', 40))
                self.assertEqual((saved['c1']['title'], saved['c1']['start'], saved['c1']['end']), ('Dos', 30, 55))
                self.assertTrue(saved['c1']['partial']); self.assertNotIn('framing', saved['c1']); self.assertNotIn('partial', saved['c0'])
                self.assertEqual(client.put('/api/jobs/missing/edits/shared', json=dict(settings={})).status_code, 404)


class ApiTests(unittest.TestCase):
    def test_export_is_kept_and_recorded_but_a_preview_is_not(self):
        import app as backend
        from fastapi.testclient import TestClient
        # ignore_cleanup_errors: the background thumbnail render may still be reading the video when the test ends
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            lib = library.Library(Path(tmp))
            with patch.object(backend, 'LIBRARY', lib), patch.object(backend, 'DATA', Path(tmp)), patch.object(backend, 'LIVE_DIR', Path(tmp) / 'live'), patch.dict(backend.JOBS, {}, clear=True):
                client = TestClient(backend.app); source = Path(tmp) / 'src.mp4'
                backend.command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:size=640x360:rate=24', '-t', '3', '-c:v', 'libx264', str(source)])
                with source.open('rb') as raw: ident = client.post('/api/upload', files={'file': ('src.mp4', raw, 'video/mp4')}).json()['id']
                backend.JOBS[ident]['clips'] = [dict(id='c0', start=0, end=2, title='Clip', text='')]; lib.sync_job(backend.JOBS[ident])
                cid = f'job:{ident}:c0'
                body = dict(start=0, end=2, title='Mi clip', subtitles='', framing='zoom', clip_id='c0')
                self.assertEqual(client.post(f'/api/jobs/{ident}/export', json=dict(body, preview=True)).status_code, 200)
                self.assertEqual(lib.exports(cid), [])
                r = client.post(f'/api/jobs/{ident}/export', json=body); self.assertEqual(r.status_code, 200)
                ex = lib.exports(cid); self.assertEqual(len(ex), 1); self.assertTrue(Path(ex[0]['path']).exists())
                self.assertIn('Mi clip', Path(ex[0]['path']).name); self.assertEqual(lib.get(cid)['status'], 'exported')
                self.assertIn('Mi%20clip', r.headers['content-disposition'])          # readable download name
                # editor changes are saved with the project
                self.assertEqual(client.put(f'/api/jobs/{ident}/clips/c0/edits', json=dict(settings=dict(title='Otro', caption_y=85))).status_code, 200)
                self.assertEqual(json.loads((Path(tmp) / ident / 'job.json').read_text(encoding='utf-8'))['clip_edits']['c0']['caption_y'], 85)
                # library API
                listing = client.get('/api/library').json(); self.assertIn(cid, [c['id'] for c in listing['items']])
                self.assertTrue(client.patch(f'/api/library/{cid}', json=dict(favorite=True)).json()['favorite'])
                self.assertEqual(client.get(f'/api/library/{cid}/thumb').status_code, 200)
                self.assertTrue(client.delete(f'/api/library/{cid}').json()['removed'])
                self.assertNotIn(cid, [c['id'] for c in client.get('/api/library').json()['items']])
                self.assertEqual(client.post(f'/api/library/{cid}/restore').status_code, 200)
            lib.db.close()

    def test_opened_live_moment_shares_the_video_instead_of_copying_it(self):
        import app as backend, live
        from fastapi.testclient import TestClient
        from test_live import FakeWhisper, make_segment
        with tempfile.TemporaryDirectory() as tmp, patch.object(backend, 'DATA', Path(tmp)), patch.dict(backend.JOBS, {}, clear=True), patch.dict(backend.LIVE, {}, clear=True):
            lib = library.Library(Path(tmp))
            with patch.object(backend, 'LIBRARY', lib), patch('layout.detect_overlay', return_value=dict(found=False)):
                s = live.LiveSession(Path(tmp) / 'live', 'https://kick.com/canal', minimum=10, maximum=30); s.segments.mkdir(parents=True); s.clips.mkdir(parents=True)
                s._model = FakeWhisper(); s.channel = 'Canal'
                for i in range(3): make_segment(s.segments / f'seg{i:06d}.ts')
                for p in s._closed_segments(): s._ingest(p)
                s._add_moment({'start': 10.5, 'end': 24.5, 'title': 'Momento', 'text': 'Frase 2 uno dos', 'score': 70, 'source': 'IA local'})
                backend.LIVE[s.id] = s; mid = s.moments[0]['id']
                job = TestClient(backend.app).post(f'/api/live/{s.id}/moments/{mid}/open').json()
                self.assertTrue(os.path.samefile(s.clips / f'{mid}.mp4', Path(tmp) / job['id'] / 'source'))
            lib.db.close()


class TitlePositionTests(unittest.TestCase):
    def test_title_goes_on_the_line_of_each_format(self):
        import app as backend, layout
        panels = layout.panels(dict(x=0, y=0, w=460, h=368, width=1920, height=1080))
        self.assertAlmostEqual(backend.default_title_y('stack', 'balanced', panels), (panels['top'] + 3) / 19.2, places=1)   # camera/game line
        self.assertEqual(backend.default_title_y('zoom', 'balanced', None), 20.0)                                       # top band edge (1152 px video)
        self.assertEqual(backend.default_title_y('crop', 'balanced', None), 12)
        # a leftover camera/game position on a clip that is no longer stack moves to the band line; a hand-made one stays
        self.assertEqual(backend.title_position('zoom', 'balanced', None, 45.2), 20.0)
        self.assertEqual(backend.title_position('zoom', 'balanced', None, 70), 70)
        self.assertEqual(backend.title_position('zoom', 'close', None, 12), backend.default_title_y('zoom', 'close', None))


class ShellTests(unittest.TestCase):
    def test_page_has_the_side_menu_and_every_section(self):
        static = Path(__file__).resolve().parents[1] / 'static'
        html = (static / 'index.html').read_text(encoding='utf-8')
        for view in ('home', 'analysis', 'live', 'library', 'editor', 'projects', 'settings'):
            self.assertIn(f'data-view="{view}"', html); self.assertIn(f'id="{view}View"', html)
        self.assertIn('/static/shell.js', html); self.assertIn('/static/theme.css', html); self.assertIn('id="removeModal"', html)
        self.assertNotIn('Ã', html)                                            # no broken accents
        js = (static / 'shell.js').read_text(encoding='utf-8')
        self.assertNotIn('innerHTML = c', js); self.assertIn('textContent', js)   # stream/AI text never goes in as HTML
        for img in ('clipping-en-vivo.webp', 'kick.png', 'youtube.png'): self.assertTrue((static / 'img' / img).exists())


if __name__ == '__main__':
    unittest.main()


class TitlePositionTests(unittest.TestCase):
    def test_title_moved_by_hand_stays_and_an_automatic_one_follows_the_format(self):
        import app as backend
        with patch.object(backend, 'default_title_y', lambda framing, zoom, panels, bar=0.0: {'stack': 44.3, 'zoom': 18.8}.get(framing, 12)):
            self.assertEqual(backend.title_position('stack', 'balanced', None, 20, '1'), 20)        # by hand
            self.assertEqual(backend.title_position('stack', 'balanced', None, 20, ''), 44.3)       # automatic: on the line
            self.assertEqual(backend.title_position('stack', 'balanced', None, 20, None), 44.3)     # old edits on «Cámara + juego»
            self.assertEqual(backend.title_position('zoom', 'balanced', None, 33, None), 33)        # old edits elsewhere: kept
            self.assertEqual(backend.title_position('zoom', 'balanced', None, None, None), 18.8)


import app as backend


class TitleOnPictureEdgeTests(unittest.TestCase):
    """«Zoom» format: the automatic title sits on the edge of the picture, also when the video carries its own bar."""
    def make(self, folder, pad):
        import subprocess
        out = Path(folder) / f'v{pad}.mp4'
        vf = f'scale=1920:{1080 - 2 * pad},pad=1920:1080:0:{pad}:color=black' if pad else 'null'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=1920x1080:rate=8', '-t', '6', '-vf', vf, '-c:v', 'libx264', str(out)], check=True)
        return out
    def test_bar_inside_the_video_moves_the_title_down_to_the_picture(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bars = backend.letterbox(self.make(tmp, 34)); plain = backend.letterbox(self.make(tmp, 0))
        self.assertAlmostEqual(bars['top'], 34 / 1080, delta=.004); self.assertEqual(plain['top'], 0.0)
        self.assertEqual(backend.default_title_y('zoom', 'balanced', None, bar=bars['top']), 21.9)        # the user's mark: 22 %
        self.assertEqual(backend.default_title_y('zoom', 'balanced', None, bar=plain['top']), 20.0)
    def test_old_automatic_place_follows_and_a_hand_placed_title_stays(self):
        self.assertEqual(backend.title_position('zoom', 'balanced', None, 20.0, None, bar=.0315), 21.9)
        self.assertEqual(backend.title_position('zoom', 'balanced', None, 21.9, '', bar=.0315), 21.9)
        self.assertEqual(backend.title_position('zoom', 'balanced', None, 30, '1', bar=.0315), 30)
        self.assertEqual(backend.title_position('crop', 'balanced', None, None, None, bar=.0315), backend.FULL_TITLE_Y)
    def test_missing_file_has_no_bars(self):
        self.assertEqual(backend.letterbox(Path('no-existe.mp4')), dict(top=0.0, bottom=0.0))

