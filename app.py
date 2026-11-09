import hashlib, json, logging, math, os, re, subprocess, threading, time, uuid
import tempfile
from fractions import Fraction
from typing import Literal
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator, SecretStr
from timeline import make_cues, clip_words
from intelligence import select_clips
from styling import FONTS, ass_color, title_layout, title_bitmap
import capabilities
capabilities.enable_cuda_libraries()

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

def command(args, cwd=None, env=None):
 r=subprocess.run(args,capture_output=True,text=True,cwd=cwd,env=env)
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

def register_video(ident,path,name,*,max_duration=7200):
 info=probe(path);duration=float(info['format']['duration'])
 if not 0<duration<=max_duration:raise ValueError(f'La duración máxima es {max_duration//60} minutos.')
 stream=next((s for s in info['streams'] if s['codec_type']=='video'),None)
 if stream is None:raise ValueError('El archivo no contiene video.')
 try:fps=float(Fraction(stream.get('avg_frame_rate','30/1')))
 except (ValueError,ZeroDivisionError):fps=30
 JOBS[ident]=dict(id=ident,name=name,duration=duration,fps=max(24,min(60,fps)),status='uploaded',clips=[],clip_settings=dict(CLIP_DEFAULTS))
 save_job(JOBS[ident]);return JOBS[ident]

IMPORTS={}
import_pool=ThreadPoolExecutor(max_workers=1)
class YouTubeInput(BaseModel):
 url:str=Field(min_length=1,max_length=2000)
 quality:Literal['fast','original']='fast'
 browser:Literal['none','managed','firefox','chrome','edge','brave']='none'

def require_local_youtube(request):
 from urllib.parse import urlsplit
 if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):
  raise HTTPException(403,'La conexión de YouTube solo se puede gestionar desde este PC.')
 if request.url.hostname not in ('127.0.0.1','localhost','::1','testserver'):
  raise HTTPException(403,'Abre Clip Studio desde su dirección local.')
 origin=request.headers.get('origin')
 if origin and (urlsplit(origin).scheme,urlsplit(origin).netloc)!=(request.url.scheme,request.url.netloc):
  raise HTTPException(403,'Origen no autorizado para gestionar YouTube.')

@app.get('/api/youtube-session')
def youtube_connection_status(request:Request):
 require_local_youtube(request)
 from youtube_session import session,SessionUnavailable
 try:return session.status()
 except SessionUnavailable:return dict(authorized=False,connected=False,message='No se pudo comprobar la conexión de YouTube. Vuelve a conectar.')

@app.post('/api/youtube-session/connect')
def connect_youtube(request:Request):
 require_local_youtube(request)
 from youtube_session import RETIRED
 raise HTTPException(410,RETIRED)

@app.post('/api/youtube-session/disconnect')
def disconnect_youtube(request:Request):
 require_local_youtube(request)
 if any(v['status'] in ('queued','downloading') for v in IMPORTS.values()):
  raise HTTPException(409,'Espera a que termine la importación antes de desconectar YouTube.')
 from youtube_session import session,SessionUnavailable
 try:return session.disconnect()
 except SessionUnavailable as e:raise HTTPException(400,str(e))

def import_youtube(ident,url,quality="fast",browser="none"):
 import shutil
 from youtube_import import download
 folder=DATA/ident;folder.mkdir(exist_ok=True)
 # Written by the worker itself, so only a download that really started can be resumed after a restart;
 # yt-dlp then continues its .part files.
 (folder/'import.json').write_text(json.dumps(dict(url=url,quality=quality)),encoding='utf-8')
 def progress(value,message,**metadata):IMPORTS[ident].update(status='downloading',progress=value,message=message,**metadata)
 try:
  progress(0,'Consultando video de YouTube…',access_mode='none',requested_browser=browser,integration_version=4)
  path,name=download(url,folder,progress,mode=quality,browser=browser)
  path.rename(folder/'source')
  job=register_video(ident,folder/'source',name,max_duration=12000)
  job['youtube']={key:IMPORTS[ident][key] for key in ['title','channel','thumbnail','duration','quality','video_width','video_height'] if key in IMPORTS[ident]}
  job['youtube_url']=url;job['youtube_quality']=quality
  job['youtube_verification_version']=IMPORTS[ident].get('verification_version',0);save_job(job)
  (folder/'import.json').unlink(missing_ok=True)
  IMPORTS[ident].update(status='ready',progress=100,message='Video listo para analizar.',job=job)
 except Exception as e:
  from youtube_import import diagnose_error
  code,message=diagnose_error(e)
  if code=='YT-SESION' and IMPORTS[ident].get('access_mode') not in ('none',None,'managed'):message='YouTube sigue exigiendo verificación tras intentar usar la sesión seleccionada. Abre el enlace en ese navegador, confirma que puedes reproducirlo y completa la verificación; cierra ese navegador antes de reintentar. Si persiste, espera o ingresa el archivo descargado.'
  if code=='YT-SESION' and IMPORTS[ident].get('access_mode')=='managed':message='YouTube no aceptó la conexión propia para este video. Pulsa Conectar YouTube, comprueba el acceso en esa ventana e inténtalo de nuevo. Una sesión guardada no garantiza acceso a todos los videos.'
  if getattr(e,'public_error_code',None):
   IMPORTS[ident]['public_error_code']=e.public_error_code
   if code!='YT-CONEXION':message='YouTube no permitió la descarga pública y tampoco se pudo completar el acceso con la sesión autorizada. '+message
  IMPORTS[ident].update(status='error',error_code=code,message=f'[{code}] {message}')
  # Safe console diagnosis: no provider URLs, cookie values or browser paths.
  logging.getLogger('uvicorn.error').info('YouTube %s: public=%s access=%s result=%s',ident[:8],IMPORTS[ident].get('public_error_code',code),IMPORTS[ident].get('access_mode','none'),code)
  JOBS.pop(ident,None)
  shutil.rmtree(folder,ignore_errors=True)

@app.post('/api/youtube')
def start_youtube(options:YouTubeInput,request:Request):
 if options.browser=='managed':
  require_local_youtube(request)
  from youtube_session import RETIRED
  raise HTTPException(410,RETIRED)
 if options.browser!="none" and request.client and request.client.host not in ("127.0.0.1","::1","testclient"):
  raise HTTPException(403,"El uso de una sesión de navegador solo está disponible desde el PC donde corre la app.")
 from youtube_import import canonical_url
 try:url=canonical_url(options.url)
 except ValueError as e:raise HTTPException(400,str(e))
 if any(v['status'] in ('queued','downloading') for v in IMPORTS.values()):raise HTTPException(409,'Ya hay una descarga en curso. Espera a que termine.')
 from native_import import configuration as native_configuration,reusable_job
 native_config=native_configuration()
 for job in JOBS.values():
  if native_config is not None and not reusable_job(job,native_config):continue
  if job.get('youtube_url')==url and job.get('youtube_quality')==options.quality and (DATA/job['id']/'source').exists():
   ident=uuid.uuid4().hex
   IMPORTS[ident]=dict(id=ident,status='ready',progress=100,access_mode='cached',integration_version=4,message='Video recuperado: ya estaba descargado.',job=job,**job.get('youtube',{}))
   return IMPORTS[ident]
 ident=uuid.uuid4().hex
 IMPORTS[ident]=dict(id=ident,status='queued',progress=0,access_mode='none',requested_browser=options.browser,integration_version=4,message='Consultando título y duración…',thumbnail='https://i.ytimg.com/vi/'+url.split('v=')[1]+'/hqdefault.jpg',title='Preparando video de YouTube…')
 import_pool.submit(import_youtube,ident,url,options.quality,options.browser)
 return IMPORTS[ident]

def resume_imports():
 """Restart YouTube imports interrupted by closing the server. Browser sessions are never reused automatically."""
 from youtube_import import canonical_url
 for marker in DATA.glob('*/import.json'):
  ident=marker.parent.name
  if not re.fullmatch(r'[a-f0-9]{32}',ident) or (marker.parent/'source').exists() or ident in IMPORTS:continue
  try:
   saved=json.loads(marker.read_text(encoding='utf-8'))
   url=canonical_url(saved['url']);quality=saved.get('quality','fast')
   if quality not in ('fast','original'):raise ValueError()
  except (OSError,ValueError,KeyError,TypeError,AttributeError):continue
  IMPORTS[ident]=dict(id=ident,status='queued',progress=0,access_mode='none',requested_browser='none',integration_version=4,resumed=True,
   message='Reanudando la descarga que se interrumpió al cerrar ClipStudio…',thumbnail='https://i.ytimg.com/vi/'+url.split('v=')[1]+'/hqdefault.jpg',title='Reanudando video de YouTube…')
  import_pool.submit(import_youtube,ident,url,quality,'none')

@app.get('/api/youtube')
def active_youtube_imports():
 return [v for v in IMPORTS.values() if v.get('status') in ('queued','downloading')]

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
 clip_settings:dict|None=None
 @model_validator(mode='after')
 def validate_range(self):
  if self.minimum>self.maximum: raise ValueError('El mínimo no puede superar el máximo.')
  return self

def whisper_model(device):
 """Keep one Whisper model; a GPU model is released after each transcription so Ollama can use the VRAM."""
 global model
 from faster_whisper import WhisperModel
 if model is None or model[0]!=device:
  model=None
  name=os.getenv('WHISPER_MODEL','small')
  model=(device,WhisperModel(name,device='cuda',compute_type='float16') if device=='cuda' else WhisperModel(name,device='cpu',compute_type='int8',cpu_threads=capabilities.transcription_threads()))
 return model[1]

def release_gpu_whisper():
 global model
 if model is not None and model[0]=='cuda':
  model=None;import gc;gc.collect()

