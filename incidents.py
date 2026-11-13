"""Incidents: every failure of a step that decides how a clip looks is written down and shown, never swallowed.

Why (Nov 2026, docs/ERRORES_CONOCIDOS.md E-01): «Cámara + juego» failed for every clip for a day because an
exception inside the camera detection was caught with `except Exception: pass`. The clips silently came out in another
format and nobody could see why. Now each failure is recorded here (data/incidents.jsonl, no personal data: only the
step, the error type and message, and ids), logged, counted, and the app shows a warning while it keeps happening.
"""
import json, logging, threading, time, traceback
from pathlib import Path

LOCK = threading.Lock()
FILE = None                 # set by app.py: DATA / 'incidents.jsonl'
MAX_LINES = 2000
STEPS = {
    'layout': 'Detección de cámara (Cámara + juego)',
    'follow': 'Seguimiento facial',
    'thumb': 'Miniatura del clip',
    'preview': 'Vista previa del clip',
    'render': 'Corte del clip en vivo',
    'format': 'Formato elegido no aplicado',
}


def record(step, error=None, **context):
    """Write one incident. `error` may be an exception or a short text. Never raises."""
    try:
        if isinstance(error, BaseException):
            kind, message = type(error).__name__, str(error)[:300]
            where = ''.join(traceback.format_tb(error.__traceback__)[-2:])[-600:] if error.__traceback__ else ''
        else:
            kind, message, where = 'Aviso', str(error or '')[:300], ''
        item = dict(time=round(time.time(), 1), step=step, kind=kind, message=message, where=where,
                    **{k: v for k, v in context.items() if isinstance(v, (str, int, float, bool)) or v is None})
        logging.getLogger('uvicorn.error').warning('Incidente [%s] %s: %s %s', step, kind, message, context)
        if FILE is None: return item
        with LOCK:
            path = Path(FILE); path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as out: out.write(json.dumps(item, ensure_ascii=False) + '\n')
            if path.stat().st_size > 2_000_000:          # keep the newest lines only
                lines = path.read_text(encoding='utf-8').splitlines()[-MAX_LINES:]
                path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return item
    except Exception:
        return None


def recent(hours=24):
    """Incidents of the last `hours`, grouped by step and error, newest first."""
    if FILE is None or not Path(FILE).exists(): return []
    since = time.time() - hours * 3600; groups = {}
    with LOCK:
        lines = Path(FILE).read_text(encoding='utf-8').splitlines()[-MAX_LINES:]
    for line in lines:
        try: item = json.loads(line)
        except ValueError: continue
        if item.get('time', 0) < since: continue
        key = (item['step'], item.get('kind'), item.get('message', '')[:120])
        g = groups.setdefault(key, dict(step=item['step'], label=STEPS.get(item['step'], item['step']), kind=item.get('kind'),
                                        message=item.get('message', ''), count=0, first=item['time'], last=item['time']))
        g['count'] += 1; g['last'] = max(g['last'], item['time']); g['first'] = min(g['first'], item['time'])
    return sorted(groups.values(), key=lambda g: -g['last'])
