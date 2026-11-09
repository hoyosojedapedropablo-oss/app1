"""'Cámara + juego' layout: the streamer's camera on top, the game (or what they react to) below, in 1080x1920.

How it works, all local:
- detect_overlay(): samples frames across the whole video, finds a face that stays in the same place (the facecam
  overlay of a stream) and then the overlay's rectangle from edges that persist over time (the overlay border, or the
  seam between camera and game, is in the same place in every frame while the game moves underneath).
- The camera rectangle is cropped to the top panel (40-50 % of the height, depending on its shape) and kept centred
  on the face; it is enlarged with Lanczos and a light sharpening, because a stream's camera is usually small.
- The game area is found the same way: a full-height sidebar or window edge bounds it, otherwise it is the whole frame.
- The bottom panel is a crop of the game area at its full height. It never shows the camera a second time when it can avoid
  it, and follows the action (motion) gently: a strong pull towards the centre of the screen (crosshair, character),
  a dead zone, zero-phase smoothing and a speed limit, as in the face tracking.
The editor preview draws the same two rectangles on a canvas, so the preview and the export match.
"""
import hashlib, json, math, subprocess
from pathlib import Path
import numpy as np

VERSION = 1
DETECTOR_VERSION = 3          # 2: steady/busy seam search (Spreen) · 3: needs real fixed edges (one-camera IRL streams)
CANVAS_W, CANVAS_H = 1080, 1920
TOP_MIN, TOP_MAX = 768, 960        # camera panel: 40-50 % of the height
SEAM = 6                           # dark line between camera and game (px)
GAME_FPS = 4                       # motion samples per second for the game focus
PATH_FPS = 30
MIN_FACE = .035                    # a stream's camera face can be small (3.5 % of the frame height)
MOTION = {'smooth': dict(tau=1.4, speed=.22, dead=.16), 'balanced': dict(tau=.9, speed=.4, dead=.12), 'fast': dict(tau=.45, speed=.8, dead=.08)}
CENTRE_PULL = .55                  # share of the target that stays on the screen centre (where games put the action)


def key(start, end):
    return hashlib.sha256(f'layout{VERSION}:{start:.6f}:{end:.6f}'.encode()).hexdigest()[:24]


def _probe(source):
    import cv2
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened(): raise ValueError('No se pudo abrir el video.')
    w, h = cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    n, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS) or 30
    cap.release()
    if not w or not h: raise ValueError('No se pudieron leer las dimensiones del video.')
    return int(w), int(h), (n / fps if n and fps else 0)


def _frame(source, t, sw, sh):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', str(source), '-frames:v', '1', '-an', '-vf', f'scale={sw}:{sh}',
                          '-pix_fmt', 'bgr24', '-f', 'rawvideo', '-'], capture_output=True, timeout=60).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(sh, sw, 3) if len(raw) == sw * sh * 3 else None


def _clusters(faces, frames):
    """Group face boxes (cx, cy, w, h, frame index) that sit in the same place; most persistent first."""
    groups = []
    for f in sorted(faces, key=lambda f: -f[3]):
        for g in groups:
            cx, cy, w = np.median([x[0] for x in g]), np.median([x[1] for x in g]), np.median([x[2] for x in g])
            if abs(f[0] - cx) < .45 * w and abs(f[1] - cy) < .45 * w and .6 < f[2] / w < 1.6: g.append(f); break
        else: groups.append([f])
    return sorted(groups, key=lambda g: -len({x[4] for x in g}))


def _border(profile, lo, hi, fallback, edge, strength=.32):
    """Strongest persistent line in profile[lo:hi]; the frame edge when the camera touches it."""
    lo, hi = max(0, int(lo)), min(len(profile), int(hi)); fallback = int(round(fallback))   # used as a slice index
    if hi - lo < 3: return fallback
    i = lo + int(np.argmax(profile[lo:hi]))
    if profile[i] >= strength: return i
    return edge if min(abs(edge - lo), abs(edge - hi)) < 2 or lo <= edge <= hi else fallback


