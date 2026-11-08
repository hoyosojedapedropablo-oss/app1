"""Hook-first titles for short clips: find the strongest claim in what is said, then write curiosity or controversy titles.

The analyst that picks moments also writes a title, but its priority is choosing the segment. This pass only reads the
clip's own words, finds the strongest statement (claim, opinion on a concrete topic, confession, criticism, prediction,
surprising fact or story) and turns it into titles built to stop the scroll. Titles must rest on words that were said:
a title whose key words are absent from the transcript is discarded instead of shown.
"""
import json, re

SYSTEM = '\n'.join([
    'Eres editor de clips virales para TikTok, Instagram Reels y YouTube Shorts en español. Lees la transcripción literal '
    'de UN clip y escribes títulos que hagan que la gente se detenga a verlo.',
    'El hablante principal es el indicado en "hablante". Palabras como broder, bro, parce, guacho, mano, causa, wey o amigo '
    'son muletillas: NO son nombres de personas.',
    'Paso 1. Lee cada frase. Encuentra la idea más fuerte que se dice al inicio o en el núcleo del clip: una afirmación tajante, '
    'una opinión sobre un tema o persona concreta, una confesión, una crítica, una predicción, una cifra o una anécdota sorprendente. '
    'Cópiala casi literal en "afirmacion".',
    'Paso 2. Escribe 5 títulos distintos a partir de ESA idea, de 25 a 80 caracteres, que generen intriga, curiosidad o polémica:',
    '- Pon el nombre del hablante al principio cuando sea claro que la frase es suya. En charlas con invitados la transcripción no '
    'indica quién habla: si no está claro, no atribuyas la frase a nadie (usa la cita sola o una pregunta).',
    '- Cada título debe decir QUÉ afirma, opina, confiesa o critica el hablante, con el tema concreto (persona, cosa, cifra o lugar).',
    '- Puedes citar entre comillas una frase corta y fuerte que se diga en el clip.',
    '- El título debe corresponder a lo que se dice al inicio del clip, no a un tema que aparece después.',
    '- No inventes nombres, cifras, lugares ni hechos que no estén en la transcripción. Exagerar el tono está bien; mentir no.',
    '- Prohibido: "Descubre", "Increíble", "No creerás", emojis, hashtags, frases todo en mayúsculas y títulos que solo describen '
    'la escena sin decir qué se afirma (por ejemplo "X recorre la casa").',
    'Ejemplos de estilo (no copies su contenido):',
    '  Dicho: "nunca voy a volver a ese torneo, nos robaron, los organizadores son unos estafadores" -> '
    '«Son unos estafadores»: Ana jura no volver al torneo | Ana explota contra los organizadores que le robaron | '
    '¿Por qué Ana no volverá nunca a ese torneo?',
    '  Dicho: "le faltan dos semanas a la casa nueva, ya me gasté todo lo que tenía" -> '
    'Leo confiesa que se gastó todo en su casa nueva | Leo revela cuándo estará lista su casa nueva | '
    '«Ya me gasté todo»: lo que le costó a Leo su casa',
    'Paso 3. En "mejor" pon el índice (0 a 4) del título con más gancho que respete las reglas.',
])
SCHEMA = {'type': 'object', 'properties': {
    'afirmacion': {'type': 'string'},
    'tipo': {'type': 'string', 'enum': ['afirmación', 'opinión', 'confesión', 'crítica', 'predicción', 'dato', 'anécdota', 'polémica', 'reacción']},
    'titulos': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 5, 'maxItems': 5},
    'mejor': {'type': 'integer', 'minimum': 0, 'maximum': 4}},
    'required': ['afirmacion', 'tipo', 'titulos', 'mejor']}
BANNED = re.compile(r'^(descubre|increíble|no creerás|mira cómo)|#|[\U0001F300-\U0001FAFF]', re.I)
STOP = set('''broder parce guacho causa amigo para pero como cuando donde porque sobre entre desde hasta todo toda todos todas
esto esta este estos estas eso esa ese esos esas muy más menos solo sólo tiene tienen hace hacen dice dicen dijo admite revela
confiesa opina cree piensa nadie nunca siempre cosa cosas razón verdad mejor peor algo alguien quién quien qué cuál cómo según
explota jura critica afirma asegura'''.split())


def words(text):
    return re.findall(r'\w+', text.lower())


def grounded_title(title, text, speaker=''):
    """At least two (or half) of the title's content words must have been said in the clip."""
    said = set(words(text)); names = set(words(speaker))
    content = [w for w in words(title) if len(w) >= 5 and w not in STOP and w not in names and not w.isdigit()]
    if not content: return False
    hits = sum(1 for w in content if w in said or any(s.startswith(w[:5]) for s in said))
    return hits >= min(2, len(content)) and hits >= len(content) / 2


def clean(title):
    title = re.split(r'\s+[|/]\s+', title)[0]   # the examples list alternatives with separators; keep one title
    title = re.sub(r'\s+', ' ', title).strip().strip('"').strip()
    if not 8 <= len(title) <= 80 or len(title.split()) > 14 or BANNED.search(title): return None
    if title.isupper(): return None
    return title


def generate(text, speaker='', context='', complete=None, cancel=None):
    """Return {'title', 'titles', 'claim', 'kind'} or None when no grounded title survives."""
    if not text.strip(): return None
    payload = {'hablante': speaker or 'desconocido', 'contexto': context, 'transcripcion_del_clip': text[:4000]}
    data = (complete or _ollama)(payload, cancel)
    raw_titles = data.get('titulos') if isinstance(data.get('titulos'), list) else []
    titles = []
    for raw in raw_titles:
        title = clean(str(raw))
        if title and grounded_title(title, text, speaker) and title not in titles: titles.append(title)
    if not titles: return None
    best = data.get('mejor', 0)
    first = clean(str(raw_titles[best])) if isinstance(best, int) and 0 <= best < len(raw_titles) else None
    if first in titles: titles.remove(first); titles.insert(0, first)
    return {'title': titles[0], 'titles': titles, 'claim': str(data.get('afirmacion', ''))[:240], 'kind': str(data.get('tipo', ''))}


def _ollama(payload, cancel=None):
    import gpu_ai
    from cloud_ai import AnalysisCancelled
    if cancel is not None and cancel.is_set(): raise AnalysisCancelled()
    body = {'model': gpu_ai.MODEL, 'stream': False, 'format': SCHEMA, 'keep_alive': '10m',
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'options': {'num_ctx': 4096, 'num_predict': 500, 'temperature': .5}}
    with gpu_ai.client(timeout=60) as conn:
        response = conn.post('/api/chat', json=body); response.raise_for_status()
    return json.loads(response.json()['message']['content'])
