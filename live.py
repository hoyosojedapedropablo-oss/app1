"""Live clipping: follow a public YouTube Live or Kick stream and propose clips while it is still on air.

Pipeline (one session at a time):
  capture   yt-dlp resolves the public HLS stream; FFmpeg copies it into 10 s segments. A supervisor reconnects with
            backoff, re-resolving the URL (YouTube's expire), and records gaps instead of failing the session.
  process   each closed segment is transcribed and its loudness measured; times are absolute session media time.
  detect    every ~2 min of new media the last ~5 min are given to the existing editorial analyst (evidence-checked,
            no invented titles). Without the AI, sustained audio peaks become candidates with neutral labels.
  moments   accepted moments are rendered from the segments to their own MP4 right away, so the rolling buffer can
            drop old segments. "Open in editor" turns a moment into a normal job with transcript and one clip.
Nothing here bypasses DRM, sign-in, age or region checks: only streams yt-dlp can read publicly are accepted.
"""
import json, math, re, shutil, subprocess, threading, time, uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

SEGMENT_S = 10
DETECT_EVERY_S = 120
WINDOW_S = 300
FIRST_DETECTION_S = 150
TAIL_CONTEXT_S = 4        # a moment must end this long before the newest audio, so reactions are not cut
PAD_S = 3                 # extra source kept around a moment so the editor can nudge its edges
MIN_FREE_DISK_GB = 5
SAVE_EVERY_S = 30
RUNNING = ('starting', 'live', 'reconnecting')


class LiveError(ValueError):
    pass


def validate_url(value):
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        raise LiveError('Enlace inválido.') from None
    host = (parts.hostname or '').lower().removeprefix('www.').removeprefix('m.')
    if parts.scheme not in ('http', 'https') or parts.username or parts.password:
        raise LiveError('Pega el enlace público del directo.')
    if host == 'kick.com':
        slug = parts.path.strip('/').split('/')[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]{2,40}', slug):
            raise LiveError('El enlace de Kick debe ser el del canal, por ejemplo https://kick.com/canal.')
        return 'kick', f'https://kick.com/{slug}'
    if host in ('youtube.com', 'youtu.be'):
        return 'youtube', value.strip()
    raise LiveError('Por ahora el clipping en vivo admite YouTube Live y Kick.')


