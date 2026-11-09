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
import json, math, os, re, shutil, subprocess, threading, time, uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlsplit

# Speed: short segments and a rolling 30 s analysis put a moment on screen well under a minute after it ends
# (measured before: 10 s segments every 120 s took 1.5-3.5 min). The window always spans a full clip plus context.
SEGMENT_S = 6
DETECT_EVERY_S = 30
WINDOW_S = 180
FIRST_DETECTION_S = 45
TAIL_CONTEXT_S = 6        # a moment must end this long before the newest audio, so reactions are not cut
MAX_TOPIC_WAIT_S = 40     # waiting for an open topic to close is capped: measured waits of 108-152 s were too slow
OVERLAP_S = 1.5           # audio carried over from the previous segment so words cut at the boundary are heard whole
DEFAULT_HEIGHT = 1080     # a 9:16 crop keeps ~56% of the width: 1080p leaves 607x1080 instead of 405x720 at 720p
LIVE_MODEL = 'large-v3-turbo'
PAD_S = 3                 # extra source kept around a moment so the editor can nudge its edges
MIN_FREE_DISK_GB = 5
SAVE_EVERY_S = 30
RUNNING = ('starting', 'live', 'reconnecting')
LANGUAGE_VOTES = 3        # 'auto' fixes the language only after this many confident detections agree in a row
_JOB = None


def kill_with_app(proc):
    """Windows: put a capture in a job object closed together with ClipStudio, so it never outlives the app.

    Before this, a forced close left FFmpeg writing segments in the background (found twice, ~4.8 GB)."""
    global _JOB
    if os.name != 'nt' or getattr(proc, '_handle', None) is None: return False
    import ctypes
    from ctypes import wintypes
    k = ctypes.windll.kernel32
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    if _JOB is None:
        class Basic(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', wintypes.DWORD),
                        ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
        class Io(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('Read', 'Write', 'Other', 'ReadBytes', 'WriteBytes', 'OtherBytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('Basic', Basic), ('Io', Io), ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
        job = k.CreateJobObjectW(None, None)
        info = Extended(); info.Basic.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not job or not k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)): return False
        _JOB = job
    try: return bool(k.AssignProcessToJobObject(_JOB, int(proc._handle)))
    except (OSError, TypeError, ValueError): return False


def kill_orphan_captures(root):
    """Stop FFmpeg captures left writing into this app's live folder by an earlier run (e.g. a forced close)."""
    if os.name != 'nt': return 0
    folder = str(Path(root).resolve()).replace("'", "''")
    script = ("$n=0; Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe'\" | Where-Object { $_.CommandLine -like '*" + folder +
              "*segments*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }; $n")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True, timeout=30)
        return int((out.stdout or '0').strip().splitlines()[-1] or 0)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return 0


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


def resolve(url, height=DEFAULT_HEIGHT, ydl_factory=None):
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


def cut_at_topic_change(clip, topics, phrases, minimum):
    """End the clip where the conversation changes topic, at the last whole phrase before the change.
    Returns None when the first topic is shorter than the minimum: mixing two topics is worse than no clip."""
    boundaries = [t['start'] for t in topics if t.get('boundary') and clip['start'] + 1 < t['start'] < clip['end'] - 1]
    if not boundaries: return clip
    change = boundaries[0]
    ends = [p['end'] for p in phrases if clip['start'] < p['end'] <= change + .3]
    if not ends or ends[-1] - clip['start'] < minimum: return None
    return {**clip, 'end': round(ends[-1], 3), 'cut_at_topic': True}


def topic_still_open(clip, topics, window_end):
    """True when the clip ends inside the newest topic and that topic reaches the live edge (still being discussed)."""
    current = next((t for t in topics if t['start'] <= clip['end'] <= t['end'] + .5), None)
    return bool(current) and current is topics[-1] and current['end'] >= window_end - TAIL_CONTEXT_S - 2 and clip['end'] >= current['end'] - 3


