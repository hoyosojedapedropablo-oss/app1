"""Shared editorial guidance and per-video validated inference cache."""
import hashlib,json

VERSION='topics-human-titles-v1'
TITLE_GUIDE='''Escribe para una persona que está deslizando TikTok, no para un noticiero. Lee TODO el clip: el tema más atractivo puede estar al final. Identifica qué le importa al espectador, la contradicción, duda, pregunta concreta o consecuencia humana. No empieces siempre con «X explica/revela/aclara». Puedes omitir el nombre si una situación compartida conecta mejor. Crea curiosidad específica sobre el tema real; no lo escondas tras «esto» ni prometas algo que no sucede. Una pregunta relevante o una frase coloquial con tensión pueden enganchar más que un resumen formal. Ejemplos de estilo, solo si el clip los respalda: «¿Dónde está el límite cuando trabajas con tu pareja?», «Así era su vida antes de caer preso», «Westcol ya se puso la vara más alta con su boxeo». No inventes conflictos, emociones ni delitos; atribuye opiniones como opiniones. Evita «no creerás», «te sorprenderá», frases de presentador y copiar literalmente el audio. Hasta 80 caracteres y 14 palabras. El título debe reflejar UN tema principal presente en el clip, aunque aparezca al final.'''

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