def _seam(edge, var, lo, hi, outside, strength=.2, contrast=.45):
    # contrast measured: ~.9 at Spreen's real border; TheDonato's animated sidebar art gave a false .26.
    """Border where the picture changes from steady (the camera's room) to busy (the game), on the camera's side.

    Measured on Spreen (Minecraft): the room behind the streamer barely changes, so the edge of a shelf is as
    persistent as the overlay border and won the old strongest-line search. Requiring the game's motion right
    outside the line and calm right inside picks the real border. `outside` is -1 (left/top) or +1 (right/bottom)."""
    lo, hi = max(11, int(lo)), min(len(edge) - 11, int(hi)); best = None
    for i in range(lo, hi):
        if edge[i] < strength: continue
        out = var[i + 2:i + 10].mean() if outside > 0 else var[i - 9:i - 1].mean()
        ins = var[i - 9:i - 1].mean() if outside > 0 else var[i + 2:i + 10].mean()
        c = (out - ins) / (out + ins + 1)
        if c >= contrast and (best is None or edge[i] * c > best[0]): best = (edge[i] * c, i)
    return None if best is None else best[1]


def _lines(profile, strength=.5, limit=8):
    """Positions of lines present along most of the frame in most samples (local maxima)."""
    found = [i for i in range(4, len(profile) - 4) if profile[i] >= strength and profile[i] == profile[i - 3:i + 4].max()]
    return sorted(sorted(found, key=lambda i: -profile[i])[:limit])


def _content_region(ex, ey, cam, sw, sh):
    """The game / reacted video area. When the layout has a full-height sidebar or a window (TheDonato: game on the
    left, camera and artwork on a sidebar), the largest area bounded by persistent full-length lines that leaves the
    camera out; otherwise the whole frame (a camera drawn on top of the game)."""
    xs = [0] + _lines(ex.mean(axis=0)) + [sw]; ys = [0] + _lines(ey.mean(axis=1)) + [sh]
    cl, ct, cr, cb = cam; cam_area = max(1, (cr - cl) * (cb - ct)); best = None
    for i, x0 in enumerate(xs):
        for x1 in xs[i + 1:]:
            for j, y0 in enumerate(ys):
                for y1 in ys[j + 1:]:
                    area = (x1 - x0) * (y1 - y0)
                    if area < .4 * sw * sh or (x0, y0, x1, y1) == (0, 0, sw, sh): continue
                    overlap = max(0, min(x1, cr) - max(x0, cl)) * max(0, min(y1, cb) - max(y0, ct))
                    if overlap <= .1 * cam_area and (best is None or area > best[0]): best = (area, x0, y0, x1, y1)
    return (0, 0, sw, sh) if best is None else best[1:]


