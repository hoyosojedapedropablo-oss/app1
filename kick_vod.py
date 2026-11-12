"""Kick VODs (a finished stream kept on the channel as a long video): read, download and list, publicly.

Only what Kick serves publicly is used: the public video API (`/api/v1/video/<uuid>`, `/api/v2/channels/<slug>/videos`)
and the HLS playlist it points to. No sign-in, cookies, DRM or region workarounds; private, deleted or still-live
broadcasts are refused with a clear message.

Limits: up to 8 hours per import (Kick VODs are often 3-9 h; YouTube stays at 200 min). A longer VOD is imported from
a chosen start time («Desde»). The file stays under 12 GB by taking the best quality that fits that length.
"""
import json, re, time
from pathlib import Path
from urllib.parse import urlsplit

MAX_SECONDS = 8 * 3600
MAX_BYTES = 12 * 1024 ** 3
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
SLUG = r'[A-Za-z0-9_-]{2,40}'


class KickVodError(ValueError):
    pass


def is_kick_vod(value):
    try: canonical_url(value); return True
    except ValueError: return False


def canonical_url(value):
    """https://kick.com/<canal>/videos/<uuid> (or /video/<uuid>) -> the canonical form. Anything else: ValueError."""
    try: parsed = urlsplit((value or '').strip())
    except ValueError: raise KickVodError('Enlace de Kick inválido.') from None
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise KickVodError('Pega el enlace público del video de Kick.')
    if (parsed.hostname or '').lower() not in ('kick.com', 'www.kick.com'): raise KickVodError('Solo se admiten enlaces de kick.com.')
    path = parsed.path.rstrip('/')
    m = re.fullmatch(rf'/({SLUG})/videos/({UUID})', path, re.I) or re.fullmatch(rf'/video/({UUID})', path, re.I)
    if not m: raise KickVodError('El enlace debe ser un video (VOD) de Kick: kick.com/canal/videos/…')
    if len(m.groups()) == 2: return f'https://kick.com/{m.group(1).lower()}/videos/{m.group(2).lower()}'
    return f'https://kick.com/video/{m.group(1).lower()}'


def _uuid(url):
    return re.search(UUID, url, re.I).group(0).lower()


def _ydl(**extra):
    import yt_dlp
    return yt_dlp.YoutubeDL(dict(quiet=True, no_warnings=True, socket_timeout=30, retries=2, **extra))


def _json(ydl, url):
    import yt_dlp
    return json.loads(ydl.urlopen(yt_dlp.networking.Request(url, headers={'Accept': 'application/json'})).read())


def _thumb(value):
    if isinstance(value, dict): return value.get('src') or value.get('url') or ''
    return value or ''


def video_info(url):
    """Title, channel, duration (s), thumbnail and HLS source of a public VOD."""
    with _ydl() as ydl:
        try: data = _json(ydl, f'https://kick.com/api/v1/video/{_uuid(url)}')
        except Exception as error:
            text = str(error)
            if '404' in text or 'Not Found' in text: raise KickVodError('Kick no encuentra ese video: puede ser privado, haber sido borrado o el enlace está incompleto.') from None
            raise KickVodError('No se pudo consultar Kick. Revisa tu conexión e inténtalo de nuevo.') from None
    live = data.get('livestream') or {}; channel = live.get('channel') or {}
    if data.get('is_private') or data.get('deleted_at') or data.get('status') not in (None, 'public'): raise KickVodError('Este video de Kick no es público.')
    if live.get('is_live'): raise KickVodError('Ese directo todavía está en curso: usa «Clips en vivo» o espera a que termine para clipear el VOD.')
    if not data.get('source'): raise KickVodError('Kick no ofrece la grabación de este directo.')
    duration = round((live.get('duration') or 0) / 1000)
    return dict(url=url, uuid=data.get('uuid'), source=data['source'], duration=duration, title=live.get('session_title') or 'Directo de Kick',
                channel=(channel.get('user') or {}).get('username') or channel.get('slug') or '', slug=channel.get('slug') or '',
                thumbnail=_thumb(live.get('thumbnail')), created=live.get('start_time') or data.get('created_at') or '')


def pick_format(formats, seconds, max_bytes=MAX_BYTES):
    """Best video format (up to 1080p) whose size for `seconds` stays under max_bytes (5 % margin)."""
    video = [f for f in formats if f.get('vcodec') not in (None, 'none') and (f.get('height') or 0) <= 1080]
    video.sort(key=lambda f: ((f.get('height') or 0), (f.get('fps') or 0), (f.get('tbr') or 0)), reverse=True)
    for f in video:
        tbr = f.get('tbr') or 0
        if tbr and tbr * 1000 / 8 * seconds <= max_bytes * .95: return f
    return video[-1] if video else None


