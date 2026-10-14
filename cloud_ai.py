"""Opt-in cloud analysis of text only. Credentials remain in process memory."""
import os,json,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
import httpx

MODEL='gpt-4.1-mini'
_session_key=None

class AnalysisCancelled(Exception):pass

def key():
    return _session_key if _session_key is not None else os.getenv('CLIP_AI_KEY') or os.getenv('OPENAI_API_KEY') or ''

def configure(value):
    global _session_key
    _session_key=value.strip()

def configured():return bool(key())

def check_connection(value=None,transport=None):
    token=value if value is not None else key()
    if not token:raise ValueError('Conecta tu clave de API en Configurar IA. No necesitas enviarla por el chat.')
    with httpx.Client(timeout=15,transport=transport) as client:
        response=client.get(f'https://api.openai.com/v1/models/{MODEL}',headers={'Authorization':f'Bearer {token}'})
    check_status(response)
    return True

def check_status(response):
    if response.is_success:return
    messages={401:'La clave de API no es válida. Revisa la conexión.',403:'El proveedor o la red bloquea el acceso a la API.',429:'La API indica falta de saldo o un límite de uso. Revisa facturación y límites.',500:'El proveedor de IA tuvo un error temporal.',503:'El proveedor de IA no está disponible temporalmente.'}
    raise ValueError(messages.get(response.status_code,f'La API no pudo completar la solicitud (HTTP {response.status_code}).'))

def complete(payload,transport=None,cancel=None):
    from intelligence import SYSTEM
    if cancel and cancel.is_set():raise AnalysisCancelled()
    token=key()
    if not token:raise ValueError('Falta conectar la clave de API.')
    # Only transcript/context go to the API. No file paths, video bytes or credentials enter the prompt.
    body={'model':MODEL,'messages':[{'role':'system','content':SYSTEM+' Usa exclusivamente IDs de frases existentes. Respeta los segundos mínimo/máximo. Cada propuesta debe incluir first, last, category, hook, payoff, novelty, emotion, discussion, coherent, reason, evidence y titles. Devuelve {"moments": [...]} con hasta 4 propuestas; para relleno devuelve {"moments": []}. Escribe títulos específicos con el tema concreto.'},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],'response_format':{'type':'json_object'},'temperature':.2,'max_tokens':1500}
    try:
        with httpx.Client(timeout=httpx.Timeout(90,connect=10),transport=transport) as client:
            response=client.post('https://api.openai.com/v1/chat/completions',headers={'Authorization':f'Bearer {token}'},json=body)
        check_status(response)
        if cancel and cancel.is_set():raise AnalysisCancelled()
        choice=response.json()['choices'][0]
        if choice.get('finish_reason')!='stop':raise ValueError('La IA no completó la respuesta. Intenta otra vez.')
        return json.loads(choice['message']['content'])
    except httpx.TimeoutException:raise ValueError('La solicitud de IA superó 90 segundos. No se continuará esperando indefinidamente.') from None
    except httpx.HTTPError:raise ValueError('No se pudo conectar con la API. Revisa Internet y vuelve a intentarlo.') from None

def select_cloud(transcript,minimum,maximum,duration,speaker='',context='',profile='',max_clips=10,on_progress=None,cancel=None,transport=None):
    from timeline import timed_sentences
    from intelligence import accept_proposals,diverse_selection,Proposals
    phrases=timed_sentences(transcript)
    if not phrases:return []
    window=max(360,maximum+30);step=window-maximum
    chunks=[]
    for offset in range(0,int(duration)+1,step):
        chunk=[p for p in phrases if p['start']>=offset and p['end']<=offset+window]
        if chunk and chunk[-1]['end']-chunk[0]['start']>=minimum:chunks.append(chunk)
    candidates=[];completed=0
    def analyze_chunk(chunk):
        payload={'rango_segundos':[minimum,maximum],'hablante_identificado':speaker,'contexto_del_video':context,'criterios_del_editor':profile,'frases':[dict(id=i,**p) for i,p in enumerate(chunk)],'instruccion':'Selecciona historias completas y excepcionales. Usa first/last inclusivos. Recorta logística al inicio/final. No copies frases como títulos ni inventes hechos. Puede haber cero resultados.'}
        # No overlapping candidate transcripts: every source phrase is serialized once per block.
        data=complete(payload,transport=transport,cancel=cancel)
        # The cloud path allows up to four proposals, then applies the same grounded filters.
        if not isinstance(data.get('moments'),list):raise ValueError('La IA devolvió una respuesta editorial inválida.')
        result=[]
        for moment in data['moments'][:4]:
            try:result.extend(accept_proposals({'moments':[moment]},chunk,transcript,minimum,maximum,speaker))
            except (ValueError,TypeError):continue
        for clip in result:clip['source']=f'{MODEL} · análisis de transcripción'
        return result
    executor=ThreadPoolExecutor(max_workers=3)
    futures=[]
    try:
        futures=[executor.submit(analyze_chunk,chunk) for chunk in chunks]
        pending=set(futures)
        while pending:
            if cancel and cancel.is_set():raise AnalysisCancelled()
            from concurrent.futures import wait,FIRST_COMPLETED
            done,pending=wait(pending,timeout=.5,return_when=FIRST_COMPLETED)
            for future in done:
                candidates.extend(future.result());completed+=1
                if on_progress:on_progress(completed,len(chunks),'cloud')
    finally:
        for future in futures:future.cancel()
        executor.shutdown(wait=False,cancel_futures=True)
    return diverse_selection(candidates,duration,minimum,maximum,max_clips)