def detect_overlay(source, duration=None, samples=40, progress=lambda v: None, start=0.0):
    """Return the facecam overlay {'found', 'x','y','w','h' (source px), 'face', 'presence', 'kind'}."""
    import cv2
    from tracking import make_detector
    W, H, probed = _probe(source)
    duration = duration or probed
    sw = 640; sh = max(2, int(round(H * sw / W / 2)) * 2); ratio = W / sw
    detect = make_detector(sw, sh)
    # The whole video by default; a clip's own range when the camera moved there (start > 0 or a short duration).
    times = (np.linspace(start + duration * .03, start + duration * .97, samples) if duration > 4 else [start + duration / 2])
    faces = []; edges_x = np.zeros((sh, sw), np.float32); edges_y = np.zeros((sh, sw), np.float32); used = 0; grays = []
    for i, t in enumerate(times):
        frame = _frame(source, float(t), sw, sh)
        progress(round(80 * (i + 1) / len(times)))
        if frame is None: continue
        used += 1
        for x, y, w, h, score in detect(frame):
            if h >= MIN_FACE * sh and .55 <= w / max(1, h) <= 1.6: faces.append((x + w / 2, y + h / 2, w, h, i))
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32)
        grays.append(gray.astype(np.uint8))
        edges_x += np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)) > 40
        edges_y += np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)) > 40
    none = dict(found=False, kind='none', detector=DETECTOR_VERSION, width=W, height=H, presence=0)
    if not used or not faces: return none
    groups = _clusters(faces, used)
    group = groups[0]; presence = len({f[4] for f in group}) / used
    fx, fy, fw, fh = (float(np.median([f[k] for f in group])) for k in range(4))
    if fh > .42 * sh:
        return dict(none, kind='fullcam', presence=round(presence, 2))   # the camera is the whole picture: normal framing
    if presence < .3: return dict(none, presence=round(presence, 2))
    ex, ey = edges_x / used, edges_y / used
    # Search each side of the face for a line that is there in most frames (border or camera/game seam).
    span_y = slice(max(0, int(fy - .6 * fh)), min(sh, int(fy + 1.4 * fh)))
    span_x = slice(max(0, int(fx - 1.2 * fw)), min(sw, int(fx + 1.2 * fw)))
    col = ex[span_y].mean(axis=0); row = ey[:, span_x].mean(axis=1)
    # How much each pixel changes across the samples: high in the game, low in the streamer's room.
    var = np.stack(grays).astype(np.float32).std(axis=0); vcol = var[span_y].mean(axis=0); vrow = var[:, span_x].mean(axis=1)
    # 1) the steady/busy seam, searched far (a wide camera can be 9 face widths across); 2) else the strongest line nearby.
    seams = (_seam(col, vcol, fx - 7 * fw, fx - .9 * fw, -1), _seam(col, vcol, fx + .9 * fw, fx + 7 * fw, 1),
             _seam(row, vrow, fy - 4 * fh, fy - .8 * fh, -1), _seam(row, vrow, fy + 1.0 * fh, fy + 4.5 * fh, 1))
    left = seams[0] if seams[0] is not None else _border(col, fx - 3.2 * fw, fx - .9 * fw, fx - 1.7 * fw, 0)
    right = seams[1] if seams[1] is not None else _border(col, fx + .9 * fw, fx + 3.2 * fw, fx + 1.7 * fw, sw - 1)
    top = seams[2] if seams[2] is not None else _border(row, fy - 2.6 * fh, fy - .8 * fh, fy - 1.3 * fh, 0)
    bottom = seams[3] if seams[3] is not None else _border(row, fy + 1.0 * fh, fy + 3.4 * fh, fy + 2.0 * fh, sh - 1)
    # Refine with the found extent (a border is a line across the camera's full height / width).
    col = ex[max(0, top + 2):max(top + 3, bottom - 1)].mean(axis=0); row = ey[:, max(0, left + 2):max(left + 3, right - 1)].mean(axis=1)
    left = _border(col, left - 6, min(left + 7, fx - .9 * fw), left, 0); right = _border(col, max(right - 6, fx + .9 * fw), right + 7, right, sw - 1)
    top = _border(row, top - 6, min(top + 7, fy - .8 * fh), top, 0); bottom = _border(row, max(bottom - 6, fy + 1.0 * fh), bottom + 7, bottom, sh - 1)
    left, top = max(0, left), max(0, top); right, bottom = min(sw - 1, right), min(sh - 1, bottom)
    w, h = right - left + 1, bottom - top + 1
    if w * h > .45 * sw * sh or not .5 <= w / max(1, h) <= 2.6:
        return dict(none, presence=round(presence, 2))
    # A real camera inset has fixed edges: borders, or the seam with the game. A one-camera stream (IRL, a webcam
    # filling the screen) has none, because the camera moves. Measured: NaimDarrechi walking in a mall gave a 648x1080
    # "box" from the top to the bottom of the frame with no line at all; TheDonato, Spreen and the tests have 2-4.
    line = lambda profile, i, size: 2 < i < size - 3 and profile[i] >= .3
    lines = sum((line(col, left, sw), line(col, right, sw), line(row, top, sh), line(row, bottom, sh)))
    full_height = top <= 2 and bottom >= sh - 3
    if lines < 2 or (full_height and lines < 3):
        return dict(none, kind='single', presence=round(presence, 2))
    even = lambda v: int(round(v * ratio / 2)) * 2
    box = dict(x=even(left), y=even(top), w=even(w), h=even(h))
    box['w'] = min(box['w'], W - box['x']); box['h'] = min(box['h'], H - box['y'])
    x0, y0, x1, y1 = _content_region(ex, ey, (left, top, right + 1, bottom + 1), sw, sh)
    content = dict(x=even(x0), y=even(y0), w=min(W, even(x1)) - even(x0), h=min(H, even(y1)) - even(y0))
    if content['w'] >= W - 4 and content['h'] >= H - 4: content = dict(x=0, y=0, w=W, h=H)
    progress(100)
    return dict(found=True, kind='overlay', detector=DETECTOR_VERSION, width=W, height=H, presence=round(presence, 2), content=content, **box,
                face=dict(x=round(fx * ratio, 1), y=round(fy * ratio, 1), w=round(fw * ratio, 1), h=round(fh * ratio, 1)))


