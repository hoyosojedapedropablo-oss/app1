"""Shared editorial guidance and per-video validated inference cache."""
import hashlib,json

VERSION='topics-human-titles-v4'   # v2 (E-22): no example titles to copy; v3 (E-23): key phrase, real tone
TITLE_GUIDE='''Escribe para una persona que está deslizando TikTok, no para un noticiero. Lee TODO el clip: el tema más atractivo puede estar al final. Identifica qué le importa al espectador, la contradicción, duda, pregunta concreta o consecuencia humana. No empieces siempre con «X explica/revela/aclara». Puedes omitir el nombre si una situación compartida conecta mejor. Crea curiosidad específica sobre el tema real; no lo escondas tras «esto» ni prometas algo que no sucede. Una pregunta relevante o una frase coloquial con tensión pueden enganchar más que un resumen formal. Formas que funcionan (escribe las tuyas con el tema de ESTE clip, nunca copies una forma): una pregunta sobre la duda concreta del clip; «Así era…» o «Así fue…» con el hecho que se cuenta; el nombre de quien habla con lo que hace y un detalle. No inventes conflictos, emociones ni delitos; atribuye opiniones como opiniones. Respeta el tono real: una broma no es una crítica, un accidente no es una pelea y un comentario no es una polémica. No preguntes por un desenlace que el clip ya muestra («¿lo lograrán?» si lo logran) ni prometas una competencia que no hay. Escribe en español: mayúscula solo al inicio y en nombres propios, sin puntos suspensivos, y habla solo de lo que pasa en ESTE clip. Evita «no creerás», «te sorprenderá», frases de presentador y copiar literalmente el audio. Hasta 80 caracteres y 14 palabras. El título debe reflejar UN tema principal presente en el clip, aunque aparezca al final.'''

def clip_identity(start,end,text):
 return hashlib.sha256(json.dumps([round(start,6),round(end,6),' '.join(text.split())],ensure_ascii=False).encode()).hexdigest()[:24]

def cached_completion(folder,engine,completion,on_hit=None):
 from coverage import TitleBatch
 from intelligence import Proposals
 folder.mkdir(exist_ok=True)
 def complete(payload,**kwargs):
  cancel=kwargs.get('cancel')
  if cancel and cancel.is_set():
   from cloud_ai import AnalysisCancelled
   raise AnalysisCancelled()
  schema=TitleBatch if payload.get('task')=='coverage_titles' else Proposals
  digest=hashlib.sha256(json.dumps([VERSION,engine,payload],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
  path=folder/f'{digest}.json'
  if path.exists():
   try:
    result=json.loads(path.read_text(encoding='utf-8'));schema.model_validate(result)
    if on_hit:on_hit()
    return result
   except (ValueError,OSError):pass
  result=completion(payload,**kwargs)
  schema.model_validate(result)
  tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');tmp.replace(path)
  return result
 return complete
