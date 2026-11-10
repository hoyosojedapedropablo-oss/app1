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

# The most relevant Kick channels (Streams Charts / Infobae rankings, 2026), checked to exist on Kick's public API.
# Spanish-speaking ones first: they are shown first on Inicio when they are live.
FEATURED_KICK = (
    [(s, 'es') for s in ('westcol', 'davooxeneize', 'lacobraaa', 'spreen', 'elzeein', 'mrstiventc', 'rdjavi', 'robleis',
                         'mernuel', 'coscu', 'zeko', 'juansguarnizo', 'benjaz', 'elded', 'shadoune666')]
    + [(s, 'other') for s in ('absi', 'maherco', 'korekore_ch', 'deenthegreat', 'jonvlogs', 'adinross', 'xqc', 'clavicular',
                              '3mr', 'trainwreckstv', 'nickmercs')])
# Spanish-speaking YouTube channels that stream live on YouTube often (checked: a public «Directos» tab with recent
# streams of 100k+ views). YouTube is checked less often (every 10 minutes) and only its /live page once a photo exists.
FEATURED_YOUTUBE = [(s, 'es') for s in ('@auronplay', '@thegrefg', '@vegetta777', '@willyrex', '@mikecrack', '@fernanfloo',
                                        '@djmariio', '@xfarganx', '@rivers_gg')]
YOUTUBE_TTL = 600


def youtube_live_page(ydl, slug):
    """What a channel's /live page shows. YouTube answers it with a redirect to the live video (a «url» result with
    no live fields), which was read as «not live» for every channel (HotSpanish, 795 k watching, «Desconectado»):
    follow it to the video and read its real state. A channel that is not live answers with an error or its page."""
    try: page = ydl.extract_info(f'https://www.youtube.com/{slug}/live', download=False, process=False) or {}
    except Exception: return {}
    if page.get('_type') == 'url' and 'watch?v=' in (page.get('url') or ''):
        try: page = ydl.extract_info(page['url'], download=False, process=False) or {}
        except Exception: return {}
    return page