def panels(overlay):
    """Top (camera) panel height and the camera crop, centred on the face, with the panel's shape."""
    cw, ch = overlay['w'], overlay['h']
    top = int(min(TOP_MAX, max(TOP_MIN, CANVAS_W * ch / cw)) / 2) * 2
    aspect = CANVAS_W / top
    if cw / ch > aspect:                      # wider than the panel: trim the sides around the face
        w = int(ch * aspect / 2) * 2; h = ch
        face_x = overlay.get('face', {}).get('x', overlay['x'] + cw / 2)
        x = int(min(max(overlay['x'], face_x - w / 2), overlay['x'] + cw - w) / 2) * 2; y = overlay['y']
    else:                                     # taller: trim top and bottom, keeping the face in the upper middle
        w = cw; h = int(cw / aspect / 2) * 2
        face_y = overlay.get('face', {}).get('y', overlay['y'] + ch / 2)
        y = int(min(max(overlay['y'], face_y - h * .45), overlay['y'] + ch - h) / 2) * 2; x = overlay['x']
    return dict(top=top, bottom=CANVAS_H - top - SEAM, cam=dict(x=x, y=y, w=w, h=h))


def content_of(overlay):
    c = overlay.get('content')
    return c if c else dict(x=0, y=0, w=overlay['width'], h=overlay['height'])


def game_window(overlay, bottom):
    """Game crop (source px) for the bottom panel: the content area's full height, or its full width when narrower."""
    c = content_of(overlay)
    gw = min(c['w'], int(c['h'] * CANVAS_W / bottom / 2) * 2)
    gh = min(c['h'], int(gw * bottom / CANVAS_W / 2) * 2)
    return gw, gh, c['y'] + int((c['h'] - gh) / 4) * 2


