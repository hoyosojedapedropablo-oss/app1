"""Local Ollama GPU analysis; fixed loopback endpoint, never sends text to a cloud API."""
import json,subprocess
import httpx
from cloud_ai import AnalysisCancelled

BASE='http://127.0.0.1:11434'
MODEL='qwen2.5:7b'

def client(transport=None,timeout=20):
    return httpx.Client(base_url=BASE,transport=transport,timeout=httpx.Timeout(timeout,connect=3),trust_env=False)

def status(transport=None):
    result={'available':False,'model_ready':False,'gpu_loaded':False,'model':MODEL,'version':None,'gpu_bytes':0,'message':'Ollama no está disponible. Ejecuta INSTALAR_GPU_WINDOWS.'}
    try:
        with client(transport) as conn:
            version=conn.get('/api/version');version.raise_for_status()
            tags=conn.get('/api/tags');tags.raise_for_status()
            loaded=conn.get('/api/ps');loaded.raise_for_status()
        result.update(available=True,version=version.json().get('version'),model_ready=any(m.get('name',m.get('model'))==MODEL for m in tags.json().get('models',[])))
        resident=next((m for m in loaded.json().get('models',[]) if m.get('name',m.get('model'))==MODEL),{})
        result['gpu_bytes']=int(resident.get('size_vram') or 0)
        result['gpu_loaded']=result['gpu_bytes']>0
        result['message']='GPU activa: modelo cargado en memoria de video.' if result['gpu_loaded'] else 'Motor disponible. Pulsa Comprobar GPU para cargar el modelo y verificar aceleración.'
        if not result['model_ready']:result['message']='Falta el modelo local. Ejecuta INSTALAR_GPU_WINDOWS para descargarlo.'
    except (httpx.HTTPError,ValueError,KeyError):pass
    return result

def warmup(transport=None):
    info=status(transport)
    if not info['available'] or not info['model_ready']:raise ValueError(info['message'])
    try:
        with client(transport,timeout=120) as conn:
            response=conn.post('/api/chat',json={'model':MODEL,'messages':[{'role':'user','content':'Responde OK.'}],'stream':False,'keep_alive':'10m','options':{'num_ctx':8192,'num_predict':8,'temperature':0}})
            response.raise_for_status()
    except httpx.HTTPError:raise ValueError('No se pudo cargar el modelo en Ollama. Revisa su ventana, memoria de GPU y el driver NVIDIA.') from None
    info=status(transport)
    if not info['gpu_loaded']:raise ValueError('Ollama cargó el modelo sin memoria GPU. No iniciaré el análisis lento en CPU. Actualiza el driver NVIDIA y Ollama, cierra otros programas que usen VRAM y comprueba de nuevo.')
    return info

def unload(transport=None):
    with client(transport,timeout=30) as conn:
        response=conn.post('/api/generate',json={'model':MODEL,'keep_alive':0})
        response.raise_for_status()

def complete(payload,transport=None,cancel=None):
    from intelligence import SYSTEM,Proposals
    if cancel and cancel.is_set():raise AnalysisCancelled()
    schema=Proposals.model_json_schema()
    count=len(payload.get('frases',[]))
    if count:
        for name in ['first','last']:schema['$defs']['Moment']['properties'][name].update(minimum=0,maximum=count-1)
    body={'model':MODEL,'messages':[{'role':'system','content':SYSTEM+' En este modo first y last son IDs inclusivos de frases. Respeta el rango. Devuelve {"moments": [...]} con hasta tres propuestas; cada una incluye first,last,category,hook,payoff,novelty,emotion,discussion,coherent,reason,evidence,titles. reason y evidence deben ser breves. No copies la transcripción como título.'},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],'format':schema,'stream':True,'keep_alive':'10m','options':{'num_ctx':8192,'num_predict':1500,'temperature':.2}}
    try:
        parts=[];data={}
        with client(transport,timeout=180) as conn:
            with conn.stream('POST','/api/chat',json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if cancel and cancel.is_set():raise AnalysisCancelled()
                    if not line:continue
                    data=json.loads(line)
                    if data.get('error'):raise ValueError('Ollama no completó la inferencia. Revisa memoria GPU y su ventana de errores.')
                    parts.append(data.get('message',{}).get('content',''))
        if not data.get('done'):raise ValueError('Ollama interrumpió la respuesta antes de terminar.')
        if cancel and cancel.is_set():raise AnalysisCancelled()
        if data.get('done_reason')=='length':raise ValueError('El modelo local agotó el límite de respuesta. Prueba un contexto más breve.')
        return json.loads(''.join(parts))
    except httpx.TimeoutException:raise ValueError('La inferencia local superó el tiempo de espera. Comprueba que la GPU siga activa en Ollama.') from None
    except httpx.HTTPError:raise ValueError('Se perdió la conexión con Ollama. Ábrelo y comprueba la GPU.') from None

def select_gpu(transcript,minimum,maximum,duration,**kwargs):
    from cloud_ai import select_cloud
    result=select_cloud(transcript,minimum,maximum,duration,completion=complete,workers=1,stage='gpu',**kwargs)
    for clip in result:clip['source']=f'{MODEL} · local GPU'
    return result
