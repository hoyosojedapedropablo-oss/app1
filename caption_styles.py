"""Animated subtitle styles for the exported MP4 (ASS, drawn by FFmpeg/libass) and the same rules for the editor preview.

Each cue is a short phrase (timeline.make_cues). With word timing a style can light up, enlarge or box the word being
said. A cue carries its words when it comes from the transcript; when the user edited its text and the words no longer
match, each word gets a share of the cue's time by its length (static/app.js does exactly the same in the preview).

Styles (`caption_style`):
- clasico:       the phrase, fixed (the app's look until now).
- karaoke:       the phrase; the word being said takes the accent colour.
- pop:           the word being said takes the accent and pops (80 % -> 115 % -> 100 % in 140 ms).
- resaltador:    the word being said gets a box in the accent colour, with dark text.
- palabra_clave: the phrase, fixed; its 1-2 key words (longest, or numbers) in the accent and 15 % bigger.
- cine:          the phrase fades in and out, thin outline and soft shadow.
- contorno:      gaming look: thick black outline and a hard shadow.
"""
import re

STYLES = ('clasico', 'karaoke', 'pop', 'resaltador', 'palabra_clave', 'cine', 'contorno')
# The face each style starts with (the editor switches to it; the user can still pick another) and its look: the
# minimum outline and the shadow. Heavy faces and a hard shadow are what make clipper subtitles read on any video.
STYLE_FONT = {'clasico': 'Montserrat ExtraBold', 'karaoke': 'Montserrat Black', 'pop': 'Luckiest Guy', 'resaltador': 'Poppins Black',
              'palabra_clave': 'Anton', 'cine': 'Bebas Neue', 'contorno': 'Bangers'}
LOOK = {'clasico': (0, 0), 'karaoke': (6, 3), 'pop': (7, 4), 'resaltador': (5, 0), 'palabra_clave': (6, 3), 'cine': (0, 2), 'contorno': (9, 4)}
WORD_BY_WORD = ('karaoke', 'pop', 'resaltador')
POP = r'\fscx80\fscy80\t(0,70,\fscx115\fscy115)\t(70,140,\fscx100\fscy100)'


def inline_color(hex_color):
    """#RRGGBB -> &HBBGGRR& for an inline \\c tag."""
    v = hex_color.lstrip('#')
    return f'&H{v[4:6]}{v[2:4]}{v[0:2]}&'


def word_times(cue):
    """[(start, end)] for each word of the cue's text, relative to the clip. The cue's own words when they still match
    its text; otherwise the cue's time shared by word length."""
    tokens = cue['text'].split()
    if not tokens: return []
    words = cue.get('words') or []
    if len(words) == len(tokens):
        out = [(max(cue['start'], float(w['start'])), min(cue['end'], float(w['end']))) for w in words]
        if all(e > s for s, e in out): return out
    total = sum(len(t) for t in tokens); span = cue['end'] - cue['start']; t = cue['start']; out = []
    for tok in tokens:
        share = span * len(tok) / total; out.append((t, t + share)); t += share
    return out


def key_words(tokens):
    """Indexes of the 1-2 words that carry the phrase: numbers first, then the longest (6+ letters)."""
    plain = [re.sub(r'\W', '', t) for t in tokens]
    numbers = [i for i, p in enumerate(plain) if any(ch.isdigit() for ch in p)]
    longest = sorted((i for i, p in enumerate(plain) if len(p) >= 6 and i not in numbers), key=lambda i: -len(plain[i]))
    return set((numbers + longest)[:2])


def _spans(laid_out):
    """The laid-out text (lines joined by \\n) as [(word, separator)], so tags can wrap one word and keep the breaks."""
    parts = re.split(r'(\s+)', laid_out)
    out = []
    for i in range(0, len(parts), 2):
        sep = parts[i + 1] if i + 1 < len(parts) else ''
        if parts[i]: out.append((parts[i], r'\N' if '\n' in sep else (' ' if sep else '')))
    return out


def _text(spans, tag_for, reset=''):
    """ASS text with `tag_for(i)` before word i (None: no tag) and `reset` after it. Not \\r alone: it would also drop
    the size the layout chose for this cue."""
    out = []
    for i, (word, sep) in enumerate(spans):
        tag = tag_for(i)
        out.append((('{' + tag + '}' + word + '{' + reset + '}') if tag else word) + sep)
    return ''.join(out)


def styles_block(font, size, color, outline, outline_width, accent, style, ass_color):
    """The [V4+ Styles] lines: the base caption style plus the box style of «resaltador»."""
    least, shadow = LOOK.get(style, (0, 0))
    back = '&H64000000' if style == 'cine' else '&H00000000' if shadow else '&H80000000'      # cine: soft; others: hard
    width = min(outline_width, 2) if style == 'cine' else max(outline_width, least)
    lines = [f'Style: Caption,{font},{size},{color},&H00FFFFFF,{outline},{back},-1,0,0,0,100,100,0,0,1,{width},{shadow},2,100,100,290,1']
    # libass draws BorderStyle 3 as an opaque box in the outline colour behind the run.
    lines.append(f'Style: Box,{font},{size},&H00111111,&H00FFFFFF,{ass_color(accent)},&H00000000,-1,0,0,0,100,100,0,0,3,10,0,2,100,100,290,1')
    return '\n'.join(lines)


def events(cue, laid_out, style, accent, prefix, stamp, color='#FFFFFF', point=64):
    """Dialogue lines for one cue. `laid_out`: its text already wrapped (\\n between lines); `prefix`: position and size
    tags; `stamp`: seconds -> ASS time; `color`, `point`: the cue's own colour and size, restored after a tagged word."""
    spans = _spans(laid_out)
    if not spans: return []
    acc = inline_color(accent)
    plain = rf'\c{inline_color(color)}\fscx100\fscy100'
    boxed = rf'\rCaption\fs{point}' 
    line = lambda start, end, text: f'Dialogue: 0,{stamp(start)},{stamp(end)},Caption,,0,0,0,,{prefix}{text}'
    if style not in WORD_BY_WORD:
        keys = key_words([w for w, _ in spans]) if style == 'palabra_clave' else set()
        lead = r'{\fad(120,80)\blur0.6}' if style == 'cine' else ''
        return [line(cue['start'], cue['end'], lead + _text(spans, lambda i: rf'\c{acc}\fscx115\fscy115' if i in keys else None, plain))]
    times = word_times(dict(cue, text=' '.join(w for w, _ in spans)))
    out = []
    for i, (start, _) in enumerate(times):
        end = times[i + 1][0] if i + 1 < len(times) else cue['end']
        if i == 0 and start > cue['start'] + .02:
            out.append(line(cue['start'], start, _text(spans, lambda k: None)))
        if end - start < .02: continue
        if style == 'karaoke': tag = lambda k, i=i: rf'\c{acc}' if k == i else None
        elif style == 'pop': tag = lambda k, i=i: rf'\c{acc}{POP}' if k == i else None
        else: tag = lambda k, i=i: rf'\rBox\fs{point}' if k == i else None
        out.append(line(start, end, _text(spans, tag, boxed if style == 'resaltador' else plain)))
    return out
