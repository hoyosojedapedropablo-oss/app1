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

def javascript_options():
 import importlib.util
 if importlib.util.find_spec('yt_dlp_ejs') is None:
  raise ValueError('Falta el componente EJS de YouTube. Cierra la app y ejecuta REPARAR_YOUTUBE_WINDOWS.')
 try:
  from deno import find_deno_bin
  path=find_deno_bin()
 except (ImportError,FileNotFoundError,RuntimeError):
  raise ValueError('Falta el motor JavaScript Deno. Cierra la app y ejecuta REPARAR_YOUTUBE_WINDOWS.') from None
 return {'deno':{'path':path}}


def diagnose_error(error):
 # Return actionable categories, never provider URLs, local paths or credential contents.
 chain=[];current=error;seen=set()
 while current is not None and id(current) not in seen and len(chain)<6:
  from youtube_session import SessionUnavailable
  if isinstance(current,SessionUnavailable):
   from youtube_session import RETIRED
   return 'YT-CONEXION',RETIRED
  seen.add(id(current));chain.append(str(current).lower());current=current.__cause__ or current.__context__
 text=' '.join(chain)
 checks=[
  ('YT-COOKIES-YOUTUBE',('no se encontraron cookies de youtube',), 'Se leyó el navegador, pero no tenía cookies de YouTube vigentes. Abre el enlace en el navegador elegido, completa la verificación y cierra ese navegador antes de reintentar.'),
  ('YT-COOKIES-CIFRADO',('failed to decrypt','decrypt with dpapi','app-bound','app bound','cookie decryption'), 'Windows no permitió leer la sesión cifrada del navegador. Esta vía de acceso no está disponible en este equipo; puedes importar el archivo original. No desactives la protección del navegador.'),
  ('YT-COOKIES-OCUPADAS',('could not copy chrome cookie','could not copy edge cookie','could not copy brave cookie','database is locked','being used by another process'), 'La sesión de ese navegador está bloqueada por Windows o por un proceso que la mantiene abierta. No se pudo usar esta vía de acceso. Puedes importar el archivo original desde tu PC.'),
  ('YT-COOKIES-PERFIL',('could not find firefox cookies','could not find chrome cookies','could not find edge cookies','could not find brave cookies','could not find cookies database'), 'No se encontró la sesión de ese navegador en este PC. Abre YouTube en ese navegador, inicia sesión y comprueba el video; luego cierra ese navegador y reintenta.'),
  ('YT-COOKIES-LECTURA',('failed to load cookies',), 'No se pudo leer la sesión del navegador seleccionado. Cierra ese navegador y reintenta. Si persiste en Chrome o Edge, usa Firefox; no hace falta volver a instalar el descargador.'),
  ('YT-RED',('proxy','tunnel connection','getaddrinfo','name resolution','failed to resolve','connection refused','network is unreachable'), 'No se pudo conectar con YouTube por un problema de red o proxy. Revisa tu conexión y prueba de nuevo.'),
  ('YT-EDAD',('age-restricted','confirm your age','age restricted'), 'YouTube exige verificar la edad para este video. La descarga pública no puede hacerlo; ingresa el archivo descargado.'),
  ('YT-SESION',("not a bot",'sign in','login required','authentication required','confirm you’re not a bot'), 'YouTube bloqueó la importación automática y exige una verificación de acceso. La app no puede completarla por ti. Puedes ingresar el archivo original desde tu PC; el uso de una sesión autorizada está en las opciones avanzadas.'),
  ('YT-PRIVADO',('private video','members-only','members only','video is not available','video unavailable','removed by','copyright'), 'El video no está disponible públicamente o tiene restricciones. Comprueba que abre en YouTube sin iniciar sesión, o ingresa el archivo descargado.'),
  ('YT-REGION',('not available in your country','geo restricted','geo-restricted'), 'El video tiene una restricción de región y no puede descargarse desde esta conexión.'),
  ('YT-LIMITE',('429','too many requests','rate limit'), 'YouTube limitó temporalmente las descargas. Espera unos minutos antes de intentarlo de nuevo.'),
  ('YT-JAVASCRIPT',('javascript','deno','ejs','signature extraction','nsig extraction','challenge solving'), 'Falta o falló el soporte JavaScript de YouTube. Cierra la app y ejecuta REPARAR_YOUTUBE_WINDOWS; después abre INICIAR_WINDOWS.'),
  ('YT-FORMATO',('requested format','no video formats','no formats found'), 'YouTube no entregó un formato descargable. Actualiza el descargador con REPARAR_YOUTUBE_WINDOWS e inténtalo de nuevo.'),
  ('YT-403',('403','forbidden'), 'YouTube rechazó el acceso al archivo (403). Cierra la app y ejecuta REPARAR_YOUTUBE_WINDOWS. Si continúa, ingresa el archivo descargado.'),
  ('YT-TIEMPO',('timed out','timeout'), 'La conexión con YouTube agotó el tiempo de espera. Revisa tu conexión e inténtalo de nuevo.'),
  ('YT-FFMPEG',('ffmpeg','ffprobe'), 'No se pudo preparar el video con FFmpeg. Revisa que FFmpeg esté instalado y haya espacio disponible en disco.'),
  ('YT-DISCO',('no space left','disk full','not enough space','errno 28'), 'No hay espacio suficiente para descargar y preparar el video. Libera espacio y vuelve a intentarlo.'),
  ('YT-CERTIFICADO',('certificate verify failed','certificate_verify_failed','ssl certificate'), 'Falló la comprobación del certificado de conexión. Revisa la fecha del equipo y la configuración de tu red.'),
 ]
 # Region and disk messages may also contain generic unavailability/FFmpeg errors.
 for code,patterns,message in sorted(checks,key=lambda item:0 if item[0] in ('YT-REGION','YT-DISCO','YT-CERTIFICADO') else 1):
  if any(pattern in text for pattern in patterns):return code,message
 if isinstance(error,ValueError) and text.startswith(('el video','la duración','no se pudo consultar','no se obtuvo','no se pudo importar','la descarga superó','los directos','calidad de descarga')):return 'YT-VALIDACION',str(error)[:500]
 return 'YT-DESCARGA','No se pudo completar la descarga. Ejecuta REPARAR_YOUTUBE_WINDOWS y vuelve a probar. Si continúa, comparte este código de error y el enlace del video.'

