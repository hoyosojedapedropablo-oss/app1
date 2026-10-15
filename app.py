import json, os, re, subprocess, threading, uuid
import tempfile
from fractions import Fraction
from typing import Literal
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator, SecretStr
from timeline import make_cues, clip_words
from intelligence import select_clips
from styling import FONTS, ass_color, title_layout

ROOT=Path(__file__).parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
os.environ.setdefault('HF_HOME',str(DATA/'models'))
app=FastAPI(title='Clip Studio')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
JOBS={}; pool=ThreadPoolExecutor(max_workers=1)
model=None
CANCEL={}
import cloud_ai
import gpu_ai
import gpu_transcribe

def command(args, cwd=None):
 r=subprocess.run(args,capture_output=True,text=True,cwd=cwd)
 if r.returncode: raise RuntimeError(r.stderr[-1800:])
 return r.stdout

def probe(path):
 return json.loads(command(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))

def decode_audio(path):
 # FFmpeg normalizes every input to the float32 mono 16 kHz waveform Whisper expects.
 # Passing an array avoids faster-whisper's incompatible PyAV metadata_errors call.
 with tempfile.TemporaryDirectory() as tmp:
  pcm=Path(tmp)/'audio.f32'
  command(['ffmpeg','-v','error','-y','-i',str(path),'-vn','-ac','1','-ar','16000','-f','f32le',str(pcm)])
  audio=np.fromfile(pcm,dtype='<f4')
 if not audio.size: raise ValueError('El video no contiene audio utilizable.')
 return audio

@app.get('/')
def home(): return FileResponse(ROOT/'static/index.html',headers={'Cache-Control':'no-store'})

def register_video(ident,path,name):
 info=probe(path);duration=float(info['format']['duration'])
 if not 0<duration<=7200:raise ValueError('La duración máxima es 120 minutos.')
 stream=next((s for s in info['streams'] if s['codec_type']=='video'),None)
 if stream is None:raise ValueError('El archivo no contiene video.')
 try:fps=float(Fraction(stream.get('avg_frame_rate','30/1')))
 except (ValueError,ZeroDivisionError):fps=30
 JOBS[ident]=dict(id=ident,name=name,duration=duration,fps=max(24,min(60,fps)),status='uploaded',clips=[])
 save_job(JOBS[ident]);return JOBS[ident]

IMPORTS={}
import_pool=ThreadPoolExecutor(max_workers=1)
class YouTubeInput(BaseModel):
 url:str=Field(min_length=1,max_length=2000)
 quality:Literal['fast','original']='fast'

def import_youtube(ident,url,quality="fast"):
 import shutil
 from youtube_import import download
 folder=DATA/ident;folder.mkdir(exist_ok=True)
 def progress(value,message,**metadata):IMPORTS[ident].update(status='downloading',progress=value,message=message,**metadata)
 try:
  progress(0,'Consultando video de YouTube…')
  path,name=download(url,folder,progress,mode=quality)
  path.rename(folder/'source')
  job=register_video(ident,folder/'source',name)
  job['youtube']={key:IMPORTS[ident][key] for key in ['title','channel','thumbnail','duration','quality'] if key in IMPORTS[ident]}
  job['youtube_url']=url;job['youtube_quality']=quality;save_job(job)
  IMPORTS[ident].update(status='ready',progress=100,message='Video listo para analizar.',job=job)
 except Exception as e:
  message=str(e) if isinstance(e,ValueError) else 'YouTube no permitió completar la descarga. Puede requerir inicio de sesión o haber cambiado su acceso. Prueba con un video público o sube el archivo descargado.'
  IMPORTS[ident].update(status='error',message=message)
  JOBS.pop(ident,None)
  shutil.rmtree(folder,ignore_errors=True)

