"""Viral judge: a second, stricter look at each proposed clip, asking what an experienced clipper asks.

Who says it, to whom and why; does it make sense; what happens after; is there humour, suspense, controversy, a
conflict; is it understood without the rest of the stream. Its answers give a 0-100 score that really separates a
weak clip from one to post right away. The old score (hook, payoff and strength from 0-5, times 20, each at least 3)
could only take a few values and the model gave 3-4 almost always: nearly every clip came out at 73 (measured on
HotSpanish, Nov 2026). The analysis also feeds the title writer.
"""
import json

SYSTEM = '\n'.join([
    'Eres el editor jefe de un equipo de cliperos virales en español (TikTok, Reels, Shorts). Recibes la transcripción '
    'automática de UN clip de un directo o video y decides, con criterio exigente, si merece publicarse.',
    'Antes de puntuar, respóndete en el JSON: ¿quién habla?, ¿a quién se lo dice?, ¿qué pasa exactamente?, ¿por qué lo '
    'dice o lo hace?, ¿qué pasa después (hay desenlace, reacción, respuesta)?, ¿tiene sentido?, ¿se entiende sin haber '
    'visto el resto del directo?',
    'Luego puntúa de 0 a 10: gancho (los primeros segundos atrapan), desenlace (hay remate, respuesta o consecuencia), '
    'humor, suspenso, polemica (una opinión fuerte, una acusación, algo que divide a la gente), emocion y conflicto '
    '(dos personas enfrentadas).',
    'Sé estricto y realista, y usa toda la escala: la mayoría de momentos de un directo son normales (veredicto "flojo", '
    'notas de 3 a 6); los que tienen una situación clara con gracia, tensión o una opinión son "bueno" (6 a 8); solo '
    'uno de cada diez merece "subir_ya" (8 a 10).',
    '"relleno" y "descartar" son SOLO para lo que no tiene contenido: saludos, silencios, ruido, frases sueltas sin '
    'sentido o algo que no se entiende. Una charla con información, una pregunta o un pedido a los fans es "flojo", no '
    'relleno.',
    'Ejemplos de calibración (no copies su contenido):',
    '  - Un streamer acusa en directo a otro de haberle robado el torneo y el otro le responde furioso -> polemica 9, '
    'conflicto 9, gancho 8, desenlace 8, veredicto subir_ya.',
    '  - Alguien cuenta un chiste que se entiende solo y todos explotan de risa -> humor 8, gancho 7, desenlace 8, bueno.',
    '  - Dos personas comentan qué van a cocinar, sin tensión -> todo 1-3, relleno, descartar.',
    '  - Alguien pide a sus fans que donen, sin reacción ni gracia -> gancho 4, desenlace 2, flojo.',
])
SCHEMA = {'type': 'object', 'properties': {
    'quien': {'type': 'string'}, 'a_quien': {'type': 'string'}, 'que_pasa': {'type': 'string'}, 'por_que': {'type': 'string'},
    'despues': {'type': 'string'}, 'tiene_sentido': {'type': 'boolean'}, 'se_entiende_solo': {'type': 'boolean'},
    'tipo': {'type': 'string', 'enum': ['humor', 'suspenso', 'polémica', 'conflicto', 'confesión', 'emoción', 'reacción', 'información', 'relleno']},
    'gancho': {'type': 'integer', 'minimum': 0, 'maximum': 10}, 'desenlace': {'type': 'integer', 'minimum': 0, 'maximum': 10},
    'humor': {'type': 'integer', 'minimum': 0, 'maximum': 10}, 'suspenso': {'type': 'integer', 'minimum': 0, 'maximum': 10},
    'polemica': {'type': 'integer', 'minimum': 0, 'maximum': 10}, 'emocion': {'type': 'integer', 'minimum': 0, 'maximum': 10},
    'conflicto': {'type': 'integer', 'minimum': 0, 'maximum': 10}, 'relleno': {'type': 'boolean'},
    'veredicto': {'type': 'string', 'enum': ['subir_ya', 'bueno', 'flojo', 'descartar']}, 'motivo': {'type': 'string'}},
    'required': ['quien', 'a_quien', 'que_pasa', 'por_que', 'despues', 'tiene_sentido', 'se_entiende_solo', 'tipo', 'gancho',
                 'desenlace', 'humor', 'suspenso', 'polemica', 'emocion', 'conflicto', 'relleno', 'veredicto', 'motivo']}
VERDICT_RANGE = {'subir_ya': (85, 100), 'bueno': (65, 84), 'flojo': (40, 64), 'descartar': (0, 39)}
DROP_BELOW = 35          # live moments below this (filler) are not offered


def score(v):
    """0-100 from the judge's answers. The strongest of humour, suspense, controversy, emotion and conflict carries the
    clip; hook and payoff decide whether it lands; the verdict keeps the number honest (a «flojo» never reads as 80)."""
    val = lambda k: max(0, min(10, int(v.get(k) or 0)))
    tension = sorted((val(k) for k in ('humor', 'suspenso', 'polemica', 'emocion', 'conflicto')), reverse=True)
    raw = 10 * (.28 * val('gancho') + .24 * val('desenlace') + .34 * tension[0] + .14 * tension[1])
    if not v.get('se_entiende_solo', True): raw -= 12
    if not v.get('tiene_sentido', True): raw -= 15
    if v.get('relleno'): raw = min(raw, 30)
    lo, hi = VERDICT_RANGE.get(v.get('veredicto'), (0, 100))
    return int(round(max(lo, min(hi, raw))))


def judge(text, speaker='', context='', names=(), complete=None, cancel=None):
    """{'score', 'verdict', 'kind', 'analysis': {...}} for one clip, or None when the judge is not available."""
    if not text.strip(): return None
    payload = {'canal': speaker or 'desconocido', 'contexto': context, 'nombres_del_directo': list(names)[:30], 'transcripcion_del_clip': text[:4000]}
    try: v = (complete or _ollama)(payload, cancel)
    except Exception: return None
    if not isinstance(v, dict) or 'veredicto' not in v: return None
    analysis = {k: v.get(k) for k in ('quien', 'a_quien', 'que_pasa', 'por_que', 'despues', 'motivo')}
    return {'score': score(v), 'verdict': v.get('veredicto'), 'kind': v.get('tipo') or '', 'analysis': analysis,
            'marks': {k: v.get(k) for k in ('gancho', 'desenlace', 'humor', 'suspenso', 'polemica', 'emocion', 'conflicto')}}


def _ollama(payload, cancel=None):
    import gpu_ai
    from cloud_ai import AnalysisCancelled
    if cancel is not None and cancel.is_set(): raise AnalysisCancelled()
    body = {'model': gpu_ai.MODEL, 'stream': False, 'format': SCHEMA, 'keep_alive': '10m',
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'options': {'num_ctx': 4096, 'num_predict': 600, 'temperature': 0, 'seed': 7}}     # the same clip, the same note
    with gpu_ai.client(timeout=60) as conn:
        response = conn.post('/api/chat', json=body); response.raise_for_status()
    return json.loads(response.json()['message']['content'])
