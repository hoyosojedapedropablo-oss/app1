"""Hook-first titles for short clips, written the way an experienced clipper would: not the transcript, but what
happens in it, said so people stop scrolling (curiosity, doubt, controversy).

The analyst that picks moments also writes a title, but its priority is choosing the segment. This pass reads the
clip's own words, finds the strongest thing that happens (a call to the fans, a confession, a fight, a claim, a
prediction, a surprising fact) and turns it into titles. Names come from the stream (its title, description, the
names the user wrote): the transcriber can mishear them («Lessie» for «JLexis»), so the model may correct a name to
the closest one of that list, but never invent one. Titles must stay anchored to what is said: at least one of their
key words was said (accents and spacing aside), and every proper name in them is from the clip, the stream or the list.
"""
import json, re, unicodedata

SYSTEM = '\n'.join([
    'Eres un clipero con años de experiencia en TikTok, Reels y YouTube Shorts en español. Lees la transcripción automática de '
    'UN clip de un directo y escribes títulos que hagan que la gente se detenga, comente y comparta.',
    'No copies la transcripción: cuenta QUÉ PASA y por qué importa, con un gancho de curiosidad, duda o polémica. '
    'Usa verbos de acción concretos que correspondan a lo que pasa (le hace un llamado a, confiesa, revela, responde a, '
    'se burla de, promete, reta a, defiende a, presume, bromea con).',
    'Si recibes "analisis_del_editor", es la verdad sobre el clip: quien habla ("quien") es la persona del título, y el '
    'tono ("que_pasa", "tipo") manda. Una broma no es una crítica ni una denuncia, un accidente no es una pelea, una '
    'explicación no es una competencia, y no preguntes por un final que el clip ya muestra ("¿lo lograrán?" si lo logran).',
    'Nombres: "nombres_del_directo" son las personas y palabras de esta transmisión. La transcripción automática puede '
    'escribir mal un nombre (por ejemplo "Lessie" o "J. Lessie" cuando se dijo "JLexis"): si un nombre de la transcripción '
    'suena parecido a uno de la lista, usa el de la lista. Nunca inventes un nombre que no esté en la lista, el contexto o '
    'la transcripción.',
    '"canal" es la cuenta que emite. En realities, podcasts o directos con varias personas, quien habla muchas veces NO es '
    'el canal: no pongas el nombre del canal como si lo dijera él salvo que esté claro. Si no sabes quién habla, nombra a '
    'la persona por lo que hace o usa una pregunta.',
    'Palabras como broder, bro, parce, guacho, mano, causa, wey, panas, panos o amigo son muletillas o formas de llamar a '
    'la gente: NO son nombres.',
    'Paso 1. Encuentra lo más fuerte que pasa en el clip (un llamado a los fans, una confesión, una pelea, una crítica, una '
    'promesa, una cifra o una anécdota). Escríbelo en "afirmacion" con tus palabras.',
    'Paso 2. Escribe 5 títulos distintos de 25 a 80 caracteres: uno que cuente la acción con el nombre, uno con una cita '
    'corta y fuerte entre comillas, uno en forma de pregunta que genere duda, uno que plantee un contraste o polémica y '
    'uno que despierte curiosidad sobre el desenlace.',
    '- Corresponde a lo que se dice en el clip, no a otro tema.',
    '- No inventes hechos, cifras, lugares, peleas ni competencias. Un tono con gancho está bien; cambiar lo que pasa, no.',
    '- Escribe en español: mayúscula solo al inicio y en nombres propios.',
    '- Prohibido: "Descubre", "Increíble", "No creerás", "te sorprenderá", emojis, hashtags y títulos todo en mayúsculas.',
    'Ejemplos de estilo (no copies su contenido):',
    '  Se dice: "actívense, quiero escuchar los super chat, pongan team JLexis y su nombre para saber quién me lo envió" -> '
    'JLexis le hace un llamado a sus fans para que se activen con los superchats | «Pongan Team JLexis»: el pedido que '
    'encendió el chat | ¿Responderán sus fans al llamado de JLexis?',
    '  Se dice: "nunca voy a volver a ese torneo, nos robaron, los organizadores son unos estafadores" -> '
    'Ana explota contra los organizadores del torneo | «Son unos estafadores»: Ana jura no volver | '
    '¿Por qué Ana no volverá nunca a ese torneo?',
    'Paso 3. En "mejor" pon el índice (0 a 4) del título con más gancho que respete las reglas.',
])
SCHEMA = {'type': 'object', 'properties': {
    'afirmacion': {'type': 'string'},
    'tipo': {'type': 'string', 'enum': ['afirmación', 'opinión', 'confesión', 'crítica', 'predicción', 'dato', 'anécdota', 'polémica', 'reacción']},
    'titulos': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 5, 'maxItems': 5},
    'mejor': {'type': 'integer', 'minimum': 0, 'maximum': 4}},
    'required': ['afirmacion', 'tipo', 'titulos', 'mejor']}