@app.post('/api/youtube')
def start_youtube(options:YouTubeInput):
 from youtube_import import canonical_url
 try:url=canonical_url(options.url)
 except ValueError as e:raise HTTPException(400,str(e))
 if any(v['status'] in ('queued','downloading') for v in IMPORTS.values()):raise HTTPException(409,'Ya hay una descarga en curso. Espera a que termine.')
 for job in JOBS.values():
  if job.get('youtube_url')==url and job.get('youtube_quality')==options.quality and (DATA/job['id']/'source').exists():
   ident=uuid.uuid4().hex
   IMPORTS[ident]=dict(id=ident,status='ready',progress=100,message='Video recuperado: ya estaba descargado.',job=job,**job.get('youtube',{}))
   return IMPORTS[ident]
 ident=uuid.uuid4().hex
 IMPORTS[ident]=dict(id=ident,status='queued',progress=0,message='Consultando título y duración…',thumbnail='https://i.ytimg.com/vi/'+url.split('v=')[1]+'/hqdefault.jpg',title='Preparando video de YouTube…')
 import_pool.submit(import_youtube,ident,url,options.quality)
 return IMPORTS[ident]

@app.get('/api/youtube/{ident}')
def youtube_status(ident:str):
 if ident not in IMPORTS:raise HTTPException(404)
 return IMPORTS[ident]

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
  return register_video(ident,path,file.filename)
 except Exception as e:
  path.unlink(missing_ok=True)
  raise HTTPException(400,str(e))

class Analysis(BaseModel):
 minimum:int=Field(default=20,ge=5,le=180)
 maximum:int=Field(default=60,ge=5,le=180)
 speaker:str=Field(default='',max_length=120)
 context:str=Field(default='',max_length=4000)
 quality:Literal['quality','fast']='fast'
 engine:Literal['gpu','cloud','local']='gpu'
 transcribe_gpu:bool=False
 max_clips:int=Field(default=10,ge=1,le=20)
 @model_validator(mode='after')
 def validate_range(self):
  if self.minimum>self.maximum: raise ValueError('El mínimo no puede superar el máximo.')
  return self

