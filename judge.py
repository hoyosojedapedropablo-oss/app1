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
    '"quien" es la persona que habla en el clip: su nombre si se dice en el clip o está en "nombres_del_directo" y suena '
    'en el clip; si no, su papel (el entrevistado, el instructor, el streamer, el invitado). Nunca el título del video, el '
    'nombre del canal ni el del programa.',
    'Antes de puntuar, respóndete en el JSON: ¿quién habla?, ¿a quién se lo dice?, ¿qué pasa exactamente?, ¿por qué lo '
    'dice o lo hace?, ¿qué pasa después (hay desenlace, reacción, respuesta)?, ¿tiene sentido?, ¿se entiende sin haber '
    'visto el resto del directo?',
    'Luego puntúa de 0 a 10: gancho (los primeros segundos atrapan), desenlace (hay remate, respuesta o consecuencia), '
    'humor, suspenso, polemica (una opinión fuerte, una acusación, algo que divide a la gente), emocion y conflicto '
    '(dos personas enfrentadas).',
    'Los clips que recibes YA fueron preseleccionados entre los mejores momentos del video o del directo. No los compares '
    'con lo más viral de todo TikTok: decide si un clipero con experiencia lo publicaría en su cuenta. Usa toda la escala '
    'con honestidad: "subir_ya" (8 a 10) si tiene gancho y remate claros y genera reacción; "bueno" (6 a 8) si funciona '
    'y alguien lo vería completo; "publicable" (5 a 6) si se entiende solo y tiene un punto de interés aunque no destaque; '
    '"flojo" (3 a 5) si le falta gancho o remate y pocos lo terminarían de ver.',
    '"relleno" y "descartar" son SOLO para lo que no tiene contenido: saludos, silencios, ruido, frases sueltas sin '
    'sentido o algo que no se entiende. Una charla con información, una pregunta o un pedido a los fans es como mínimo "flojo", no '
    'relleno.',
    'Ejemplos de calibración (no copies su contenido):',
    '  - Un streamer acusa en directo a otro de haberle robado el torneo y el otro le responde furioso -> polemica 9, '
    'conflicto 9, gancho 8, desenlace 8, veredicto subir_ya.',
    '  - Alguien cuenta un chiste que se entiende solo y todos explotan de risa -> humor 8, gancho 7, desenlace 8, bueno.',
    '  - Un streamer da su opinión clara sobre un tema conocido, con una frase que se puede citar -> polemica 6, gancho 6, '
    'desenlace 5, publicable.',
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
    'veredicto': {'type': 'string', 'enum': ['subir_ya', 'bueno', 'publicable', 'flojo', 'descartar']}, 'motivo': {'type': 'string'}},
    'required': ['quien', 'a_quien', 'que_pasa', 'por_que', 'despues', 'tiene_sentido', 'se_entiende_solo', 'tipo', 'gancho',
                 'desenlace', 'humor', 'suspenso', 'polemica', 'emocion', 'conflicto', 'relleno', 'veredicto', 'motivo']}
# Recalibrated (Nov 2026): the old scale told the model that most moments are «flojo» and boxed them at 40-64, so the
# clips of a whole video averaged about 40 and the tool looked weak. The clips reaching the judge are already the best of
# their video; the question now is whether an experienced clipper would post them.
VERDICT_RANGE = {'subir_ya': (85, 99), 'bueno': (70, 84), 'publicable': (55, 69), 'flojo': (35, 54), 'descartar': (0, 34)}
DROP_BELOW = 35          # live moments below this (filler) are not offered
SPREAD = (15, 90)        # raw marks mapped across each verdict's range (bottom, top)


def score(v):
    """0-100 from the judge's answers. The strongest of humour, suspense, controversy, emotion and conflict carries the
    clip; hook and payoff decide whether it lands; the verdict keeps the number honest (a «flojo» never reads as 80)."""
    val = lambda k: max(0, min(10, int(v.get(k) or 0)))
    tension = sorted((val(k) for k in ('humor', 'suspenso', 'polemica', 'emocion', 'conflicto')), reverse=True)
    raw = 10 * (.28 * val('gancho') + .24 * val('desenlace') + .34 * tension[0] + .14 * tension[1])
    if not v.get('se_entiende_solo', True): raw -= 8
    if not v.get('tiene_sentido', True): raw -= 12
    if v.get('relleno'): raw = min(raw, 30)
    if v.get('veredicto') not in VERDICT_RANGE: return int(round(max(0, min(100, raw))))
    # Inside its verdict's range the note follows the marks (raw 15 -> bottom, 90 -> top). Clamping raw to the range
    # put 9 of 11 «publicable» clips of a real video at exactly 55: the judge could not tell a strong one from a weak one.
    lo, hi = VERDICT_RANGE[v['veredicto']]
    return int(round(lo + (hi - lo) * max(0., min(1., (raw - SPREAD[0]) / (SPREAD[1] - SPREAD[0])))))


ROLES = ('el ', 'la ', 'los ', 'las ', 'un ', 'una ')


def who(quien, text, context='', speaker=''):
    """E-27: «quien» filled with words of the video title or the channel («Sobreviví», «ASÍ CONTRATAN», «Más Allá del
    Silencio Podcast») made the title writer put a podcast's name on its guest. A role («el entrevistado») is kept; a name
    is kept only when something in the clip sounds like it; otherwise it is left empty."""
    import viral
    q = str(quien or '').strip()
    if not q or q.lower().startswith(ROLES) and q[:1].islower(): return q
    if speaker and viral.fold(q) in viral.fold(speaker): return q           # the user named them, or the live channel
    if q.isupper() and len(q) > 4: return ''                              # a shouted title, not a person
    parts = [viral.fold(p) for p in viral.re.findall(r'\w{3,}', q)]
    if parts and all(viral.sounds_said(p, text, .7, joined=.6) for p in parts): return q
    return ''


def judge(text, speaker='', context='', names=(), complete=None, cancel=None):
    """{'score', 'verdict', 'kind', 'analysis': {...}} for one clip, or None when the judge is not available."""
    if not text.strip(): return None
    payload = {'canal': speaker or 'desconocido', 'contexto': context, 'nombres_del_directo': list(names)[:30], 'transcripcion_del_clip': text[:4000]}
    try: v = (complete or _ollama)(payload, cancel)
    except Exception: return None
    if not isinstance(v, dict) or 'veredicto' not in v: return None
    analysis = {k: v.get(k) for k in ('quien', 'a_quien', 'que_pasa', 'por_que', 'despues', 'motivo')}
    analysis['quien'] = who(analysis.get('quien'), text, context, speaker)
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
