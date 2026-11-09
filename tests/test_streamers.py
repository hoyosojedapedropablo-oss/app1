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


if __name__ == '__main__':
    unittest.main()