def transcribe_audio(audio,job,event):
 device,reason=capabilities.transcription_plan()
 job['message']=('Transcribiendo con la GPU' if device=='cuda' else 'Transcribiendo con la CPU')+f' · {reason}'
 def run(device):
  segments,info=whisper_model(device).transcribe(audio,vad_filter=True,word_timestamps=True)
  transcript=[]
  for s in segments:
   if event.is_set():raise cloud_ai.AnalysisCancelled()
   transcript.append(dict(start=s.start,end=s.end,text=s.text,words=[dict(start=w.start,end=w.end,text=w.word) for w in (s.words or [])]))
   job['progress']=min(60,round(s.end/job['duration']*60))
  return transcript
 try:
  if device=='cuda':
   try:return run('cuda'),'cuda'
   except cloud_ai.AnalysisCancelled:raise
   except Exception as error:
    # CUDA errors (driver, out of memory) must not cost the user the analysis: redo it on the CPU.
    logging.getLogger('uvicorn.error').warning('GPU transcription failed, using CPU: %s',str(error)[:300])
    release_gpu_whisper();job.update(progress=0,message='La GPU no pudo transcribir; continuando con la CPU…')
  return run('cpu'),'cpu'
 finally:release_gpu_whisper()

def analyze(ident,options):
 job=JOBS[ident]
 try:
  job['timings']={}
  job.update(clips=[],progress=0,analysis_range={'minimum':options.minimum,'maximum':options.maximum},status='transcribing',message='Transcribiendo con Whisper local. La primera ejecución descarga el modelo.')
  event=CANCEL.setdefault(ident,threading.Event())
  if event.is_set():raise cloud_ai.AnalysisCancelled()
  if options.engine=='gpu':
   job.update(message='Cargando el modelo local y comprobando memoria GPU…')
   job['gpu_status']=gpu_ai.warmup()
  # «Cámara + juego»: look for the streamer camera on the CPU while the GPU transcribes, so clips open ready.
  if wants_stack(job):start_overlay(ident)
  cached=DATA/ident/'transcript.json'
  if cached.exists():
   transcript=json.loads(cached.read_text(encoding='utf-8'))
  elif options.transcribe_gpu:
   if options.engine=='gpu':gpu_ai.unload()
   transcript=gpu_transcribe.transcribe(DATA/ident/'source',DATA/ident,event,lambda percentage,message:job.update(progress=round(percentage*.6),message=message))
   cached.write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
  else:
   # Free Ollama's VRAM first so the transcription can use the GPU; it is reloaded right after.
   if options.engine=='gpu':
    try:
     gpu_ai.unload()
     # Ollama frees VRAM asynchronously; starting Whisper earlier overfills an 8 GB card and Windows
     # spills to shared memory (measured: 172 s instead of 39 s for a 15-min video).
     for _ in range(30):
      if not gpu_ai.status()['gpu_loaded']:break
      time.sleep(.5)
    except Exception:pass
   started=time.monotonic();audio=decode_audio(DATA/ident/'source')
   transcript,device=transcribe_audio(audio,job,event)
   job['timings']['transcription_s']=round(time.monotonic()-started,1);job['timings']['transcription_device']=device
   cached.write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
  if not any(segment.get('text','').strip() for segment in transcript):raise ValueError('No se detectó voz transcribible. Revisa el audio o crea un clip manual; no se forzarán fragmentos vacíos.')
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
  from editorial import cached_completion
  from coverage import TitleBatch
  base_completion=gpu_ai.complete if options.engine=='gpu' else cloud_ai.complete if options.engine=='cloud' else lambda payload,**kwargs: __import__('intelligence').query_json(json.dumps(payload,ensure_ascii=False),TitleBatch.model_json_schema(),options.quality)
  job['analysis_cache_hits']=0
  def cache_hit():job['analysis_cache_hits']+=1
  completion=cached_completion(DATA/ident/'analysis-cache',options.engine+':'+options.quality,base_completion,cache_hit)
  topics=[];started=time.monotonic()
  if options.engine=='cloud':
   job['selection_diagnostics']=[]
   clips=cloud_ai.select_cloud(transcript,options.minimum,options.maximum,job['duration'],speaker=options.speaker,context=options.context,profile=profile,max_clips=options.max_clips,on_progress=progress,cancel=event,diagnostics=job['selection_diagnostics'],topic_ranges=topics,completion=completion)
  elif options.engine=='gpu':
   job['selection_diagnostics']=[]
   clips=gpu_ai.select_gpu(transcript,options.minimum,options.maximum,job['duration'],speaker=options.speaker,context=options.context,profile=profile,max_clips=options.max_clips,on_progress=progress,cancel=event,diagnostics=job['selection_diagnostics'],topic_ranges=topics,completion=completion)
  else:
   clips=select_clips(transcript,options.minimum,options.maximum,job['duration'],speaker=options.speaker,context=options.context,profile=profile,quality=options.quality,max_clips=options.max_clips,on_progress=progress)
  job['timings']['analysis_s']=round(time.monotonic()-started,1);started=time.monotonic()
  from coverage import complete_coverage,covered,TitleBatch
  job.update(progress=98,message='Separando conversaciones por tema y creando títulos…')
  def title_progress(done,total,stage):job.update(progress=98+round(done/max(1,total)),message=f'Títulos de clips para revisar · {done} de {total}')
  clips=complete_coverage(clips,transcript,job['duration'],options.minimum,options.maximum,completion,speaker=options.speaker,context=options.context,profile=profile,cancel=event,on_progress=title_progress,topics=topics)
  job['timings']['titles_s']=round(time.monotonic()-started,1)
  job['topics']=topics
  job['coverage_percent']=round(100*covered(clips)/job['duration'],2)
  message=f'{len(clips)} clips · cobertura {job["coverage_percent"]}% del video. Mayor potencial identifica los destacados; el resto queda para tu revisión.' if clips else 'La selección quedó vacía tras la revisión. Esto no demuestra que el video no tenga potencial. Revisa la transcripción y añade contexto para volver a analizar sin transcribir de nuevo.'
  if job['coverage_percent']<75:message+=f' Cobertura {job["coverage_percent"]}%: no se mezclaron temas ni se forzaron respuestas incompletas para llegar al 75%. Puedes reducir el mínimo o ampliar el máximo.'
  t=job['timings']
  parts=([f"transcripción {t['transcription_s']} s ({'GPU' if t['transcription_device']=='cuda' else 'CPU'})"] if 'transcription_s' in t else ['transcripción reutilizada'])+[f"análisis {t['analysis_s']} s",f"títulos {t['titles_s']} s"]
  message+=' Tiempos: '+', '.join(parts)+'.'
  job.update(status='ready',progress=100,clips=clips,message=message)
  if wants_stack(job):layout_pool.submit(prepare_layouts,ident)
  try:LIBRARY.sync_job(job);LIBRARY.log('analysis',f"Análisis terminado: {len(clips)} clips · {job.get('name','video')}",ident)
  except Exception as e:logging.getLogger('uvicorn.error').warning('Library sync failed: %s',e)
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
 if options.clip_settings is not None:
  try:JOBS[ident]['clip_settings']=ClipSettings(**options.clip_settings).model_dump()
  except ValueError:raise HTTPException(400,'Configuración de clips inválida.')
 JOBS[ident]['analysis_options']=options.model_dump(exclude={'clip_settings'})
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

@app.get('/api/capabilities')
def hardware_capabilities():return capabilities.summary()

class Performance(BaseModel):
 transcription:Literal['auto','gpu','cpu']='auto'
 export:Literal['auto','gpu','cpu']='auto'

@app.put('/api/performance')
def set_performance(values:Performance):
 global _nvenc
 capabilities.save_settings(values.model_dump());_nvenc=None
 return capabilities.summary()

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
 def info(j):
  meta=DATA/j['id']/'job.json'
  live=j.get('live') or {};yt=j.get('youtube') or {}
  return dict(id=j['id'],name=j['name'],duration=j['duration'],cached=(DATA/j['id']/'transcript.json').exists(),
              clips=len(j.get('clips') or []),status=j.get('status'),kind='live' if live else 'youtube' if yt else 'local',
              channel=live.get('channel') or yt.get('channel') or '',title=live.get('stream_title') or yt.get('title') or j['name'],
              updated=meta.stat().st_mtime if meta.exists() else 0,edited=len(j.get('clip_edits') or {}))
 return [info(j) for j in JOBS.values()]

@app.get('/api/jobs/{ident}')
def status(ident:str):
 if ident not in JOBS: raise HTTPException(404)
 return {**{key:value for key,value in JOBS[ident].items() if key!='transcript'},'clip_settings':clip_settings(JOBS[ident])}

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
 title_padding_x:int=Field(default=10,ge=0,le=100)
 title_padding_y:int=Field(default=4,ge=0,le=70)
 title_bg_color:str=Field(default='#FFFFFF',pattern=r'^#[0-9A-Fa-f]{6}$')
 title_text_color:str=Field(default='#000000',pattern=r'^#[0-9A-Fa-f]{6}$')
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
 auto_follow:bool=False
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
 # Defaults keep the previous behaviour for old projects; new projects send their saved "Configura tus clips" values.
 zoom:Literal['soft','balanced','close']='balanced'
 tracking_person:str=Field(default='auto',pattern=r'^(auto|\d{1,4})$')
 tracking_motion:Literal['smooth','balanced','fast']='balanced'
 show_subtitles:bool=True
 title_corners:Literal['rounded','square']='square'
 # 'Cámara + juego' (framing='stack'): follow the game's action, and output size (1440 gives YouTube Shorts more bitrate).
 game_follow:bool=True
 resolution:Literal[1080,1440]=1080
 preview:bool=False               # «Comprobar MP4»: not an export, not recorded in the library

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

TRACKING={}
tracking_pool=ThreadPoolExecutor(max_workers=1)
class TrackingInput(BaseModel):
 start:float=Field(ge=0)
 end:float=Field(gt=0)

def track_clip(ident,start,end,track_key):
 import tracking
 state=TRACKING[(ident,track_key)]
 try:
  state.update(status='running',progress=0)
  result=tracking.analyze(DATA/ident/'source',start,end,lambda value:state.update(progress=value))
  result.update(start=start,end=end,status='ready',progress=100)
  target=DATA/ident/f'tracking-{track_key}.json';tmp=target.with_suffix('.tmp')
  tmp.write_text(json.dumps(result),encoding='utf-8');tmp.replace(target)
  state.update(result)
 except Exception as e:state.update(status='error',message=str(e))

