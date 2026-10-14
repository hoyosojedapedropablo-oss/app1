"""Shared, clip-relative caption timings for browser and FFmpeg."""
import re
from difflib import SequenceMatcher


def normalized(text):
    return re.sub(r'[^\wáéíóúñ]', '', text.lower())


def words_from_transcript(transcript):
    result = []
    for segment in transcript:
        words = segment.get('words') or []
        if words:
            for word in words:
                text = word.get('text', word.get('word', '')).strip()
                if text and word['end'] > word['start']:
                    result.append({'start':float(word['start']), 'end':float(word['end']), 'text':text})
        else:
            texts=segment['text'].split()
            span=max(0,segment['end']-segment['start'])
            for i,text in enumerate(texts):
                result.append(dict(text=text,start=segment['start']+span*i/len(texts),end=segment['start']+span*(i+1)/len(texts)))
    return sorted(result,key=lambda word:word['start'])


def clip_words(transcript,start,end):
    return [dict(text=w['text'],start=max(start,w['start'])-start,end=min(end,w['end'])-start)
            for w in words_from_transcript(transcript) if w['start']<end and w['end']>start]


def timed_sentences(transcript):
    """Split even long ASR segments; keep phrase boundaries in absolute source time."""
    phrases=[]; current=[]
    for word in words_from_transcript(transcript):
        if current and (word['start']-current[-1]['end']>.7 or word['end']-current[0]['start']>8):
            phrases.append(dict(start=current[0]['start'],end=current[-1]['end'],text=' '.join(w['text'] for w in current)))
            current=[]
        current.append(word)
        if re.search(r'[.!?]$',word['text']) and word['end']-current[0]['start']>=1:
            phrases.append(dict(start=current[0]['start'],end=current[-1]['end'],text=' '.join(w['text'] for w in current)))
            current=[]
    if current: phrases.append(dict(start=current[0]['start'],end=current[-1]['end'],text=' '.join(w['text'] for w in current)))
    return phrases


def align_edits(original,text,duration):
    edited=text.split()
    if not edited:return []
    if not original:
        return [dict(text=w,start=i*duration/len(edited),end=(i+1)*duration/len(edited)) for i,w in enumerate(edited)]
    result=[]
    matcher=SequenceMatcher(None,[normalized(w['text']) for w in original],[normalized(w) for w in edited],autojunk=False)
    for tag,a,b,c,d in matcher.get_opcodes():
        if tag=='equal':
            result.extend(dict(original[a+i],text=edited[c+i]) for i in range(d-c))
        elif tag in ('replace','insert'):
            left=original[a]['start'] if a<len(original) else original[-1]['end']
            right=original[b-1]['end'] if b>a else (original[a]['start'] if a<len(original) else duration)
            if right<=left:
                left=original[a-1]['end'] if a else 0
                right=original[a]['start'] if a<len(original) else duration
            for i,w in enumerate(edited[c:d]):
                result.append(dict(text=w,start=left+(right-left)*i/(d-c),end=left+(right-left)*(i+1)/(d-c)))
    return [w for w in result if w['end']>w['start']]


def make_cues(transcript,start,end,text=None):
    words=clip_words(transcript,start,end)
    if text is not None: words=align_edits(words,text,end-start)
    cues=[]; current=[]
    def flush():
        if current:
            cues.append(dict(start=round(current[0]['start'],3),end=round(min(end-start,current[-1]['end']+.08),3),text=' '.join(w['text'] for w in current)))
            current.clear()
    for word in words:
        word=dict(word,end=min(word['end'],word['start']+1.72))
        if current and (len(current)>=4 or len(' '.join(w['text'] for w in current)+' '+word['text'])>32 or word['end']-current[0]['start']>1.8 or word['start']-current[-1]['end']>.5):
            flush()
        current.append(word)
    flush()
    for a,b in zip(cues,cues[1:]): a['end']=min(a['end'],b['start'])
    return [c for c in cues if c['end']>c['start']]
