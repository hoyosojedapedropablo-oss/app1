"""Fixed source coverage, independent of editorial score or requested clip count."""
import math,uuid
from pydantic import BaseModel,Field
from intelligence import clean_title
from timeline import clip_words,make_cues

TARGET=.75
class ClipTitles(BaseModel):
 id:str
 titles:list[str]=Field(min_length=1,max_length=3)
class TitleBatch(BaseModel):
 clips:list[ClipTitles]=Field(max_length=3)

def covered(clips):
 total=0;end=0
 for c in sorted(clips,key=lambda c:c['start']):
  total+=max(0,c['end']-max(end,c['start']));end=max(end,c['end'])
 return total

def plan(selected,transcript,duration,minimum,maximum):
 if duration<minimum:
  raise ValueError('El video es más corto que la duración mínima. Reduce el mínimo para poder generar clips.')
 result=[dict(c,potential=c.get('score',0)>=75) for c in selected]
 n=math.ceil(duration/maximum)
 # Equal tiles prevent a final fragment shorter than the minimum where feasible.
 if duration/n>=minimum:
  windows=[(i*duration/n,(i+1)*duration/n) for i in range(n)]
 else:
  windows=[(min(i*maximum,duration-minimum),min((i+1)*maximum,duration)) for i in range(n)]
 # Spread review clips across the source, rather than always choosing its beginning.
 windows.sort(key=lambda w:abs((w[0]+w[1])/2-duration/2))
 while covered(result)<duration*TARGET-1e-6:
  if not windows:raise ValueError('No se pudo completar la cobertura del video.')
  start,end=windows.pop(0)
  if covered(result+[dict(start=start,end=end)])<=covered(result)+1e-6:continue
  text=' '.join(w['text'] for w in clip_words(transcript,start,end))
  result.append(dict(id=uuid.uuid4().hex,start=start,end=end,duration=end-start,text=text,title='',titles=[],score=None,category='Para revisar',potential=False,reason='Incluido para cubrir el video. Tú decides si publicarlo.',evidence='',captions=make_cues(transcript,start,end),source='Cobertura 75%'))
 return sorted(result,key=lambda c:c['start'])

def complete_coverage(selected,transcript,duration,minimum,maximum,completion,speaker='',context='',profile='',cancel=None,on_progress=None):
 from cloud_ai import AnalysisCancelled
 clips=plan(selected,transcript,duration,minimum,maximum)
 missing=[c for c in clips if not c['title']]
 for offset in range(0,len(missing),3):
  if cancel and cancel.is_set():raise AnalysisCancelled()
  batch=missing[offset:offset+3]
  payload=dict(task='coverage_titles',hablante_identificado=speaker,contexto_del_video=context,criterios_del_editor=profile,clips=[dict(id=c['id'],text=c['text']) for c in batch],instruccion='Cuenta lo que sucede con sujeto + acción + detalle o contraste. Ejemplos respaldados por el audio: «Cuenta cómo delinquía antes de terminar en prisión» o «Westcol promete que su boxeo superará a todos». Dale fuerza al tono, sin exagerar los hechos, inventar identidades ni convertir opiniones en certezas. Evita preguntas genéricas. Escribe títulos editoriales creativos y específicos para CADA clip, aunque sea cotidiano. Hasta 3 opciones, máximo 80 caracteres y 14 palabras. No copies el audio ni inventes hechos. No evalúes ni descartes clips. Para silencio describe honestamente la pausa, sin inventar diálogo. Devuelve {"clips":[{"id":"...","titles":["..."]}]} respetando todos los IDs.')
  pending={c['id']:c for c in batch}
  for attempt in range(2):
   if cancel and cancel.is_set():raise AnalysisCancelled()
   data=TitleBatch.model_validate(completion(payload,cancel=cancel))
   for item in data.clips:
    if item.id not in pending:continue
    clip=pending[item.id];titles=list(dict.fromkeys(t for t in (clean_title(t,clip['text']) for t in item.titles) if t))
    if titles:clip.update(title=titles[0],titles=titles);pending.pop(item.id)
   if not pending:break
   payload['clips']=[dict(id=c['id'],text=c['text']) for c in pending.values()]
   payload['correccion']='Faltan títulos válidos para estos IDs. No copies el audio; respeta longitud.'
  if pending:raise ValueError('La IA no generó títulos válidos para todos los clips. La transcripción se conserva para reintentar.')
  if on_progress:on_progress(min(offset+3,len(missing)),len(missing),'titles')
 return clips