@app.post('/api/jobs/{ident}/tracking')
def start_tracking(ident:str,opts:TrackingInput):
 import tracking
 if ident not in JOBS:raise HTTPException(404)
 if not opts.start<opts.end<=JOBS[ident]['duration'] or opts.end-opts.start>180:raise HTTPException(400,'Elige un clip válido de hasta 180 segundos.')
 track_key=tracking.key(opts.start,opts.end);cache=DATA/ident/f'tracking-{track_key}.json'
 if cache.exists():return dict(key=track_key,**json.loads(cache.read_text(encoding='utf-8')))
 if (ident,track_key) not in TRACKING or TRACKING[(ident,track_key)]['status']=='error':
  TRACKING[(ident,track_key)]=dict(status='queued',progress=0)
  tracking_pool.submit(track_clip,ident,opts.start,opts.end,track_key)
 return dict(key=track_key,**TRACKING[(ident,track_key)])

class PathInput(TrackingInput):
 person:str=Field(default='auto',pattern=r'^(auto|\d{1,4})$')
 motion:Literal['smooth','balanced','fast']='balanced'
 framing:Literal['crop','zoom']='zoom'
 zoom:Literal['soft','balanced','close']='balanced'
 focus_y:float=Field(default=50,ge=0,le=100)

@app.post('/api/jobs/{ident}/tracking/path')
def tracking_path(ident:str,opts:PathInput):
 """The exact camera path the export will use, so the preview can play the same motion."""
 import tracking
 if ident not in JOBS:raise HTTPException(404)
 cache=DATA/ident/f'tracking-{tracking.key(opts.start,opts.end)}.json'
 if not cache.exists():raise HTTPException(404,'Calcula el seguimiento primero.')
 result=json.loads(cache.read_text(encoding='utf-8'))
 if 'samples' not in result:raise HTTPException(409,'El seguimiento se calculó con una versión anterior. Vuelve a calcularlo.')
 return dict(tracking.build_path(result,opts.person,opts.motion,opts.framing,opts.zoom,opts.focus_y),persons=result.get('persons',[]))

@app.get('/api/jobs/{ident}/tracking/{track_key}')
def tracking_status(ident:str,track_key:str):
 if (ident,track_key) not in TRACKING:raise HTTPException(404)
 return dict(key=track_key,**TRACKING[(ident,track_key)])

class TitleInput(TrackingInput):
 text:str=Field(default='',max_length=20000)

@app.post('/api/jobs/{ident}/titles')
def improve_titles(ident:str,opts:TitleInput):
 from coverage import TitleBatch
 from intelligence import clean_title,query_json
 if ident not in JOBS:raise HTTPException(404)
 job=JOBS[ident]
 if not opts.start<opts.end<=job['duration'] or opts.end-opts.start>180:raise HTTPException(400,'Elige un clip válido de hasta 180 segundos.')
 text=opts.text.strip() or ' '.join(w['text'] for w in clip_words(job.get('transcript',[]),opts.start,opts.end))
 if not text:raise HTTPException(400,'Este clip aún no tiene transcripción. Analiza el video o escribe sus subtítulos primero.')
 options=job.get('analysis_options',{});engine=options.get('engine','gpu')
 from editorial import TITLE_GUIDE
 payload=dict(task='coverage_titles',hablante_identificado=options.get('speaker',''),contexto_del_video=options.get('context',''),criterios_del_editor=read_profile()['instructions'],clips=[dict(id='clip',text=text)],instruccion=TITLE_GUIDE+' Da tres alternativas distintas: una con duda concreta, otra con tensión o contraste y otra con una situación humana compartida, si el contenido las permite. No fuerces conflictos inexistentes. Devuelve clips/id/titles y usa el ID clip.')
 try:
  if engine=='gpu':gpu_ai.warmup()
  completion=gpu_ai.complete if engine=='gpu' else cloud_ai.complete if engine=='cloud' else lambda value:query_json(json.dumps(value,ensure_ascii=False),TitleBatch.model_json_schema(),options.get('quality','fast'))
  data=TitleBatch.model_validate(completion(payload))
  titles=list(dict.fromkeys(title for item in data.clips if item.id=='clip' for title in (clean_title(t,text) for t in item.titles) if title))
  if not titles:raise ValueError('La IA no devolvió títulos válidos. Intenta generar otras propuestas.')
  return dict(titles=titles)
 except (ValueError,RuntimeError) as e:raise HTTPException(400,str(e))

@app.post('/api/jobs/{ident}/captions')
def captions(ident:str,opts:Export):
 if ident not in JOBS:raise HTTPException(404)
 if opts.end<=opts.start or opts.end>JOBS[ident]['duration']:raise HTTPException(400,'Tiempos fuera del video.')
 return {'captions':make_cues(JOBS[ident].get('transcript',[]),opts.start,opts.end,opts.subtitles)}

def ass_file(path,opts,transcript=None):
 font=opts.font if opts.font in FONTS else 'Montserrat'
 color=ass_color(opts.caption_color);outline=ass_color(opts.outline_color)
 header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{opts.caption_size},{color},&H00FFFFFF,{outline},&H80000000,-1,0,0,0,100,100,0,0,1,{opts.outline_width},0,2,100,100,290,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
 duration=opts.end-opts.start
 caption_pos=r'{\an5\pos('+f'{opts.caption_x*10.8:.1f},{opts.caption_y*19.2:.1f}'+')}'
 events=[]
 for cue in caption_cues(opts,transcript or []):
  caption,point=title_layout(cue['text'],font,opts.caption_size)
  size_tag=r'{\fs'+str(point)+'}'
  events.append(f"Dialogue: 0,{stamp(cue['start'])},{stamp(cue['end'])},Caption,,0,0,0,,{caption_pos}{size_tag}{safe(caption)}")
 path.write_text(header+'\n'.join(events),encoding='utf-8')

def render_title(opts):
 font=opts.title_font if opts.title_font in FONTS else 'Montserrat'
 return title_bitmap(opts.title,font,opts.title_size,opts.title_padding_x,opts.title_padding_y,opts.title_bg_color,opts.title_text_color,opts.title_outline_color,opts.title_outline_width,opts.title_corners)

@app.post('/api/title-preview')
def title_preview(opts:Export):
 import io
 try:image=render_title(opts)
 except ValueError as e:raise HTTPException(400,str(e))
 if image is None:return Response(status_code=204)
 buffer=io.BytesIO();image.save(buffer,format='PNG')
 return Response(buffer.getvalue(),media_type='image/png',headers={'Cache-Control':'no-store'})

