"""Clip templates, like OpusClip's: one click gives every clip of a project the same format, subtitles and title.

A template is a set of editor values. The built-in ones cover the usual niches; the user's own are kept in
data/templates.json. Applying one (static/app.js) sets the project's format (framing and zoom) and copies the look to
every clip through «Aplicar a todos los clips»; each clip keeps its text, times and tracking.
"""
import json, re, threading, uuid
from pathlib import Path

FILE = Path('data/templates.json')        # app.py points it at DATA
LOCK = threading.Lock()

# The values a template may carry: format, subtitles and title. Not times, texts or the logo's file (a user template may
# keep its logo choice).
KEYS = {'framing', 'zoom', 'style', 'font', 'caption_size', 'caption_color', 'outline_color', 'outline_width', 'caption_style',
        'caption_accent', 'caption_upper', 'caption_y', 'show_subtitles', 'title_font', 'title_size', 'title_bg_color',
        'title_text_color', 'title_outline_color', 'title_outline_width', 'title_corners', 'title_padding_x', 'title_padding_y',
        'logo', 'logo_width', 'logo_x', 'logo_y'}

def _t(ident, name, niche, **values):
    return {'id': ident, 'name': name, 'niche': niche, 'builtin': True, 'values': values}

BUILTIN = [
    _t('streamer-pop', 'Streamer · Pop', 'Streamers', framing='zoom', zoom='balanced', caption_style='pop', font='Luckiest Guy',
       caption_size=72, caption_color='#FFFFFF', caption_accent='#FFE14D', caption_upper=True, outline_color='#000000', outline_width=7,
       title_font='Montserrat', title_bg_color='#FFFFFF', title_text_color='#000000', title_corners='rounded', show_subtitles=True),
    _t('futbol-contorno', 'Fútbol · Contorno', 'Fútbol', framing='crop', zoom='balanced', caption_style='contorno', font='Bangers',
       caption_size=76, caption_color='#FFFFFF', caption_accent='#39FF14', caption_upper=True, outline_color='#000000', outline_width=9,
       title_font='Anton', title_bg_color='#39FF14', title_text_color='#000000', title_corners='square', show_subtitles=True),
    _t('podcast-karaoke', 'Podcast · Karaoke', 'Podcasts', framing='zoom', zoom='soft', caption_style='karaoke', font='Montserrat Black',
       caption_size=64, caption_color='#FFFFFF', caption_accent='#FFD400', caption_upper=False, outline_color='#000000', outline_width=6,
       title_font='Montserrat', title_bg_color='#FFFFFF', title_text_color='#000000', title_corners='rounded', show_subtitles=True),
    _t('musica-cine', 'Música · Cine', 'Música', framing='zoom', zoom='soft', caption_style='cine', font='Bebas Neue',
       caption_size=70, caption_color='#FFFFFF', caption_accent='#FFFFFF', caption_upper=True, outline_color='#000000', outline_width=2,
       title_font='Bebas Neue', title_bg_color='#000000', title_text_color='#FFFFFF', title_corners='square', show_subtitles=True),
    _t('reaccion-resaltador', 'Reacción · Resaltador', 'Reacciones', framing='zoom', zoom='balanced', caption_style='resaltador',
       font='Poppins Black', caption_size=66, caption_color='#FFFFFF', caption_accent='#FF3B6B', caption_upper=False,
       outline_color='#000000', outline_width=5, title_font='Poppins', title_bg_color='#FF3B6B', title_text_color='#FFFFFF',
       title_corners='rounded', show_subtitles=True),
    _t('datos-clave', 'Datos · Palabra clave', 'Noticias y datos', framing='crop', zoom='balanced', caption_style='palabra_clave',
       font='Anton', caption_size=70, caption_color='#FFFFFF', caption_accent='#00E5FF', caption_upper=True, outline_color='#000000',
       outline_width=6, title_font='Anton', title_bg_color='#00E5FF', title_text_color='#000000', title_corners='square', show_subtitles=True),
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
    return BUILTIN + [dict(t, builtin=False) for t in _load()]


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