def featured_all():
    return [('kick', s, l) for s, l in FEATURED_KICK] + [('youtube', s, l) for s, l in FEATURED_YOUTUBE]


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
        self.featured_file = self.data / 'featured.json'
        try: self.featured = json.loads(self.featured_file.read_text(encoding='utf-8'))
        except (OSError, ValueError): self.featured = {}
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
                            viewers=ls.get('viewer_count'), thumb=(ls.get('thumbnail') or {}).get('url') or '', followers=data.get('followers_count'),
                            playback=data.get('playback_url') or '' if ls else '')
            info = {}
            try: info = ydl.extract_info(f'https://www.youtube.com/{slug}', download=False, process=False) or {}
            except Exception: info = {}
            photo = next((t.get('url') for t in reversed(info.get('thumbnails') or []) if 'avatar' in (t.get('id') or '') or (t.get('width') or 0) == (t.get('height') or -1)), '')
            live = {}
            live = youtube_live_page(ydl, slug)
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
            item.update(info, checked=time.time(), error='', read=self.LIVE_READ_VERSION)
            self._avatar(key, info.get('photo'))
            self._live_still(key, item)
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

    def _live_still(self, key, item):
        """Kick refuses its thumbnail URLs outside its site (403), so take one frame of the public stream itself (the
        same stream ClipStudio records when clipping) and serve it locally. One frame every few minutes at most."""
        target = self.avatars / f'{key.replace(":", "_")}-live.jpg'
        if not item.get('live') or not item.get('playback'):
            target.unlink(missing_ok=True); return
        import subprocess
        try:
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', item['playback'], '-frames:v', '1', '-vf', 'scale=640:-2', '-q:v', '5', str(target)],
                           capture_output=True, timeout=25)
        except Exception: pass

    def live_still(self, key):
        p = self.avatars / f'{key.replace(":", "_")}-live.jpg'
        return p if p.exists() else None

    def avatar_path(self, key):
        p = self.avatars / f'{key.replace(":", "_")}.jpg'
        return p if p.exists() else None

    # --- the user's streamers ------------------------------------------------------------------------------------------
    def follow(self, url, clips=0, name=None, explicit=False):
        platform, slug = slug_from_url(url)
        if not platform: raise ValueError('Usa un enlace de Kick (kick.com/canal) o de YouTube (youtube.com/@canal).')
        key = f'{platform}:{slug}'
        with _lock:
            item = self.items.setdefault(key, dict(platform=platform, slug=slug, url=url_for(platform, slug), name=name or slug, checked=0))
            item['clips'] = max(item.get('clips', 0), clips)
            if explicit: item['followed'] = True; item.pop('hidden', None)     # «Seguir»: shown on Inicio again
        self.save(); return key

    def unfollow(self, key):
        """«Dejar de seguir»: hidden from Inicio and the search, but its saved setup and clip count stay."""
        with _lock:
            item = self.items.get(key)
            if not item: return False
            item['hidden'] = True; item['followed'] = False
        self.save(); return True

    # --- preferences per streamer: the last «Configura tus clips» used for that channel ---------------------------------
    PREF_KEYS = ('clip_settings', 'language', 'minimum', 'maximum', 'height', 'buffer_minutes', 'vocabulary')

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

    LIVE_READ_VERSION = 2      # 2: the /live redirect is followed (before, every YouTube channel read as «not live»)

    def recheck_old_youtube(self):
        with _lock:
            for item in self.items.values():
                if item.get('platform') == 'youtube' and item.get('read', 1) < self.LIVE_READ_VERSION: item['checked'] = 0
            for item in self.featured.values():
                if item.get('platform') == 'youtube' and item.get('read', 1) < self.LIVE_READ_VERSION: item['checked'] = 0

    def check_all(self):
        """Background pass: refresh stale streamers one at a time (most clipped first)."""
        if self._checking: return
        self._checking = True
        try:
            for key, item in sorted(self.items.items(), key=lambda kv: -kv[1].get('clips', 0)):
                if not item.get('hidden'): self.refresh(key)
        finally:
            self._checking = False

    def listing(self):
        cached = getattr(self, '_yt_live', None)
        live_now = {r['key']: r for r in cached[1]} if cached and time.time() - cached[0] < YOUTUBE_TTL else {}
        with _lock:
            out = []
            for k, v in self.items.items():
                if v.get('hidden'): continue
                row = {x: y for x, y in v.items() if x != 'playback'}          # the stream address stays on the server
                row.update(key=k, avatar=f'/api/streamers/{k}/avatar' if self.avatar_path(k) else '')
                still = self.live_still(k)
                if v.get('platform') == 'kick': row['thumb'] = f'/api/streamers/{k}/live.jpg?t={int(still.stat().st_mtime)}' if still and v.get('live') else ''
                yt = live_now.get(k)
                if yt and not row.get('live'):      # newer than the last check of this channel: the YouTube live list
                    row.update(live=True, title=yt.get('title', ''), viewers=yt.get('viewers'), video_id=yt.get('video_id', ''), thumb=yt.get('thumb', ''))
                out.append(row)
        return sorted(out, key=lambda v: (not v.get('live'), -v.get('clips', 0), v.get('name', '').lower()))

    # --- featured Kick streamers: recommended on Inicio as soon as they go live (kept apart from the user's own) -------
    def _youtube_live(self, slug):
        with self._ydl() as ydl:
            live = youtube_live_page(ydl, slug)
        on = bool(live.get('is_live') or live.get('live_status') == 'is_live')
        return dict(live=on, title=(live.get('title') or '') if on else '', viewers=live.get('concurrent_view_count') if on else None,
                    thumb=(live.get('thumbnail') or '') if on else '', video_id=live.get('id') if on else '')

    def check_featured(self, channels=None):
        """Background pass: one public request per channel (Kick every 5 minutes, YouTube every 10), a frame of the
        Kick ones live. Entries are (slug, lang) for Kick or (platform, slug, lang)."""
        for entry in (channels if channels is not None else featured_all()):
            platform, slug, lang = entry if len(entry) == 3 else ('kick', *entry)
            key = f'{platform}:{slug}'; item = self.featured.get(key) or {}
            if time.time() - item.get('checked', 0) < (LIVE_TTL if platform == 'kick' else YOUTUBE_TTL): continue
            try:
                if platform == 'youtube' and item.get('name') and self.avatar_path(key):
                    info = self._youtube_live(slug)                  # photo and name already known
                else:
                    info = self.lookup(platform, slug); self._avatar(key, info.get('photo'))
                item.update(info, platform=platform, slug=slug, url=url_for(platform, slug), lang=lang, checked=time.time(), error='', read=self.LIVE_READ_VERSION)
                if platform == 'kick': self._live_still(key, item)
            except Exception as e:
                item.update(platform=platform, slug=slug, url=url_for(platform, slug), name=item.get('name') or slug, lang=lang, checked=time.time(), error=type(e).__name__, live=False)
            with _lock: self.featured[key] = item
            with _lock:
                tmp = self.featured_file.with_suffix('.tmp'); tmp.write_text(json.dumps(self.featured, ensure_ascii=False), encoding='utf-8'); tmp.replace(self.featured_file)

    def featured_listing(self, include_offline=False):
        """Recommended channels the user does not follow: the ones live now (Spanish first, then by viewers), or with
        include_offline also the others, to follow them."""
        known = {f'{p}:{s}' for p, s, _ in featured_all()}
        with _lock:
            out = []
            for k, v in self.featured.items():
                followed = k in self.items and not self.items[k].get('hidden')
                if k not in known or followed or (not v.get('live') and not include_offline) or not v.get('name'): continue
                row = {x: y for x, y in v.items() if x != 'playback'}
                row.update(key=k, avatar=f'/api/streamers/{k}/avatar' if self.avatar_path(k) else '')
                if v.get('platform', 'kick') == 'kick':
                    still = self.live_still(k)
                    row['thumb'] = f'/api/streamers/{k}/live.jpg?t={int(still.stat().st_mtime)}' if still and v.get('live') else ''
                out.append(row)
        num = lambda v: float(v) if str(v or '').replace('.', '', 1).isdigit() else 0.0      # counts can arrive as text
        return sorted(out, key=lambda v: (not v.get('live'), v.get('lang') != 'es', -num(v.get('viewers')), -num(v.get('followers'))))

    # --- YouTube live right now: the Spanish-speaking streams with the biggest audience (HotSpanish «La Mansión VIP»:
    # 733 754 people). Found with YouTube's own search filtered to live videos; cached 10 minutes. --------------------
    # Streamer content (reality, IRL, games, reactions); TV, radio, news, church services and 24 h re-runs are left out.
    YT_LIVE_QUERIES = ('en vivo', 'reality en vivo', 'en vivo jugando', 'en vivo free fire', 'en vivo minecraft',
                       'reaccionando en vivo')
    YT_LIVE_SKIP = re.compile(r'noticias|news|24/7|24 ?horas|24h|marat[oó]n|radio|m[uú]sica|music|lofi|chill|relax|se[ñn]al|'
                              r'\btv\b|televisi|\bcanal\b|onda cero|cadena|gobierno|alcald|congreso|senado|\bpapa\b|\bmisa\b|iglesia|hillsong|'
                              r'worship|oraci[oó]n|culto|poker|casino|boomerang|cartoon|disney|telemundo|univision|caracol|\brcn\b|\bdw\b|\brai\b|\bcnn\b|'
                              r'episodios completos|full episodes', re.I)
    YT_SPANISH = re.compile(r'[áéíóúñ¿¡]|\b(en vivo|directo|jugando|con|los|las|del|para|que|reality|temporada|d[ií]a|vamos|hoy|nuevo|partida)\b', re.I)

    def youtube_live_now(self, force=False):
        cached = getattr(self, '_yt_live', None)
        if cached and not force and time.time() - cached[0] < YOUTUBE_TTL: return cached[1]
        import urllib.parse
        found = {}
        with self._ydl() as ydl:
            ydl.params['playlistend'] = 20
            for q in self.YT_LIVE_QUERIES:
                url = 'https://www.youtube.com/results?search_query=' + urllib.parse.quote(q) + '&sp=EgJAAQ%253D%253D&hl=es&gl=MX'
                try: info = ydl.extract_info(url, download=False) or {}
                except Exception: continue
                for e in info.get('entries') or []:
                    handle = (e.get('uploader_id') or '').lower(); vid = e.get('id'); viewers = e.get('concurrent_view_count') or 0
                    title = (e.get('title') or '').strip()
                    if e.get('live_status') != 'is_live' or not handle.startswith('@') or not vid or viewers < 500: continue
                    if self.YT_LIVE_SKIP.search(title) or self.YT_LIVE_SKIP.search(e.get('channel') or '') or not self.YT_SPANISH.search(title): continue
                    key = f'youtube:{handle}'
                    if key in found and found[key]['viewers'] >= viewers: continue
                    found[key] = dict(key=key, platform='youtube', slug=handle, url=url_for('youtube', handle), name=e.get('channel') or handle,
                                      title=title, viewers=viewers, live=True, video_id=vid, lang='es',
                                      thumb=f'https://i.ytimg.com/vi/{vid}/hqdefault_live.jpg', avatar=self.featured.get(key, {}).get('photo', ''))
        rows = sorted(found.values(), key=lambda r: -r['viewers'])[:12]
        self._yt_live = (time.time(), rows)
        return rows

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
            row = {k: v for k, v in info.items() if k != 'playback'}
            if platform == 'kick' and row.get('live'): row['thumb'] = f'/api/streamers/{key}/live.jpg'
            return [dict(row, key=key, avatar=info.get('photo') or '', clips=self.items.get(key, {}).get('clips', 0), new=key not in known)]
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
                    info = self.lookup('kick', r['slug']); r.update(title=info.get('title'), thumb=f"/api/streamers/{r['key']}/live.jpg", viewers=info.get('viewers'))
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
            self._youtube_live_status(out)
            return sorted(out, key=lambda r: not r['live'])
        return []

    def _youtube_live_status(self, rows, check=6):
        """YouTube's channel search does not say who is live (HotSpanish, 795 k watching, showed «Desconectado»):
        take it from the live list already known, and look at the /live page of the first few results, in parallel."""
        known = {r['key']: r for r in ((getattr(self, '_yt_live', None) or (0, []))[1])}
        known.update({k: v for k, v in self.featured.items() if v.get('platform') == 'youtube' and v.get('live') and time.time() - v.get('checked', 0) < YOUTUBE_TTL})
        def apply(r, info):
            if info.get('live'): r.update(live=True, title=info.get('title') or '', viewers=info.get('viewers'), video_id=info.get('video_id') or '',
                                          thumb=info.get('thumb') or (f"https://i.ytimg.com/vi/{info['video_id']}/hqdefault_live.jpg" if info.get('video_id') else ''))
        todo = []
        for r in rows:
            if r['key'] in known: apply(r, known[r['key']])
            elif len(todo) < check: todo.append(r)
        if todo:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=len(todo)) as pool:
                for r, info in zip(todo, pool.map(lambda r: self._youtube_live(r['slug']), todo)):
                    try: apply(r, info)
                    except Exception: pass

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