@app.post('/api/jobs/{ident}/export')
def export(ident:str,opts:Export):
 if ident not in JOBS: raise HTTPException(404)
 if opts.end<=opts.start or opts.end>JOBS[ident]['duration'] or opts.end-opts.start>180: raise HTTPException(400,'El clip debe durar entre 0 y 180 segundos y estar dentro del video.')
 if opts.framing not in ['fit','crop','zoom','stack']: raise HTTPException(400)
 if not re.fullmatch(r'(none|kick|roobet|rainbet|[a-f0-9]{32})',opts.logo): raise HTTPException(400)
 logo=DATA/f'{opts.logo}.png'
 if opts.logo!='none' and not logo.exists(): raise HTTPException(400,'Primero carga el archivo del logo seleccionado.')
 logo_end=opts.logo_end if opts.logo_end is not None else opts.end-opts.start
 if opts.logo!='none' and (opts.logo_start>=logo_end or logo_end>opts.end-opts.start):raise HTTPException(400,'El intervalo del logo debe estar dentro del clip: inicio menor que final.')
 if opts.clip_id:
  limits=JOBS[ident].get('analysis_range')
  if limits and not limits['minimum']-.001<=opts.end-opts.start<=limits['maximum']+.001:raise HTTPException(400,f"El clip debe respetar el rango {limits['minimum']}–{limits['maximum']} s del análisis.")
 folder=DATA/ident; token=uuid.uuid4().hex; ass=folder/f'{token}.ass'; output=folder/f'{token}.mp4'
 try:
  ass_file(ass,opts,JOBS[ident].get('transcript',[]))
  image=render_title(opts)
 except ValueError as e:raise HTTPException(400,str(e))
 import tracking
 if opts.framing=='stack':
  try:result=clip_layout(ident,opts.start,opts.end)
  except ValueError as e:raise HTTPException(400,str(e))
  if not result.get('panels'):raise HTTPException(400,'No se encontró la cámara del streamer en este video. Marca el recuadro en «Ajustar recuadro de cámara» o usa otro encuadre.')
  import layout
  geometry=layout.filter_graph(result,folder/f'{token}-layout.cmd',opts.end-opts.start,JOBS[ident].get('fps',30),opts.tracking_motion,opts.game_follow)
 else:geometry=tracking.static_filter(opts.framing,opts.zoom,opts.focus_x,opts.focus_y)
 if opts.auto_follow and opts.framing!='stack':
  if opts.framing not in ('crop','zoom'):raise HTTPException(400,'El seguimiento necesita el encuadre con zoom o pantalla completa.')
  cache=folder/f'tracking-{tracking.key(opts.start,opts.end)}.json'
  if not cache.exists():raise HTTPException(400,'Calcula el seguimiento del clip en el editor antes de exportarlo.')
  result=json.loads(cache.read_text(encoding='utf-8'))
  path=tracking.build_path(result,opts.tracking_person,opts.tracking_motion,opts.framing,opts.zoom,opts.focus_y)
  geometry=tracking.commands(path,folder/f'{token}-tracking.cmd',opts.end-opts.start,JOBS[ident].get('fps',30),result['width'],result['height'])
 # Relative font directory avoids escaping Windows drive letters in FFmpeg filters.
 import shutil
 fonts=folder/'fonts'
 if not fonts.exists():shutil.copytree(ROOT/'static/fonts',fonts)
 # Without subtitles the transcript still drives the analysis; only the burned-in layer is skipped.
 filters=f'{geometry},setsar=1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=2'+(f',ass={ass.name}:fontsdir=fonts' if opts.show_subtitles else '')
 args=['ffmpeg','-v','error','-y','-ss',str(opts.start),'-t',str(opts.end-opts.start),'-i',str(folder/'source')]
 title_path=folder/f'{token}-title.png'
 graph=[f'[0:v]{filters}[v0]'];last='v0';input_index=1
 if image is not None:
  image.save(title_path)
  args+=['-i',str(title_path)]
  graph.append(f'[{last}][{input_index}:v]overlay=x=W*{opts.title_x/100}-w/2:y=H*{opts.title_y/100}-h/2:eof_action=repeat[v1]')
  last='v1';input_index+=1
 if opts.logo!='none':
  from PIL import Image
  with Image.open(logo) as mark:logo_pixel_width=min(round(1080*opts.logo_width/100),round(1440*mark.width/mark.height))
  args+=['-i',str(logo)]
  graph.append(f'[{input_index}:v]scale={max(1,logo_pixel_width)}:-1[l]')
  graph.append(f"[{last}][l]overlay=(W-w)*{opts.logo_x/100}:(H-h)*{opts.logo_y/100}:enable='gte(t,{opts.logo_start})*lt(t,{logo_end})'[v2]")
  last='v2'
 if opts.resolution==1440:
  graph.append(f'[{last}]scale=1440:2560:flags=lanczos[vbig]');last='vbig'
 args+=['-filter_complex',';'.join(graph),'-map',f'[{last}]','-map','0:a?']
 args+=['-t',str(opts.end-opts.start),'-r',str(JOBS[ident].get('fps',30)),'-fps_mode','cfr','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)]
 export_env=None
 if os.name!='nt':
  # Keep host-wide font substitutions from replacing the bundled face used for measurements.
  from xml.sax.saxutils import escape
  cache=folder/'font-cache';cache.mkdir(exist_ok=True)
  config=folder/'fontconfig.xml'
  config.write_text(f'<fontconfig><dir>{escape(str(fonts.resolve()))}</dir><cachedir>{escape(str(cache.resolve()))}</cachedir></fontconfig>',encoding='utf-8')
  export_env={**os.environ,'FONTCONFIG_FILE':str(config.resolve())}
 try: encode(args,cwd=folder,env=export_env)
 except Exception as e: raise HTTPException(500,str(e))
 name=f'clip-{token[:6]}.mp4'
 cid=library_id(JOBS[ident],opts.clip_id)
 if not opts.preview and cid:
  # Keep every real export with a readable name and record it, so the library shows it as «Exportado».
  try:
   target=export_target(JOBS[ident],opts.title or 'clip',opts.resolution);os.replace(output,target);output=target;name=target.name
   LIBRARY.record_export(cid,target,opts.resolution);LIBRARY.log('export',f'Clip exportado en {opts.resolution}p · {opts.title or "sin título"}',cid)
  except OSError as e:logging.getLogger('uvicorn.error').warning('Export not moved to the library folder: %s',e)
 return FileResponse(output,media_type='video/mp4',filename=name)

CPU_VIDEO=['-c:v','libx264','-preset','fast','-crf','18']
# Measured on a real 1080p60 source (60 s vertical crop, RTX 5060 Ti): x264 CRF18 29 s / 54 MB / SSIM 0.9938,
# NVENC cq26 11 s / 62 MB / SSIM 0.9945. Filters (subtitles, overlays) still run on CPU.
# Nov 2026, measured on a 20 s 1080p60 stream clip: cq 26 39 MB, cq 23 55 MB, cq 21 69 MB (SSIM vs cq 14: .9892/.9920/.9933).
# cq 23 plus temporal AQ: cleaner uploads (platforms recompress) without doubling the size; 40 Mb/s ceiling.
GPU_VIDEO=['-c:v','h264_nvenc','-preset','p5','-tune','hq','-rc','vbr','-cq','23','-b:v','0','-maxrate','40M','-bufsize','80M','-spatial-aq','1','-temporal-aq','1','-profile:v','high']
_nvenc=None

def nvenc_available():
 """Probe once per process with a real tiny encode: an encoder listed by FFmpeg may still lack a driver."""
 global _nvenc
 if capabilities.read_settings()['export']=='cpu':return False
 if _nvenc is None:
  if os.environ.get('CLIP_EXPORT_ENCODER','').lower()=='cpu':_nvenc=False
  else:
   try:_nvenc=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=size=256x256:rate=30:duration=0.2','-c:v','h264_nvenc','-f','null','-'],capture_output=True,timeout=30).returncode==0
   except (OSError,subprocess.SubprocessError):_nvenc=False
 return _nvenc

def encode(args,cwd=None,env=None):
 """Run an export with NVENC when available, falling back to libx264 so a GPU problem never blocks the clip."""
 global _nvenc
 head,tail=args[:-1],args[-1:]
 if nvenc_available():
  try:return command(head+GPU_VIDEO+tail,cwd=cwd,env=env)
  except RuntimeError as error:
   logging.getLogger('uvicorn.error').warning('NVENC export failed, using CPU: %s',str(error)[-300:])
   _nvenc=False
 return command(head+CPU_VIDEO+tail,cwd=cwd,env=env)


# "Configura tus clips": per-project preferences. New projects get the new defaults; projects saved before this
# feature keep the behaviour they had (full 9:16 crop, square titles, no automatic tracking).
CLIP_DEFAULTS=dict(framing='zoom',zoom='balanced',tracking=True,tracking_motion='balanced',subtitles=True,title_corners='rounded',auto_stack=True,resolution=1080)
LEGACY_CLIP_SETTINGS=dict(framing='crop',zoom='balanced',tracking=False,tracking_motion='balanced',subtitles=True,title_corners='square',auto_stack=False,resolution=1080)

class ClipSettings(BaseModel):
 framing:Literal['zoom','crop','fit','stack']='zoom'
 zoom:Literal['soft','balanced','close']='balanced'
 tracking:bool=True
 auto_stack:bool=True             # use 'Cámara + juego' automatically when the video has a streamer camera overlay
 resolution:Literal[1080,1440]=1080
 tracking_motion:Literal['smooth','balanced','fast']='balanced'
 subtitles:bool=True
 title_corners:Literal['rounded','square']='rounded'

def clip_settings(job):
 return {**LEGACY_CLIP_SETTINGS,**job['clip_settings']} if job.get('clip_settings') else dict(LEGACY_CLIP_SETTINGS,legacy=True)

@app.put('/api/jobs/{ident}/clip-settings')
def save_clip_settings(ident:str,values:ClipSettings):
 if ident not in JOBS:raise HTTPException(404)
 JOBS[ident]['clip_settings']=values.model_dump();save_job(JOBS[ident])
 return JOBS[ident]['clip_settings']

@app.get('/api/jobs/{ident}/frame')
def video_frame(ident:str,t:float=0):
 """Small still of the source, used to preview the two framing styles before generating clips."""
 if ident not in JOBS:raise HTTPException(404)
 t=max(0,min(float(t),JOBS[ident]['duration']-.1))
 result=subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',str(DATA/ident/'source'),'-frames:v','1','-vf','scale=640:-2','-f','image2','-vcodec','mjpeg','-'],capture_output=True,timeout=30)
 if result.returncode or not result.stdout:raise HTTPException(500,'No se pudo leer un fotograma del video.')
 return Response(result.stdout,media_type='image/jpeg',headers={'Cache-Control':'max-age=3600'})

# --- "Cámara + juego": the streamer camera overlay (per video) and the stacked layout (per clip) ------------------------
OVERLAY={}
layout_pool=ThreadPoolExecutor(max_workers=1)

def overlay_file(ident):return DATA/ident/'overlay.json'

def read_overlay(ident):
 path=overlay_file(ident)
 if not path.exists():return None
 try:value=json.loads(path.read_text(encoding='utf-8'))
 except (OSError,ValueError):return None
 import layout
 # An automatic result from an older detector is computed again; a rectangle marked by hand is always kept.
 if not value.get('manual') and value.get('detector',1)<layout.DETECTOR_VERSION:return None
 return value

def write_overlay(ident,value):
 path=overlay_file(ident);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value),encoding='utf-8');tmp.replace(path)

def detect_job_overlay(ident):
 import layout
 state=OVERLAY[ident]
 try:
  state.update(status='running',progress=0)
  value=layout.detect_overlay(DATA/ident/'source',JOBS[ident].get('duration'),progress=lambda v:state.update(progress=v))
  value.update(status='ready',manual=False);write_overlay(ident,value);state.clear();state.update(value)
 except Exception as e:state.update(status='error',message=str(e))

@app.post('/api/jobs/{ident}/overlay')
def start_overlay(ident:str):
 """Find the streamer's camera once per video (about 40 sampled frames), in the background."""
 if ident not in JOBS:raise HTTPException(404)
 saved=read_overlay(ident)
 if saved:return saved
 if ident not in OVERLAY or OVERLAY[ident].get('status')=='error':
  OVERLAY[ident]=dict(status='queued',progress=0);layout_pool.submit(detect_job_overlay,ident)
 return OVERLAY[ident]

@app.get('/api/jobs/{ident}/overlay')
def overlay_status(ident:str):
 if ident not in JOBS:raise HTTPException(404)
 return read_overlay(ident) or OVERLAY.get(ident) or dict(status='none')

class OverlayBox(BaseModel):
 x:int=Field(ge=0);y:int=Field(ge=0);w:int=Field(gt=16);h:int=Field(gt=16)

