r"""Compara modelos de Ollama escribiendo los títulos de clips ya analizados (E-27). No cambia ningún proyecto.

Uso, con la app cerrada o abierta (solo lee data/):
    .venv\Scripts\python tools\comparar_modelos_titulos.py --data "C:\ruta\a\data" --jobs ID1 ID2 --models qwen2.5:7b qwen3:8b

Para cada clip y cada modelo pide 5 títulos a viral.py (con el análisis del juez si el clip lo tiene) y anota cuáles pasan
y por qué se rechaza cada uno: «formato» (largo, emojis, mayúsculas), «sin anclar» (nombre o palabra que no está en el clip,
cita inventada) o «filtro de la app» (genérico, ejemplo copiado, nombre ausente). Escribe un informe .md y un .json.
"""
import argparse, json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import viral, intelligence, gpu_ai


def names_of(job):
    yt = job.get('youtube') or {}; live = job.get('live') or {}; opt = job.get('analysis_options') or {}
    found = [opt.get('speaker'), yt.get('channel'), live.get('channel')]
    found += re.findall(r'\b[A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,}', ' '.join(filter(None, [yt.get('title'), live.get('title')])))
    out, seen = [], set()
    for n in found:
        if n and n.lower() not in seen: seen.add(n.lower()); out.append(n)
    return out[:30]


def reason(title, text, speaker, names, context):
    t = viral.clean(str(title))
    if not t: return None, 'formato'
    if not viral.grounded_title(t, text, speaker, names, context): return None, 'sin anclar'
    if not intelligence.clean_title(t, text): return None, 'filtro de la app'
    return intelligence.clean_title(t, text), None


def installed():
    with gpu_ai.client(timeout=10) as conn:
        return {m['name'] for m in conn.get('/api/tags').json().get('models', [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=str(ROOT / 'data'))
    ap.add_argument('--jobs', nargs='+', required=True)
    ap.add_argument('--models', nargs='+', default=['qwen2.5:7b', 'qwen3:8b'])
    ap.add_argument('--out', default=None, help='carpeta del informe (por defecto <data>/comparacion-titulos)')
    args = ap.parse_args()
    have = installed()
    missing = [m for m in args.models if m not in have and m + ':latest' not in have]
    if missing:
        sys.exit('Faltan modelos en Ollama: ' + ', '.join(missing) + '. Instálalos con: ollama pull ' + ' / ollama pull '.join(missing))
    rows, report = [], ['# Comparación de modelos para títulos', '']
    for ident in args.jobs:
        job = json.loads((Path(args.data) / ident / 'job.json').read_text(encoding='utf-8'))
        opt = job.get('analysis_options') or {}; speaker, context = opt.get('speaker', ''), opt.get('context', '')
        names = names_of(job)
        report += [f"## {(job.get('youtube') or {}).get('title') or job.get('name') or ident}", '']
        for c in job.get('clips', []):
            text = c.get('text', '')
            if not text.strip(): continue
            report += [f"### {int(c['start'] // 60)}:{int(c['start'] % 60):02d} · {c.get('category', '')}", '',
                       f"> {text[:280]}{'…' if len(text) > 280 else ''}", '', f"- Título actual: {c.get('title', '')}"]
            for model in args.models:
                raw = {}
                def complete(payload, cancel=None, model=model):
                    raw.update(viral._ollama(payload, cancel, model)); return raw
                started = time.monotonic()
                try: viral.generate(text, speaker=speaker, context=context, names=names, analysis=c.get('analysis'), complete=complete)
                except Exception as e: raw = {'error': str(e)}
                seconds = round(time.monotonic() - started, 1)
                checked = [(t,) + reason(t, text, speaker, names, context) for t in raw.get('titulos', [])]
                ok = [r[1] for r in checked if r[1]]
                rows.append({'job': ident, 'clip': c.get('id'), 'start': c['start'], 'model': model, 'seconds': seconds,
                             'accepted': ok, 'rejected': [{'title': r[0], 'reason': r[2]} for r in checked if not r[1]],
                             'error': raw.get('error')})
                shown = ' | '.join(ok) if ok else '—'
                rej = '; '.join(f"«{r[0]}» ({r[2]})" for r in checked if not r[1])
                report.append(f"- **{model}** ({seconds} s): {shown}" + (f"  \n  rechazados: {rej}" if rej else '') +
                              (f"  \n  error: {raw['error']}" if raw.get('error') else ''))
            report.append('')
    summary = ['| Modelo | Clips con algún título válido | Títulos válidos | s por clip | formato | sin anclar | filtro de la app |',
               '| --- | --- | --- | --- | --- | --- | --- |']
    for model in args.models:
        mine = [r for r in rows if r['model'] == model]
        count = lambda why: sum(1 for r in mine for x in r['rejected'] if x['reason'] == why)
        summary.append(f"| {model} | {sum(1 for r in mine if r['accepted'])} de {len(mine)} | {sum(len(r['accepted']) for r in mine)} | "
                       f"{round(sum(r['seconds'] for r in mine) / max(1, len(mine)), 1)} | {count('formato')} | {count('sin anclar')} | {count('filtro de la app')} |")
    out = Path(args.out or Path(args.data) / 'comparacion-titulos'); out.mkdir(parents=True, exist_ok=True)
    (out / 'informe.md').write_text('\n'.join(report[:2] + summary + [''] + report[2:]), encoding='utf-8')
    (out / 'resultados.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print('\n'.join(summary)); print(f'\nInforme: {out / "informe.md"}')


if __name__ == '__main__':
    main()
