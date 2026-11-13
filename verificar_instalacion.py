"""Check a code version against the user's own recent clips BEFORE installing it (read-only: nothing is written).

    python verificar_instalacion.py "<carpeta data de la instalación>" [--max 3]

For the newest live sessions and projects it runs, with THIS folder's code, the steps that decide how a clip looks:
- «Cámara + juego» chosen → camera detection and the per-clip layout must run without errors;
- face tracking on → the tracking of a few seconds must run without errors.
Any crash (like E-01, docs/ERRORES_CONOCIDOS.md) makes it exit with code 1. A clip where the camera simply is not
seen is reported, not counted as a crash. Only local files are read; nothing is uploaded.
"""
import argparse, json, sys, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def live_items(data, limit):
    sessions = []
    for state in (data / 'live').glob('*/state.json'):
        try: s = json.loads(state.read_text(encoding='utf-8'))
        except (OSError, ValueError): continue
        sessions.append((s.get('created') or '', state.parent, s))
    for _, folder, s in sorted(sessions, key=lambda x: x[0], reverse=True)[:6]:
        settings = s.get('clip_settings') or {}
        moments = [m for m in s.get('moments', []) if m.get('status') not in ('discarded', 'error') and (folder / 'moments' / f"{m['id']}.mp4").exists()]
        for m in moments[-limit:]:
            base = m.get('file_start', m['start'] - 3)
            yield dict(where=f"{s.get('channel') or 'directo'} · {m.get('title', '')[:50]}", source=folder / 'moments' / f"{m['id']}.mp4",
                       start=max(0.0, m['start'] - base), end=m['end'] - base, settings=settings)


def check(item, report):
    import layout, tracking
    settings = item['settings']; out = dict(where=item['where'], framing=settings.get('framing'))
    try:
        if settings.get('framing') == 'stack' or settings.get('auto_stack', True):
            t0 = time.time()
            overlay = layout.detect_overlay(item['source'], item['end'] + 3, samples=24, prefer=settings.get('framing') == 'stack')
            result = layout.analyze(item['source'], round(item['start'], 3), round(item['end'], 3), overlay) if overlay.get('found') else None
            out.update(camera=bool(overlay.get('found')), presence=overlay.get('presence'), layout_s=round(time.time() - t0, 1), panels=bool(result and result.get('panels')))
            if settings.get('framing') == 'stack' and not overlay.get('found'): out['note'] = 'Cámara + juego elegido pero no se vio la cámara (el clip lo avisa)'
        if settings.get('tracking') and settings.get('framing', 'zoom') in ('crop', 'zoom'):
            t0 = time.time()
            try:
                r = tracking.analyze(item['source'], item['start'], min(item['end'], item['start'] + 6), lambda v: None)
                out.update(tracking=True, persons=len(r['persons']), tracking_s=round(time.time() - t0, 1))
            except ValueError as e:
                if 'rostros' not in str(e): raise
                out.update(tracking=False, note='sin caras en esos segundos')
        out['ok'] = True
    except Exception as e:
        out.update(ok=False, error=f'{type(e).__name__}: {e}', where_code=traceback.format_exc().splitlines()[-3:])
    report.append(out); return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('data'); ap.add_argument('--max', type=int, default=3)
    args = ap.parse_args(); data = Path(args.data)
    report = []
    for item in live_items(data, args.max):
        o = check(item, report)
        mark = 'OK ' if o['ok'] else 'ERROR'
        extra = ' · '.join(f'{k}={v}' for k, v in o.items() if k not in ('ok', 'where', 'where_code'))
        print(f'[{mark}] {o["where"]} · {extra}', flush=True)
    failed = [o for o in report if not o['ok']]
    print(f'\n{len(report)} clips reales revisados · {len(failed)} con error')
    for o in failed: print('  ', o['where'], '→', o['error'], *o.get('where_code', []), sep='\n    ')
    sys.exit(1 if failed or not report else 0)


if __name__ == '__main__':
    main()