def game_motion(source, start, end, overlay, progress=lambda v: None):
    """Horizontal centre of the game's motion at GAME_FPS (source px), ignoring the camera and the screen edges."""
    W, H = overlay['width'], overlay['height']
    sw = 320; sh = max(2, int(round(H * sw / W / 2)) * 2); r = W / sw
    duration = end - start
    proc = subprocess.Popen(['ffmpeg', '-v', 'error', '-ss', str(start), '-t', str(duration), '-i', str(source), '-an', '-vf',
                             f'fps={GAME_FPS},scale={sw}:{sh}', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    mask = np.ones((sh, sw), np.float32)
    if overlay.get('found'):
        x0, y0 = int(overlay['x'] / r), int(overlay['y'] / r)
        mask[max(0, y0 - 2):y0 + int(overlay['h'] / r) + 3, max(0, x0 - 2):x0 + int(overlay['w'] / r) + 3] = 0
    c = content_of(overlay); cx0, cy0 = int(c['x'] / r), int(c['y'] / r); cx1, cy1 = int((c['x'] + c['w']) / r), int((c['y'] + c['h']) / r)
    outside = np.ones_like(mask); outside[cy0:cy1, cx0:cx1] = 0; mask[outside > 0] = 0
    edge = int((cy1 - cy0) * .06); mask[cy0:cy0 + edge] = 0; mask[max(cy0, cy1 - edge):cy1] = 0   # tickers, HUD strips at the edges
    columns = np.arange(sw, dtype=np.float32)
    xs, energy = [], []; prev = None; n = math.ceil(duration * GAME_FPS)
    try:
        for i in range(n):
            raw = proc.stdout.read(sw * sh)
            if len(raw) != sw * sh: break
            frame = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            frame = frame.reshape(sh, sw)
            if prev is None: xs.append(W / 2); energy.append(0); prev = frame; continue
            diff = np.abs(frame - prev) * mask; prev = frame
            diff[diff < 18] = 0
            weight = diff.sum(axis=0)
            total = float(weight.sum())
            # Whole-screen motion (camera turning in the game) says nothing about where the action is.
            moving = float((diff > 0).mean())
            if total <= 0 or moving > .55: xs.append(xs[-1]); energy.append(0)
            else: xs.append(float((weight * columns).sum() / total) * r); energy.append(total)
            if i % GAME_FPS == 0: progress(round(100 * i / max(1, n)))
    finally:
        proc.stdout.close()
        if proc.poll() is None: proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    return dict(xs=[round(x, 1) for x in xs], energy=[round(e, 1) for e in energy])


def _smooth(values, tau, fps):
    a = 1 - math.exp(-1 / (tau * fps)); out = np.array(values, dtype=float)
    for _ in range(2):
        for i in range(1, len(out)): out[i] = out[i - 1] + a * (out[i] - out[i - 1])
        for i in range(len(out) - 2, -1, -1): out[i] = out[i + 1] + a * (out[i] - out[i + 1])
    return out


def game_path(result, motion='balanced', follow=True, cuts=()):
    """Left edge of the game crop (source px) at PATH_FPS, avoiding the camera when possible.

    No jumps at scene cuts by default: in games, flashes and explosions look like cuts to a detector (measured: 4 of
    10 "cuts" in a 40 s Free Fire clip were action), and a jump there would be visible. The crop always glides."""
    o = result['overlay']; p = result['panels']; c = content_of(o)
    gw, gh, gy = game_window(o, p['bottom'])
    lo, hi = c['x'], c['x'] + c['w'] - gw
    # Keep the camera out of the game panel: if it sits on one side of the game, use the other side when it fits.
    cam_l, cam_r = o['x'], o['x'] + o['w']
    inside = cam_l < c['x'] + c['w'] and cam_r > c['x'] and o['y'] < gy + gh and o['y'] + o['h'] > gy
    if o.get('found') and inside:
        mid = c['x'] + c['w'] / 2
        if cam_r <= mid and c['x'] + c['w'] - cam_r >= gw: lo = cam_r
        elif cam_l >= mid and cam_l - c['x'] >= gw: hi = cam_l - gw
    centre = (lo + hi) / 2 + gw / 2
    xs = np.array(result['motion']['xs'] or [centre], dtype=float)
    duration = len(xs) / GAME_FPS
    n = max(2, int(math.ceil(duration * PATH_FPS)) + 1)
    if not follow or lo >= hi:
        left = [float(min(max(lo, centre - gw / 2), max(lo, hi)))] * n
        return dict(fps=PATH_FPS, left=[round(v, 2) for v in left], window=gw, height=gh, y=gy, static=True)
    m = MOTION.get(motion, MOTION['balanced'])
    target = CENTRE_PULL * centre + (1 - CENTRE_PULL) * xs
    held = np.empty(len(target)); c = target[0]
    for i, x in enumerate(target):
        if abs(x - c) > m['dead'] * gw: c = x
        held[i] = c
    t_s = np.arange(len(held)) / GAME_FPS; t = np.arange(n) / PATH_FPS
    out = np.empty(n); bounds = [0.0] + [c for c in cuts if 0 < c < duration] + [duration + 1]
    limit = m['speed'] * gw / PATH_FPS
    for a, b in zip(bounds, bounds[1:]):
        shot = (t >= a) & (t < b); inside = (t_s >= a) & (t_s < b)
        if not shot.any(): continue
        part = np.interp(t[shot], t_s[inside], held[inside]) if inside.any() else np.full(shot.sum(), held[min(len(held) - 1, int(a * GAME_FPS))])
        part = _smooth(part, m['tau'], PATH_FPS)
        for i in range(1, len(part)): part[i] = part[i - 1] + max(-limit, min(limit, part[i] - part[i - 1]))
        out[shot] = _smooth(part, .08, PATH_FPS)
    left = np.clip(out - gw / 2, lo, hi)
    return dict(fps=PATH_FPS, left=[round(float(v), 2) for v in left], window=gw, height=gh, y=gy, static=bool(np.ptp(left) < 1))


def cam_presence(source, start, end, overlay, samples=6):
    """Share of sampled frames of this clip with a face inside the camera rectangle (an intro or a full-screen
    moment has none: the editor warns instead of showing an empty top panel)."""
    from tracking import make_detector
    W, H = overlay['width'], overlay['height']; sw = 640; sh = max(2, int(round(H * sw / W / 2)) * 2); r = W / sw
    detect = make_detector(sw, sh); hits = seen = 0
    for t in np.linspace(start + .3, max(start + .3, end - .3), samples):
        frame = _frame(source, float(t), sw, sh)
        if frame is None: continue
        seen += 1
        for x, y, w, h, score in detect(frame):
            cx, cy = (x + w / 2) * r, (y + h / 2) * r
            if overlay['x'] <= cx <= overlay['x'] + overlay['w'] and overlay['y'] <= cy <= overlay['y'] + overlay['h']: hits += 1; break
    return round(hits / seen, 2) if seen else 0


def analyze(source, start, end, overlay, progress=lambda v: None):
    """Per-clip layout: panels, camera crop, game motion. `overlay` comes from detect_overlay (cached per video)."""
    result = dict(version=VERSION, start=start, end=end, overlay=overlay, panels=panels(overlay) if overlay.get('found') else None)
    if not overlay.get('found'): return result
    # No automatic re-detection inside a clip: tried on an edited video whose camera moves and zooms within the same
    # 20 s, it chose a wrong crop (a chest instead of a face). A clear warning plus the manual rectangle is safer.
    result['cam_presence'] = cam_presence(source, start, end, overlay)
    result['motion'] = game_motion(source, start, end, overlay, progress)
    return result


def filter_graph(result, cmd_file, duration, fps, motion='balanced', follow=True, sharpen=True):
    """FFmpeg graph fragment for the stacked layout (to be wrapped as [0:v]<graph>[v0])."""
    o, p = result['overlay'], result['panels']; W = o['width']; c = p['cam']
    path = game_path(result, motion, follow)
    gw, gh, gy = path['window'], path['height'], path['y']
    src = np.arange(len(path['left'])) / path['fps']; lines = []
    even = lambda v: min(max(0, int(round(v / 2)) * 2), W - gw)     # yuv420p crops at even offsets; the preview rounds the same way
    for t in np.arange(0, duration, 1 / fps):
        lines.append(f'{t:.6f} crop@game x {even(float(np.interp(t, src, path["left"])))};')
    Path(cmd_file).write_text('\n'.join(lines), encoding='utf-8')
    sharp = ',unsharp=5:5:0.7:5:5:0.0' if sharpen else ''
    x0 = even(path['left'][0])
    return (f'setpts=PTS-STARTPTS,split[lcam][lgame];'
            f'[lcam]crop={c["w"]}:{c["h"]}:{c["x"]}:{c["y"]},scale={CANVAS_W}:{p["top"]}:flags=lanczos{sharp},setsar=1,pad={CANVAS_W}:{p["top"] + SEAM}:0:0:color=0x0b0b0b[ltop];'
            f'[lgame]sendcmd=f={Path(cmd_file).name},crop@game={gw}:{gh}:{x0}:{gy},scale={CANVAS_W}:{p["bottom"]}:flags=lanczos,setsar=1[lbottom];'
            f'[ltop][lbottom]vstack')


def preview_path(result, motion='balanced', follow=True):
    """What the editor needs to draw the same picture on a canvas."""
    o, p = result['overlay'], result['panels']
    path = game_path(result, motion, follow)
    return dict(found=True, top=p['top'], bottom=p['bottom'], seam=SEAM, cam=p['cam'], width=o['width'], height=o['height'],
                game=dict(fps=path['fps'], left=path['left'], w=path['window'], h=path['height'], y=path['y'], static=path['static']),
                overlay={k: o[k] for k in ('x', 'y', 'w', 'h')}, content=content_of(o), cam_presence=result.get('cam_presence', 1))
