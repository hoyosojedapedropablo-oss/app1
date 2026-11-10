"""Streamers: follow from live sessions, live status, search, photos; all through public data with a fake yt-dlp."""
import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
import streamers

CHANNELS = {
    'spreen': dict(user=dict(username='Spreen', profile_pic='https://files.kick.com/spreen.jpg'), followers_count=2000000,
                   livestream=dict(session_title='MI MUNDO HARDCORE', viewer_count=12000, thumbnail=dict(url='https://images.kick.com/t.jpg'))),
    'juanferlamata': dict(user=dict(username='JuanFerLaMata', profile_pic=''), followers_count=900000, livestream=None),
}


class FakeIE:
    calls = []
    def _call_api(self, path, slug, note=''):
        FakeIE.calls.append(slug)
        if slug not in CHANNELS: raise RuntimeError('404')
        return CHANNELS[slug]


class FakeYDL:
    def __init__(self, options): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get_info_extractor(self, name): return FakeIE()
    def extract_info(self, url, **kw):
        if url.endswith('/live'): raise RuntimeError('The channel is not currently live')
        if '@thedonato' in url: return dict(channel='TheDonato', thumbnails=[dict(id='avatar_uncropped', url='https://yt3/avatar.jpg')])
        raise RuntimeError('no channel')
    def urlopen(self, url):
        class R:
            def read(self, n): return b'\xff\xd8\xff\xe0fakejpeg'
        return R()


class StreamerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.s = streamers.Streamers(self.tmp.name, ydl_factory=FakeYDL); FakeIE.calls = []

    def tearDown(self): self.tmp.cleanup()

    def test_streamers_clipped_live_are_followed_with_their_clip_counts(self):
        self.s.sync_from([dict(url='https://kick.com/Spreen', channel='Spreen'), dict(url='https://kick.com/juanferlamata', channel='JuanFerLaMata')], {'spreen': 91, 'juanferlamata': 102})
        self.s.check_all()
        listing = self.s.listing()
        self.assertEqual([v['name'] for v in listing], ['Spreen', 'JuanFerLaMata'])             # live first, then most clipped
        self.assertTrue(listing[0]['live']); self.assertEqual(listing[0]['viewers'], 12000); self.assertEqual(listing[1]['clips'], 102)
        self.assertTrue(listing[0]['avatar']); self.assertFalse(listing[1]['avatar'])           # photo cached only when there is one

    def test_live_status_is_cached_for_five_minutes(self):
        key = self.s.follow('https://kick.com/spreen'); self.s.refresh(key); self.s.refresh(key)
        self.assertEqual(FakeIE.calls.count('spreen'), 1)
        self.s.items[key]['checked'] = time.time() - streamers.LIVE_TTL - 1; self.s.refresh(key)
        self.assertEqual(FakeIE.calls.count('spreen'), 2)

    def test_search_finds_known_streamers_and_new_ones_on_kick_and_youtube(self):
        self.s.follow('https://kick.com/juanferlamata', name='JuanFerLaMata')
        names = [r['name'] for r in self.s.search('juan')]; self.assertIn('JuanFerLaMata', names)
        found = self.s.search('spreen'); self.assertEqual(found[0]['name'], 'Spreen'); self.assertTrue(found[0]['new']); self.assertTrue(found[0]['live'])
        yt = self.s.search('thedonato'); self.assertEqual([(r['platform'], r['name']) for r in yt], [('youtube', 'TheDonato')])
        self.assertEqual(self.s.search('nadieexiste'), [])

    def test_a_channel_that_does_not_answer_is_not_live_and_nothing_breaks(self):
        key = self.s.follow('https://kick.com/desconocido'); item = self.s.refresh(key)
        self.assertFalse(item['live']); self.assertTrue(item['error'])

    def test_links_from_other_sites_are_refused(self):
        with self.assertRaises(ValueError): self.s.follow('https://twitch.tv/alguien')
        self.assertEqual(streamers.slug_from_url('https://www.youtube.com/@TheDonato/live'), ('youtube', '@thedonato'))

    def test_followed_streamers_survive_a_restart(self):
        self.s.follow('https://kick.com/spreen', clips=5)
        again = streamers.Streamers(self.tmp.name, ydl_factory=FakeYDL)
        self.assertIn('kick:spreen', again.items)