def download(url, folder, progress, start=0.0, max_seconds=MAX_SECONDS):
    """Download [start, start + up to 8 h] of the VOD to folder/download.mp4. Returns (path, name, metadata)."""
    info = video_info(url)
    total = info['duration']
    start = max(0.0, float(start or 0))
    if total and start >= total - 30: raise KickVodError('El minuto de inicio está después del final del video.')
    length = min(max_seconds, (total - start) if total else max_seconds)
    progress(0, 'Consultando calidades del VOD de Kick…', title=info['title'], channel=info['channel'], duration=round(length), thumbnail=info['thumbnail'],
             vod_duration=total, vod_start=start)
    with _ydl() as ydl:
        probe = ydl.extract_info(info['source'], download=False, process=False)
        chosen = pick_format(probe.get('formats') or [], length)
        if not chosen: raise KickVodError('Kick no ofrece un formato de video descargable para este VOD.')
        expected = int((chosen.get('tbr') or 0) * 1000 / 8 * length)
        quality = f"{chosen.get('height')}p" + (f"{int(chosen['fps'])}" if (chosen.get('fps') or 0) > 30 else '')
        progress(0, 'Descargando VOD de Kick…', quality=quality, video_width=chosen.get('width'), video_height=chosen.get('height'))
        _hls_range(ydl, chosen['url'], Path(folder), start, length, expected, progress)
    path = Path(folder) / 'download.mp4'
    if not path.exists(): raise KickVodError('No se obtuvo un archivo de video válido de Kick.')
    if path.stat().st_size > MAX_BYTES: raise KickVodError('El video supera 12 GB.')
    name = f"{info['channel'] or 'Kick'} · {info['title']}"
    if start: name += f' · desde {int(start // 3600)}h{int(start % 3600 // 60):02d}'
    return path, re.sub(r'[\\/:*?"<>|]+', ' ', name)[:150] + '.mp4', dict(info, quality=quality, start=start, length=round(length))


def parse_playlist(text, base):
    """HLS media playlist -> (init segment URL or None, [(start s, duration s, URL)])."""
    from urllib.parse import urljoin
    init, out, t, dur = None, [], 0.0, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#EXT-X-MAP:'):
            m = re.search(r'URI="([^"]+)"', line)
            if m: init = urljoin(base, m.group(1))
        elif line.startswith('#EXTINF:'):
            try: dur = float(line[8:].split(',')[0])
            except ValueError: dur = None
        elif line and not line.startswith('#') and dur is not None:
            out.append((t, dur, urljoin(base, line))); t += dur; dur = None
    return init, out


def _hls_range(ydl, playlist, folder, start, length, expected, progress):
    """The pieces of the HLS playlist covering [start, start + length] (8 at a time), appended in order into one stream
    file and copied to MP4 without re-encoding. Nothing before `start` is fetched; at most ~8 pieces sit on disk."""
    import subprocess, os
    from concurrent.futures import ThreadPoolExecutor
    import yt_dlp
    text = ydl.urlopen(yt_dlp.networking.Request(playlist)).read().decode('utf-8', 'replace')
    init, segments = parse_playlist(text, playlist)
    chosen = [s for s in segments if s[0] + s[1] > start and s[0] < start + length]
    if not chosen: raise KickVodError('Kick no devolvió los fragmentos de ese tramo del VOD.')
    offset = max(0.0, start - chosen[0][0])                 # the first piece starts a little before the chosen time
    joined = folder / 'download.stream'; parts = folder / 'parts'; parts.mkdir(exist_ok=True)
    began = time.monotonic(); written = 0

    def fetch(item):
        i, (_, _, url) = item
        target = parts / f'{i:06d}.bin'
        for attempt in range(5):
            try:
                data = ydl.urlopen(yt_dlp.networking.Request(url)).read()
                target.write_bytes(data); return target
            except Exception:
                if attempt == 4: raise KickVodError('Kick cortó la descarga del VOD. Vuelve a intentarlo en unos minutos.') from None
                time.sleep(1 + attempt * 2)

    with open(joined, 'wb') as out, ThreadPoolExecutor(max_workers=8) as pool:
        if init: out.write(ydl.urlopen(yt_dlp.networking.Request(init)).read())
        futures = [pool.submit(fetch, item) for item in enumerate(chosen)]
        for n, future in enumerate(futures, 1):
            piece = future.result()
            data = piece.read_bytes(); out.write(data); written += len(data); piece.unlink()
            if written > MAX_BYTES:
                for f in futures: f.cancel()
                raise KickVodError('El video supera 12 GB.')
            if time.monotonic() - began > 6 * 3600: raise KickVodError('La descarga superó el tiempo de espera (6 h).')
            if n % 4 == 0 or n == len(futures):
                elapsed = time.monotonic() - began; rate = written / max(1e-3, elapsed)
                progress(min(95, round(95 * n / len(futures))), 'Descargando VOD de Kick…', speed=rate,
                         eta=(len(futures) - n) * elapsed / n, downloaded_bytes=written, total_bytes=max(expected, written))
    try: parts.rmdir()
    except OSError: pass
    progress(97, 'Preparando el video para el editor…')
    tmp = folder / 'download.part.mp4'
    run = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{offset:.3f}', '-i', str(joined), '-t', f'{length:.3f}', '-map', '0:v:0', '-map', '0:a:0?',
                          '-c', 'copy', '-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart', str(tmp)], capture_output=True, text=True,
                         creationflags=0x08000000 if os.name == 'nt' else 0)
    joined.unlink(missing_ok=True)
    if run.returncode or not tmp.exists(): raise KickVodError('No se pudo preparar el video de Kick (' + (run.stderr or '').strip()[-160:] + ').')
    tmp.replace(folder / 'download.mp4')


def channel_vods(slug, limit=6):
    """The channel's latest finished broadcasts (newest first), public data only."""
    with _ydl() as ydl:
        rows = _json(ydl, f'https://kick.com/api/v2/channels/{slug}/videos')
    out = []
    for v in rows or []:
        video = v.get('video') or {}
        if v.get('is_live') or not video.get('uuid') or video.get('is_private') or video.get('deleted_at'): continue
        out.append(dict(url=f'https://kick.com/{slug}/videos/{video["uuid"]}', title=v.get('session_title') or 'Directo', duration=round((v.get('duration') or 0) / 1000),
                        thumb=_thumb(v.get('thumbnail')), created=v.get('start_time') or v.get('created_at') or '', views=video.get('views') or v.get('views') or 0, slug=slug))
        if len(out) >= limit: break
    return out
