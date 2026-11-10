import tempfile
import unittest
from pathlib import Path

import streamers


def fake_factory(pages):
    class Y:
        def __init__(self, options): self.params = dict(options)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download=False, process=True):
            for key, info in pages.items():
                if key in url: return info
            raise Exception('not found')
        def urlopen(self, url): raise Exception('offline')
    return Y


def video(i, views, minutes):
    return {'id': f'v{i}', 'title': f'Video {i}', 'view_count': views, 'duration': minutes * 60}


class DiscoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)

    def test_popular_long_videos_every_creator_kept(self):
        pages = {'@big/videos': {'channel': 'Big', 'entries': [video(1, 9_000_000, 30), video(2, 8_000_000, 40), video(3, 7_000_000, 25), video(4, 6_000_000, 20)]},
                 '@small/videos': {'channel': 'Small', 'entries': [video(5, 90_000, 50), video(6, 50_000, 3)]}}
        streamers.DISCOVER['test'] = ('Test', [('Big', '@big'), ('Small', '@small'), ('Gone', '@gone')])
        self.addCleanup(streamers.DISCOVER.pop, 'test')
        s = streamers.Streamers(Path(self.tmp.name), ydl_factory=fake_factory(pages))
        rows = s.discover_videos('test')
        self.assertIn('v5', [r['id'] for r in rows])                       # the small channel keeps its best video
        self.assertNotIn('v6', [r['id'] for r in rows])                    # 3 min: too short to clip
        self.assertEqual([r['views'] for r in rows], sorted((r['views'] for r in rows), reverse=True))
        self.assertLessEqual(sum(r['channel'] == 'Big' for r in rows), 3)  # a mix of creators
        self.assertTrue(all(r['url'].startswith('https://www.youtube.com/watch?v=') for r in rows))

    def test_too_long_videos_are_left_out(self):
        pages = {'@x/videos': {'channel': 'X', 'entries': [video(1, 5, 260), video(2, 4, 100)]}}
        streamers.DISCOVER['test2'] = ('T', [('X', '@x')]); self.addCleanup(streamers.DISCOVER.pop, 'test2')
        rows = streamers.Streamers(Path(self.tmp.name), ydl_factory=fake_factory(pages)).discover_videos('test2')
        self.assertEqual([r['id'] for r in rows], ['v2'])                  # over the 200 min YouTube import limit

    def test_channel_photo_is_a_normal_size(self):
        info = {'thumbnails': [{'url': 'banner', 'width': 2560, 'height': 424}, {'url': 'a88', 'width': 88, 'height': 88},
                               {'url': 'a176', 'width': 176, 'height': 176}, {'url': 'a2347', 'width': 2347, 'height': 2347}]}
        self.assertEqual(streamers.channel_photo(info), 'a176')
        self.assertEqual(streamers.channel_photo({'thumbnails': [{'url': 'a88', 'width': 88, 'height': 88}]}), 'a88')
        self.assertEqual(streamers.channel_photo({}), '')


if __name__ == '__main__':
    unittest.main()