def _download_attempt(url,folder,progress,mode="fast",browser="none"):
 if browser not in ("none","managed","firefox","chrome","edge","brave"):raise ValueError("Navegador no admitido.")
 if browser=='managed':
  from youtube_session import SessionUnavailable,RETIRED
  raise SessionUnavailable(RETIRED)
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
 options=dict(js_runtimes=javascript_options(),concurrent_fragment_downloads=8,http_chunk_size=10*1024*1024,postprocessor_hooks=[post_hook],noplaylist=True,quiet=True,logger=Logger(),socket_timeout=30,retries=2,fragment_retries=2,progress_hooks=[hook],match_filter=match,max_filesize=MAX_BYTES,outtmpl=str(folder/'download.%(ext)s'),merge_output_format='mp4',format=selector,postprocessors=[dict(key='FFmpegVideoRemuxer',preferedformat='mp4')])
 if browser!='none':
  options['cookiesfrombrowser']=(browser,)
  options['cachedir']=False
 with yt_dlp.YoutubeDL(options) as ydl:
  if browser!='none':
   # Read only after the caller explicitly requested this browser. Report presence, never values.
   progress(0,'Leyendo la sesión del navegador seleccionado…',access_mode=browser)
   cookies=[cookie for cookie in ydl.cookiejar if (cookie.domain.lstrip('.')=='youtube.com' or cookie.domain.endswith('.youtube.com')) and not cookie.is_expired()]
   if not cookies:raise ValueError('No se encontraron cookies de YouTube en el navegador seleccionado.')
   auth_names={'SID','SAPISID','__Secure-1PSID','__Secure-3PSID','__Secure-1PAPISID','__Secure-3PAPISID','LOGIN_INFO'}
   progress(0,'Cookies de YouTube leídas; consultando el video…',access_mode=browser,browser_cookies_read=True,youtube_login_cookie_present=any(cookie.name in auth_names for cookie in cookies))
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

class ImportAccessFailure(Exception):
 def __init__(self,public_code):
  super().__init__('No se pudo completar el acceso a YouTube.')
  self.public_error_code=public_code


def download(url,folder,progress,mode='fast',browser='none'):
 """Public first. Reading a browser is an explicit, last-resort opt-in, never a prerequisite."""
 if browser not in ('none','managed','firefox','chrome','edge','brave'):raise ValueError('Navegador no admitido.')
 progress(0,'Conectando con YouTube…',access_mode='none',requested_browser=browser,attempt=1)
 try:return _download_attempt(url,folder,progress,mode=mode,browser='none')
 except Exception as public_error:
  code,_=diagnose_error(public_error)
  # Do not read sessions for network, format, duration, disk or installation failures.
  if browser=='none' or code not in ('YT-SESION','YT-403'):raise
 progress(0,'YouTube pide acceso adicional; intentando la sesión que autorizaste…',access_mode=browser,requested_browser=browser,public_error_code=code,attempt=2)
 try:return _download_attempt(url,folder,progress,mode=mode,browser=browser)
 except Exception as session_error:raise ImportAccessFailure(code) from session_error

if __name__=='__main__':
 import subprocess,shutil
 from importlib.metadata import version
 try:
  runtime=javascript_options()['deno']['path']
  result=subprocess.run([runtime,'--version'],capture_output=True,text=True,timeout=10,check=True)
  print('yt-dlp: '+version('yt-dlp'))
  print('EJS: '+version('yt-dlp-ejs'))
  print(result.stdout.splitlines()[0])
  if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):raise ValueError('Falta FFmpeg o ffprobe en PATH.')
  from yt_dlp.utils._jsruntime import DenoJsRuntime
  info=DenoJsRuntime(runtime).info
  if not info or not info.supported:raise ValueError('Deno no es compatible con esta versión de yt-dlp.')
  print('Componentes de YouTube listos. La descarga real depende del acceso de YouTube al video.')
 except Exception as error:
  code,message=diagnose_error(error);print(f'[{code}] {message}');raise SystemExit(1)
