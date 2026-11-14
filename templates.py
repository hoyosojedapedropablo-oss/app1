"""Subtitle templates: one click gives a clip (or every clip of a project) the same subtitle look.

A template is only a subtitle look: font, size, colours, outline, animation, accent, capitals and height. Never the
format (framing, zoom), the title or the logo: those stay as each project has them. The built-in ones cover the usual
niches; the user's own are kept in data/templates.json (older ones that also kept a format or a title are read with
only their subtitle values; the file is not rewritten).
"""
import json, re, threading, uuid
from pathlib import Path

FILE = Path('data/templates.json')        # app.py points it at DATA
LOCK = threading.Lock()

# The values a template may carry: the subtitles' look, nothing else.
KEYS = {'font', 'caption_size', 'caption_color', 'outline_color', 'outline_width', 'caption_style', 'caption_accent',
        'caption_upper', 'caption_y'}

def _t(ident, name, niche, **values):
    return {'id': ident, 'name': name, 'niche': niche, 'builtin': True, 'values': values}

BUILTIN = [
    _t('streamer-pop', 'Streamer · Pop', 'Streamers', caption_style='pop', font='Luckiest Guy', caption_size=76,
       caption_color='#FFFFFF', caption_accent='#FFE14D', caption_upper=True, outline_color='#000000', outline_width=7),
    _t('futbol-contorno', 'Fútbol · Contorno', 'Fútbol', caption_style='contorno', font='Bangers', caption_size=88,
       caption_color='#FFFFFF', caption_accent='#39FF14', caption_upper=True, outline_color='#000000', outline_width=9),
    _t('podcast-karaoke', 'Podcast · Karaoke', 'Podcasts', caption_style='karaoke', font='Montserrat Black', caption_size=68,
       caption_color='#FFFFFF', caption_accent='#FFD400', caption_upper=False, outline_color='#000000', outline_width=6),
    _t('musica-cine', 'Música · Cine', 'Música', caption_style='cine', font='Bebas Neue', caption_size=90,
       caption_color='#FFFFFF', caption_accent='#FFFFFF', caption_upper=True, outline_color='#000000', outline_width=2),
    _t('reaccion-resaltador', 'Reacción · Resaltador', 'Reacciones', caption_style='resaltador', font='Poppins Black', caption_size=70,
       caption_color='#FFFFFF', caption_accent='#FF3B6B', caption_upper=False, outline_color='#000000', outline_width=5),
    _t('datos-clave', 'Datos · Palabra clave', 'Noticias y datos', caption_style='palabra_clave', font='Anton', caption_size=88,
       caption_color='#FFFFFF', caption_accent='#00E5FF', caption_upper=True, outline_color='#000000', outline_width=6),
]


def clean(values):
    """Only the allowed keys, with short plain values (a template is data the user can import)."""
    out = {}
    for k, v in (values or {}).items():
        if k not in KEYS: continue
        if isinstance(v, bool) or (isinstance(v, (int, float)) and abs(v) < 10000): out[k] = v
        elif isinstance(v, str) and len(v) <= 40 and re.fullmatch(r'[\w #.\-áéíóúñÁÉÍÓÚÑ]*', v): out[k] = v
    return out


def _load():
    try: return json.loads(FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError): return []


def all_templates():
    return BUILTIN + [dict(t, builtin=False, values=clean(t.get('values'))) for t in _load() if isinstance(t, dict)]


def save(name, values):
    name = re.sub(r'\s+', ' ', str(name or '')).strip()[:40]
    if not name: raise ValueError('Ponle un nombre a la plantilla.')
    values = clean(values)
    if not values: raise ValueError('La plantilla no tiene ningún ajuste que guardar.')
    with LOCK:
        mine = [t for t in _load() if t.get('name', '').lower() != name.lower()]      # same name: replaced
        item = {'id': uuid.uuid4().hex[:12], 'name': name, 'niche': 'Mis plantillas', 'values': values}
        mine.append(item)
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(mine, ensure_ascii=False, indent=1), encoding='utf-8'); tmp.replace(FILE)
    return dict(item, builtin=False)


def delete(ident):
    with LOCK:
        mine = _load(); rest = [t for t in mine if t.get('id') != ident]
        if len(rest) == len(mine): return False
        tmp = FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(rest, ensure_ascii=False, indent=1), encoding='utf-8'); tmp.replace(FILE)
    return True