def resolve(url, height=720, ydl_factory=None):
    """Return stream info for a live broadcast, or raise LiveError with a clear reason."""
    import yt_dlp
    from youtube_import import javascript_options, SafeLog
    options = {'quiet': True, 'skip_download': True, 'noplaylist': True, 'logger': SafeLog('live'), 'socket_timeout': 20,
               'js_runtimes': javascript_options(), 'format': f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'}
    try:
        with (ydl_factory or yt_dlp.YoutubeDL)(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as error:
        text = str(error).lower()
        if 'not currently live' in text or 'is offline' in text:
            raise LiveError('El canal no está transmitiendo en vivo en este momento.') from None
        if any(word in text for word in ('sign in', 'login', 'members', 'private', 'age')):
            raise LiveError('Este directo no es accesible públicamente. ClipStudio no evita restricciones de acceso.') from None
        raise LiveError('No se pudo conectar con el directo. Revisa el enlace y tu conexión.') from None
    if not info or not info.get('is_live'):
        raise LiveError('El enlace no corresponde a una transmisión en vivo activa.')
    parts = info.get('requested_formats') or [info]
    if any(not part.get('url') for part in parts):
        raise LiveError('La plataforma no entregó una señal de video accesible.')
    return {'title': info.get('title') or 'Directo', 'channel': info.get('uploader') or info.get('channel') or '',
            'platform': info.get('extractor_key') or '', 'parts': [{'url': p['url'], 'headers': p.get('http_headers') or info.get('http_headers') or {}} for p in parts]}


def ffmpeg_capture_command(stream, folder, start_number):
    inputs = []
    for part in stream['parts']:
        headers = ''.join(f'{k}: {v}\r\n' for k, v in part['headers'].items())
        inputs += ['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_on_network_error', '1', '-reconnect_delay_max', '10',
                   '-rw_timeout', '20000000', '-headers', headers, '-i', part['url']]
    # YouTube sends audio and video as separate playlists; Kick sends one muxed playlist.
    return ['ffmpeg', '-v', 'error', '-y', *inputs, '-map', '0:v:0?', '-map', f'{len(stream["parts"]) - 1}:a:0?', '-c', 'copy',
            '-f', 'segment', '-segment_time', str(SEGMENT_S), '-reset_timestamps', '1', '-segment_start_number', str(start_number),
            str(folder / 'seg%06d.ts')]


def loudness(audio, rate=16000):
    """dBFS per second of mono float audio."""
    import numpy as np
    values = []
    for i in range(0, len(audio), rate):
        chunk = audio[i:i + rate]
        if len(chunk) < rate // 4: break
        values.append(round(20 * math.log10(float(np.sqrt(np.mean(chunk.astype('float64') ** 2))) + 1e-9), 1))
    return values


def audio_peaks(levels, start, end, above_db=9, min_len=2):
    """Sustained loud stretches (shouting, laughter, hype) relative to the window's median level."""
    window = [(t, db) for t, db in levels if start <= t < end and db > -70]
    if len(window) < 30: return []
    baseline = sorted(db for _, db in window)[len(window) // 2]
    peaks, run = [], []
    for t, db in window:
        if db >= baseline + above_db: run.append((t, db))
        else:
            if len(run) >= min_len: peaks.append({'start': run[0][0], 'end': run[-1][0] + 1, 'db': max(d for _, d in run) - baseline})
            run = []
    if len(run) >= min_len: peaks.append({'start': run[0][0], 'end': run[-1][0] + 1, 'db': max(d for _, d in run) - baseline})
    return peaks


def overlaps(a, b, threshold=.5):
    inter = min(a['end'], b['end']) - max(a['start'], b['start'])
    return inter > 0 and inter >= threshold * min(a['end'] - a['start'], b['end'] - b['start'])


def similar_text(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > .8


def peak_moment(peak, phrases, minimum, maximum, window_start, window_end):
    """Build a neutral candidate around an audio peak using whole phrases; never invent a title."""
    before = [p for p in phrases if p['end'] <= peak['start'] + .5]
    after = [p for p in phrases if p['start'] >= peak['start'] - .5]
    if not before and not after: return None
    target = (minimum + maximum) / 2
    start_phrase = next((p for p in reversed(before) if peak['start'] - p['start'] >= target * .4), before[0] if before else after[0])
    start = max(window_start, start_phrase['start'])
    ends = [p['end'] for p in phrases if p['end'] >= max(peak['end'], start + minimum)]
    end = next((e for e in ends if e - start >= minimum), None)
    if end is None or end > window_end - TAIL_CONTEXT_S: return None
    if end - start > maximum: end = start + maximum
    return {'start': round(start, 3), 'end': round(end, 3)}


class LiveSession:
    def __init__(self, root, url, minimum=20, maximum=60, buffer_minutes=60, height=720, sid=None, engine='gpu'):
        self.id = sid or uuid.uuid4().hex
        self.root = Path(root) / self.id
        self.segments = self.root / 'segments'
        self.clips = self.root / 'moments'
        self.platform, self.url = validate_url(url)
        self.minimum, self.maximum = minimum, maximum
        self.buffer_s = buffer_minutes * 60
        self.height, self.engine = height, engine
        self.status, self.message = 'starting', 'Conectando con el directo…'
        self.title = self.channel = ''
        self.created = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self.media_s = 0.0            # seconds of processed stream (session timeline)
        self.next_index = 0           # next segment number for FFmpeg
        self.processed_index = -1
        self.segment_times = {}       # index -> [media_start, media_end]
        self.transcript, self.levels, self.moments, self.events = [], [], [], []
        self.gaps = []                # media times where the capture restarted
        self.reconnects = 0
        self.last_detection = 0.0
        self.transcription_device = ''
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.proc = None
        self.threads = []
        self._saved = 0.0
        self._model = None

    # --- state -------------------------------------------------------------------------------------------------
    def public(self, full=True):
        with self.lock:
            data = {'id': self.id, 'url': self.url, 'platform': self.platform, 'title': self.title, 'channel': self.channel,
                    'status': self.status, 'message': self.message, 'created': self.created, 'media_s': round(self.media_s, 1),
                    'reconnects': self.reconnects, 'gaps': len(self.gaps), 'minimum': self.minimum, 'maximum': self.maximum,
                    'buffer_minutes': self.buffer_s // 60, 'transcription_device': self.transcription_device,
                    'moments': [{k: v for k, v in m.items() if k not in ('captions', 'titles_all')} for m in self.moments if m['status'] != 'discarded']}
            if full:
                data['recent_text'] = ' '.join(w['text'] for s in self.transcript[-6:] for w in s.get('words', []))[-280:]
                data['events'] = self.events[-8:]
            return data

    def note(self, message):
        with self.lock:
            self.message = message
            self.events.append({'at': datetime.now().strftime('%H:%M:%S'), 'message': message})
            self.events = self.events[-50:]

    def save(self, force=False):
        if not force and time.monotonic() - self._saved < SAVE_EVERY_S: return
        with self.lock:
            state = {'id': self.id, 'url': self.url, 'minimum': self.minimum, 'maximum': self.maximum, 'buffer_s': self.buffer_s,
                     'height': self.height, 'engine': self.engine, 'status': self.status, 'message': self.message, 'title': self.title,
                     'channel': self.channel, 'created': self.created, 'media_s': self.media_s, 'next_index': self.next_index,
                     'processed_index': self.processed_index, 'segment_times': self.segment_times, 'transcript': self.transcript,
                     'levels': self.levels[-3 * 3600:], 'moments': self.moments, 'gaps': self.gaps, 'reconnects': self.reconnects,
                     'last_detection': self.last_detection, 'events': self.events}
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.root / 'state.tmp'
        temp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8'); temp.replace(self.root / 'state.json')
        self._saved = time.monotonic()

    @classmethod
    def load(cls, folder):
        state = json.loads((Path(folder) / 'state.json').read_text(encoding='utf-8'))
        session = cls(Path(folder).parent, state['url'], state['minimum'], state['maximum'], state['buffer_s'] // 60,
                      state.get('height', 720), sid=state['id'], engine=state.get('engine', 'gpu'))
        for key in ('status', 'message', 'title', 'channel', 'created', 'media_s', 'next_index', 'processed_index', 'transcript',
                    'levels', 'moments', 'gaps', 'reconnects', 'last_detection', 'events'):
            if key in state: setattr(session, key, state[key])
        session.segment_times = {int(k): v for k, v in state.get('segment_times', {}).items()}
        session.levels = [tuple(x) for x in session.levels]
        if session.status in RUNNING:
            session.status = 'interrupted'
            session.message = 'ClipStudio se cerró durante la sesión. Los momentos guardados siguen aquí; pulsa Reanudar para seguir el directo.'
        return session

    # --- lifecycle ---------------------------------------------------------------------------------------------
    def start(self, resolver=resolve):
        self.stop_event.clear()
        self.segments.mkdir(parents=True, exist_ok=True); self.clips.mkdir(parents=True, exist_ok=True)
        self.status = 'starting'; self.note('Conectando con el directo…'); self.save(force=True)
        self.threads = [threading.Thread(target=self._capture, args=(resolver,), daemon=True, name='live-capture'),
                        threading.Thread(target=self._process, daemon=True, name='live-process')]
        for thread in self.threads: thread.start()

    def stop(self, reason='Sesión detenida. Los momentos se conservan.', status='stopped'):
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(10)
            except subprocess.TimeoutExpired: self.proc.kill()
        for thread in self.threads:
            if thread is not threading.current_thread(): thread.join(30)
        self._final_detection()
        self._model = None
        shutil.rmtree(self.segments, ignore_errors=True)   # temporary buffer; rendered moments stay
        with self.lock:
            self.status = status
        self.note(reason)
        self.save(force=True)

    def _capture(self, resolver):
        backoff = 2
        while not self.stop_event.is_set():
            if shutil.disk_usage(self.root).free < MIN_FREE_DISK_GB * 1024 ** 3:
                threading.Thread(target=self.stop, args=(f'Se detuvo para proteger el disco: quedan menos de {MIN_FREE_DISK_GB} GB libres.', 'error'), daemon=True).start()
                return
            try:
                stream = resolver(self.url, self.height)
            except LiveError as error:
                if self.media_s > 0 and 'no está transmitiendo' in str(error):
                    threading.Thread(target=self.stop, args=('El directo terminó. Los momentos detectados se conservan.', 'ended'), daemon=True).start()
                    return
                if self.media_s == 0 and self.reconnects == 0:
                    with self.lock: self.status = 'error'
                    self.note(str(error)); self.save(force=True); self.stop_event.set(); return
                self._wait_retry(backoff, str(error)); backoff = min(60, backoff * 2); continue
            with self.lock:
                self.title, self.channel = stream['title'], stream['channel']
                if self.next_index > 0: self.gaps.append(round(self.media_s, 1))
                self.status = 'live'
            self.note('Capturando el directo y buscando momentos.' if self.reconnects == 0 else f'Reconectado (intento {self.reconnects}).')
            started = time.monotonic()
            try:
                self.proc = subprocess.Popen(ffmpeg_capture_command(stream, self.segments, self.next_index), stdin=subprocess.DEVNULL,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except OSError:
                with self.lock: self.status = 'error'
                self.note('No se pudo iniciar FFmpeg.'); self.save(force=True); self.stop_event.set(); return
            while self.proc.poll() is None and not self.stop_event.is_set():
                time.sleep(1)
            if self.stop_event.is_set(): return
            with self.lock:
                existing = sorted(int(p.stem[3:]) for p in self.segments.glob('seg*.ts'))
                self.next_index = (existing[-1] + 1) if existing else self.next_index
                self.reconnects += 1; self.status = 'reconnecting'
            if time.monotonic() - started > 60: backoff = 2
            self._wait_retry(backoff, 'Se perdió la señal del directo.'); backoff = min(60, backoff * 2)

    def _wait_retry(self, seconds, why):
        with self.lock: self.status = 'reconnecting'
        self.note(f'{why} Reintentando en {seconds} s…'); self.save()
        self.stop_event.wait(seconds)

    def _closed_segments(self):
        files = sorted(self.segments.glob('seg*.ts'), key=lambda p: int(p.stem[3:]))
        running = self.proc is not None and self.proc.poll() is None
        if running and files: files = files[:-1]       # FFmpeg is still writing the newest one
        return [p for p in files if int(p.stem[3:]) > self.processed_index]

    def _process(self):
        while not self.stop_event.is_set():
            pending = self._closed_segments()
            if not pending:
                self.stop_event.wait(1); continue
            for path in pending:
                if self.stop_event.is_set(): break
                try: self._ingest(path)
                except Exception as error:   # one bad segment must not end the session
                    self.processed_index = int(path.stem[3:]); self.note(f'Se omitió un fragmento dañado ({type(error).__name__}).')
            self._evict()
            if self.media_s >= FIRST_DETECTION_S and self.media_s - self.last_detection >= DETECT_EVERY_S:
                self._detect(self.media_s)
            self.save()

    def _whisper(self):
        if self._model is None:
            import capabilities
            from faster_whisper import WhisperModel
            import os
            # The detector keeps the local AI model in VRAM, so live transcription stays on the CPU unless the
            # GPU clearly has room for both (measured: CPU transcribes a 10 s segment in ~3.5 s, enough for live).
            device, _ = capabilities.transcription_plan()
            if self.engine == 'gpu' and capabilities.free_vram_mb() < 6500: device = 'cpu'
            name = os.getenv('WHISPER_MODEL', 'small')
            self._model = WhisperModel(name, device='cuda', compute_type='float16') if device == 'cuda' else \
                WhisperModel(name, device='cpu', compute_type='int8', cpu_threads=capabilities.transcription_threads())
            self.transcription_device = 'GPU' if device == 'cuda' else 'CPU'
        return self._model

    def _ingest(self, path):
        import numpy as np
        index = int(path.stem[3:])
        audio = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                                             capture_output=True, timeout=60).stdout, dtype='<f4')
        duration = len(audio) / 16000 if len(audio) else probe_duration(path)
        start = self.media_s
        words_segments = []
        if len(audio) >= 8000:
            segments, _ = self._whisper().transcribe(audio, vad_filter=True, word_timestamps=True)
            for s in segments:
                words = [{'start': round(start + w.start, 3), 'end': round(start + w.end, 3), 'text': w.word} for w in (s.words or [])]
                if s.text.strip(): words_segments.append({'start': round(start + s.start, 3), 'end': round(start + s.end, 3), 'text': s.text, 'words': words})
        with self.lock:
            self.transcript += words_segments
            self.levels += [(round(start + i, 1), db) for i, db in enumerate(loudness(audio))]
            self.segment_times[index] = [round(start, 3), round(start + duration, 3)]
            self.media_s = start + duration
            self.processed_index = index

    def _evict(self):
        """Keep only the rolling buffer on disk; moments are rendered to their own files when detected."""
        limit = self.media_s - self.buffer_s
        for index, (start, end) in list(self.segment_times.items()):
            if end < limit:
                (self.segments / f'seg{index:06d}.ts').unlink(missing_ok=True)

    # --- detection ---------------------------------------------------------------------------------------------
    def _window(self, until):
        start = max(0.0, until - WINDOW_S, max([g for g in self.gaps if g < until], default=0.0))
        return start, until

    def _detect(self, until, final=False):
        from timeline import timed_sentences
        self.last_detection = until
        start, end = self._window(until)
        tail = 0 if final else TAIL_CONTEXT_S
        with self.lock:
            window = [s for s in self.transcript if s['start'] >= start and s['end'] <= end]
            levels = list(self.levels)
        if not window or end - start < self.minimum: return
        candidates = []
        try:
            candidates = self._ai_candidates(window, start, end, cancel=None if final else self.stop_event)
            source = 'IA local'
        except Exception as error:
            self.note(f'La IA no estuvo disponible ({type(error).__name__}); se usan los picos de audio.')
            source = None
        if source is None:
            phrases = timed_sentences(window)
            for peak in audio_peaks(levels, start, end):
                spot = peak_moment(peak, phrases, self.minimum, self.maximum, start, end + TAIL_CONTEXT_S - tail)
                if spot: candidates.append({**spot, 'title': f'Reacción intensa · minuto {int(spot["start"] // 60)}', 'titles': [],
                                            'category': 'pico de audio', 'score': min(100, round(50 + peak['db'] * 3)), 'reason': f'El volumen subió {peak["db"]:.0f} dB sobre el nivel del directo.',
                                            'evidence': '', 'source': 'Señal de audio'})
        for clip in candidates:
            if clip['end'] > end - tail: continue
            text = ' '.join(w['text'].strip() for s in window for w in s.get('words', []) if clip['start'] <= w['start'] < clip['end'])
            with self.lock:
                if any(m['status'] != 'discarded' and (overlaps(m, clip) or similar_text(m.get('text', ''), text)) for m in self.moments): continue
            self._add_moment({**clip, 'text': text, 'source': clip.get('source', source)})

    def _ai_candidates(self, window, start, end, cancel=None):
        import gpu_ai
        info = gpu_ai.status()
        if self.engine != 'gpu' or not info['available'] or not info['model_ready']:
            raise RuntimeError('motor local no disponible')
        shifted = [{**s, 'start': s['start'] - start, 'end': s['end'] - start,
                    'words': [{**w, 'start': w['start'] - start, 'end': w['end'] - start} for w in s.get('words', [])]} for s in window]
        peaks = [f'{p["start"] - start:.0f}s' for p in audio_peaks(self.levels, start, end)]
        # Measured on a real stream: extra instructions here lowered the share of grounded proposals (6 vs 8 in 6 rounds).
        context = f'Transmisión en vivo de {self.channel or "un streamer"}: {self.title}.' + (f' Picos de volumen en: {", ".join(peaks)}.' if peaks else '')
        diagnostics = []
        clips = gpu_ai.select_gpu(shifted, self.minimum, self.maximum, end - start, context=context, max_clips=3, cancel=cancel, diagnostics=diagnostics, repair=True)
        proposed = sum(d['proposed'] for d in diagnostics)
        self.note(f'Ronda de análisis (minuto {int(end // 60)}): la IA propuso {proposed} y se aceptaron {len(clips)}.')
        return [{**c, 'start': round(c['start'] + start, 3), 'end': round(c['end'] + start, 3), 'source': 'IA local'} for c in clips]

    def _final_detection(self):
        if self.media_s - self.last_detection >= 30 and self.media_s >= self.minimum:
            try: self._detect(self.media_s, final=True)
            except Exception: pass

    def _add_moment(self, clip):
        mid = uuid.uuid4().hex[:12]
        moment = {'id': mid, 'start': clip['start'], 'end': clip['end'], 'duration': round(clip['end'] - clip['start'], 1),
                  'title': clip.get('title') or 'Momento del directo', 'titles': clip.get('titles') or [], 'text': clip.get('text', ''),
                  'score': clip.get('score'), 'category': clip.get('category', ''), 'reason': clip.get('reason', ''),
                  'evidence': clip.get('evidence', ''), 'source': clip.get('source', ''), 'detected_at': datetime.now().strftime('%H:%M:%S'),
                  'status': 'rendering', 'job_id': None}
        with self.lock: self.moments.append(moment)
        self.note(f'Momento detectado: {moment["title"]}')
        try:
            self._render(moment)
            moment['status'] = 'draft'
        except Exception as error:
            moment['status'] = 'error'; moment['reason'] = f'No se pudo preparar el clip ({type(error).__name__}).'
        self.save(force=True)

    def _render(self, moment):
        """Cut [start-PAD, end+PAD] from the buffered segments into the moment's own MP4."""
        start, end = max(0.0, moment['start'] - PAD_S), min(self.media_s, moment['end'] + PAD_S)
        parts = [(i, t) for i, t in sorted(self.segment_times.items()) if t[1] > start and t[0] < end and (self.segments / f'seg{i:06d}.ts').exists()]
        if not parts: raise FileNotFoundError('segments')
        listing = self.clips / f'{moment["id"]}.txt'
        listing.write_text(''.join(f"file '{(self.segments / f'seg{i:06d}.ts').as_posix()}'\n" for i, _ in parts), encoding='utf-8')
        offset = start - parts[0][1][0]
        from app import nvenc_available
        video = ['-c:v', 'h264_nvenc', '-preset', 'p5', '-cq', '21'] if nvenc_available() else ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18']
        target = self.clips / f'{moment["id"]}.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-ss', f'{offset:.3f}', '-t', f'{end - start:.3f}',
                        *video, '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(target)], check=True, capture_output=True, timeout=300)
        listing.unlink(missing_ok=True)
        moment['file_start'] = round(start, 3)

    def moment(self, mid):
        found = next((m for m in self.moments if m['id'] == mid), None)
        if not found: raise LiveError('Momento no encontrado.')
        return found

    def moment_transcript(self, moment):
        """Transcript of the moment's MP4, in that file's own time."""
        base = moment.get('file_start', moment['start'] - PAD_S)
        end = moment['end'] + PAD_S
        result = []
        with self.lock:
            for s in self.transcript:
                # Keep only words inside the file; a phrase cut by the file edge keeps its inner words, never negative times.
                words = [{**w, 'start': round(w['start'] - base, 3), 'end': round(w['end'] - base, 3)} for w in s.get('words', [])
                         if w['start'] >= base and w['end'] <= end]
                if words:
                    result.append({'start': words[0]['start'], 'end': words[-1]['end'], 'text': ' ' + ' '.join(w['text'].strip() for w in words), 'words': words})
        return result


def probe_duration(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)], capture_output=True, text=True)
    try: return float(result.stdout.strip())
    except ValueError: return 0.0