def analyze(ident,options):
 global model
 job=JOBS[ident]
 try:
  job.update(clips=[],progress=0,analysis_range={'minimum':options.minimum,'maximum':options.maximum},status='transcribing',message='Transcribiendo con Whisper local. La primera ejecución descarga el modelo.')
  event=CANCEL.setdefault(ident,threading.Event())
  if event.is_set():raise cloud_ai.AnalysisCancelled()
  if options.engine=='gpu':
   job.update(message='Cargando el modelo local y comprobando memoria GPU…')
   job['gpu_status']=gpu_ai.warmup()
  cached=DATA/ident/'transcript.json'
  if cached.exists():
   transcript=json.loads(cached.read_text(encoding='utf-8'))
  elif options.transcribe_gpu:
   if options.engine=='gpu':gpu_ai.unload()
   transcript=gpu_transcribe.transcribe(DATA/ident/'source',DATA/ident,event,lambda percentage,message:job.update(progress=round(percentage*.6),message=message))
   cached.write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
  else:
   from faster_whisper import WhisperModel
   if model is None:model=WhisperModel(os.getenv('WHISPER_MODEL','small'),device='cpu',compute_type='int8',cpu_threads=4)
   audio=decode_audio(DATA/ident/'source')
   segments,info=model.transcribe(audio,vad_filter=True,word_timestamps=True)
   transcript=[]
   for s in segments:
    if event.is_set():raise cloud_ai.AnalysisCancelled()
    transcript.append(dict(start=s.start,end=s.end,text=s.text,words=[dict(start=w.start,end=w.end,text=w.word) for w in (s.words or [])]))
    job['progress']=min(60,round(s.end/job['duration']*60))
   cached.write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
  job['transcript']=transcript
  if options.engine=='gpu':job['gpu_status']=gpu_ai.warmup()
  if event.is_set():raise cloud_ai.AnalysisCancelled()
  job.update(status='selecting',progress=60,message='Analizando transcripción en la nube…' if options.engine=='cloud' else 'Analizando con GPU local…' if options.engine=='gpu' else 'Preparando modelo local (primera descarga hasta 4,68 GB). Puede tardar en CPU.')
  profile=read_profile()['instructions']
  def progress(i,total,stage='selection'):
   if event.is_set():raise cloud_ai.AnalysisCancelled()
   if stage in ['cloud','gpu']:
    job.update(progress=60+round(38*i/max(1,total)),message=f"Análisis {'GPU local' if stage=='gpu' else 'en nube'} · {i} de {total} bloques completados")
    return
   job.update(progress=(60+round(25*i/max(1,total))) if stage=='selection' else (85+round(13*i/max(1,total))),message=f'Analizando contexto · bloque {i+1} de {total}' if stage=='selection' else f'Revisando cortes y títulos · clip {i+1} de {total}')
  if options.engine=='cloud':
   job['selection_diagnostics']=[]
   clips=cloud_ai.select_cloud(transcript,options.minimum,options.maximum,job['duration'],speaker=options.speaker,context=options.context,profile=profile,max_clips=options.max_clips,on_progress=progress,cancel=event,diagnostics=job['selection_diagnostics'])
  elif options.engine=='gpu':
   job['selection_diagnostics']=[]
   clips=gpu_ai.select_gpu(transcript,options.minimum,options.maximum,job['duration'],speaker=options.speaker,context=options.context,profile=profile,max_clips=options.max_clips,on_progress=progress,cancel=event,diagnostics=job['selection_diagnostics'])
  else:
   clips=select_clips(transcript,options.minimum,options.maximum,job['duration'],speaker=options.speaker,context=options.context,profile=profile,quality=options.quality,max_clips=options.max_clips,on_progress=progress)
  from coverage import complete_coverage,covered,TitleBatch
  completion=gpu_ai.complete if options.engine=='gpu' else cloud_ai.complete if options.engine=='cloud' else lambda payload,**kwargs: __import__('intelligence').query_json(json.dumps(payload,ensure_ascii=False),TitleBatch.model_json_schema(),options.quality)
  job.update(progress=98,message='Completando cobertura del 75% y títulos de todos los clips…')
  def title_progress(done,total,stage):job.update(progress=98+round(done/max(1,total)),message=f'Títulos de clips para revisar · {done} de {total}')
  clips=complete_coverage(clips,transcript,job['duration'],options.minimum,options.maximum,completion,speaker=options.speaker,context=options.context,profile=profile,cancel=event,on_progress=title_progress)
  job['coverage_percent']=round(100*covered(clips)/job['duration'],2)
  message=f'{len(clips)} clips · cobertura {job["coverage_percent"]}% del video. Mayor potencial identifica los destacados; el resto queda para tu revisión.' if clips else 'La selección quedó vacía tras la revisión. Esto no demuestra que el video no tenga potencial. Revisa la transcripción y añade contexto para volver a analizar sin transcribir de nuevo.'
  job.update(status='ready',progress=100,clips=clips,message=message)
 except cloud_ai.AnalysisCancelled:job.update(status='cancelled',message='Análisis cancelado. Puedes reutilizar la transcripción completa si ya se guardó.')
 except Exception as e: job.update(status='error',message=str(e))
 finally:save_job(job)

@app.post('/api/jobs/{ident}/analyze')
def start(ident:str,options:Analysis):
 if ident not in JOBS: raise HTTPException(404)
 if options.minimum>options.maximum: raise HTTPException(400,'El mínimo no puede superar el máximo.')
 if JOBS[ident]['status'] in ['queued','transcribing','selecting']: raise HTTPException(409,'El análisis ya está en curso.')
 if options.engine=='cloud' and not cloud_ai.configured():raise HTTPException(400,'Conecta tu clave de API en Configurar IA antes de iniciar el modo rápido.')
 if options.engine=='gpu':
  info=gpu_ai.status()
  if not info['available'] or not info['model_ready']:raise HTTPException(400,info['message'])
 if options.engine=='local':
  import importlib.util
  if importlib.util.find_spec('llama_cpp') is None:raise HTTPException(400,'Para usar IA local, ejecuta INSTALAR_IA_LOCAL y reinicia la app. El modo nube no necesita ese motor.')
 CANCEL[ident]=threading.Event()
 JOBS[ident]['analysis_options']=options.model_dump()
 JOBS[ident]['status']='queued'; JOBS[ident]['started_at']=__import__('time').time();save_job(JOBS[ident]); pool.submit(analyze,ident,options)
 return JOBS[ident]