class FeaturedTests(unittest.TestCase):
    def test_featured_kick_streamers_appear_only_while_live_and_not_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=FakeYDL); FakeIE.calls = []
            s.check_featured([('spreen', 'es'), ('westcol', 'es')])          # westcol does not answer in the fake API
            rows = s.featured_listing()
            self.assertEqual([r['name'] for r in rows], ['Spreen'])
            self.assertEqual(rows[0]['lang'], 'es'); self.assertNotIn('playback', rows[0])
            self.assertTrue(rows[0]['avatar'])
            s.check_featured([('spreen', 'es')]); self.assertEqual(FakeIE.calls, ['spreen', 'westcol'])   # cached 5 minutes
            self.assertEqual(len(streamers.Streamers(tmp, ydl_factory=FakeYDL).featured_listing()), 1)      # survives a restart
            s.follow('https://kick.com/spreen')                                # already one of the user's: shown once, above
            self.assertEqual(s.featured_listing(), [])

    def test_follow_and_unfollow_keep_the_saved_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=FakeYDL)
            key = s.follow('https://kick.com/spreen', explicit=True); s.set_prefs('https://kick.com/spreen', dict(language='es'))
            self.assertTrue(s.items[key]['followed']); self.assertEqual([v['key'] for v in s.listing()], [key])
            self.assertTrue(s.unfollow(key)); self.assertEqual(s.listing(), [])
            s.sync_from([dict(url='https://kick.com/spreen', channel='Spreen')], {})            # a later live session does not bring it back
            self.assertEqual(s.listing(), []); self.assertEqual(s.get_prefs('https://kick.com/spreen')['language'], 'es')
            FakeIE.calls = []; s.check_all(); self.assertNotIn('spreen', FakeIE.calls)                            # no longer checked
            s.follow('https://kick.com/spreen', explicit=True); self.assertEqual(len(s.listing()), 1)
            self.assertFalse(s.unfollow('kick:nobody'))

    def test_recommended_offline_channels_can_be_listed_to_follow(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=FakeYDL)
            s.check_featured([('juanferlamata', 'es')])
            s.featured['kick:westcol'] = dict(platform='kick', slug='westcol', name='Westcol', live=False, checked=time.time())
            self.assertEqual(s.featured_listing(), [])
            self.assertEqual([r['name'] for r in s.featured_listing(include_offline=True)], ['Westcol'])   # only channels of the list

    def test_the_featured_list_is_real_kick_channels_spanish_first(self):
        slugs = [x for x, _ in streamers.FEATURED_KICK]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertEqual(streamers.FEATURED_KICK[0], ('westcol', 'es'))


class SearchScopeTests(unittest.TestCase):
    def test_kick_suggestions_link_and_local_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=FakeYDL); s.follow('https://kick.com/juanferlamata', clips=102, name='JuanFerLaMata')
            fake = dict(channels=[dict(slug='spreen', isLive=True, followersCount=2000000, user=dict(username='Spreen', profilePic='https://p/s.jpg')),
                                  dict(slug='elspreendmc', isLive=False, followersCount=21000, user=dict(username='ElSpreenDMC'))])
            with patch.object(streamers.Streamers, '_json', return_value=fake):
                kick = s.search_scope('spre', 'kick')
            self.assertEqual([r['name'] for r in kick], ['Spreen', 'ElSpreenDMC'])          # live first
            self.assertEqual(kick[0]['title'], 'MI MUNDO HARDCORE')                          # details for live results
            self.assertEqual([r['name'] for r in s.search_scope('juan', 'local')], ['JuanFerLaMata'])
            link = s.search_scope('https://kick.com/Spreen', 'link'); self.assertEqual((link[0]['name'], link[0]['live']), ('Spreen', True))
            self.assertEqual(s.search_scope('hola', 'link'), [])


class PrefsAndStorageTests(unittest.TestCase):
    def test_last_setup_per_streamer_is_remembered(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=FakeYDL)
            self.assertIsNone(s.get_prefs('https://kick.com/spreen'))
            s.set_prefs('https://kick.com/Spreen', dict(clip_settings=dict(framing='stack', subtitles=True), language='es', minimum=25, maximum=50, secret='x'))
            p = streamers.Streamers(tmp, ydl_factory=FakeYDL).get_prefs('https://kick.com/spreen')
            self.assertEqual((p['clip_settings']['framing'], p['language'], p['minimum']), ('stack', 'es', 25)); self.assertNotIn('secret', p)

    def test_storage_cleanup_needs_confirmation_and_never_touches_a_recording(self):
        import app as backend, live
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp, patch.dict(backend.LIVE, {}, clear=True):
            sessions = {}
            for name, status in (('parado', 'stopped'), ('grabando', 'live')):
                se = live.LiveSession(Path(tmp) / 'live', f'https://kick.com/{name}'); se.status = status; se.channel = name
                se.segments.mkdir(parents=True); se.clips.mkdir(parents=True)
                (se.segments / 'seg000001.ts').write_bytes(b'x' * 300_000); (se.clips / 'm1.mp4').write_bytes(b'clip')
                backend.LIVE[se.id] = se; sessions[name] = se
            client = TestClient(backend.app)
            listing = client.get('/api/storage').json()
            self.assertEqual([b['channel'] for b in listing['buffers']], ['parado'])            # a recording session is not offered
            ids = [s.id for s in sessions.values()]
            self.assertEqual(client.post('/api/storage/clean', json=dict(sessions=ids)).status_code, 400)   # no confirmation
            r = client.post('/api/storage/clean', json=dict(sessions=ids, confirm=True)).json()
            self.assertEqual(r['sessions'], [sessions['parado'].id])
            self.assertFalse(sessions['parado'].segments.exists()); self.assertTrue(sessions['grabando'].segments.exists())
            self.assertTrue((sessions['parado'].clips / 'm1.mp4').exists())                     # moments are never removed