@app.put('/api/jobs/{ident}/overlay')
def set_overlay(ident:str,box:OverlayBox):
 """Manual correction of the camera rectangle from the editor."""
 import layout
 if ident not in JOBS:raise HTTPException(404)
 W,H,_=layout._probe(DATA/ident/'source')
 if box.x+box.w>W or box.y+box.h>H:raise HTTPException(400,'El recuadro se sale del video.')
 even=lambda v:int(v)//2*2
 old=read_overlay(ident) or {}
 face=old.get('face') if old.get('face') and box.x<=old['face']['x']<=box.x+box.w and box.y<=old['face']['y']<=box.y+box.h else None
 value=dict(found=True,kind='overlay',status='ready',manual=True,width=W,height=H,presence=old.get('presence',1),x=even(box.x),y=even(box.y),w=even(box.w),h=even(box.h))
 if face:value['face']=face
 # Keep the detected game area unless the new camera rectangle falls inside it.
 c=old.get('content')
 if c and not (value['x']<c['x']+c['w'] and value['x']+value['w']>c['x'] and value['y']<c['y']+c['h'] and value['y']+value['h']>c['y']):value['content']=c
 write_overlay(ident,value);OVERLAY.pop(ident,None)
 return value

def wants_stack(job):
 settings=clip_settings(job)
 return settings.get('framing')=='stack' or bool(settings.get('auto_stack'))

def layout_cache(ident,start,end,overlay):
 import layout
 box=':'.join(str(overlay[k]) for k in ('x','y','w','h'))
 return DATA/ident/f"layout-{layout.key(start,end)}-{hashlib.sha256(box.encode()).hexdigest()[:8]}.json"

LAYOUT_LOCKS={};_layout_locks=threading.Lock()

def clip_layout(ident,start,end):
 """Per-clip stacked layout, cached; depends on the camera rectangle, so a manual correction recomputes it."""
 import layout
 overlay=read_overlay(ident)
 if overlay is None:
  with _layout_locks:lock=LAYOUT_LOCKS.setdefault((ident,'overlay'),threading.Lock())
  with lock:
   overlay=read_overlay(ident)
   if overlay is None:
    overlay=layout.detect_overlay(DATA/ident/'source',JOBS[ident].get('duration'));overlay.update(status='ready',manual=False);write_overlay(ident,overlay)
 if not overlay.get('found'):return dict(overlay=overlay,panels=None)
 cache=layout_cache(ident,start,end,overlay)
 with _layout_locks:lock=LAYOUT_LOCKS.setdefault(cache.name,threading.Lock())
 with lock:
  if cache.exists():return json.loads(cache.read_text(encoding='utf-8'))
  result=layout.analyze(DATA/ident/'source',start,end,overlay)
  tmp=cache.with_suffix(f'.{uuid.uuid4().hex[:6]}.tmp');tmp.write_text(json.dumps(result),encoding='utf-8');tmp.replace(cache)
 return result

def prepare_layouts(ident):
 """After the analysis: prepare «Cámara + juego» for every clip, in list order (the first ones are opened first)."""
 job=JOBS.get(ident)
 if not job:return
 clips=list(job.get('clips',[]));job['layout_ready']=0
 for n,clip in enumerate(clips,1):
  try:
   if not clip_layout(ident,clip['start'],clip['end']).get('panels'):job['layout_ready']=len(clips);return   # no camera: nothing to prepare
  except Exception as e:logging.getLogger('uvicorn.error').warning('Layout preparation failed: %s',e)
  job['layout_ready']=n

class LayoutInput(TrackingInput):
 motion:Literal['smooth','balanced','fast']='balanced'
 follow:bool=True

@app.post('/api/jobs/{ident}/layout/path')
def layout_path(ident:str,opts:LayoutInput):
 """The camera crop and the per-frame game crop the export will use, for the editor preview."""
 import layout
 if ident not in JOBS:raise HTTPException(404)
 if not opts.start<opts.end<=JOBS[ident]['duration'] or opts.end-opts.start>180:raise HTTPException(400,'Elige un clip válido de hasta 180 segundos.')
 try:result=clip_layout(ident,opts.start,opts.end)
 except ValueError as e:raise HTTPException(400,str(e))
 if not result.get('panels'):return dict(found=False,kind=result['overlay'].get('kind','none'))
 return layout.preview_path(result,opts.motion,opts.follow)

@app.get('/api/jobs/{ident}/layout-preview')
def layout_preview(ident:str,t:float=0):
 """Still of the stacked layout (camera centred, game centred), for the «Configura tus clips» card."""
 import layout
 if ident not in JOBS:raise HTTPException(404)
 overlay=read_overlay(ident)
 if not overlay or not overlay.get('found'):raise HTTPException(404,'Sin cámara detectada.')
 t=max(0,min(float(t),JOBS[ident]['duration']-.1))
 fake=dict(overlay=overlay,panels=layout.panels(overlay),motion=dict(xs=[overlay['width']/2]))
 with tempfile.TemporaryDirectory() as tmp:
  graph=layout.filter_graph(fake,Path(tmp)/'still.cmd',.04,25,follow=False)
  result=subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',str(DATA/ident/'source'),'-frames:v','1','-filter_complex',f'[0:v]{graph},scale=360:640[o]','-map','[o]','-f','image2','-vcodec','mjpeg','-'],capture_output=True,timeout=60,cwd=tmp)
 if result.returncode or not result.stdout:raise HTTPException(500,'No se pudo crear la vista previa.')
 return Response(result.stdout,media_type='image/jpeg',headers={'Cache-Control':'no-store'})

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
resume_imports()

# --- Clipping en vivo ---------------------------------------------------------------------------------------
import live
LIVE={};LIVE_DIR=DATA/'live'

def recover_live():
 live.kill_orphan_captures(LIVE_DIR)
 for state in LIVE_DIR.glob('*/state.json'):
  try:session=live.LiveSession.load(state.parent);LIVE[session.id]=session
  except (OSError,ValueError,KeyError,TypeError):continue

class LiveInput(BaseModel):
 url:str=Field(min_length=8,max_length=2000)
 minimum:int=Field(default=20,ge=5,le=180)
 maximum:int=Field(default=60,ge=5,le=180)
 buffer_minutes:int=Field(default=60,ge=10,le=180)
 height:Literal[720,1080,1440]=1080
 language:str=Field(default='auto',pattern=r'^(auto|[a-z]{2})$')
 clip_settings:dict|None=None
 @model_validator(mode='after')
 def validate_range(self):
  if self.minimum>self.maximum:raise ValueError('El mínimo no puede superar el máximo.')
  return self

def live_session(sid):
 if sid not in LIVE:raise HTTPException(404,'Sesión no encontrada.')
 return LIVE[sid]

@app.post('/api/live')
def start_live(options:LiveInput):
 try:settings=ClipSettings(**(options.clip_settings or {})).model_dump()
 except ValueError:raise HTTPException(400,'Configuración de clips inválida.')
 try:session=live.LiveSession(LIVE_DIR,options.url,options.minimum,options.maximum,options.buffer_minutes,height=options.height,language=options.language,clip_settings=settings)
 except live.LiveError as e:raise HTTPException(400,str(e))
 if any(s.status in live.RUNNING for s in LIVE.values()):raise HTTPException(409,'Ya hay una sesión en vivo activa. Detenla antes de iniciar otra.')
 LIVE[session.id]=session;session.start()
 # Remember this streamer's setup so the next session starts with the same choices.
 try:STREAMERS.set_prefs(options.url,dict(clip_settings=settings,language=options.language,minimum=options.minimum,maximum=options.maximum,height=options.height,buffer_minutes=options.buffer_minutes))
 except Exception as e:logging.getLogger('uvicorn.error').warning('Streamer preferences not saved: %s',e)
 return session.public()

@app.get('/api/live')
def list_live():return sorted((s.public(full=False) for s in LIVE.values()),key=lambda s:s['created'],reverse=True)

@app.get('/api/live/{sid}')
def live_status(sid:str):return live_session(sid).public()

@app.post('/api/live/{sid}/stop')
def stop_live(sid:str):
 session=live_session(sid)
 if session.status in live.RUNNING:
  session.status='stopping';session.note('Deteniendo y revisando los últimos minutos…')
  threading.Thread(target=session.stop,daemon=True).start()
 return session.public()

@app.post('/api/live/{sid}/resume')
def resume_live(sid:str):
 session=live_session(sid)
 if any(s.status in live.RUNNING for s in LIVE.values()):raise HTTPException(409,'Ya hay una sesión en vivo activa.')
 if session.status not in ('interrupted','stopped','ended','error'):raise HTTPException(409,'La sesión no se puede reanudar en su estado actual.')
 session.start();return session.public()

def live_moment(sid,mid):
 session=live_session(sid)
 try:return session,session.moment(mid)
 except live.LiveError as e:raise HTTPException(404,str(e))

@app.get('/api/live/{sid}/moments/{mid}/video')
def live_moment_video(sid:str,mid:str):
 session,moment=live_moment(sid,mid);path=session.clips/f'{mid}.mp4'
 if not path.exists():raise HTTPException(404,'El clip todavía se está preparando.')
 return FileResponse(path,media_type='video/mp4')

@app.post('/api/live/{sid}/moments/{mid}/discard')
def discard_live_moment(sid:str,mid:str):
 session,moment=live_moment(sid,mid);moment['status']='discarded';session.save(force=True);return session.public()

