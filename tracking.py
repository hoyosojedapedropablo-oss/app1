"""Local face tracking for vertical reframing. Faces only, no identity recognition.

v2 (Nov 2026), after measuring v1 on real clips (max 156 px jump in one frame, hundreds of visible steps):
- Faces come from OpenCV's YuNet detector (eyes, nose and mouth landmarks), which ignores hands and objects; the old
  Haar cascades are only a fallback when the model file is missing. Tiny faces (background, game footage) are dropped.
- Detection runs at 8 samples/s. Faces are linked into persons so the editor can follow a chosen person or, in
  "auto", whoever is speaking (mouth motion + voice activity, with a stable lead before switching).
- The camera path is built separately (build_path): a dead zone avoids needless moves, a clip whose subject fits in
  one window stays static, a zero-phase smoothing pass gives eased motion without lag, a speed limit per motion mode
  prevents sudden pans, and FFmpeg receives one position per output frame instead of 12 per second.

v3 (Nov 2026), after a real clip opened on a non-speaking person (the biggest face: someone close to the lens, looking
down) and only reached the speaker 2.5 s later:
- Who to follow is decided for the whole shot at once (choose_speakers), so the clip starts on the person who is
  speaking from its first frame instead of catching up after a delay.
- Only faces that show speech count: mouth motion while a voice is heard, weighted by how frontal the face is (eye
  contact with the camera). A person who just moves, without talking, does not pull the camera.
- People close to the camera win over people in the background: a face clearly smaller than the biggest one in the
  frame barely counts, and switching to it costs much more. Switching between two people talking side by side (a
  conversation) is easier than switching to someone far away.
- With nobody speaking yet, the clip starts on the most central, frontal face near the camera.
- The camera keeps the followed face closer to the centre (smaller dead zone and still-camera window).
"""
import hashlib, json, math, subprocess
from pathlib import Path
import numpy as np

VERSION = 3
SAMPLE_FPS = 8
PATH_FPS = 30
MODEL = Path(__file__).resolve().parent / 'models' / 'face_detection_yunet_2023mar.onnx'
MIN_FACE = .06            # faces shorter than 6% of the frame height are ignored (background people, thumbnails)
ZOOM = {'soft': .50, 'balanced': .60, 'close': .72}   # share of the 9:16 height used by the video band
# tau: smoothing time constant (s); speed: max pan per second as a share of the visible width; dead: half-width of the
# zone (share of the visible width) the face may move in before the camera follows.
MOTION = {'smooth': dict(tau=.9, speed=.4, dead=.16), 'balanced': dict(tau=.45, speed=.9, dead=.12), 'fast': dict(tau=.22, speed=1.6, dead=.08)}
STILL = .24               # a subject that always stays within this share of the visible width keeps the camera still
NEAR = .62                # a face smaller than this share of the biggest face in the frame is background


def key(start, end):
    return hashlib.sha256(f'{VERSION}:{start:.6f}:{end:.6f}'.encode()).hexdigest()[:24]


def band_height(framing, zoom='balanced'):
    return 1920 if framing == 'crop' else int(round(1920 * ZOOM.get(zoom, ZOOM['balanced']) / 2) * 2)


def geometry(width, height, framing, zoom='balanced'):
    """Scaled source size (even) and the visible band for a 1080x1920 canvas."""
    band = band_height(framing, zoom)
    scale = max(1080 / width, band / height)
    return dict(band=band, scale=scale, sw=max(1080, math.ceil(width * scale / 2) * 2), sh=max(band, math.ceil(height * scale / 2) * 2))


def static_filter(framing, zoom, focus_x, focus_y):
    """FFmpeg geometry without tracking; mirrors the editor preview (object-fit: cover + object-position)."""
    if framing == 'fit':
        return 'scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black'
    band = band_height(framing, zoom)
    crop = f'scale=1080:{band}:force_original_aspect_ratio=increase,crop=1080:{band}:(iw-ow)*{focus_x / 100}:(ih-oh)*{focus_y / 100}'
    return crop if band == 1920 else crop + f',pad=1080:1920:0:{(1920 - band) // 2}:color=black'