BANNED = re.compile(r'^(descubre|increíble|no creerás|mira cómo)|te sorprender|#|[\U0001F300-\U0001FAFF]', re.I)
STOP = set('''broder parce guacho causa amigo para pero como cuando donde porque sobre entre desde hasta todo toda todos todas
esto esta este estos estas eso esa ese esos esas muy más menos solo sólo tiene tienen hace hacen dice dicen dijo admite revela
confiesa opina cree piensa nadie nunca siempre cosa cosas razón verdad mejor peor algo alguien quién quien qué cuál cómo según
explota jura critica afirma asegura'''.split())


def fold(text):
    """Lower case without accents: «Actívense» and «activen» share their root."""
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')


def words(text):
    return re.findall(r'\w+', fold(text))


# Words often capitalised in titles that are not people's names.
COMMON_CAPS = set('team super chat superchat superchats live stream vip fans clip clips gamer reality podcast tiktok youtube kick shorts'.split())
ORDINARY = re.compile(r'(ran|ria|rian|aba|aban|ara|aran|ado|ada|ados|adas|ido|ida|idos|idas|ando|iendo|cion|ciones|mente|mos|ste)$')


def grounded_title(title, text, speaker='', names=(), context=''):
    """A title tells what happens in the clip with its own words: at least one key word was said (same root, accents
    and spacing aside: «superchats» = «super chat»), and every proper name in it comes from the clip, the stream's
    names or its context, so a creative title passes and an invented one does not."""
    said = set(words(text)); joined = fold(re.sub(r'\s+', '', text))
    known = set(words(' '.join([speaker, context, *names]))) | said
    root = lambda w, pool: w in pool or any(len(k) >= 5 and (k.startswith(w[:5]) or w.startswith(k[:5])) for k in pool)
    content = [w for w in words(title) if len(w) >= 5 and w not in STOP and not w.isdigit()]
    if not any(root(w, said) or w in joined for w in content if not (w in known and w not in said)): return False
    # Every proper name must be known. A capitalised word starting a phrase is a name unless it reads as an ordinary
    # word (a verb or adverb form, a short word): «Westcol le hace…» is rejected when Westcol is not in the stream,
    # «Responderán sus fans…» is not.
    for m in re.finditer(r'\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{2,})', title):
        w = fold(m.group(1)); before = title[:m.start(1)].rstrip()
        if w in COMMON_CAPS or root(w, known) or w in joined: continue
        if (not before or before[-1] in '.:!?¿¡«"|»') and (len(w) <= 4 or w in STOP or ORDINARY.search(w)): continue
        return False
    # E-26: a name taken from the context or the list (not from the clip) must still sound said in the clip, also when
    # it opens the title («Westcol: mi historia en la cárcel» on a clip where the guest, not Westcol, speaks).
    for m in re.finditer(r'\b([A-ZÁÉÍÓÚÑ][\wáéíóúñ]{3,})', title):
        w = fold(m.group(1)); before = title[:m.start(1)].rstrip()
        if w in COMMON_CAPS or w in said or w in joined: continue
        if (not before or before[-1] in '.:!?¿¡«"|»') and (w in STOP or ORDINARY.search(w)): continue
        # .7, not .6: at .6 «westcol» sounded like «estuvo»; «uescol» (a misheard Westcol) is .77.
        if w in set(words(' '.join([context, *names]))) and not sounds_said(w, text, .7, joined=.6): return False
    # A name from the stream's list only where something that sounds like it is said in the clip («J. Lessie» ~
    # «JLexis»): measured, the model otherwise put the only listed name on every clip, also where someone else spoke.
    for name in names:
        n = fold(re.sub(r'\W+', '', name))
        if len(n) >= 4 and n in fold(re.sub(r'\W+', '', title)) and not sounds_said(n, text): return False
    # A quote must have been said (the model made up «Actívense o desaparecerán»).
    for quote in re.findall(r'[«"“\'‘]([^«»"“”\'’]{6,})[»"”\'’]', title):
        q = [w for w in words(quote) if len(w) >= 3]
        if q and sum(1 for w in q if root(w, said) or w in joined) < .7 * len(q): return False
    return True


