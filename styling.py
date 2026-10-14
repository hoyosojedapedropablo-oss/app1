"""Typography and shared layout limits for ASS exports and the editor."""
import re
from pathlib import Path
from PIL import ImageFont
ROOT=Path(__file__).parent
FONTS={'Montserrat':'montserrat.ttf','Poppins':'poppins.ttf','Anton':'anton.ttf','Bebas Neue':'bebasneue.ttf','Oswald':'oswald.ttf','Barlow Condensed':'barlowcondensed.ttf'}

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

def title_layout(text,font,size):
    text=re.sub(r'\s+',' ',text).strip()
    if not text:return '',size
    for point in range(size,27,-1):
        lines,face=wrap_text(text,font,point,800)
        if len(lines)<=2 and all(face.getlength(line)<=800 for line in lines):
            return '\n'.join(lines),point
    raise ValueError('El título es demasiado largo. Acórtalo para que quepa en dos líneas.')
