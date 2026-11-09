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

    # --- preferences per streamer: the last «Configura tus clips» used for that channel ---------------------------------
    PREF_KEYS = ('clip_settings', 'language', 'minimum', 'maximum', 'height', 'buffer_minutes')

    def set_prefs(self, url, prefs):
        key = self.follow(url)
        with _lock: self.items[key]['prefs'] = {k: prefs[k] for k in self.PREF_KEYS if k in prefs}
        self.save(); return key

    def get_prefs(self, url):
        platform, slug = slug_from_url(url)
        if not platform: return None
        item = self.items.get(f'{platform}:{slug}') or {}
        return dict(name=item.get('name') or slug, **item['prefs']) if item.get('prefs') else None

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

    def _json(self, url):
        import yt_dlp
        with self._ydl() as ydl:
            return json.loads(ydl.urlopen(yt_dlp.networking.Request(url, headers={'Accept': 'application/json'})).read())

    def search_scope(self, q, scope):
        """Search one source, so the page can show results as each one answers:
        'link' (a pasted URL), 'local' (your streamers), 'kick' (Kick's public search), 'youtube' (channel search)."""
        import urllib.parse
        q = (q or '').strip()
        if not q: return self.listing() if scope == 'local' else []
        known = {v['key'] for v in self.listing()}
        if scope == 'link':
            platform, slug = slug_from_url(q)
            if not platform: return []
            info = self.lookup(platform, slug); key = f'{platform}:{slug}'
            return [dict(info, key=key, avatar=info.get('photo') or '', clips=self.items.get(key, {}).get('clips', 0), new=key not in known)]
        if scope == 'local':
            low = q.lower().lstrip('@')
            return [v for v in self.listing() if low in v.get('name', '').lower() or low in v.get('slug', '').lower()]
        if scope == 'kick':
            data = self._json('https://kick.com/api/search?searched_word=' + urllib.parse.quote(q[:40]))
            out = []
            for c in (data.get('channels') or [])[:8]:
                user = c.get('user') or {}; slug = (c.get('slug') or '').lower()
                if not slug: continue
                key = f'kick:{slug}'
                out.append(dict(key=key, platform='kick', slug=slug, url=url_for('kick', slug), name=user.get('username') or slug,
                                avatar=user.get('profilePic') or user.get('profile_pic') or '', live=bool(c.get('isLive') or c.get('is_live')),
                                followers=c.get('followersCount') or c.get('followers_count'), clips=self.items.get(key, {}).get('clips', 0), new=key not in known,
                                verified=bool(c.get('verified'))))
            # Details (title, image, viewers) for the first live results only: one request each.
            for r in [r for r in out if r['live']][:3]:
                try:
                    info = self.lookup('kick', r['slug']); r.update(title=info.get('title'), thumb=info.get('thumb'), viewers=info.get('viewers'))
                except Exception: pass
            return sorted(out, key=lambda r: (not r['live'], -(int(r.get('followers') or 0))))
        if scope == 'youtube':
            url = 'https://www.youtube.com/results?search_query=' + urllib.parse.quote(q[:60]) + '&sp=EgIQAg%253D%253D'   # channels only
            with self._ydl() as ydl:
                ydl.params['playlistend'] = 6                      # measured: 1.4 s for six channels
                info = ydl.extract_info(url, download=False) or {}
            out = []
            for e in list(info.get('entries') or [])[:6]:
                handle = e.get('uploader_id') or ''
                if not handle.startswith('@'): continue
                slug = handle.lower(); key = f'youtube:{slug}'
                thumbs = e.get('thumbnails') or []
                out.append(dict(key=key, platform='youtube', slug=slug, url=url_for('youtube', slug), name=e.get('channel') or e.get('title') or slug,
                                avatar=('https:' + thumbs[-1]['url']) if thumbs and thumbs[-1].get('url', '').startswith('//') else (thumbs[-1].get('url') if thumbs else ''),
                                live=False, followers=e.get('channel_follower_count'), clips=self.items.get(key, {}).get('clips', 0), new=key not in known))
            return out
        return []

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