class Profile(BaseModel):
 instructions:str=Field(default='Elige títulos según el contexto: para opiniones o anuncios, atribuye y resume (ejemplos: Westcol opina sobre la situación del país; Westcol anuncia la pelea más esperada de su evento). Para emociones compartidas usa identificación, sin inventar causas: si el hablante está triste por una derrota de Colombia, Todos somos Westcol después del partido, Westcol y yo estamos pasando por lo mismo o Mood Westcol. Usa nombres solo cuando estén identificados. No copiar la transcripción ni inventar polémicas. Las frases de identificación son recursos retóricos ligados a la emoción del fragmento; no inventes hechos.',max_length=3000)

def read_profile():
 path=DATA/'editorial-profile.json'
 return json.loads(path.read_text(encoding='utf-8')) if path.exists() else Profile().model_dump()

@app.get('/api/profile')
def profile(): return read_profile()

@app.put('/api/profile')
def save_profile(options:Profile):
 (DATA/'editorial-profile.json').write_text(options.model_dump_json(),encoding='utf-8')
 return options

@app.post('/api/jobs/{ident}/cancel')
def cancel_job(ident:str):
 if ident not in JOBS:raise HTTPException(404)
 CANCEL.setdefault(ident,threading.Event()).set()
 JOBS[ident]['message']='Cancelación solicitada. Puedes cerrar la app para detener inmediatamente un cálculo local.'
 return {'ok':True}

@app.get('/api/gpu')
def gpu_status():return dict(gpu_ai.status(),transcription_installed=gpu_transcribe.installed(),transcription_ready=gpu_transcribe.installed() and (DATA/'cuda-transcription-ready.json').exists())

@app.post('/api/gpu/check')
def check_gpu():
 try:return gpu_ai.warmup()
 except ValueError as e:raise HTTPException(400,str(e))

class Connection(BaseModel):
 key:SecretStr

@app.get('/api/ai')
def ai_status():return {'configured':cloud_ai.configured(),'model':cloud_ai.MODEL}

@app.post('/api/ai')
def connect_ai(options:Connection,request:Request):
 if request.client and request.client.host not in ['127.0.0.1','::1','testclient']:raise HTTPException(403,'Configura la clave desde este equipo o mediante CLIP_AI_KEY.')
 origin=request.headers.get('origin')
 if origin and origin not in ['http://127.0.0.1:8000','http://localhost:8000']:raise HTTPException(403)
 try:cloud_ai.check_connection(options.key.get_secret_value().strip())
 except Exception as e:raise HTTPException(400,str(e))
 cloud_ai.configure(options.key.get_secret_value())
 return {'configured':True,'model':cloud_ai.MODEL,'message':'Conexión verificada. La clave queda en memoria hasta cerrar la app. El análisis consume saldo de API.'}

@app.delete('/api/ai')
def disconnect_ai(request:Request):
 if request.client and request.client.host not in ['127.0.0.1','::1','testclient']:raise HTTPException(403)
 cloud_ai.configure('');return {'configured':False}

@app.get('/api/jobs')
def list_jobs():
 return [dict(id=j['id'],name=j['name'],duration=j['duration'],cached=(DATA/j['id']/'transcript.json').exists()) for j in JOBS.values()]

@app.get('/api/jobs/{ident}')
def status(ident:str):
 if ident not in JOBS: raise HTTPException(404)
 return {key:value for key,value in JOBS[ident].items() if key!='transcript'}

