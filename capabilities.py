"""Detect this PC's resources once per start and choose CPU or GPU for each stage separately.

Transcription, AI analysis and export use different engines (CTranslate2, Ollama, FFmpeg NVENC), so each one
is checked on its own. Nothing here downloads models or installs software.
"""
import ctypes,glob,json,os,platform,subprocess,sys,threading
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SETTINGS=ROOT/'data'/'performance.json'
STAGES=('transcription','export')
MODES=('auto','gpu','cpu')
# Whisper small in float16 measured ~1 GB on an RTX 5060 Ti; keep headroom for the desktop and the decoder.
MIN_FREE_VRAM_MB=1500
_lock=threading.Lock();_cache=None


def cuda_library_dirs():
    """NVIDIA runtime wheels (e.g. nvidia-cublas-cu12) ship their DLLs in site-packages/nvidia/*/bin."""
    found=[]
    for base in sys.path:
        found+=[path for path in glob.glob(os.path.join(base,'nvidia','*','bin')) if os.path.isdir(path)]
    return sorted(set(found))


def enable_cuda_libraries():
    for path in cuda_library_dirs():
        if hasattr(os,'add_dll_directory'):
            try:os.add_dll_directory(path)
            except OSError:continue
        if path not in os.environ.get('PATH',''):os.environ['PATH']=path+os.pathsep+os.environ.get('PATH','')


def memory():
    if os.name=='nt':
        class Status(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong),('total',ctypes.c_ulonglong),('free',ctypes.c_ulonglong),
                      ('page_total',ctypes.c_ulonglong),('page_free',ctypes.c_ulonglong),('virtual_total',ctypes.c_ulonglong),
                      ('virtual_free',ctypes.c_ulonglong),('extended',ctypes.c_ulonglong)]
        status=Status();status.length=ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {'total_gb':round(status.total/1024**3,1),'free_gb':round(status.free/1024**3,1)}
    try:
        values={line.split(':')[0]:int(line.split()[1]) for line in open('/proc/meminfo',encoding='utf-8')}
        return {'total_gb':round(values['MemTotal']/1024**2,1),'free_gb':round(values['MemAvailable']/1024**2,1)}
    except (OSError,KeyError,ValueError,IndexError):return {'total_gb':None,'free_gb':None}


def nvidia_gpu(run=subprocess.run):
    try:
        result=run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.free','--format=csv,noheader,nounits'],
                   capture_output=True,text=True,timeout=10)
        if result.returncode:return None
        name,driver,total,free=[part.strip() for part in result.stdout.splitlines()[0].split(',')]
        return {'name':name,'driver':driver,'vram_total_mb':int(total),'vram_free_mb':int(free)}
    except (OSError,subprocess.SubprocessError,ValueError,IndexError):return None


def free_vram_mb():
    gpu=nvidia_gpu()
    return gpu['vram_free_mb'] if gpu else 0


def whisper_cuda_ready():
    """CTranslate2 sees a CUDA device and the cuBLAS 12 runtime it needs can be loaded."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count()<1:return False,'CTranslate2 no detecta una GPU CUDA.'
    except Exception:return False,'Falta CTranslate2 con soporte CUDA.'
    if os.name=='nt':
        enable_cuda_libraries()
        try:ctypes.WinDLL('cublas64_12.dll')
        except OSError:return False,'Falta la biblioteca cuBLAS 12 de NVIDIA en el entorno de la app.'
    return True,'CUDA listo para la transcripción.'


def read_settings():
    try:saved=json.loads(SETTINGS.read_text(encoding='utf-8'))
    except (OSError,ValueError):saved={}
    return {stage:(saved.get(stage) if saved.get(stage) in MODES else 'auto') for stage in STAGES}


def save_settings(values):
    current=read_settings()
    current.update({stage:mode for stage,mode in values.items() if stage in STAGES and mode in MODES})
    SETTINGS.parent.mkdir(parents=True,exist_ok=True)
    SETTINGS.write_text(json.dumps(current),encoding='utf-8')
    return current


def detect(refresh=False):
    global _cache
    with _lock:
        if _cache is None or refresh:
            ready,reason=whisper_cuda_ready()
            _cache={'cpu':{'name':platform.processor() or platform.machine(),'threads':os.cpu_count() or 1},
                    'ram':memory(),'gpu':nvidia_gpu(),'whisper_cuda':ready,'whisper_cuda_reason':reason}
        return dict(_cache)


def transcription_threads():
    # Measured on a Ryzen 7 5700X: 8 threads beat 4 (34.7 s vs 37.5 s per 120 s) and leave the rest of the PC responsive.
    return max(1,min(8,(os.cpu_count() or 2)//2))


def transcription_plan():
    """Return (device, reason). GPU only when CUDA works and there is enough free VRAM right now."""
    mode=read_settings()['transcription'];info=detect()
    if mode=='cpu':return 'cpu','Elegiste CPU para la transcripción.'
    if not info['whisper_cuda']:return 'cpu',info['whisper_cuda_reason']
    free=free_vram_mb()
    if free<MIN_FREE_VRAM_MB:
        return 'cpu',f'Solo hay {free} MB libres en la GPU; se usa CPU para no saturarla.'
    return 'cuda','Transcripción en GPU (CUDA).'


def summary():
    from app import nvenc_available
    import gpu_ai
    info=detect();settings=read_settings();device,reason=transcription_plan();ai=gpu_ai.status()
    export_gpu=nvenc_available()
    return {**info,'ram':memory(),'gpu':nvidia_gpu() or info['gpu'],'settings':settings,
            'stages':{'transcription':{'device':'GPU' if device=='cuda' else 'CPU','reason':reason},
                      'ai':{'device':'GPU' if ai['gpu_loaded'] else ('GPU (se carga al analizar)' if ai['model_ready'] else 'No disponible'),'reason':ai['message']},
                      'export':{'device':'GPU (NVENC)' if export_gpu else 'CPU','reason':'Exportación con NVENC.' if export_gpu else ('Elegiste CPU para exportar.' if settings['export']=='cpu' else 'NVENC no está disponible; se usa CPU.')}}}