class LiveSession:
    def __init__(self, root, url, minimum=20, maximum=60, buffer_minutes=60, height=DEFAULT_HEIGHT, sid=None, engine='gpu', language='auto', clip_settings=None):
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
        self._tail, self._tail_end = None, None
        self.language_choice = language if language else 'auto'
        self.language = '' if self.language_choice == 'auto' else self.language_choice
        self._votes = []
        self.clip_settings = clip_settings or {}
        self.segment_wall = {}        # index -> wall clock when the segment was processed (for real latency)

    # --- state -------------------------------------------------------------------------------------------------
    def public(self, full=True):
        with self.lock:
            data = {'id': self.id, 'url': self.url, 'platform': self.platform, 'title': self.title, 'channel': self.channel,
                    'status': self.status, 'message': self.message, 'created': self.created, 'media_s': round(self.media_s, 1),
                    'reconnects': self.reconnects, 'gaps': len(self.gaps), 'minimum': self.minimum, 'maximum': self.maximum,
                    'buffer_minutes': self.buffer_s // 60, 'transcription_device': self.transcription_device,
                    'language': self.language or 'detectando…', 'language_choice': self.language_choice, 'clip_settings': self.clip_settings,
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
                     'last_detection': self.last_detection, 'events': self.events, 'language': self.language, 'language_choice': self.language_choice, 'clip_settings': self.clip_settings}
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.root / 'state.tmp'
        temp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8'); temp.replace(self.root / 'state.json')
        self._saved = time.monotonic()

    @classmethod
    def load(cls, folder):
        state = json.loads((Path(folder) / 'state.json').read_text(encoding='utf-8'))
        session = cls(Path(folder).parent, state['url'], state['minimum'], state['maximum'], state['buffer_s'] // 60,
                      state.get('height', DEFAULT_HEIGHT), sid=state['id'], engine=state.get('engine', 'gpu'))
        for key in ('status', 'message', 'title', 'channel', 'created', 'media_s', 'next_index', 'processed_index', 'transcript',
                    'levels', 'moments', 'gaps', 'reconnects', 'last_detection', 'events', 'language', 'language_choice', 'clip_settings'):
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
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                kill_with_app(self.proc)
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
            import capabilities, os, gpu_ai
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model
            # large-v3-turbo on the GPU (int8_float16, ~1.7 GB) fits next to the local AI model on an 8 GB card and
            # transcribes a 6 s segment in ~0.3 s; measured on a real stream it matched a full-context reference 93% vs
            # 86% for small on CPU. Never download it here: use it only if it is already installed.
            name = os.getenv('LIVE_WHISPER_MODEL', LIVE_MODEL)
            try:
                download_model(name, local_files_only=True)
                installed = True
            except Exception:
                installed = False
            reserve = 0 if self.engine != 'gpu' or gpu_ai.status().get('gpu_loaded') else 4400   # room the AI model will need
            device, _ = capabilities.transcription_plan()
            # int8 measured next to Qwen: +940 MB VRAM, 0.42 s per 6 s segment, same text as int8_float16 (+1.12 GB).
            if installed and device == 'cuda' and capabilities.free_vram_mb() >= 1200 + reserve:
                try:
                    self._model = WhisperModel(name, device='cuda', compute_type='int8')
                    self.transcription_device = f'GPU · {name}'
                except Exception:
                    self._model = None
            if self._model is None:
                self._model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=capabilities.transcription_threads())
                self.transcription_device = 'CPU · small' + ('' if installed else ' (instala large-v3-turbo para subtítulos más precisos)')
        return self._model

    def _ingest(self, path):
        import numpy as np
        index = int(path.stem[3:])
        audio = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                                             capture_output=True, timeout=60).stdout, dtype='<f4')
        duration = len(audio) / 16000 if len(audio) else probe_duration(path)
        start = self.media_s
        words_segments = []
        tail = self._tail if self._tail is not None and self._tail_end == round(start, 3) else np.zeros(0, dtype='<f4')
        if len(audio) >= 8000:
            # Carry the end of the previous segment so a word cut at the boundary is heard whole, keep the language
            # fixed once detected (short chunks misdetect it) and give the model the recent text as context.
            clip = np.concatenate([tail, audio]); offset = start - len(tail) / 16000
            with self.lock: prompt = ''.join(w['text'] for s in self.transcript[-12:] for w in s.get('words', []))[-200:]
            segments, info = self._whisper().transcribe(clip, vad_filter=True, word_timestamps=True, language=self.language or None,
                                                        initial_prompt=prompt or None, condition_on_previous_text=False)
            segments = list(segments)
            if not self.language and info is not None and segments:
                # One noisy chunk (music, a clip in another language) used to lock English on a Spanish stream.
                self._votes = (self._votes + [info.language])[-LANGUAGE_VOTES:] if getattr(info, 'language_probability', 0) >= .8 else []
                if len(self._votes) == LANGUAGE_VOTES and len(set(self._votes)) == 1: self.language = self._votes[0]
            for s in segments:
                words = [{'start': round(offset + w.start, 3), 'end': round(offset + w.end, 3), 'text': w.word} for w in (s.words or [])
                         if offset + w.start >= start - .05]   # words from the carried audio were already transcribed
                if words: words_segments.append({'start': words[0]['start'], 'end': words[-1]['end'], 'text': ''.join(w['text'] for w in words), 'words': words})
        self._tail = audio[-int(OVERLAP_S * 16000):].copy() if len(audio) else None
        self._tail_end = round(start + duration, 3)
        with self.lock:
            self.transcript += words_segments
            self.levels += [(round(start + i, 1), db) for i, db in enumerate(loudness(audio))]
            self.segment_times[index] = [round(start, 3), round(start + duration, 3)]
            self.segment_wall[index] = time.time()
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
        # Always room for the longest clip plus context before and after it.
        span = min(400, max(WINDOW_S, 2 * self.maximum + 30))
        start = max(0.0, until - span, max([g for g in self.gaps if g < until], default=0.0))
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
        phrases = timed_sentences(window)
        candidates, topics = [], []
        try:
            candidates, topics = self._ai_candidates(window, start, end, cancel=None if final else self.stop_event)
            source = 'IA local'
        except Exception as error:
            self.note(f'La IA no estuvo disponible ({type(error).__name__}); se usan los picos de audio.')
            source = None
        if source is None:
            for peak in audio_peaks(levels, start, end):
                spot = peak_moment(peak, phrases, self.minimum, self.maximum, start, end + TAIL_CONTEXT_S - tail)
                if spot: candidates.append({**spot, 'title': f'Reacción intensa · minuto {int(spot["start"] // 60)}', 'titles': [],
                                            'category': 'pico de audio', 'score': min(100, round(50 + peak['db'] * 3)), 'reason': f'El volumen subió {peak["db"]:.0f} dB sobre el nivel del directo.',
                                            'evidence': '', 'source': 'Señal de audio'})
        for clip in candidates:
            clip = cut_at_topic_change(clip, topics, phrases, self.minimum)
            if clip is None: continue
            if clip['end'] > end - tail: continue
            # Wait while the conversation is still on the clip's topic: proposing it now would cut it mid-thought.
            if (not final and topic_still_open(clip, topics, end) and clip['end'] - clip['start'] < self.maximum - 1
                    and end - clip['end'] < MAX_TOPIC_WAIT_S): continue
            text = ' '.join(w['text'].strip() for s in window for w in s.get('words', []) if clip['start'] <= w['start'] < clip['end'])
            with self.lock:
                if any(m['status'] != 'discarded' and (overlaps(m, clip) or similar_text(m.get('text', ''), text)) for m in self.moments): continue
            if source:
                clip = {**clip, **self._viral_title(text, clip)}
            self._add_moment({**clip, 'text': text, 'source': clip.get('source', source)})

    def _viral_title(self, text, clip):
        """Hook-first titles from what is actually said; the analyst's own title stays as an alternative."""
        try:
            import viral
            result = viral.generate(text, speaker=self.channel, context=self.title, cancel=self.stop_event)
        except Exception:
            return {}
        if not result: return {}
        alternatives = [t for t in result['titles'] + [clip.get('title')] + list(clip.get('titles') or []) if t]
        return {'title': result['title'], 'titles': list(dict.fromkeys(alternatives))[:5], 'claim': result['claim'], 'claim_kind': result['kind']}

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
        diagnostics, topics = [], []
        clips = gpu_ai.select_gpu(shifted, self.minimum, self.maximum, end - start, context=context, max_clips=3, cancel=cancel,
                                  diagnostics=diagnostics, topic_ranges=topics, repair=True)
        proposed = sum(d['proposed'] for d in diagnostics)
        self.note(f'Ronda de análisis (minuto {int(end // 60)}): la IA propuso {proposed} y se aceptaron {len(clips)}.')
        moved = lambda item: {**item, 'start': round(item['start'] + start, 3), 'end': round(item['end'] + start, 3)}
        return [{**moved(c), 'source': 'IA local'} for c in clips], [moved(t) for t in topics]

    def _final_detection(self):
        if self.media_s - self.last_detection >= 15 and self.media_s >= self.minimum:
            try: self._detect(self.media_s, final=True)
            except Exception: pass

    def _ready_after(self, moment_end):
        """Seconds between processing the segment where the moment ended and the clip being ready."""
        index = next((i for i, (a, b) in sorted(self.segment_times.items()) if b >= moment_end), None)
        wall = self.segment_wall.get(index)
        return round(time.time() - wall, 1) if wall else None

    def _add_moment(self, clip):
        mid = uuid.uuid4().hex[:12]
        moment = {'id': mid, 'start': clip['start'], 'end': clip['end'], 'duration': round(clip['end'] - clip['start'], 1),
                  'title': clip.get('title') or 'Momento del directo', 'titles': clip.get('titles') or [], 'text': clip.get('text', ''),
                  'score': clip.get('score'), 'category': clip.get('category', ''), 'reason': clip.get('reason', ''),
                  'evidence': clip.get('evidence', ''), 'claim': clip.get('claim', ''), 'source': clip.get('source', ''), 'cut_at_topic': bool(clip.get('cut_at_topic')),
                  'detected_at': datetime.now().strftime('%H:%M:%S'), 'status': 'rendering', 'job_id': None}
        with self.lock: self.moments.append(moment)
        self.note(f'Momento detectado: {moment["title"]}')
        try:
            self._render(moment)
            self._prepare_layout(moment)
            moment['status'] = 'draft'
            moment['ready_after_s'] = self._ready_after(moment['end'])
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
        # High quality on purpose: this file is the source the 9:16 export crops and upscales from.
        video = ['-c:v', 'h264_nvenc', '-preset', 'p5', '-tune', 'hq', '-rc', 'vbr', '-cq', '18', '-b:v', '0'] if nvenc_available() else ['-c:v', 'libx264', '-preset', 'fast', '-crf', '16']
        target = self.clips / f'{moment["id"]}.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-ss', f'{offset:.3f}', '-t', f'{end - start:.3f}',
                        *video, '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(target)], check=True, capture_output=True, timeout=300)
        listing.unlink(missing_ok=True)
        moment['file_start'] = round(start, 3)

    def _prepare_layout(self, moment):
        """«Cámara + juego»: find the camera and the game motion now, so the moment opens ready in the editor."""
        settings = self.clip_settings or {}
        if not (settings.get('framing') == 'stack' or settings.get('auto_stack', True)): return
        try:
            import layout
            target = self.clips / f'{moment["id"]}.mp4'
            base = moment.get('file_start', moment['start'] - PAD_S)
            start, end = max(0.0, moment['start'] - base), moment['end'] - base
            overlay = layout.detect_overlay(target, end + PAD_S, samples=24)
            result = layout.analyze(target, round(start, 3), round(end, 3), overlay)
            (self.clips / f'{moment["id"]}.layout.json').write_text(json.dumps(result), encoding='utf-8')
        except Exception:
            pass        # the editor computes it when the moment is opened

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