@app.post('/api/live/{sid}/moments/{mid}/open')
def open_live_moment(sid:str,mid:str):
 """Turn a live moment into a normal job (source, transcript and one clip) so the full editor applies."""
 import shutil
 from editorial import clip_identity
 session,moment=live_moment(sid,mid)
 if moment.get('job_id') in JOBS:return JOBS[moment['job_id']]
 path=session.clips/f'{mid}.mp4'
 if not path.exists():raise HTTPException(409,'El clip todavía se está preparando.')
 ident=uuid.uuid4().hex;folder=DATA/ident;folder.mkdir()
 try:
  try:os.link(path,folder/'source')            # same file on disk, no extra space; either can be removed safely
  except OSError:shutil.copyfile(path,folder/'source')
  name=re.sub(r'[\/:*?"<>|]+',' ',f"{session.channel or 'Directo'} · {moment['title']}")[:120]+'.mp4'
  job=register_video(ident,folder/'source',name,max_duration=12000)
  transcript=session.moment_transcript(moment)
  (folder/'transcript.json').write_text(json.dumps(transcript,ensure_ascii=False),encoding='utf-8')
  base=moment.get('file_start',moment['start']-live.PAD_S)
  start,end=round(moment['start']-base,3),round(min(job['duration'],moment['end']-base),3)
  clip=dict(id=clip_identity(start,end,moment['text']),start=start,end=end,duration=round(end-start,3),title=moment['title'],titles=moment['titles'] or [moment['title']],
            text=moment['text'],score=moment['score'],category=moment['category'],reason=moment['reason'],evidence=moment['evidence'],source=moment['source'],
            captions=make_cues(transcript,start,end))
  job.update(status='ready',clips=[clip],transcript=transcript,analysis_range={'minimum':min(session.minimum,int(end-start)),'maximum':max(session.maximum,math.ceil(end-start))},
             live={'session':sid,'moment':mid,'channel':session.channel,'stream_title':session.title},message='Momento del directo listo para editar.',
             clip_settings=dict(session.clip_settings or CLIP_DEFAULTS))
  save_job(job)
  # «Cámara + juego» prepared by the live session while the moment was rendered: the clip opens ready.
  ready=session.clips/f'{mid}.layout.json'
  if ready.exists():
   prepared=json.loads(ready.read_text(encoding='utf-8'));overlay=dict(prepared['overlay'],status='ready',manual=False)
   write_overlay(ident,overlay)
   if prepared.get('panels'):layout_cache(ident,start,end,overlay).write_text(json.dumps(dict(prepared,start=start,end=end,overlay=overlay)),encoding='utf-8')
 except Exception as e:
  JOBS.pop(ident,None);shutil.rmtree(folder,ignore_errors=True)
  raise HTTPException(500,f'No se pudo abrir el momento en el editor: {e}')
 moment['status']='opened';moment['job_id']=ident;session.save(force=True)
 return job

@app.on_event('shutdown')
def stop_live_captures():
 # Never leave an FFmpeg capture running after ClipStudio closes; the saved state is resumed on the next start.
 for session in LIVE.values():
  if session.proc and session.proc.poll() is None:
   session.stop_event.set();session.proc.terminate()
  session.save(force=True)

recover_live()


# --- Biblioteca permanente (Fase 1) --------------------------------------------------------------------------------
import library
LIBRARY=library.Library(DATA)
_thumb_gate=threading.Semaphore(2)

def library_id(job,clip_id):
 if not clip_id:return None
 live=job.get('live')
 return f"live:{live['session']}:{live['moment']}" if live else f"job:{job['id']}:{clip_id}"

def export_target(job,title,resolution):
 channel=(job.get('live') or {}).get('channel') or (job.get('youtube') or {}).get('channel') or 'Mis videos'
 clean=lambda v:re.sub(r'[\\/:*?"<>|]+',' ',v).strip()[:60] or 'clip'
 folder=DATA/'exports'/clean(channel);folder.mkdir(parents=True,exist_ok=True)
 base=f"{time.strftime('%Y-%m-%d %H%M')} {clean(title)}{' 1440p' if resolution==1440 else ''}"
 target=folder/f'{base}.mp4';n=2
 while target.exists():target=folder/f'{base} ({n}).mp4';n+=1
 return target

def library_sync():
 try:LIBRARY.sync_all(list(JOBS.values()),LIVE_DIR)
 except Exception as e:logging.getLogger('uvicorn.error').warning('Library sync failed: %s',e)

def library_startup():
 library_sync();LIBRARY.empty_trash()
 for item in LIBRARY.list(limit=60):           # warm the latest thumbnails, one at a time
  try:clip_thumb(item['id'])
  except Exception:continue

threading.Thread(target=library_startup,daemon=True).start()

@app.get('/api/library')
def library_list(q:str='',origin:str='',status:str='',platform:str='',channel:str='',favorite:bool=False,removed:bool=False,sort:str='recent',
                 min_score:float|None=None,min_dur:float|None=None,max_dur:float|None=None):
 library_sync()
 return dict(items=LIBRARY.list(q[:100],origin,status,platform,channel,favorite,removed,sort,min_score,min_dur,max_dur),**LIBRARY.summary())

class LibraryPatch(BaseModel):
 favorite:bool|None=None
 tags:list[str]|None=Field(default=None,max_length=12)
 title:str|None=Field(default=None,max_length=120)
 status:Literal['detected','draft','edited','exported']|None=None

@app.patch('/api/library/{cid}')
def library_patch(cid:str,change:LibraryPatch):
 try:LIBRARY.update(cid,change.favorite,change.tags,change.title,change.status)
 except KeyError:raise HTTPException(404,'Clip no encontrado.')
 return LIBRARY.public(LIBRARY.get(cid))

@app.get('/api/library/{cid}/files')
def library_files(cid:str):
 """What «also the file» would move to the trash, so the confirmation can say it exactly."""
 if LIBRARY.get(cid) is None:raise HTTPException(404)
 files=LIBRARY.owned_files(cid)
 return dict(files=[dict(name=f.name,mb=round(f.stat().st_size/1e6,1)) for f in files],exports=LIBRARY.exports(cid))

@app.delete('/api/library/{cid}')
def library_remove(cid:str,files:bool=False):
 try:moved=LIBRARY.remove(cid,files)
 except KeyError:raise HTTPException(404,'Clip no encontrado.')
 return dict(removed=True,moved=moved,trash_days=library.TRASH_DAYS)

@app.post('/api/library/{cid}/restore')
def library_restore(cid:str):
 try:LIBRARY.restore(cid)
 except KeyError:raise HTTPException(404,'Clip no encontrado.')
 return LIBRARY.public(LIBRARY.get(cid))

@app.get('/api/library/{cid}/thumb')
def library_thumb(cid:str):
 if LIBRARY.get(cid) is None:library_sync()
 try:path=clip_thumb(cid,render=False)
 except Exception as e:
  logging.getLogger('uvicorn.error').warning('Clip thumbnail failed (%s): %s',cid,e);path=None
 if not path:queue_thumb(cid)      # rendered in the background; meanwhile the plain frame (the page asks again)
 if not path:
  with _thumb_gate:
   try:path=LIBRARY.make_thumb(cid)          # plain frame as a fallback
   except Exception:path=None
 if not path or not Path(path).exists():raise HTTPException(404,'Sin miniatura.')
 return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'max-age=86400'})

@app.get('/api/library/{cid}/video')
def library_video(cid:str):
 """The clip's video for previews: a live moment's own MP4, or the project video (the page seeks to the clip)."""
 r=LIBRARY.get(cid)
 if r is None or not r['file'] or not Path(r['file']).exists():raise HTTPException(404,'El video de este clip no está disponible.')
 return FileResponse(r['file'],media_type='video/mp4')

class ClipEdits(BaseModel):
 settings:dict

@app.put('/api/jobs/{ident}/clips/{clip_id}/edits')
def save_clip_edits(ident:str,clip_id:str,edits:ClipEdits):
 """Editor changes are saved with the project, so closing the app or switching streamer never loses them."""
 if ident not in JOBS:raise HTTPException(404)
 if len(json.dumps(edits.settings))>200000:raise HTTPException(413,'Demasiados datos de edición.')
 job=JOBS[ident];job.setdefault('clip_edits',{})[clip_id]=edits.settings;save_job(job)
 cid=library_id(job,clip_id)
 if cid:LIBRARY.mark(cid,'edited')
 return dict(saved=True)


# «Aplicar a todos los clips»: the look (logo, title style, subtitles, quality) copied to every clip of the project.
# Each clip keeps its own text, times, subtitles and framing; the vertical title position depends on each clip's format.
SHARED_STYLE=('logo','logo_width','logo_x','logo_y','title_font','title_size','title_padding_x','title_padding_y','title_bg_color',
 'title_text_color','title_outline_color','title_outline_width','title_corners','title_x','style','font','caption_size','caption_color',
 'outline_color','outline_width','caption_x','caption_y','show_subtitles','resolution')
class SharedEdits(BaseModel):
 settings:dict

@app.put('/api/jobs/{ident}/edits/shared')
def save_shared_edits(ident:str,item:SharedEdits):
 if ident not in JOBS:raise HTTPException(404)
 style={k:v for k,v in item.settings.items() if k in SHARED_STYLE and isinstance(v,(str,int,float,bool))}
 job=JOBS[ident];saved=job.setdefault('clip_edits',{})
 for c in job.get('clips') or []:
  entry=saved.get(c['id'])
  # A clip never opened gets its own defaults plus the shared look; «partial» tells the editor to fill the rest.
  if entry is None:entry=saved[c['id']]=dict(title=c.get('title',''),subtitles=c.get('text',''),start=c['start'],end=c['end'],captions=c.get('captions') or [],clip_id=c['id'],partial=True)
  entry.update(style)
 save_job(job)
 return dict(clip_edits=saved,shared=sorted(style))


# --- Clips en vivo: what the stream looks like now, from the recording ClipStudio already makes -------------------
_frames={}
@app.get('/api/live/{sid}/frame')
def live_frame(sid:str):
 """A still of the newest finished segment (no second download of the stream; refreshed at most every 4 s)."""
 session=live_session(sid)
 cached=_frames.get(sid)
 if cached and time.time()-cached[0]<4:return Response(cached[1],media_type='image/jpeg',headers={'Cache-Control':'no-store'})
 segments=sorted(session.segments.glob('seg*.ts')) if session.segments.exists() else []
 source=segments[-2] if len(segments)>1 else None
 if source is None:
  moments=[session.clips/f"{m['id']}.mp4" for m in reversed(session.moments) if (session.clips/f"{m['id']}.mp4").exists()]
  source=moments[0] if moments else None
 if source is None:raise HTTPException(404,'Todavía no hay imagen del directo.')
 result=subprocess.run(['ffmpeg','-v','error','-ss','2','-i',str(source),'-frames:v','1','-vf','scale=960:-2','-f','image2','-vcodec','mjpeg','-'],capture_output=True,timeout=20)
 if result.returncode or not result.stdout:raise HTTPException(500,'No se pudo leer la imagen del directo.')
 _frames[sid]=(time.time(),result.stdout)
 return Response(result.stdout,media_type='image/jpeg',headers={'Cache-Control':'no-store'})


