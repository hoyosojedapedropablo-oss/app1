"""Streamers the user clips: profile photo, whether they are live now, and search by name.

Uses only public data through yt-dlp, the same library and requests ClipStudio already uses to connect to a live
stream (Kick's public channel API; YouTube's public channel and /live pages). No login, no cookies, no attempt to get
around age, region or subscriber restrictions: a channel that does not answer publicly is simply shown as unknown.
Results are cached (5 minutes for live status, 7 days for photos) so the app never polls the platforms aggressively.
"""
import json, re, threading, time
from pathlib import Path

LIVE_TTL = 300          # seconds between live checks of one streamer
AVATAR_TTL = 7 * 86400
_lock = threading.RLock()


def slug_from_url(url):
    m = re.search(r'kick\.com/([\w-]+)', url or '', re.I)
    if m: return 'kick', m.group(1).lower()
    m = re.search(r'youtube\.com/(@[\w.-]+)', url or '', re.I)
    if m: return 'youtube', m.group(1).lower()
    return None, None


def url_for(platform, slug):
    return f'https://kick.com/{slug}' if platform == 'kick' else f'https://www.youtube.com/{slug}/live'


class Streamers:
    def __init__(self, data, ydl_factory=None):
        self.data = Path(data); self.file = self.data / 'streamers.json'; self.avatars = self.data / 'avatars'
        self.avatars.mkdir(parents=True, exist_ok=True)
        self.ydl_factory = ydl_factory
        try: self.items = json.loads(self.file.read_text(encoding='utf-8'))
        except (OSError, ValueError): self.items = {}
        self._checking = False

    def save(self):
        with _lock:
            tmp = self.file.with_suffix('.tmp'); tmp.write_text(json.dumps(self.items, ensure_ascii=False), encoding='utf-8'); tmp.replace(self.file)

    def _ydl(self):
        import yt_dlp
        class Quiet:   # «channel is not live» is an expected answer, not an error to print
            def debug(self, msg): pass
            info = warning = error = debug
        options = {'logger': Quiet(), 'quiet': True, 'no_warnings': True, 'skip_download': True, 'noplaylist': True, 'socket_timeout': 15, 'extract_flat': 'in_playlist'}
        return (self.ydl_factory or yt_dlp.YoutubeDL)(options)

    # --- one channel ------------------------------------------------------------------------------------------------
    def lookup(self, platform, slug):
        """Public info of one channel: name, photo URL, live, title, viewers, stream thumbnail."""
        with self._ydl() as ydl:
            if platform == 'kick':
                ie = ydl.get_info_extractor('Kick')
                data = ie._call_api(f'v2/channels/{slug}', slug, note='Canal')
                user = data.get('user') or {}; ls = data.get('livestream') or {}
                return dict(platform='kick', slug=slug, url=url_for('kick', slug), name=user.get('username') or slug,
                            photo=user.get('profile_pic') or '', live=bool(ls), title=(ls.get('session_title') or '').strip(),
                            viewers=ls.get('viewer_count'), thumb=(ls.get('thumbnail') or {}).get('url') or '', followers=data.get('followers_count'))
            info = {}
            try: info = ydl.extract_info(f'https://www.youtube.com/{slug}', download=False, process=False) or {}
            except Exception: info = {}
            photo = next((t.get('url') for t in reversed(info.get('thumbnails') or []) if 'avatar' in (t.get('id') or '') or (t.get('width') or 0) == (t.get('height') or -1)), '')
            live = {}
            try: live = ydl.extract_info(f'https://www.youtube.com/{slug}/live', download=False, process=False) or {}
            except Exception: live = {}
            on = bool(live.get('is_live') or live.get('live_status') == 'is_live')
            return dict(platform='youtube', slug=slug, url=url_for('youtube', slug), name=info.get('channel') or info.get('uploader') or slug,
                        photo=photo, live=on, title=(live.get('title') or '') if on else '', viewers=live.get('concurrent_view_count') if on else None,
                        thumb=(live.get('thumbnail') or '') if on else '', video_id=live.get('id') if on else '')

    def refresh(self, key, force=False):
        item = self.items.get(key)
        if not item: return None
        if not force and time.time() - item.get('checked', 0) < LIVE_TTL: return item
        try:
            info = self.lookup(item['platform'], item['slug'])
            item.update(info, checked=time.time(), error='')
            self._avatar(key, info.get('photo'))
        except Exception as e:
            item.update(checked=time.time(), error=type(e).__name__, live=False)
        self.save()
        return item

    def _avatar(self, key, url):
        if not url: return
        target = self.avatars / f'{key.replace(":", "_")}.jpg'
        if target.exists() and time.time() - target.stat().st_mtime < AVATAR_TTL: return
        try:
            with self._ydl() as ydl:
                body = ydl.urlopen(url).read(2_000_000)
            if body[:3] in (b'\xff\xd8\xff', b'\x89PN', b'RIF', b'GIF') or body[:4] == b'\x89PNG': target.write_bytes(body)
        except Exception: pass

    def avatar_path(self, key):
        p = self.avatars / f'{key.replace(":", "_")}.jpg'
        return p if p.exists() else None

    # --- the user's streamers ------------------------------------------------------------------------------------------
    def follow(self, url, clips=0, name=None):
        platform, slug = slug_from_url(url)
        if not platform: raise ValueError('Usa un enlace de Kick (kick.com/canal) o de YouTube (youtube.com/@canal).')
        key = f'{platform}:{slug}'
        with _lock:
            item = self.items.setdefault(key, dict(platform=platform, slug=slug, url=url_for(platform, slug), name=name or slug, checked=0))
            item['clips'] = max(item.get('clips', 0), clips)
        self.save(); return key

    def sync_from(self, sessions, clip_counts):
        """Every streamer the user has clipped live becomes a followed streamer (counts from the library)."""
        for s in sessions:
            platform, slug = slug_from_url(s.get('url'))
            if platform:
                key = f'{platform}:{slug}'
                with _lock:
                    item = self.items.setdefault(key, dict(platform=platform, slug=slug, url=url_for(platform, slug), name=s.get('channel') or slug, checked=0))
                    item['clips'] = clip_counts.get((s.get('channel') or '').lower(), item.get('clips', 0))
        self.save()

    def check_all(self):
        """Background pass: refresh stale streamers one at a time (most clipped first)."""
        if self._checking: return
        self._checking = True
        try:
            for key, _ in sorted(self.items.items(), key=lambda kv: -kv[1].get('clips', 0)):
                self.refresh(key)
        finally:
            self._checking = False

    def listing(self):
        with _lock:
            out = [dict(v, key=k, avatar=f'/api/streamers/{k}/avatar' if self.avatar_path(k) else '') for k, v in self.items.items()]
        return sorted(out, key=lambda v: (not v.get('live'), -v.get('clips', 0), v.get('name', '').lower()))

    def search(self, q):
        """Known streamers matching the name, plus an exact public lookup of the name on Kick (and @name on YouTube)."""
        q = (q or '').strip()
        if not q: return self.listing()
        low = q.lower().lstrip('@')
        found = [v for v in self.listing() if low in v.get('name', '').lower() or low in v.get('slug', '').lower()]
        keys = {v['key'] for v in found}
        if re.fullmatch(r'[\w-]{2,40}', low):
            for platform, slug in (('kick', low), ('youtube', '@' + low)):
                key = f'{platform}:{slug}'
                if key in keys: continue
                try:
                    info = self.lookup(platform, slug)
                    if platform == 'youtube' and not info.get('photo') and not info.get('live'): continue    # no such channel
                    info.update(key=key, avatar=info.get('photo') or '', clips=0, new=True); found.append(info)
                except Exception: continue
        return found
