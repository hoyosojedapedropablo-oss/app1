"""Single public YouTube video import with bounded size and duration."""
import re,time
from urllib.parse import urlsplit,parse_qs

MAX_BYTES=12*1024**3

def canonical_url(value):
 try:parsed=urlsplit(value.strip())
 except ValueError:raise ValueError('Enlace de YouTube inválido.') from None
 if parsed.scheme not in ('http','https') or parsed.username or parsed.password or parsed.port not in (None,80,443):raise ValueError('Pega un enlace público de YouTube.')
 host=(parsed.hostname or '').lower()
 if host=='youtu.be':ident=parsed.path.strip('/')
 elif host in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'):
  ident=parse_qs(parsed.query).get('v',[''])[0] if parsed.path=='/watch' else parsed.path.split('/')[2] if re.match(r'^/(shorts|live|embed)/',parsed.path) else ''
 else:raise ValueError('Solo se admiten enlaces de YouTube.')
 if not re.fullmatch(r'[A-Za-z0-9_-]{11}',ident):raise ValueError('El enlace debe apuntar a un video individual de YouTube.')
 return 'https://www.youtube.com/watch?v='+ident

def download(url,folder,progress,mode="fast"):
 if mode not in ("fast","original"):raise ValueError("Calidad de descarga inválida.")
 import yt_dlp
 started=time.monotonic()
 metadata={};sizes={};received={}
 def hook(data):
  if time.monotonic()-started>7200:raise ValueError('La descarga superó el tiempo de espera. Intenta subir el archivo.')
  size=data.get('total_bytes') or data.get('total_bytes_estimate') or 0
  if data.get('downloaded_bytes',0)>MAX_BYTES or size>MAX_BYTES:raise ValueError('El video supera 12 GB.')
  filename=data.get('filename','video')
  sizes[filename]=size;received[filename]=data.get('downloaded_bytes',0)
  downloaded=sum(received.values());total=max(sum(sizes.values()),metadata.get('expected_bytes',0))
  if downloaded>MAX_BYTES:raise ValueError('El video supera 12 GB.')
  progress(min(95,round(downloaded/total*95)) if total else 0,'Descargando video de YouTube…',speed=data.get('speed'),eta=data.get('eta'),downloaded_bytes=downloaded,total_bytes=total)
 def post_hook(data):
  progress(98,'Preparando audio y video para el editor…')
 def match(info,*,incomplete=False):
  if info.get('is_live') or info.get('live_status') in ('is_live','is_upcoming'):return 'Los directos deben haber terminado antes de descargarlos.'
  if info.get('duration') and info['duration']>7200:return 'La duración máxima es 120 minutos.'
  if info.get('filesize',0) and info['filesize']>MAX_BYTES:return 'El video supera 12 GB.'
 class Logger:
  def debug(self,*args):pass
  def warning(self,*args):pass
  def error(self,*args):pass
 limit='[height<=1080]' if mode=='fast' else ''
 selector=f'bestvideo[ext=mp4][vcodec^=avc1]{limit}+bestaudio[ext=m4a]/best[ext=mp4]{limit}/bestvideo{limit}+bestaudio/best{limit}' if mode=='fast' else 'bestvideo+bestaudio/best'
 options=dict(concurrent_fragment_downloads=8,http_chunk_size=10*1024*1024,postprocessor_hooks=[post_hook],noplaylist=True,quiet=True,logger=Logger(),socket_timeout=30,retries=2,fragment_retries=2,progress_hooks=[hook],match_filter=match,max_filesize=MAX_BYTES,outtmpl=str(folder/'download.%(ext)s'),merge_output_format='mp4',format=selector,postprocessors=[dict(key='FFmpegVideoRemuxer',preferedformat='mp4')])
 with yt_dlp.YoutubeDL(options) as ydl:
  info=ydl.extract_info(url,download=False)
  if not info:raise ValueError('No se pudo consultar el video.')
  reason=match(info)
  if reason:raise ValueError(reason)
  metadata['expected_bytes']=sum(f.get('filesize') or f.get('filesize_approx') or 0 for f in info.get('requested_formats',[info]))
  if metadata['expected_bytes']>MAX_BYTES:raise ValueError('El video supera 12 GB.')
  ident=parse_qs(urlsplit(url).query)['v'][0]
  progress(0,'Descargando video de YouTube…',title=info.get('title') or 'Video de YouTube',channel=info.get('channel') or info.get('uploader') or '',duration=info.get('duration'),thumbnail=f'https://i.ytimg.com/vi/{ident}/hqdefault.jpg',quality='Hasta 1080p' if mode=='fast' else 'Máxima disponible')
  info=ydl.process_ie_result(info,download=True)
 if not info:raise ValueError('No se pudo importar el video. Verifica que dure hasta 120 minutos y que el directo haya terminado.')
 path=folder/'download.mp4'
 if not path.exists():raise ValueError('No se obtuvo un archivo de video válido.')
 if path.stat().st_size>MAX_BYTES:raise ValueError('El video supera 12 GB.')
 return path,(info.get('title') or 'Video de YouTube')+'.mp4'
