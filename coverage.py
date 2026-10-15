"""Fixed source coverage, independent of editorial score or requested clip count."""
import math,re
from pydantic import BaseModel,Field
from intelligence import clean_title
from timeline import clip_words,make_cues,timed_sentences,words_from_transcript
from editorial import TITLE_GUIDE,clip_identity

TARGET=.75
class ClipTitles(BaseModel):
 id:str
 titles:list[str]=Field(min_length=1,max_length=3)
class TitleBatch(BaseModel):
 clips:list[ClipTitles]=Field(max_length=6)

def covered(clips):
 total=0;end=0
 for c in sorted(clips,key=lambda c:c['start']):
  total+=max(0,c['end']-max(end,c['start']));end=max(end,c['end'])
 return total

def topic_windows(transcript,duration,minimum,maximum,topics):
 phrases=timed_sentences(transcript)
 boundaries=[0.,duration]
 if topics:
  boundaries += [t['start'] for t in topics if t.get('boundary',True) and 0<t['start']<duration]
 else:
  for i,p in enumerate(phrases):
   if i and (p['start']-phrases[i-1]['end']>3 or re.match(r'(?i)^(cambiando de tema|por otro lado|ahora hablemos|otra pregunta|pasando a otro)',p['text'])):boundaries.append(p['start'])
 boundaries=sorted(set(boundaries));words=words_from_transcript(transcript)
 # Natural sentence ends only; never close a clip at a question before its answer.
 ends=[w['end'] for w in words if re.search(r'[.!…]$',w['text'])]
 windows=[]
 for a,b in zip(boundaries,boundaries[1:]):
  if b-a<minimum-1e-6:continue
  # Topic end itself is an editorial boundary even if ASR omitted punctuation.
  natural=sorted(set([x for x in ends if a<x<b]+[b]))
  cursor=a
  while b-cursor>=minimum-1e-6:
   choices=[x for x in natural if minimum-1e-6<=x-cursor<=maximum+1e-6 and (b-x<1e-6 or b-x>=minimum-1e-6)]
   if not choices:
    # Try a complete shorter answer even if a short remainder must be left for review.
    choices=[x for x in natural if minimum-1e-6<=x-cursor<=maximum+1e-6]
   if not choices:break
   end=max(choices);label=next((t.get('label','') for t in (topics or []) if t['start']<=cursor+.5<t['end']),'')
   windows.append((cursor,end,label));cursor=end
 return windows,boundaries

def plan(selected,transcript,duration,minimum,maximum,topics=None):
 if duration<minimum:
  raise ValueError('El video es más corto que la duración mínima. Reduce el mínimo para poder generar clips.')
 if transcript:
  windows,boundaries=topic_windows(transcript,duration,minimum,maximum,topics)
  result=[dict(c,potential=c.get('score',0)>=75) for c in selected if not any(c['start']+.1<cut<c['end']-.1 for cut in boundaries[1:-1]) and not c.get('text','').rstrip().endswith('?')]
  windows.sort(key=lambda w:abs((w[0]+w[1])/2-duration/2))
  while windows and covered(result)<duration*TARGET-1e-6:
   start,end,label=windows.pop(0)
   if covered(result+[dict(start=start,end=end)])<=covered(result)+1e-6:continue
   text=' '.join(w['text'] for w in clip_words(transcript,start,end))
   result.append(dict(id=clip_identity(start,end,text),start=start,end=end,duration=end-start,text=text,title='',titles=[],score=None,category='Para revisar',potential=False,reason='Tema: '+label if label else 'Conversación agrupada por tema; revisa antes de publicar.',topic=label,evidence='',captions=make_cues(transcript,start,end),source='Cobertura por temas'))
  return sorted(result,key=lambda c:c['start'])
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
  result.append(dict(id=clip_identity(start,end,text),start=start,end=end,duration=end-start,text=text,title='',titles=[],score=None,category='Para revisar',potential=False,reason='Incluido para cubrir el video. Tú decides si publicarlo.',evidence='',captions=make_cues(transcript,start,end),source='Cobertura 75%'))
 return sorted(result,key=lambda c:c['start'])

def complete_coverage(selected,transcript,duration,minimum,maximum,completion,speaker='',context='',profile='',cancel=None,on_progress=None,topics=None):
 from cloud_ai import AnalysisCancelled
 clips=plan(selected,transcript,duration,minimum,maximum,topics=topics)
 missing=[c for c in clips if not c['title']]
 offset=0
 while offset<len(missing):
  if cancel and cancel.is_set():raise AnalysisCancelled()
  batch=[];chars=0
  for clip in missing[offset:offset+6]:
   if batch and chars+len(clip['text'])>10000:break
   batch.append(clip);chars+=len(clip['text'])
  payload=dict(task='coverage_titles',hablante_identificado=speaker,contexto_del_video=context,criterios_del_editor=profile,clips=[dict(id=c['id'],text=c['text']) for c in batch],instruccion=TITLE_GUIDE+' Genera UN título principal para CADA clip, sin descartar ninguno. Lee desde el inicio hasta el final para elegir el tema más atractivo. No copies el audio ni inventes hechos. Para silencio describe la pausa con honestidad. Devuelve {"clips":[{"id":"...","titles":["..."]}]} respetando todos los IDs. Las alternativas se pedirán después en el editor.')
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
  offset+=len(batch)
  if on_progress:on_progress(offset,len(missing),'titles')
 return clips
