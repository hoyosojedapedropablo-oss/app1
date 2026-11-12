import unittest
import kick_vod


class KickVodTests(unittest.TestCase):
    def test_links(self):
        u = 'https://kick.com/Westcol/videos/7A0D391D-1645-4567-9b7c-22254f2b2570?t=10'
        self.assertEqual(kick_vod.canonical_url(u), 'https://kick.com/westcol/videos/7a0d391d-1645-4567-9b7c-22254f2b2570')
        self.assertEqual(kick_vod.canonical_url('https://www.kick.com/video/7a0d391d-1645-4567-9b7c-22254f2b2570'),
                         'https://kick.com/video/7a0d391d-1645-4567-9b7c-22254f2b2570')
        for bad in ('https://kick.com/westcol', 'https://youtube.com/watch?v=abc', 'https://evil.com/westcol/videos/7a0d391d-1645-4567-9b7c-22254f2b2570',
                    'ftp://kick.com/westcol/videos/7a0d391d-1645-4567-9b7c-22254f2b2570', 'https://user:pw@kick.com/video/7a0d391d-1645-4567-9b7c-22254f2b2570'):
            self.assertFalse(kick_vod.is_kick_vod(bad), bad)

    def test_quality_fits_12_gb(self):
        formats = [dict(format_id='1080p60', height=1080, fps=60, tbr=8090, vcodec='avc1'), dict(format_id='720p60', height=720, fps=60, tbr=3487, vcodec='avc1'),
                   dict(format_id='480p', height=480, fps=30, tbr=1492, vcodec='avc1'), dict(format_id='audio', vcodec='none', tbr=128)]
        self.assertEqual(kick_vod.pick_format(formats, 3 * 3600)['format_id'], '1080p60')     # 3 h: 10.9 GB
        self.assertEqual(kick_vod.pick_format(formats, 6 * 3600)['format_id'], '720p60')      # 6 h: 9.4 GB
        self.assertEqual(kick_vod.pick_format(formats, 8 * 3600)['format_id'], '480p')        # 8 h: 720p would be 12.6 GB

    def test_playlist_range(self):
        text = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:2.0,\na.m4s\n#EXTINF:2.0,\nb.m4s\n#EXTINF:1.5,\nhttps://cdn/c.m4s\n#EXT-X-ENDLIST\n'
        init, segs = kick_vod.parse_playlist(text, 'https://stream.kick.com/x/720p60/playlist.m3u8')
        self.assertEqual(init, 'https://stream.kick.com/x/720p60/init.mp4')
        self.assertEqual([(s, d) for s, d, _ in segs], [(0.0, 2.0), (2.0, 2.0), (4.0, 1.5)])
        self.assertEqual(segs[1][2], 'https://stream.kick.com/x/720p60/b.m4s'); self.assertEqual(segs[2][2], 'https://cdn/c.m4s')

    def test_limits(self):
        self.assertEqual(kick_vod.MAX_SECONDS, 8 * 3600)
        self.assertEqual(kick_vod.MAX_BYTES, 12 * 1024 ** 3)