def position(cx, cy, width, height):
    """Legacy helper: crop position (%) that centres a point in a full 9:16 crop."""
    scale = max(1080 / width, 1920 / height); w = round(width * scale); h = round(height * scale)
    x = 50 if w == 1080 else 100 * (cx * scale - 540) / (w - 1080)
    y = 50 if h == 1920 else 100 * (cy * scale - 1920 * .35) / (h - 1920)
    return max(0, min(100, x)), max(0, min(100, y))


def face_front(f):
    """0..1: how much a YuNet face looks at the camera (nose centred between the eyes, eyes level and wide apart)."""
    w = max(1.0, float(f[2])); rx, ry, lx, ly, nx = (float(v) for v in (f[4], f[5], f[6], f[7], f[8]))
    eyes = math.hypot(lx - rx, ly - ry)
    if eyes < 1: return 0.0
    turn = abs(nx - (rx + lx) / 2) / eyes                    # 0 facing the camera, ~.5 and more in profile
    tilt = abs(ly - ry) / eyes
    wide = min(1.0, eyes / w / .38)                            # eyes close together: head turned away
    return round(max(0.0, 1 - 1.6 * turn) * max(0.0, 1 - tilt) * wide, 3)


def make_detector(width, height, with_front=False):
    """Return detect(frame_bgr) -> [(x, y, w, h, score)].

    CONTRACT (used by tracking.py and by layout.py in three places): every face is exactly 5 values. With
    `with_front=True` (face tracking only) a 6th value is added: how much the face looks at the camera. Never change
    the default shape: in Nov 2026 a 6th value broke «Cámara + juego» for every clip (see docs/ERRORES_CONOCIDOS.md, E-01)."""
    import cv2
    if MODEL.exists() and hasattr(cv2, 'FaceDetectorYN'):
        net = cv2.FaceDetectorYN.create(str(MODEL), '', (width, height), .72, .3, 50)
        def detect(frame):
            _, faces = net.detect(frame)
            if faces is None: return []
            return [(float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[14])) + ((face_front(f),) if with_front else ()) for f in faces]
        return detect
    frontal = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml')
    if frontal.empty(): raise ValueError('Falta el detector de rostros. Vuelve a iniciar INICIAR_WINDOWS.')
    def detect(frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return [(float(x), float(y), float(w), float(h), 1.0) + ((1.0,) if with_front else ()) for x, y, w, h in frontal.detectMultiScale(gray, 1.1, 5, minSize=(28, 28))]
    return detect


def scene_cuts(source, start, duration, threshold=10):
    """Frame-accurate hard cuts from FFmpeg's scene detector (measured: 2 real cuts where a histogram test saw 8)."""
    run = subprocess.run(['ffmpeg', '-hide_banner', '-v', 'info', '-ss', str(start), '-t', str(duration), '-i', str(source), '-an',
                          '-vf', f'scale=192:-2,scdet=threshold={threshold}', '-f', 'null', '-'], capture_output=True, text=True, errors='replace')
    cuts = []
    for line in run.stderr.splitlines():
        if 'lavfi.scd.time:' in line:
            try: cuts.append(round(float(line.split('lavfi.scd.time:')[1].split()[0]), 3))
            except (ValueError, IndexError): continue
    return [c for c in cuts if 0 < c < duration]


def analyze(source, start, end, progress):
    import cv2
    cv2.setNumThreads(2)
    from faster_whisper.vad import get_speech_timestamps, VadOptions
    duration = end - start
    audio = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-t', str(duration), '-i', str(source), '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'], capture_output=True)
    speech = []
    if audio.returncode == 0 and audio.stdout:
        wave = np.frombuffer(audio.stdout, dtype='<f4')
        speech = [(s['start'] / 16000, s['end'] / 16000) for s in get_speech_timestamps(wave, VadOptions(min_speech_duration_ms=120, min_silence_duration_ms=150))]
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened(): raise ValueError('No se pudo abrir el video para seguir rostros.')
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH); height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT); cap.release()
    if not width or not height: raise ValueError('No se pudieron leer las dimensiones del video.')
    sw = max(2, int(min(640, width) / 2) * 2); shh = max(2, int(height * sw / width / 2) * 2); ratio = sw / width
    detect = make_detector(sw, shh, with_front=True)
    frames = subprocess.Popen(['ffmpeg', '-v', 'error', '-threads', '2', '-ss', str(start), '-t', str(duration), '-i', str(source), '-an',
                               '-vf', f'fps={SAMPLE_FPS},scale={sw}:{shh}', '-pix_fmt', 'bgr24', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    tracks = {}; next_id = 0; samples = []; face_frames = speaking_frames = 0
    cuts = scene_cuts(source, start, duration); pending_cuts = list(cuts)
    size = sw * shh * 3
    try:
        for index in range(math.ceil(duration * SAMPLE_FPS)):
            t = index / SAMPLE_FPS
            raw = frames.stdout.read(size)
            if len(raw) != size: break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(shh, sw, 3)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if pending_cuts and pending_cuts[0] <= t:
                while pending_cuts and pending_cuts[0] <= t: pending_cuts.pop(0)
                tracks = {}   # a new shot: faces before the cut are other people or other places
            faces = [f for f in detect(frame) if f[3] >= MIN_FACE * shh and .55 <= f[2] / max(1, f[3]) <= 1.6]
            speaking = any(a <= t <= b for a, b in speech)
            visible = {}; used = set()
            for x, y, w, h, score, *rest in sorted(faces, key=lambda f: f[2] * f[3], reverse=True):
                center = np.array([x + w / 2, y + h / 2])
                # Link to the nearest recent face of this person; a person may vanish for up to 3 s.
                near = [(float(np.linalg.norm(center - tr['center'])), ident) for ident, tr in tracks.items()
                        if ident not in used and t - tr['time'] <= 3 and np.linalg.norm(center - tr['center']) < max(w, tr['width']) * 1.4]
                ident = min(near)[1] if near else next_id
                if not near: next_id += 1
                used.add(ident)
                x0, y0 = max(0, int(x)), max(0, int(y)); x1, y1 = min(sw, int(x + w)), min(shh, int(y + h))
                patch = cv2.resize(gray[y0:y1, x0:x1], (64, 64)).astype(np.float32) if x1 > x0 + 4 and y1 > y0 + 4 else np.zeros((64, 64), np.float32)
                patch = (patch - patch.mean()) / (patch.std() + 10)
                old = tracks.get(ident); activity = 0.0
                if old is not None and t - old['time'] <= .3:
                    diff = np.abs(patch - old['patch']); mouth = float(diff[39:58, 12:52].mean()); upper = float(diff[10:30, 12:52].mean())
                    activity = max(0.0, mouth - upper * .8)
                activity = .55 * activity + .45 * (old['activity'] if old else 0)
                visible[ident] = dict(center=center, width=w, time=t, patch=patch, activity=activity, front=rest[0] if rest else 1.0,
                                      box=(x / ratio, y / ratio, w / ratio, h / ratio))
            tracks = {i: tr for i, tr in tracks.items() if t - tr['time'] <= 3}; tracks.update(visible)
            if visible:
                face_frames += 1
                if speaking: speaking_frames += 1
            samples.append(dict(t=round(t, 3), active=None, speech=speaking,
                                faces=[dict(id=i, x=round(v['box'][0], 1), y=round(v['box'][1], 1), w=round(v['box'][2], 1), h=round(v['box'][3], 1),
                                            act=round(float(v['activity']), 4), front=round(float(v['front']), 3)) for i, v in visible.items()]))
            if index % SAMPLE_FPS == 0: progress(round(100 * t / duration))
    finally:
        frames.stdout.close()
        if frames.poll() is None: frames.terminate()
        try: frames.wait(timeout=5)
        except subprocess.TimeoutExpired: frames.kill(); frames.wait()
    if not face_frames: raise ValueError('No se detectaron rostros en este clip. Usa el encuadre manual; prueba un fragmento donde se vean las caras.')
    merge_tracks(samples)
    changes = choose_speakers(samples, cuts, width, height)
    persons = summarize_persons(samples, width)
    result = dict(samples=samples, persons=persons, cuts=cuts, width=width, height=height, face_frames=face_frames, speaking_frames=speaking_frames,
                  speaker_changes=changes, detector='YuNet' if MODEL.exists() else 'Haar',
                  method='Rostros (YuNet), movimiento de boca con voz, mirada a cámara y cercanía. Estimación visual; revisa los cambios de hablante.')
    path = build_path(result)
    result['points'] = [dict(time=round(i / PATH_FPS, 3), x=x, y=path['y']) for i, x in enumerate(path['x'])][::max(1, PATH_FPS // SAMPLE_FPS)]
    return result


def merge_tracks(samples):
    """Join tracks of the same person that the detector lost for a moment: never on screen at the same time and
    reappearing near where the other one was. Rewrites face ids in place so a chosen person keeps being followed."""
    info = {}
    for i, s in enumerate(samples):
        for f in s['faces']:
            d = info.setdefault(f['id'], dict(frames=set(), xs=[], ws=[]))
            d['frames'].add(i); d['xs'].append(f['x'] + f['w'] / 2); d['ws'].append(f['w'])
    order = sorted(info, key=lambda k: len(info[k]['frames']), reverse=True)
    alias = {}
    for k in order:
        for root in order:
            if root == k: break
            if alias.get(root, root) != root: continue
            a, b = info[root], info[k]
            near = abs(np.median(a['xs']) - np.median(b['xs'])) < 1.5 * max(np.median(a['ws']), np.median(b['ws']))
            if near and not (a['frames'] & b['frames']):
                alias[k] = root; a['frames'] |= b['frames']; a['xs'] += b['xs']; a['ws'] += b['ws']; break
    for s in samples:
        for f in s['faces']: f['id'] = alias.get(f['id'], f['id'])
        if s.get('active') is not None: s['active'] = alias.get(s['active'], s['active'])
    return samples


def choose_speakers(samples, cuts, width, height):
    """Sets samples[i]['active'] to the person to follow and returns the number of speaker changes.

    Each shot (between scene cuts) is solved as a whole with a Viterbi pass over its persons: every sample rewards the
    person who shows speech (mouth motion while a voice is heard, more when facing the camera) and, much less, the
    face that is near the camera, frontal and central; changing person has a cost, lower between two people side by
    side (a conversation) and higher towards the background. Looking at the whole shot means the clip starts on the
    speaker from its first frame and a switch lands when that person starts talking, not half a second later."""
    n = len(samples); changes = 0
    if not n: return 0
    cut_index = sorted({min(n, max(0, int(round(c * SAMPLE_FPS)))) for c in cuts or []} - {0, n})
    for a, b in zip([0] + cut_index, cut_index + [n]):
        shot = samples[a:b]
        ids = sorted({f['id'] for s in shot for f in s['faces']})
        if not ids: continue
        col = {k: j for j, k in enumerate(ids)}; P = len(ids); m = len(shot)
        act = np.zeros((m, P)); seen = np.zeros((m, P), bool); prior = np.zeros((m, P)); near = np.zeros((m, P))
        for i, s in enumerate(shot):
            if not s['faces']: continue
            hmax = max(f['h'] for f in s['faces'])
            for f in s['faces']:
                j = col[f['id']]; seen[i, j] = True
                prom = f['h'] / max(1.0, hmax); front = f.get('front', 1.0)
                cx = f['x'] + f['w'] / 2; cy = f['y'] + f['h'] / 2
                central = 1 - min(1.0, abs(cx - width / 2) / (width / 2))
                cut_off = f['x'] < 2 or f['x'] + f['w'] > width - 2 or f['y'] + f['h'] > height - 2 or cy > height * .82
                near[i, j] = 1.0 if prom >= NEAR else .2
                act[i, j] = f.get('act', 0.0) if s.get('speech') else 0.0
                prior[i, j] = (.06 * min(1.0, prom) + .05 * front + .07 * central - (.05 if cut_off else 0)) * near[i, j]
                front_w = .6 + .4 * front
                act[i, j] *= front_w * near[i, j] * min(1.0, prom) ** 2
        # Talking is judged over ~1 s (centred), so one noisy sample does not decide anything.
        k = np.ones(7) / 7
        talk = np.stack([np.convolve(act[:, j], k, mode='same') for j in range(P)], axis=1) if m >= 7 else act
        score = np.where(seen, 4 * talk + prior, -.35)
        # Switch costs between persons: cheap for a neighbour of similar size, expensive towards the background.
        pos = {}; size = {}; closeness = {}
        for j, ident in enumerate(ids):
            xs = [f['x'] + f['w'] / 2 for s in shot for f in s['faces'] if f['id'] == ident]
            ws = [f['w'] for s in shot for f in s['faces'] if f['id'] == ident]
            pos[j] = float(np.median(xs)); size[j] = float(np.median(ws)); closeness[j] = float(near[seen[:, j], j].mean())
        cost = np.zeros((P, P))
        for i in range(P):
            for j in range(P):
                if i == j: continue
                beside = abs(pos[i] - pos[j]) < 2.6 * max(size[i], size[j]) and min(size[i], size[j]) / max(size[i], size[j]) > .6
                cost[i, j] = (1.1 if beside else 1.8) + (2.5 if closeness[j] < .5 else 0)
        total = score[0].copy(); back = np.zeros((m, P), int)
        for i in range(1, m):
            options = total[:, None] - cost              # options[from, to]
            back[i] = options.argmax(axis=0)
            total = options.max(axis=0) + score[i]
        state = int(total.argmax()); chosen = [0] * m
        for i in range(m - 1, -1, -1):
            chosen[i] = state; state = int(back[i, state])
        for i, s in enumerate(shot):
            s['active'] = ids[chosen[i]] if seen[i, chosen[i]] else None
            if i and chosen[i] != chosen[i - 1]: changes += 1
    return changes


def summarize_persons(samples, width):
    """Persons seen in at least 10% of the samples, named by their order from left to right."""
    merge_tracks(samples)
    seen = {}
    for s in samples:
        for f in s['faces']: seen.setdefault(f['id'], []).append(f['x'] + f['w'] / 2)
    total = max(1, len(samples))
    keep = sorted((float(np.median(xs)), ident, len(xs)) for ident, xs in seen.items() if len(xs) >= .1 * total)
    names = {1: ['principal'], 2: ['izquierda', 'derecha'], 3: ['izquierda', 'centro', 'derecha']}.get(len(keep))
    persons = []
    for n, (cx, ident, count) in enumerate(keep):
        side = names[n] if names else f'{n + 1}.ª desde la izquierda'
        persons.append(dict(id=ident, label=f'Persona {n + 1} · {side}', presence=round(count / total, 2)))
    return persons


def _target_centres(result, person):
    """Horizontal centre (source px) of the followed face at every sample, held through gaps."""
    xs = []
    for s in result['samples']:
        want = s['active'] if person in (None, 'auto') else int(person)
        face = next((f for f in s['faces'] if f['id'] == want), None)
        if face is None and person not in (None, 'auto'):
            # The chosen person is not in this shot: frame whoever is speaking instead of an empty spot.
            face = next((f for f in s['faces'] if f['id'] == s['active']), None)
        xs.append(face['x'] + face['w'] / 2 if face else None)
    known = [x for x in xs if x is not None]
    if not known: return None
    last = known[0]
    for i, x in enumerate(xs):
        if x is None: xs[i] = last
        else: last = x
    return np.array(xs, dtype=float)


def _smooth(values, tau, fps):
    """Zero-phase exponential smoothing (forward then backward): eased motion without lag."""
    a = 1 - math.exp(-1 / (tau * fps))
    out = np.array(values, dtype=float)
    for _ in range(2):
        for i in range(1, len(out)): out[i] = out[i - 1] + a * (out[i] - out[i - 1])
        for i in range(len(out) - 2, -1, -1): out[i] = out[i + 1] + a * (out[i] - out[i + 1])
    return out


def build_path(result, person='auto', motion='balanced', framing='crop', zoom='balanced', focus_y=50):
    """Camera path at PATH_FPS as object-position percentages (same numbers drive the preview and the export)."""
    W, H = result['width'], result['height']
    g = geometry(W, H, framing, zoom)
    duration = len(result['samples']) / SAMPLE_FPS
    n = max(2, int(math.ceil(duration * PATH_FPS)) + 1)
    base = dict(fps=PATH_FPS, y=focus_y, person=person or 'auto', motion=motion, framing=framing, zoom=zoom)
    centres = _target_centres(result, person)
    extra = g['sw'] - 1080
    if centres is None or extra <= 0:
        return dict(base, x=[50.0] * n, static=True)
    m = MOTION.get(motion, MOTION['balanced'])
    visible = 1080 / g['scale']                 # visible width in source pixels
    half = visible / 2
    lo, hi = half, W - half
    t_s = np.arange(len(centres)) / SAMPLE_FPS; t = np.arange(n) / PATH_FPS
    cut_times = [c for c in result.get('cuts', []) if 0 < c < duration]
    bounds = [0.0] + cut_times + [duration + 1]
    cam = np.empty(n); static = True
    limit = m['speed'] * visible / PATH_FPS
    for a, b in zip(bounds, bounds[1:]):
        shot = (t >= a) & (t < b); samples_in = (t_s >= a) & (t_s < b)
        if not shot.any(): continue
        xs = centres[samples_in] if samples_in.any() else centres[[min(len(centres) - 1, int(a * SAMPLE_FPS))]]
        # Subject always fits one window in this shot (with margin): keep the camera still.
        if xs.max() - xs.min() <= visible * STILL:
            cam[shot] = (xs.max() + xs.min()) / 2
            continue
        static = False
        # Dead zone: recentre only when the face leaves the central band; this turns small head motion into no motion.
        held = np.empty(len(xs)); c = xs[0]
        for i, x in enumerate(xs):
            if abs(x - c) > m['dead'] * visible: c = x
            held[i] = c
        part = np.interp(t[shot], t_s[samples_in] if samples_in.any() else [a], held)
        part = _smooth(part, m['tau'], PATH_FPS)
        for i in range(1, len(part)): part[i] = part[i - 1] + max(-limit, min(limit, part[i] - part[i - 1]))
        cam[shot] = _smooth(part, .08, PATH_FPS)      # remove kinks left by the speed limit
    if cut_times: static = static and len(set(np.round(cam, 1))) == 1
    cam = np.clip(cam, lo, hi)
    px = np.clip(cam * g['scale'] - 540, 0, extra)
    # FFmpeg crops yuv420p video at even offsets only; the export and the preview both round each frame's offset to
    # the nearest even pixel of the scaled width ('extra'), so they show the same pixels.
    return dict(base, x=[round(float(v), 4) for v in px / extra * 100], static=static, extra=extra)


def commands(path, cmd_file, duration, fps, width, height):
    """One crop position per output frame, linearly interpolated from the path; returns the FFmpeg filter."""
    g = geometry(width, height, path['framing'], path.get('zoom', 'balanced'))
    extra_x = g['sw'] - 1080; extra_y = g['sh'] - g['band']
    y = round(extra_y * path.get('y', 50) / 100)
    src = np.arange(len(path['x'])) / path['fps']
    lines = []
    for t in np.arange(0, duration, 1 / fps):
        x = int(round(float(np.interp(t, src, path['x'])) * extra_x / 200)) * 2   # even offset, as FFmpeg applies it
        lines.append(f'{t:.6f} crop@follow x {x};')
    Path(cmd_file).write_text('\n'.join(lines), encoding='utf-8')
    chain = f'setpts=PTS-STARTPTS,sendcmd=f={Path(cmd_file).name},scale={g["sw"]}:{g["sh"]},crop@follow=1080:{g["band"]}:0:{y}'
    return chain if g['band'] == 1920 else chain + f',pad=1080:1920:0:{(1920 - g["band"]) // 2}:color=black'