if __name__ == '__main__':
    unittest.main()


class YoutubeLiveTests(unittest.TestCase):
    def test_spanish_live_streams_by_audience_without_tv_radio_or_reruns(self):
        entries = [dict(live_status='is_live', concurrent_view_count=733754, uploader_id='@hotspanishvlogs', id='a1', channel='HotSpanish Vlogs', title='LA MANSIÓN VIP TEMPORADA 2 | DÍA 2'),
                   dict(live_status='is_live', concurrent_view_count=4576, uploader_id='@noticiascaracol', id='a2', channel='Noticias Caracol', title='🔴 NOTICIAS CARACOL EN VIVO'),
                   dict(live_status='is_live', concurrent_view_count=2296, uploader_id='@elchavodel8', id='a3', channel='El Chavo del 8', title='El Chavo del 8 🔴 EN VIVO 🤣 Maratón de travesuras'),
                   dict(live_status='is_live', concurrent_view_count=29786, uploader_id='@typicalgamer', id='a4', channel='Typical Gamer', title='LIVE! - FINDING the PIRATE TOKEN in FORTNITE!'),
                   dict(live_status='is_live', concurrent_view_count=1384, uploader_id='@alfregames', id='a5', channel='Alfre Games', title='GTA: SAN ANDREAS EN VIVO | RUMBO A GTA 6'),
                   dict(live_status='was_live', concurrent_view_count=99999, uploader_id='@old', id='a6', channel='Old', title='directo de ayer'),
                   dict(live_status='is_live', concurrent_view_count=120, uploader_id='@tiny', id='a7', channel='Tiny', title='jugando en vivo')]
        class YDL(FakeYDL):
            params = {}
            def extract_info(self, url, **kw): return dict(entries=entries)
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=YDL)
            rows = s.youtube_live_now()
        self.assertEqual([r['name'] for r in rows], ['HotSpanish Vlogs', 'Alfre Games'])
        self.assertEqual(rows[0]['url'], 'https://www.youtube.com/@hotspanishvlogs/live')
        self.assertEqual(rows[0]['video_id'], 'a1'); self.assertTrue(rows[0]['thumb'].endswith('/a1/hqdefault_live.jpg'))


class YoutubeLivePageTests(unittest.TestCase):
    def test_the_live_page_redirect_is_followed_to_the_live_video(self):
        """YouTube answers @canal/live with a redirect to the video (no live fields): it used to read as «not live»."""
        class YDL(FakeYDL):
            def extract_info(self, url, **kw):
                if url.endswith('@hotspanishvlogs/live'): return dict(_type='url', url='https://www.youtube.com/watch?v=DxgDeW-gIcU', id='DxgDeW-gIcU')
                if 'watch?v=DxgDeW-gIcU' in url: return dict(id='DxgDeW-gIcU', live_status='is_live', title='LA MANSIÓN VIP TEMPORADA 2 | DÍA 2', concurrent_view_count=795000)
                raise RuntimeError('The channel is not currently live')
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=YDL)
            on = s._youtube_live('@hotspanishvlogs')
            self.assertTrue(on['live']); self.assertEqual(on['viewers'], 795000); self.assertEqual(on['video_id'], 'DxgDeW-gIcU')
            self.assertFalse(s._youtube_live('@otro')['live'])
            rows = [dict(key='youtube:@otro', slug='@otro', live=False), dict(key='youtube:@hotspanishvlogs', slug='@hotspanishvlogs', live=False)]
            s._youtube_live_status(rows)
            self.assertEqual([r['live'] for r in rows], [False, True])


class FollowedYoutubeStateTests(unittest.TestCase):
    def test_a_followed_channel_shows_live_from_the_newer_live_list_and_old_reads_are_redone(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = streamers.Streamers(tmp, ydl_factory=FakeYDL)
            key = s.follow('https://www.youtube.com/@hotspanishvlogs', explicit=True)
            s.items[key].update(live=False, checked=time.time())                     # read before the /live fix
            s._yt_live = (time.time(), [dict(key=key, title='LA MANSIÓN VIP', viewers=795000, video_id='DxgDeW-gIcU', thumb='t.jpg')])
            row = next(r for r in s.listing() if r['key'] == key)
            self.assertTrue(row['live']); self.assertEqual(row['viewers'], 795000)
            s.recheck_old_youtube(); self.assertEqual(s.items[key]['checked'], 0)     # checked again on the next pass