# --- Streamers: «En vivo ahora», search by name and profile photos (Rediseño parte 3) ------------------------------
import streamers as streamers_mod
STREAMERS=streamers_mod.Streamers(DATA)

def streamers_sync():
 counts={c['channel'].lower():c['n'] for c in LIBRARY.summary()['channels']}
 STREAMERS.sync_from([s.public(full=False) for s in LIVE.values()],counts)

def streamers_loop():
 # Every streamer the user clips is checked at most every 5 minutes, one request at a time.
 while True:
  try:streamers_sync();STREAMERS.check_all()
  except Exception as e:logging.getLogger('uvicorn.error').warning('Streamer check failed: %s',e)
  try:STREAMERS.check_featured()
  except Exception as e:logging.getLogger('uvicorn.error').warning('Featured streamer check failed: %s',e)
  time.sleep(60)

@app.on_event('startup')
def start_streamer_checks():
 # Runs when the app really starts (uvicorn), not when tests import the module.
 if os.environ.get('CLIPSTUDIO_NO_STREAMER_CHECKS')!='1':threading.Thread(target=streamers_loop,daemon=True).start()

@app.get('/api/streamers')
def streamers_list():
 return STREAMERS.listing()

@app.get('/api/streamers/featured')
def streamers_featured():
 return STREAMERS.featured_listing()

@app.get('/api/streamers/search')
def streamers_search(q:str='',scope:Literal['all','link','local','kick','youtube']='all'):
 if len(q)>300:raise HTTPException(400,'Escribe un nombre más corto.')
 if scope=='all':return STREAMERS.search(q)
 try:return STREAMERS.search_scope(q,scope)
 except Exception as e:
  logging.getLogger('uvicorn.error').warning('Streamer search (%s) failed: %s',scope,e)
  return []

class FollowInput(BaseModel):
 url:str=Field(min_length=8,max_length=300)

@app.post('/api/streamers/follow')
def streamers_follow(item:FollowInput):
 try:key=STREAMERS.follow(item.url)
 except ValueError as e:raise HTTPException(400,str(e))
 threading.Thread(target=STREAMERS.refresh,args=(key,True),daemon=True).start()
 return dict(key=key)

@app.get('/api/streamers/{key}/avatar')
def streamer_avatar(key:str):
 path=STREAMERS.avatar_path(key)
 if not path:raise HTTPException(404)
 return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'max-age=86400'})


@app.get('/api/streamers/prefs')
def streamer_prefs(url:str):
 return STREAMERS.get_prefs(url) or {}

# --- Espacio en disco: temporary live buffers, only removed when the user confirms ----------------------------------
def folder_mb(folder):
 try:return round(sum(f.stat().st_size for f in Path(folder).rglob('*') if f.is_file())/1e6,1)
 except OSError:return 0

@app.get('/api/storage')
def storage():
 """What ClipStudio keeps on disk. «Temporales» are the rolling buffers of stopped live sessions: the detected
 moments are separate files and are never part of them."""
 buffers=[]
 for s in LIVE.values():
  if s.status in live.RUNNING+('stopping',) or not s.segments.exists():continue
  mb=folder_mb(s.segments)
  if mb>0:buffers.append(dict(id=s.id,channel=s.channel or s.url,title=s.title,created=s.created,status=s.status,mb=mb,moments=len(s.moments)))
 buffers.sort(key=lambda b:-b['mb'])
 return dict(buffers=buffers,buffers_mb=round(sum(b['mb'] for b in buffers),1),moments_mb=round(sum(folder_mb(s.clips) for s in LIVE.values()),1),
             exports_mb=folder_mb(DATA/'exports'),trash_mb=folder_mb(DATA/'papelera'),trash_days=library.TRASH_DAYS)

class CleanInput(BaseModel):
 sessions:list[str]=Field(default_factory=list,max_length=200)
 confirm:bool=False

@app.post('/api/storage/clean')
def storage_clean(item:CleanInput):
 import shutil
 if not item.confirm:raise HTTPException(400,'Confirma antes de liberar espacio.')
 freed=0;done=[]
 for sid in item.sessions:
  s=LIVE.get(sid)
  if not s or s.status in live.RUNNING+('stopping',) or not s.segments.exists():continue   # never a session that is recording
  mb=folder_mb(s.segments);shutil.rmtree(s.segments,ignore_errors=True)
  freed+=mb;done.append(sid)
 if done:LIBRARY.log('storage',f'Espacio liberado: {freed/1000:.1f} GB de archivos temporales de {len(done)} directos','')
 return dict(freed_mb=round(freed,1),sessions=done)


# --- Live preview as video: the recorded 6 s segments, remuxed to MP4 (no re-encode, no second download) ----------
_segments_mp4={}
@app.get('/api/live/{sid}/segments')
def live_segments(sid:str):
 """Indexes of the finished segments (the newest file is still being written)."""
 session=live_session(sid)
 if not session.segments.exists():return dict(done=[],running=session.status in live.RUNNING)
 names=sorted(session.segments.glob('seg*.ts'))
 done=[int(n.stem[3:]) for n in names[:-1]][-6:] if session.status in live.RUNNING else [int(n.stem[3:]) for n in names][-6:]
 return dict(done=done,running=session.status in live.RUNNING,segment_s=live.SEGMENT_S)

@app.get('/api/live/{sid}/segment/{index}')
def live_segment(sid:str,index:int):
 session=live_session(sid)
 if index<0:raise HTTPException(400)
 path=session.segments/f'seg{index:06d}.ts'
 if not path.exists():raise HTTPException(404,'Ese fragmento ya no está en el búfer.')
 cached=_segments_mp4.get((sid,index))
 if cached is None:
  r=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-map','0:a:0?','-c','copy','-bsf:a','aac_adtstoasc','-movflags','frag_keyframe+empty_moov+default_base_moof','-f','mp4','-'],capture_output=True,timeout=20)
  if r.returncode or not r.stdout:raise HTTPException(500,'No se pudo preparar el fragmento.')
  cached=r.stdout;_segments_mp4[(sid,index)]=cached
  for key in sorted(k for k in _segments_mp4 if k[0]==sid)[:-6]:_segments_mp4.pop(key,None)   # keep the last 6
 return Response(cached,media_type='video/mp4',headers={'Cache-Control':'no-store'})


@app.get('/api/streamers/{key}/live.jpg')
def streamer_live_still(key:str):
 """Current image of a Kick stream, taken from its public stream (Kick refuses its own thumbnails outside its site)."""
 platform,_,slug=key.partition(':')
 if platform!='kick' or not re.fullmatch(r'[\w-]{1,40}',slug):raise HTTPException(404)
 path=STREAMERS.live_still(key)
 if not path or time.time()-path.stat().st_mtime>180:
  try:
   info=STREAMERS.lookup('kick',slug.lower())
   if info.get('live'):STREAMERS._live_still(key,info)
  except Exception:pass
  path=STREAMERS.live_still(key)
 if not path:raise HTTPException(404,'Sin imagen del directo.')
 return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'no-store'})


# --- Library thumbnails that look like the finished clip: its format (Cámara + juego, zoom…) and its title -------
def thumb_spec(r):
 """Source, time, format, overlay and title of a library clip, from its saved edits or the project's settings."""
 import layout
 cid=r['id'];edits={};overlay=None
 if r['project_id'] and r['project_id'] in JOBS:
  job=JOBS[r['project_id']];settings=clip_settings(job)
  ref=job['clips'][0]['id'] if job.get('live') and job.get('clips') else r['clip_ref']
  edits=(job.get('clip_edits') or {}).get(ref) or {}
  overlay=read_overlay(job['id']);source=DATA/job['id']/'source'
  clip=next((c for c in job.get('clips',[]) if c['id']==ref),None)
  start=float(edits.get('start',clip['start'] if clip else r['start'] or 0));end=float(edits.get('end',clip['end'] if clip else r['end'] or start+10))
 else:
  if r['origin']!='live' or not r['file']:return None
  session=LIVE.get(r['session_id']);settings={**CLIP_DEFAULTS,**((session.clip_settings if session else None) or {})}
  prepared=Path(r['file']).with_suffix('.layout.json')
  if prepared.exists():
   try:overlay=json.loads(prepared.read_text(encoding='utf-8')).get('overlay')
   except (OSError,ValueError):overlay=None
  source=Path(r['file']);start=3.0;end=3.0+float(r['duration'] or 10)
 if not Path(source).exists():return None
 found=bool(overlay and overlay.get('found'))
 framing=edits.get('framing') or ('stack' if found and (settings.get('framing')=='stack' or settings.get('auto_stack')) else ('zoom' if settings.get('framing')=='stack' else settings.get('framing','zoom')))
 if framing=='stack' and not found:framing='zoom'
 return dict(source=source,t=start+max(.5,(end-start)*.35),framing=framing,zoom=edits.get('zoom',settings.get('zoom','balanced')),overlay=overlay if framing=='stack' else None,
             title=edits.get('title') or r['user_title'] or r['title'] or '',edits=edits,corners=edits.get('title_corners',settings.get('title_corners','rounded')))

def default_title_y(framing,zoom,panels):
 """Where the title goes: on the camera/game line, on the line between the top black band and the video, or near the top."""
 import layout,tracking
 if framing=='stack' and panels:return round((panels['top']+layout.SEAM/2)/19.2,1)
 if framing=='zoom':return round((1920-tracking.band_height('zoom',zoom))/2/19.2,1)
 return 12

def title_position(framing,zoom,panels,saved):
 """The saved position, unless it is a default left by another format (12 %, or a camera/game line 40-50 % on a clip
 that is no longer «Cámara + juego»: seen on live clips that had been set to stack by mistake)."""
 if saved is None:return default_title_y(framing,zoom,panels)
 v=float(saved)
 if v==12 or (framing!='stack' and 40<=v<=50.3) or any(abs(v-default_title_y('zoom',z,None))<.6 for z in ('soft','balanced','close')):
  return default_title_y(framing,zoom,panels)
 return v