@app.get('/api/jobs/{ident}/video')
def video(ident:str):
 if ident not in JOBS: raise HTTPException(404)
 return FileResponse(DATA/ident/'source',media_type='video/mp4')

@app.post('/api/logos/{brand}')
async def logo(brand:str,file:UploadFile=File(...)):
 if brand not in ['kick','roobet','rainbet','custom']: raise HTTPException(400)
 from PIL import Image
 raw=await file.read(5*1024*1024+1)
 if len(raw)>5*1024*1024: raise HTTPException(400,'Máximo 5 MB.')
 import io
 try:
  im=Image.open(io.BytesIO(raw)); im.thumbnail((1024,1024))
  logo_id=uuid.uuid4().hex if brand=='custom' else brand
  im.convert('RGBA').save(DATA/f'{logo_id}.png')
 except Exception: raise HTTPException(400,'Usa un logo PNG, JPG o WebP válido.')
 catalog_path=DATA/'logos.json'
 catalog=json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else {}
 catalog[logo_id]=file.filename or logo_id
 catalog_path.write_text(json.dumps(catalog,ensure_ascii=False),encoding='utf-8')
 return {'ok':True,'id':logo_id,'name':catalog[logo_id]}

@app.get('/api/logos')
def logos():
 path=DATA/'logos.json'
 catalog=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
 return [{'id':key,'name':value} for key,value in catalog.items() if (DATA/f'{key}.png').exists()]

@app.get('/api/logos/{logo_id}/image')
def logo_image(logo_id:str):
 if not re.fullmatch(r'(kick|roobet|rainbet|[a-f0-9]{32})',logo_id) or not (DATA/f'{logo_id}.png').exists():raise HTTPException(404)
 return FileResponse(DATA/f'{logo_id}.png',media_type='image/png')

class Caption(BaseModel):
 start:float=Field(ge=0)
 end:float=Field(gt=0)
 text:str=Field(max_length=100)
 @model_validator(mode='after')
 def validate_times(self):
  if self.end<=self.start:raise ValueError('El final del subtítulo debe superar su inicio.')
  return self

class Export(BaseModel):
 start:float=Field(ge=0)
 end:float=Field(gt=0)
 title:str=Field(max_length=96)
 subtitles:str=Field(max_length=20000)
 style:str='classic'
 font:str='Montserrat'
 title_font:str='Montserrat'
 title_size:int=Field(default=48,ge=28,le=64)
 title_outline_color:str=Field(default='#000000',pattern=r'^#[0-9A-Fa-f]{6}$')
 title_outline_width:int=Field(default=0,ge=0,le=6)
 title_x:float=Field(default=50,ge=0,le=100)
 title_y:float=Field(default=12,ge=0,le=100)
 caption_x:float=Field(default=50,ge=0,le=100)
 caption_y:float=Field(default=81,ge=0,le=100)
 caption_size:int=Field(default=64,ge=40,le=90)
 caption_color:str=Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
 outline_color:str=Field(default='#000000',pattern=r'^#[0-9A-Fa-f]{6}$')
 outline_width:int=Field(default=4,ge=0,le=9)
 clip_id:str|None=None
 captions:list[Caption]|None=Field(default=None,max_length=1000)
 logo:str='none'
 logo_width:int=Field(default=16,ge=5,le=100)
 logo_x:float=Field(default=90,ge=0,le=100)
 logo_y:float=Field(default=8,ge=0,le=100)
 logo_start:float=Field(default=0,ge=0)
 logo_end:float|None=Field(default=None,gt=0)
 framing:str='crop'
 focus_x:float=Field(default=50,ge=0,le=100)
 focus_y:float=Field(default=50,ge=0,le=100)

def stamp(seconds):
 c=round(max(0,seconds)*100); return f'{c//360000}:{c//6000%60:02}:{c//100%60:02}.{c%100:02}'

def safe(text): return text.replace('\\','').replace('{','').replace('}','').replace('\n',r'\N')

