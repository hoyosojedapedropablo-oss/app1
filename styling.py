"""Typography and shared layout limits for ASS exports and the editor."""
import re,math
from pathlib import Path
from PIL import ImageFont
ROOT=Path(__file__).parent
ALL_FONTS={'Montserrat':'montserrat.ttf','Poppins':'poppins.ttf','Anton':'anton.ttf','Bebas Neue':'bebasneue.ttf','Oswald':'oswald.ttf','Barlow Condensed':'barlowcondensed.ttf',
           # Fase 3: heavy display faces for the animated subtitle styles (caption_styles.STYLE_FONT)
           'Montserrat ExtraBold':'montserrat-extrabold.ttf','Montserrat Black':'montserrat-black.ttf','Poppins Black':'poppins-black.ttf',
           'Luckiest Guy':'luckiestguy.ttf','Bangers':'bangers.ttf'}
# Only the faces whose file is installed: a missing download falls back to Montserrat instead of failing an export.
FONTS={name:file for name,file in ALL_FONTS.items() if (ROOT/'static/fonts'/file).exists()}

def _win_ratio(path, mtime):
    """(usWinAscent + usWinDescent) / unitsPerEm read from the font file itself (OS/2 and head tables)."""
    import struct
    data = Path(path).read_bytes(); count = struct.unpack('>H', data[4:6])[0]; tables = {}
    for i in range(count):
        tag, _, offset, _ = struct.unpack('>4sIII', data[12 + 16 * i: 28 + 16 * i]); tables[tag] = offset
    upm = struct.unpack('>H', data[tables[b'head'] + 18: tables[b'head'] + 20])[0]
    ascent, descent = struct.unpack('>HH', data[tables[b'OS/2'] + 74: tables[b'OS/2'] + 78])
    return (ascent + descent) / upm if upm and ascent + descent else 1.0

_ratios = {}
def ass_scale(font):
    """E-30: libass sizes a font by its whole Windows line (usWinAscent + usWinDescent) while the browser, PIL and
    title_layout size it by its em, so the MP4 drew Bangers, Poppins or Anton at 56-59 % of the size asked for. Every
    size written to the ASS is multiplied by this ratio, read from the font's own file (cached per file and its date),
    so a face added later needs nothing else. 1.0 when the file is missing or unreadable."""
    import struct
    file = ROOT / 'static/fonts' / FONTS.get(font, FONTS.get('Montserrat', ''))
    try: key = (str(file), file.stat().st_mtime)
    except OSError: return 1.0
    if key not in _ratios:
        try: _ratios[key] = _win_ratio(*key)
        except (OSError, KeyError, ValueError, IndexError, struct.error): _ratios[key] = 1.0
    return _ratios[key]

def ass_color(hex_color):
    value=hex_color.lstrip('#')
    return '&H00'+value[4:6]+value[2:4]+value[0:2]

def wrap_text(text,font,size,max_width,max_lines=2):
    face=ImageFont.truetype(str(ROOT/'static/fonts'/FONTS[font]),size)
    lines=[];current=''
    for word in text.split():
        proposal=(current+' '+word).strip()
        if face.getlength(proposal)>max_width and current:
            lines.append(current);current=word
        else:current=proposal
    if current:lines.append(current)
    return lines,face

def title_layout(text,font,size,two_lines=False):
    text=re.sub(r'\s+',' ',text).strip()
    if not text:return '',size
    for point in range(size,27,-1):
        lines,face=wrap_text(text,font,point,800)
        words=text.split()
        if two_lines and len(words)>1:
            pairs=[(' '.join(words[:i]),' '.join(words[i:])) for i in range(1,len(words))]
            left,right=min(pairs,key=lambda pair:max(face.getlength(pair[0]),face.getlength(pair[1]))+.25*abs(face.getlength(pair[0])-face.getlength(pair[1])))
            lines=[left,right]
        if len(lines)<=2 and all(face.getlength(line)<=800 for line in lines):
            return '\n'.join(lines),point
    raise ValueError('El título es demasiado largo. Acórtalo para que quepa en dos líneas.')

def title_bitmap(text,font,size,padding_x=10,padding_y=4,background='#FFFFFF',foreground='#000000',outline='#000000',outline_width=0,corners='square'):
    """One raster layer shared by preview/export; padding measures from actual glyph ink."""
    from PIL import Image,ImageDraw
    text,point=title_layout(text,font,size,two_lines=True)
    if not text:return None
    face=ImageFont.truetype(str(ROOT/'static/fonts'/FONTS[font]),point)
    spacing=max(1,round(point*.10))
    measure=ImageDraw.Draw(Image.new('RGBA',(1,1)))
    box=measure.multiline_textbbox((0,0),text,font=face,spacing=spacing,align='center',stroke_width=outline_width)
    ink=Image.new('RGBA',(math.ceil(box[2]-box[0])+4,math.ceil(box[3]-box[1])+4))
    ImageDraw.Draw(ink).multiline_text((2-box[0],2-box[1]),text,font=face,spacing=spacing,align='center',fill=foreground,stroke_width=outline_width,stroke_fill=outline)
    ink=ink.crop(ink.getbbox())
    size=(ink.width+2*padding_x,ink.height+2*padding_y)
    if corners=='rounded':
        # Radius grows with the box but never exceeds a pill shape; the same PNG is used by the preview and the MP4.
        image=Image.new('RGBA',size,(0,0,0,0))
        radius=round(min(size[1]/2,14+.18*size[1]))
        ImageDraw.Draw(image).rounded_rectangle((0,0,size[0]-1,size[1]-1),radius=radius,fill=background)
    else:image=Image.new('RGBA',size,background)
    image.alpha_composite(ink,(padding_x,padding_y))
    return image
