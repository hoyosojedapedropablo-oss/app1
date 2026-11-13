"""«Silenciar malas palabras»: finds bad words in the transcript (word timings from Whisper) and mutes them.

- The list is the user's (data/profanity.json): strong words on by default, doubtful ones (used as fillers in Colombia,
  Puerto Rico or Argentina) off until the user turns them on, plus the user's own words.
- Matching ignores case, accents and punctuation, and knows the usual spellings («hijueputa», «hijo e puta», «hp»).
- Audio: silence (volume 0) or a beep during each word, with a small margin so the first syllable is not heard.
  The stream has one mixed track, so the game/music is also silent for that fraction of a second.
- Subtitles: the word is shown as its first letter plus asterisks (p***).
Only what the transcription understood can be muted: a misheard word slips through.
"""
import json, re, threading, unicodedata
from pathlib import Path

FILE = None                  # set by app.py: DATA / 'profanity.json'
LOCK = threading.Lock()
LEAD, TAIL = .06, .05        # seconds muted before / after each word

# Each entry: the word as shown, and the spellings that count as it (normalized: lower case, no accents).
STRONG = {
    'puta': ['puta', 'putas', 'putita', 'putisima'], 'puto': ['puto', 'putos'],
    'hijueputa': ['hijueputa', 'hijueputas', 'hijoeputa', 'hijodeputa', 'jueputa', 'hp', 'hijo de puta', 'hijo e puta', 'hijos de puta', 'hija de puta'],
    'malparido': ['malparido', 'malparida', 'malparidos', 'malparidas'], 'gonorrea': ['gonorrea', 'gonorreas'],
    'mierda': ['mierda', 'mierdas'], 'coño': ['cono', 'coño'], 'carajo': ['carajo'], 'cabrón': ['cabron', 'cabrona', 'cabrones'],
    'pendejo': ['pendejo', 'pendeja', 'pendejos', 'pendejas', 'pendejada'], 'verga': ['verga', 'vergas'], 'careverga': ['careverga', 'cara de verga'],
    'pinga': ['pinga'], 'cojones': ['cojones'], 'culiao': ['culiao', 'culiado', 'culiada', 'culia'],
    'mamaguevo': ['mamaguevo', 'mamaguebo', 'mamahuevo', 'mamahuevos', 'mamaguevos'], 'maricón': ['maricon', 'maricones', 'maricona'],
    'joto': ['joto', 'jotos'], 'chingada': ['chingada', 'chingado', 'chingar', 'chingas', 'chingate', 'chingues'], 'pinche': ['pinche', 'pinches'],
    'pelotudo': ['pelotudo', 'pelotuda', 'pelotudos'], 'concha de tu madre': ['concha de tu madre', 'concha tu madre', 'conchetumare', 'conchatumadre'],
    'follar': ['follar', 'follando', 'follo'], 'polla': ['polla', 'pollas'], 'zorra': ['zorra', 'zorras'],
}
DOUBTFUL = {
    'marica': ['marica', 'maricas'], 'chimba': ['chimba', 'chimbas'], 'huevón': ['huevon', 'huevona', 'huevones', 'guevon', 'webon', 'weon'],
    'boludo': ['boludo', 'boluda', 'boludos'], 'culo': ['culo', 'culos'], 'perra': ['perra', 'perras'], 'bicho': ['bicho'],
    'coger': ['coger', 'cogiendo'], 'joder': ['joder', 'jodido', 'jodida', 'jodete'],
}


def norm(text):
    text = unicodedata.normalize('NFD', (text or '').lower().replace('ñ', 'n'))
    return re.sub(r'[^a-z0-9 ]+', '', ''.join(c for c in text if unicodedata.category(c) != 'Mn')).strip()