def caption_cues(opts,transcript):
 if opts.captions is not None:
  cues=[c.model_dump() for c in opts.captions]
  duration=opts.end-opts.start
  if any(c['end']>duration+.001 for c in cues):raise ValueError('Un subtítulo termina fuera del clip.')
  if any(a['end']>b['start']+.001 for a,b in zip(cues,cues[1:])):raise ValueError('Los subtítulos no deben solaparse y deben estar ordenados.')
  return cues
 return make_cues(transcript,opts.start,opts.end,opts.subtitles)

@app.post('/api/jobs/{ident}/captions')
def captions(ident:str,opts:Export):
 if ident not in JOBS:raise HTTPException(404)
 if opts.end<=opts.start or opts.end>JOBS[ident]['duration']:raise HTTPException(400,'Tiempos fuera del video.')
 return {'captions':make_cues(JOBS[ident].get('transcript',[]),opts.start,opts.end,opts.subtitles)}

def ass_file(path,opts,transcript=None):
 font=opts.font if opts.font in FONTS else 'Montserrat'
 title_font=opts.title_font if opts.title_font in FONTS else 'Montserrat'
 title,title_size=title_layout(opts.title,title_font,opts.title_size)
 color=ass_color(opts.caption_color);outline=ass_color(opts.outline_color)
 header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{opts.caption_size},{color},&H00FFFFFF,{outline},&H80000000,-1,0,0,0,100,100,0,0,1,{opts.outline_width},0,2,100,100,290,1
Style: Title,{title_font},{title_size},&H00000000,&H00000000,{ass_color(opts.title_outline_color)},&H00FFFFFF,-1,0,0,0,100,100,0,0,1,{opts.title_outline_width},0,8,140,140,140,1
Style: TitleBox,{title_font},1,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
 duration=opts.end-opts.start
 title_pos=r'{\an5\pos('+f'{opts.title_x*10.8:.1f},{opts.title_y*19.2:.1f}'+')}'
 caption_pos=r'{\an5\pos('+f'{opts.caption_x*10.8:.1f},{opts.caption_y*19.2:.1f}'+')}'
 events=[]
 if title:
  from PIL import ImageFont
  face=ImageFont.truetype(str(ROOT/'static/fonts'/FONTS[title_font]),title_size)
  width=max(face.getlength(line) for line in title.split('\n'))+24
  height=title_size*1.35*len(title.split('\n'))+18
  x=opts.title_x*10.8-width/2;y=opts.title_y*19.2-height/2
  box_tag=r'{\an7\pos('+f'{x:.1f},{y:.1f}'+r')\p1}'
  rectangle=f'm 0 0 l {width:.1f} 0 l {width:.1f} {height:.1f} l 0 {height:.1f}'
  events.append(f'Dialogue: 1,0:00:00.00,{stamp(duration)},TitleBox,,0,0,0,,{box_tag}{rectangle}')
  events.append(f'Dialogue: 2,0:00:00.00,{stamp(duration)},Title,,0,0,0,,{title_pos}{safe(title)}')
 for cue in caption_cues(opts,transcript or []):
  caption,point=title_layout(cue['text'],font,opts.caption_size)
  size_tag=r'{\fs'+str(point)+'}'
  events.append(f"Dialogue: 0,{stamp(cue['start'])},{stamp(cue['end'])},Caption,,0,0,0,,{caption_pos}{size_tag}{safe(caption)}")
 path.write_text(header+'\n'.join(events),encoding='utf-8')