def sounds_said(name, text, threshold=.6, joined=None):
    """Whether something in the clip sounds like `name` (folded, no spaces): a word or two joined words close to it.
    `joined`: threshold for two or three words joined (default: `threshold`). E-26: a single word needs .7 («westcol»
    ~ «estuvo» is .62, a false match) while a name the ASR split in two keeps .6 («j lessie» ~ «jlexis» is .62)."""
    from difflib import SequenceMatcher
    said = words(text)
    near = lambda p: abs(len(p) - len(name)) <= 3
    if any(SequenceMatcher(None, name, p).ratio() >= threshold for p in said if near(p)): return True
    pieces = [a + b for a, b in zip(said, said[1:])] + [a + b + c for a, b, c in zip(said, said[1:], said[2:])]
    return any(SequenceMatcher(None, name, p).ratio() >= (threshold if joined is None else joined) for p in pieces if near(p))


def clean(title):
    title = re.split(r'\s+[|/]\s+', title)[0]   # the examples list alternatives with separators; keep one title
    title = re.sub(r'\s+', ' ', title).strip().strip('"').strip()
    if not 8 <= len(title) <= 80 or len(title.split()) > 16 or BANNED.search(title): return None
    if title.isupper(): return None
    return title


def generate(text, speaker='', context='', complete=None, cancel=None, names=(), analysis=None, model=None):
    """Return {'title', 'titles', 'claim', 'kind'} or None when no grounded title survives."""
    if not text.strip(): return None
    payload = {'canal': speaker or 'desconocido', 'contexto': context, 'nombres_del_directo': list(names)[:30],
               'transcripcion_del_clip': text[:4000]}
    if analysis: payload['analisis_del_editor'] = {k: v for k, v in analysis.items() if v}      # who, to whom, what, why, after
    data = complete(payload, cancel) if complete else _ollama(payload, cancel, model)
    raw_titles = data.get('titulos') if isinstance(data.get('titulos'), list) else []
    titles = []
    for raw in raw_titles:
        title = clean(str(raw))
        if title and grounded_title(title, text, speaker, names, context) and title not in titles: titles.append(title)
    if not titles: return None
    best = data.get('mejor', 0)
    first = clean(str(raw_titles[best])) if isinstance(best, int) and 0 <= best < len(raw_titles) else None
    if first in titles: titles.remove(first); titles.insert(0, first)
    return {'title': titles[0], 'titles': titles, 'claim': str(data.get('afirmacion', ''))[:240], 'kind': str(data.get('tipo', ''))}


def _ollama(payload, cancel=None, model=None):
    import gpu_ai
    from cloud_ai import AnalysisCancelled
    if cancel is not None and cancel.is_set(): raise AnalysisCancelled()
    body = {'model': model or gpu_ai.MODEL, 'stream': False, 'format': SCHEMA, 'keep_alive': '10m',
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'options': {'num_ctx': 4096, 'num_predict': 500, 'temperature': .5}}
    if (model or '').startswith('qwen3'): body['think'] = False      # Qwen 3: answer directly, no reasoning block
    with gpu_ai.client(timeout=90) as conn:
        response = conn.post('/api/chat', json=body); response.raise_for_status()
    return json.loads(response.json()['message']['content'])
