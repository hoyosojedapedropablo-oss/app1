import json, os, re, subprocess, threading, uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT=Path(__file__).parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
app=FastAPI(title='Clip Studio')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
JOBS={}; pool=ThreadPoolExecutor(max_workers=1)
model=None
CATEGORIES={
 'Polémica':['mentira','verdad','nadie','equivocado','odio','polémica','controversia'],
 'Curiosidad':['sabías','increíble','curioso','descubr','secreto','imagina'],
 'Datos':['por ciento','millones','estudio','investigación','dato','científico'],
 'Relato':['recuerdo','pasó','historia','cuando','un día','entonces'],
 'Humor':['risa','jaja','gracioso','chiste','broma'],
 'Emoción':['llor','triste','amor','miedo','perdí','feliz','sueño','familia']}

def command(args, cwd=None):
 r=subprocess.run(args,capture_output=True,text=True,cwd=cwd)
 if r.returncode: raise RuntimeError(r.stderr[-1800:])
 return r.stdout

def probe(path):
 return json.loads(command(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))

def select_clips(segments,minimum,maximum):
 candidates=[]
 for i,s in enumerate(segments):
  end=s['end']; chosen=[]
  for t in segments[i:]:
   if t['end']-s['start']>maximum: break
   chosen.append(t); end=t['end']
   if end-s['start']>=minimum and re.search(r'[.!?]$',t['text'].strip()): break
  if end-s['start']<minimum: continue
  text=' '.join(t['text'].strip() for t in chosen)
  counts={k:sum(text.lower().count(w) for w in words) for k,words in CATEGORIES.items()}
  cat=max(counts,key=counts.get)
  score=min(95,35+sum(counts.values())*7+min(14,len(text.split())//8)+(8 if '?' in text else 0))
  title=re.split(r'[.!?]',text)[0].strip()[:85] or 'Un momento para compartir'
  candidates.append(dict(id=uuid.uuid4().hex,start=s['start'],end=end,title=title,text=text,segments=chosen,score=score,category=cat if counts[cat] else 'Conversación',reason='Señales de lenguaje y cierre de frase; revisa el contexto antes de publicar.'))
 result=[]
 for c in sorted(candidates,key=lambda c:c['score'],reverse=True):
  if c['score']<49: continue
  if any(min(c['end'],a['end'])>max(c['start'],a['start']) for a in result): continue
  result.append(c)
 return sorted(result,key=lambda c:c['start'])

@app.get('/')
def home(): return FileResponse(ROOT/'static/index.html')

@app.post('/api/upload')
async def upload(file:UploadFile=File(...)):
 ident=uuid.uuid4().hex; folder=DATA/ident; folder.mkdir(); path=folder/'source'
 try:
  with path.open('wb') as out:
   total=0
   while chunk:=await file.read(1024*1024):
    total+=len(chunk)
    if total>12*1024**3: raise ValueError('El archivo supera 12 GB.')
    out.write(chunk)
  info=probe(path); duration=float(info['format']['duration'])
  if duration>7200: raise ValueError('La duración máxima es 120 minutos.')
  if not any(s['codec_type']=='video' for s in info['streams']): raise ValueError('El archivo no contiene video.')
  JOBS[ident]=dict(id=ident,name=file.filename,duration=duration,status='uploaded',clips=[])
  return JOBS[ident]
 except Exception as e:
  path.unlink(missing_ok=True)
  raise HTTPException(400,str(e))

class Analysis(BaseModel):
 minimum:int=Field(default=20,ge=5,le=180)
 maximum:int=Field(default=60,ge=5,le=180)

def analyze(ident,options):
 global model
 job=JOBS[ident]
 try:
  job.update(status='transcribing',message='Transcribiendo con Whisper local. La primera ejecución descarga el modelo.')
  from faster_whisper import WhisperModel
  if model is None: model=WhisperModel(os.getenv('WHISPER_MODEL','base'),device='cpu',compute_type='int8',cpu_threads=4)
  segments,info=model.transcribe(str(DATA/ident/'source'),vad_filter=True,word_timestamps=True)
  transcript=[]
  for s in segments:
   transcript.append(dict(start=s.start,end=s.end,text=s.text,words=[dict(start=w.start,end=w.end,text=w.word) for w in (s.words or [])]))
   job['progress']=min(99,round(s.end/job['duration']*100))
  job.update(status='ready',progress=100,transcript=transcript,clips=select_clips(transcript,options.minimum,options.maximum),message='Análisis terminado. La puntuación es heurística, no una predicción de viralidad.')
 except Exception as e: job.update(status='error',message=str(e))

@app.post('/api/jobs/{ident}/analyze')
def start(ident:str,options:Analysis):
 if ident not in JOBS: raise HTTPException(404)
 if options.minimum>options.maximum: raise HTTPException(400,'El mínimo no puede superar el máximo.')
 if JOBS[ident]['status'] in ['queued','transcribing']: raise HTTPException(409,'El análisis ya está en curso.')
 JOBS[ident]['status']='queued'; pool.submit(analyze,ident,options)
 return JOBS[ident]

@app.get('/api/jobs/{ident}')
def status(ident:str):
 if ident not in JOBS: raise HTTPException(404)
 return JOBS[ident]

@app.get('/api/jobs/{ident}/video')
def video(ident:str):
 if ident not in JOBS: raise HTTPException(404)
 return FileResponse(DATA/ident/'source',media_type='video/mp4')

@app.post('/api/logos/{brand}')
async def logo(brand:str,file:UploadFile=File(...)):
 if brand not in ['kick','roobet','rainbet']: raise HTTPException(400)
 from PIL import Image
 raw=await file.read(5*1024*1024+1)
 if len(raw)>5*1024*1024: raise HTTPException(400,'Máximo 5 MB.')
 import io
 try:
  im=Image.open(io.BytesIO(raw)); im.thumbnail((1024,1024)); im.convert('RGBA').save(DATA/f'{brand}.png')
 except Exception: raise HTTPException(400,'Usa un logo PNG, JPG o WebP válido.')
 return {'ok':True}

class Export(BaseModel):
 start:float=Field(ge=0)
 end:float=Field(gt=0)
 title:str=Field(max_length=140)
 subtitles:str=Field(max_length=20000)
 style:str='classic'
 font:str='DejaVu Sans'
 logo:str='none'
 framing:str='fit'

def stamp(seconds):
 c=round(max(0,seconds)*100); return f'{c//360000}:{c//6000%60:02}:{c//100%60:02}.{c%100:02}'

def safe(text): return text.replace('\\','').replace('{','').replace('}','').replace('\n',r'\N')

def ass_file(path,opts,transcript=None):
 color={'classic':'&H00FFFFFF','bold':'&H0000FFFF','mint':'&H0085F5AA'}.get(opts.style,'&H00FFFFFF')
 font=opts.font if opts.font in ['DejaVu Sans','DejaVu Serif','Liberation Sans','Liberation Mono'] else 'DejaVu Sans'
 header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},64,{color},&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,85,85,250,1
Style: Title,{font},58,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,20,0,8,95,95,180,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
 duration=opts.end-opts.start
 events=[f'Dialogue: 1,0:00:00.00,{stamp(duration)},Title,,0,0,0,,{safe(opts.title)}'] if opts.title.strip() else []
 # Editable captions are divided into readable phrases and distributed across the clip.
 words=opts.subtitles.split(); phrases=[' '.join(words[i:i+7]) for i in range(0,len(words),7)]
 timed=[t for t in (transcript or []) if t['start']>=opts.start and t['end']<=opts.end]
 original=' '.join(t['text'].strip() for t in timed)
 if timed and original.strip()==opts.subtitles.strip():
  for t in timed:
   events.append(f"Dialogue: 0,{stamp(t['start']-opts.start)},{stamp(t['end']-opts.start)},Caption,,0,0,0,,{safe(t['text'].strip())}")
  phrases=[]
 for i,phrase in enumerate(phrases):
  events.append(f'Dialogue: 0,{stamp(i*duration/len(phrases))},{stamp((i+1)*duration/len(phrases))},Caption,,0,0,0,,{safe(phrase)}')
 path.write_text(header+'\n'.join(events))

@app.post('/api/jobs/{ident}/export')
def export(ident:str,opts:Export):
 if ident not in JOBS: raise HTTPException(404)
 if opts.end<=opts.start or opts.end>JOBS[ident]['duration'] or opts.end-opts.start>180: raise HTTPException(400,'El clip debe durar entre 0 y 180 segundos y estar dentro del video.')
 if opts.framing not in ['fit','crop']: raise HTTPException(400)
 if opts.logo not in ['none','kick','roobet','rainbet']: raise HTTPException(400)
 logo=DATA/f'{opts.logo}.png'
 if opts.logo!='none' and not logo.exists(): raise HTTPException(400,'Primero carga el archivo del logo seleccionado.')
 folder=DATA/ident; token=uuid.uuid4().hex; ass=folder/f'{token}.ass'; output=folder/f'{token}.mp4'; ass_file(ass,opts,JOBS[ident].get('transcript',[]))
 geometry='scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black' if opts.framing=='fit' else 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920'
 filters=f'{geometry},setsar=1,ass={ass.name}'
 args=['ffmpeg','-v','error','-y','-ss',str(opts.start),'-i',str(folder/'source')]
 if opts.logo!='none':
  args+=['-i',str(logo),'-filter_complex',f'[0:v]{filters}[v];[1:v]scale=150:-1[l];[v][l]overlay=W-w-45:80[out]','-map','[out]','-map','0:a?']
 else: args+=['-vf',filters]
 args+=['-t',str(opts.end-opts.start),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)]
 try: command(args,cwd=folder)
 except Exception as e: raise HTTPException(500,str(e))
 return FileResponse(output,media_type='video/mp4',filename=f'clip-{token[:6]}.mp4')