_thumb_pool=ThreadPoolExecutor(max_workers=1);_thumb_queued=set()
def queue_thumb(cid):
 if cid in _thumb_queued:return
 _thumb_queued.add(cid)
 def run():
  try:clip_thumb(cid)
  except Exception as e:logging.getLogger('uvicorn.error').warning('Clip thumbnail failed (%s): %s',cid,e)
  finally:_thumb_queued.discard(cid)
 _thumb_pool.submit(run)

def clip_thumb(cid,render=True):
 """Render (once) a 9:16 still of the clip as it will be exported, with its title; cached by what it shows."""
 import layout,tracking
 r=LIBRARY.get(cid)
 if r is None:return None
 spec=thumb_spec(r)
 if spec is None:return None
 ov=spec['overlay'];panels=layout.panels(ov) if ov else None
 title_y=title_position(spec['framing'],spec['zoom'],panels,spec['edits'].get('title_y'))
 sig=hashlib.sha256(json.dumps([3,spec['title'],spec['framing'],spec['zoom'],title_y,spec['corners'],ov and [ov[k] for k in 'xywh'],round(spec['t'],1)]).encode()).hexdigest()[:10]
 target=DATA/'thumbs'/f"{cid.replace(':','_')}-{sig}.jpg"
 if target.exists() or not render:return target if target.exists() else None
 target.parent.mkdir(exist_ok=True)
 with _thumb_gate, tempfile.TemporaryDirectory() as tmp:
  if ov:geometry=layout.filter_graph(dict(overlay=ov,panels=panels,motion=dict(xs=[ov['width']/2])),Path(tmp)/'t.cmd',.04,25,follow=False)
  else:geometry=tracking.static_filter(spec['framing'],spec['zoom'],50,50)
  args=['ffmpeg','-v','error','-y','-ss',f"{spec['t']:.2f}",'-i',str(spec['source'])]
  graph=f'[0:v]{geometry},setsar=1[b]';last='b'
  try:
   style={k:v for k,v in spec['edits'].items() if k in Export.model_fields and k not in ('start','end','title','subtitles','captions','clip_id')}
   image=render_title(Export(**{**style,'start':0,'end':1,'title':spec['title'][:96],'subtitles':'','title_corners':spec['corners']}))
  except Exception:image=None
  if image is not None:
   image.save(Path(tmp)/'title.png');args+=['-i',str(Path(tmp)/'title.png')]
   graph+=f";[b][1:v]overlay=x=W*{float(spec['edits'].get('title_x',50))/100}-w/2:y=H*{float(title_y)/100}-h/2[t]";last='t'
  graph+=f';[{last}]scale=360:640:flags=lanczos[o]'
  flags=0x00004000 if os.name=='nt' else 0      # below normal priority: never slows an analysis down
  subprocess.run(args+['-frames:v','1','-filter_complex',graph,'-map','[o]','-q:v','4',str(target)],capture_output=True,timeout=60,cwd=tmp,creationflags=flags)
 for old in target.parent.glob(f"{cid.replace(':','_')}-*.jpg"):
  if old!=target:old.unlink(missing_ok=True)      # only previous versions of this same thumbnail
 return target if target.exists() else None


# --- Library: big preview on hover and high-quality download, both with the clip's own look -----------------------
def clip_look(cid):
 """Everything that decides how a library clip looks, shared by the preview video and the download."""
 import layout
 r=LIBRARY.get(cid)
 if r is None:raise HTTPException(404,'Clip no encontrado.')
 spec=thumb_spec(r)
 if spec is None:raise HTTPException(404,'El video de este clip no está disponible.')
 ov=spec['overlay'];panels=layout.panels(ov) if ov else None
 return r,spec,ov,panels,title_position(spec['framing'],spec['zoom'],panels,spec['edits'].get('title_y'))

_previews=threading.Lock()
@app.get('/api/library/{cid}/preview.mp4')
def library_preview(cid:str):
 """Small MP4 of the whole clip as it will look (format and title), made once on first hover and kept."""
 import layout,tracking
 r,spec,ov,panels,title_y=clip_look(cid)
 job_start,job_end=None,None
 edits=spec['edits']
 if r['project_id'] and r['project_id'] in JOBS:
  job=JOBS[r['project_id']];ref=job['clips'][0]['id'] if job.get('live') and job.get('clips') else r['clip_ref']
  clip=next((c for c in job.get('clips',[]) if c['id']==ref),None)
  job_start=float(edits.get('start',clip['start'] if clip else 0));job_end=float(edits.get('end',clip['end'] if clip else job_start+30))
 else:job_start,job_end=3.0,3.0+float(r['duration'] or 20)
 sig=hashlib.sha256(json.dumps([2,spec['title'],spec['framing'],spec['zoom'],title_y,spec['corners'],ov and [ov[k] for k in 'xywh'],job_start,job_end]).encode()).hexdigest()[:10]
 target=DATA/'previews'/f"{cid.replace(':','_')}-{sig}.mp4";target.parent.mkdir(exist_ok=True)
 if not target.exists():
  with _previews, tempfile.TemporaryDirectory() as tmp:
   if not target.exists():
    if ov:geometry=layout.filter_graph(dict(overlay=ov,panels=panels,motion=dict(xs=[ov['width']/2])),Path(tmp)/'p.cmd',job_end-job_start,24,follow=False)
    else:geometry=tracking.static_filter(spec['framing'],spec['zoom'],50,50)
    args=['ffmpeg','-v','error','-y','-ss',f'{job_start:.2f}','-t',f'{job_end-job_start:.2f}','-i',str(spec['source'])]
    graph=f'[0:v]{geometry},setsar=1[b]';last='b'
    try:
     style={k:v for k,v in edits.items() if k in Export.model_fields and k not in ('start','end','title','subtitles','captions','clip_id')}
     image=render_title(Export(**{**style,'start':0,'end':1,'title':spec['title'][:96],'subtitles':'','title_corners':spec['corners']}))
    except Exception:image=None
    if image is not None:
     image.save(Path(tmp)/'title.png');args+=['-loop','1','-i',str(Path(tmp)/'title.png')]
     graph+=f";[b][1:v]overlay=x=W*{float(edits.get('title_x',50))/100}-w/2:y=H*{float(title_y)/100}-h/2:shortest=1[t]";last='t'
    graph+=f';[{last}]scale=360:640:flags=bicubic,fps=24[o]'
    out=Path(tmp)/'p.mp4'
    run=subprocess.run(args+['-filter_complex',graph,'-map','[o]','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','28','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-movflags','+faststart','-t',f'{job_end-job_start:.2f}',str(out)],
                       capture_output=True,timeout=240,cwd=tmp,creationflags=0x00004000 if os.name=='nt' else 0)
    if run.returncode or not out.exists():raise HTTPException(500,'No se pudo preparar la vista previa.')
    os.replace(out,target)
    for old in target.parent.glob(f"{cid.replace(':','_')}-*.mp4"):
     if old!=target:old.unlink(missing_ok=True)
 return FileResponse(target,media_type='video/mp4',headers={'Cache-Control':'no-store'})

class LibraryExport(BaseModel):
 resolution:Literal[1080,1440]=1080

@app.post('/api/library/{cid}/export')
def library_export(cid:str,item:LibraryExport):
 """Download a library clip in high quality with its saved edits (or the project's look when it was never edited)."""
 r,spec,ov,panels,title_y=clip_look(cid)
 if r['origin']=='live' and not (r['project_id'] and r['project_id'] in JOBS):
  job=open_live_moment(r['session_id'],r['clip_ref'])      # a live moment becomes a project the first time
  try:LIBRARY.sync_job(job)
  except Exception:pass
 else:job=JOBS.get(r['project_id'])
 if not job:raise HTTPException(404,'No se encontró el proyecto de este clip.')
 ref=job['clips'][0]['id'] if job.get('live') else r['clip_ref']
 clip=next((c for c in job.get('clips',[]) if c['id']==ref),None)
 if not clip:raise HTTPException(404,'No se encontró el clip en su proyecto.')
 edits=dict((job.get('clip_edits') or {}).get(ref) or {})
 settings=clip_settings(job)
 base=dict(start=clip['start'],end=clip['end'],title=clip.get('title') or '',subtitles=clip.get('text') or '',clip_id=ref,
           framing=spec['framing'],zoom=spec['zoom'],title_corners=spec['corners'],show_subtitles=bool(settings.get('subtitles',True)),
           caption_y=85 if spec['framing']=='stack' else 81,tracking_motion=settings.get('tracking_motion','balanced'))
 values={**base,**{k:v for k,v in edits.items() if k in Export.model_fields},'title_y':title_y,'resolution':item.resolution,'preview':False}
 if values.get('framing')=='stack' and not ov:values['framing']='zoom'
 values['auto_follow']=bool(values.get('auto_follow')) and values['framing']!='stack' and (DATA/job['id']/f"tracking-{__import__('tracking').key(values['start'],values['end'])}.json").exists()
 try:opts=Export(**values)
 except Exception as e:raise HTTPException(400,f'No se pudo preparar la exportación: {e}')
 return export(job['id'],opts)


_preview_pool=ThreadPoolExecutor(max_workers=1);_preview_queued=set()
class WarmInput(BaseModel):
 ids:list[str]=Field(default_factory=list,max_length=30)

@app.post('/api/library/previews/warm')
def library_previews_warm(item:WarmInput):
 """Prepare the hover previews of the clips on screen, one at a time at low priority, so hovering plays at once."""
 for cid in item.ids:
  if cid in _preview_queued:continue
  _preview_queued.add(cid)
  def run(cid=cid):
   try:library_preview(cid)
   except Exception:pass
   finally:_preview_queued.discard(cid)
  _preview_pool.submit(run)
 return dict(queued=len(_preview_queued))