@app.post('/api/jobs/{ident}/export')
def export(ident:str,opts:Export):
 if ident not in JOBS: raise HTTPException(404)
 if opts.end<=opts.start or opts.end>JOBS[ident]['duration'] or opts.end-opts.start>180: raise HTTPException(400,'El clip debe durar entre 0 y 180 segundos y estar dentro del video.')
 if opts.framing not in ['fit','crop']: raise HTTPException(400)
 if not re.fullmatch(r'(none|kick|roobet|rainbet|[a-f0-9]{32})',opts.logo): raise HTTPException(400)
 logo=DATA/f'{opts.logo}.png'
 if opts.logo!='none' and not logo.exists(): raise HTTPException(400,'Primero carga el archivo del logo seleccionado.')
 logo_end=opts.logo_end if opts.logo_end is not None else opts.end-opts.start
 if opts.logo!='none' and (opts.logo_start>=logo_end or logo_end>opts.end-opts.start):raise HTTPException(400,'El intervalo del logo debe estar dentro del clip: inicio menor que final.')
 if opts.clip_id:
  limits=JOBS[ident].get('analysis_range')
  if limits and not limits['minimum']<=opts.end-opts.start<=limits['maximum']:raise HTTPException(400,f"El clip debe respetar el rango {limits['minimum']}–{limits['maximum']} s del análisis.")
 folder=DATA/ident; token=uuid.uuid4().hex; ass=folder/f'{token}.ass'; output=folder/f'{token}.mp4'
 try:ass_file(ass,opts,JOBS[ident].get('transcript',[]))
 except ValueError as e:raise HTTPException(400,str(e))
 geometry='scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black' if opts.framing=='fit' else f'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(iw-ow)*{opts.focus_x/100}:(ih-oh)*{opts.focus_y/100}'
 # Relative font directory avoids escaping Windows drive letters in FFmpeg filters.
 import shutil
 fonts=folder/'fonts'
 if not fonts.exists():shutil.copytree(ROOT/'static/fonts',fonts)
 filters=f'{geometry},setsar=1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=2,ass={ass.name}:fontsdir=fonts'
 args=['ffmpeg','-v','error','-y','-ss',str(opts.start),'-t',str(opts.end-opts.start),'-i',str(folder/'source')]
 if opts.logo!='none':
  from PIL import Image
  with Image.open(logo) as image:logo_pixel_width=min(round(1080*opts.logo_width/100),round(1440*image.width/image.height))
  args+=['-i',str(logo),'-filter_complex',f"[0:v]{filters}[v];[1:v]scale={max(1,logo_pixel_width)}:-1[l];[v][l]overlay=(W-w)*{opts.logo_x/100}:(H-h)*{opts.logo_y/100}:enable='gte(t,{opts.logo_start})*lt(t,{logo_end})'[out]",'-map','[out]','-map','0:a?']
 else: args+=['-vf',filters,'-map','0:v:0','-map','0:a?']
 args+=['-t',str(opts.end-opts.start),'-c:v','libx264','-preset','fast','-r',str(JOBS[ident].get('fps',30)),'-fps_mode','cfr','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)]
 try: command(args,cwd=folder)
 except Exception as e: raise HTTPException(500,str(e))
 return FileResponse(output,media_type='video/mp4',filename=f'clip-{token[:6]}.mp4')


def save_job(job):
 path=DATA/job['id']/'job.json'
 tmp=path.with_suffix('.tmp')
 tmp.write_text(json.dumps(job,ensure_ascii=False),encoding='utf-8');tmp.replace(path)

def recover_jobs():
 for folder in DATA.iterdir():
  if not folder.is_dir() or not re.fullmatch(r'[a-f0-9]{32}',folder.name) or not (folder/'source').exists():continue
  try:
   metadata=folder/'job.json'
   if metadata.exists():job=json.loads(metadata.read_text(encoding='utf-8'))
   else:
    info=probe(folder/'source');job=dict(id=folder.name,name=f'Video recuperado {folder.name[:6]}',duration=float(info['format']['duration']),fps=30,clips=[],status='uploaded')
   if job.get('status') in ['queued','selecting','transcribing']:job.update(status='uploaded',message='El análisis anterior se interrumpió. Puedes reutilizar su transcripción.')
   job['id']=folder.name
   JOBS[folder.name]=job
  except (OSError,ValueError,RuntimeError):continue

recover_jobs()