def load():
    """{'words': [{word, group, on}], 'custom': [..]} with defaults for anything the user never touched."""
    saved = {}
    if FILE and Path(FILE).exists():
        try: saved = json.loads(Path(FILE).read_text(encoding='utf-8'))
        except (OSError, ValueError): saved = {}
    state = saved.get('on', {})
    words = [dict(word=w, group='fuerte', on=state.get(w, True)) for w in STRONG] + [dict(word=w, group='dudosa', on=state.get(w, False)) for w in DOUBTFUL]
    custom = [c for c in saved.get('custom', []) if isinstance(c, str) and norm(c)][:200]
    return dict(words=words, custom=custom)


def save(on, custom):
    known = set(STRONG) | set(DOUBTFUL)
    data = dict(on={k: bool(v) for k, v in (on or {}).items() if k in known}, custom=[c.strip()[:40] for c in (custom or []) if isinstance(c, str) and norm(c)][:200])
    if FILE:
        with LOCK:
            Path(FILE).parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(FILE).with_suffix('.tmp'); tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8'); tmp.replace(FILE)
    return load()


def patterns(config=None):
    """Active spellings as tuples of normalized tokens, longest first (so «hijo de puta» wins over «puta»)."""
    config = config or load(); out = set()
    table = {**STRONG, **DOUBTFUL}
    for item in config['words']:
        if item['on']: out.update(tuple(norm(s).split()) for s in table[item['word']])
    out.update(tuple(norm(c).split()) for c in config['custom'])
    return sorted((p for p in out if p), key=len, reverse=True)


def find(words, start, end, config=None):
    """Bad words in [start, end): [(a, b) seconds relative to `start`], merged. `words`: [{start, end, text}]."""
    pats = patterns(config)
    if not pats: return []
    inside = sorted((w for w in words if start <= w['start'] < end), key=lambda w: w['start'])
    tokens = [(norm(w['text']), w) for w in inside]
    hits = []; i = 0
    while i < len(tokens):
        for p in pats:
            n = len(p)
            if tuple(t for t, _ in tokens[i:i + n]) == p:
                hits.append((tokens[i][1]['start'], tokens[i + n - 1][1]['end'])); i += n - 1; break
            # a word glued to punctuation or a short suffix: «mierda,» «putas!» are normalized already
        i += 1
    ranges = []
    for a, b in hits:
        a = max(0.0, a - start - LEAD); b = min(end - start, b - start + TAIL)
        if ranges and a <= ranges[-1][1] + .05: ranges[-1] = (ranges[-1][0], max(ranges[-1][1], b))
        else: ranges.append((a, b))
    return [(round(a, 3), round(b, 3)) for a, b in ranges]


def audio_filter(ranges, sound='silence'):
    """FFmpeg filter_complex part from [0:a] to [aout], or None when there is nothing to mute."""
    if not ranges: return None
    on = '+'.join(f'between(t,{a:.3f},{b:.3f})' for a, b in ranges)
    if sound == 'beep':
        return (f"[0:a]volume=0:enable='{on}'[amuted];"
                f"sine=frequency=1000:sample_rate=48000,volume=1.4,volume=0:enable='not({on})'[abeep];"
                f"[amuted][abeep]amix=inputs=2:duration=first:normalize=0[aout]")
    return f"[0:a]volume=0:enable='{on}'[aout]"


def censor_text(text, config=None):
    """Subtitle text with each bad word as its first letter plus asterisks."""
    pats = patterns(config)
    if not pats: return text
    parts = re.split(r'(\s+)', text or '')
    words = [(i, norm(p)) for i, p in enumerate(parts) if p.strip()]
    k = 0
    while k < len(words):
        for p in pats:
            n = len(p)
            if tuple(w for _, w in words[k:k + n]) == p:
                for idx, _ in words[k:k + n]:
                    raw = parts[idx]; m = re.match(r'^(\W*)(\w)(\w*)(\W*)$', raw)
                    parts[idx] = f'{m.group(1)}{m.group(2)}{"*" * len(m.group(3))}{m.group(4)}' if m else '*' * len(raw)
                k += n - 1; break
        k += 1
    return ''.join(parts)
