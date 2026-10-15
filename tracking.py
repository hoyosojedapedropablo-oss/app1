"""Local face/mouth-motion + speech-presence reframing. No identity recognition."""
import hashlib,json,math,subprocess
import numpy as np

VERSION=1

def key(start,end):return hashlib.sha256(f'{VERSION}:{start:.6f}:{end:.6f}'.encode()).hexdigest()[:24]

def position(cx,cy,width,height):
 scale=max(1080/width,1920/height);w=round(width*scale);h=round(height*scale)
 x=50 if w==1080 else 100*(cx*scale-540)/(w-1080)
 y=50 if h==1920 else 100*(cy*scale-1920*.35)/(h-1920)
 return max(0,min(100,x)),max(0,min(100,y))

def analyze(source,start,end,progress):
 import cv2
 cv2.setNumThreads(2)
 from faster_whisper.vad import get_speech_timestamps,VadOptions
 duration=end-start
 # Decode only the selected clip, with FFmpeg (same seek/time basis as export).
 audio=subprocess.run(['ffmpeg','-v','error','-ss',str(start),'-t',str(duration),'-i',str(source),'-vn','-ac','1','-ar','16000','-f','f32le','-'],capture_output=True)
 speech=[]
 if audio.returncode==0 and audio.stdout:
  waveform=np.frombuffer(audio.stdout,dtype='<f4')
  speech=get_speech_timestamps(waveform,VadOptions(min_speech_duration_ms=120,min_silence_duration_ms=150))
  speech=[(s['start']/16000,s['end']/16000) for s in speech]
 cap=cv2.VideoCapture(str(source))
 if not cap.isOpened():raise ValueError('No se pudo abrir el video para seguir rostros.')
 width=cap.get(cv2.CAP_PROP_FRAME_WIDTH);height=cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
 cap.release()
 if not width or not height:raise ValueError('No se pudieron leer las dimensiones del video.')
 small_width=max(2,int(min(800,width)/2)*2);small_height=max(2,int(height*small_width/width/2)*2)
 ratio=small_width/width
 cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_alt2.xml')
 profiles=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_profileface.xml')
 if cascade.empty() or profiles.empty():raise ValueError('Falta el detector de rostros. Vuelve a iniciar INICIAR_WINDOWS.')
 frames=subprocess.Popen(['ffmpeg','-v','error','-threads','2','-ss',str(start),'-t',str(duration),'-i',str(source),'-an','-vf',f'fps=4,scale={small_width}:{small_height}', '-pix_fmt','gray','-f','rawvideo','-'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 tracks={};next_id=0;active=None;challenger=None;streak=0;points=[];face_frames=0;speaking_frames=0;changes=0
 current_x=current_y=50;has_position=False
 try:
  for index in range(math.ceil(duration*4)):
   t=index/4
   raw=frames.stdout.read(small_width*small_height)
   if len(raw)!=small_width*small_height:break
   gray=np.frombuffer(raw,dtype=np.uint8).reshape(small_height,small_width)
   faces=list(cascade.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=4,minSize=(28,28)))
   # Profiles are checked even when a frontal face exists (typical two-person podcasts).
   profile_faces=list(profiles.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=5,minSize=(28,28)))
   flipped=profiles.detectMultiScale(cv2.flip(gray,1),scaleFactor=1.1,minNeighbors=5,minSize=(28,28))
   profile_faces.extend((gray.shape[1]-x-w,y,w,h) for x,y,w,h in flipped)
   for box in profile_faces:
    x,y,w,h=box
    if not any(max(0,min(x+w,a+c)-max(x,a))*max(0,min(y+h,b+d)-max(y,b)) / max(1,min(w*h,c*d))>.4 for a,b,c,d in faces):faces.append(box)
   speaking=any(a<=t<=b for a,b in speech)
   visible={};used=set()
   for x,y,w,h in sorted(faces,key=lambda f:f[2]*f[3],reverse=True):
    center=np.array([x+w/2,y+h/2])
    # Greedy one-to-one association; never compare motion from different faces.
    candidates=[(float(np.linalg.norm(center-tr['center'])),ident) for ident,tr in tracks.items() if ident not in used and t-tr['time']<=1 and np.linalg.norm(center-tr['center'])<max(w,tr['width'])*.9]
    ident=min(candidates)[1] if candidates else next_id
    if not candidates:next_id+=1
    used.add(ident)
    patch=cv2.resize(gray[y:y+h,x:x+w],(64,64)).astype(np.float32)
    patch=(patch-patch.mean())/(patch.std()+10)
    old=tracks.get(ident);activity=0
    if old is not None:
     diff=np.abs(patch-old['patch']);mouth=float(diff[39:58,12:52].mean());upper=float(diff[10:30,12:52].mean())
     activity=max(0,mouth-upper*.8)
    activity=.55*activity+.45*(old['activity'] if old else 0)
    visible[ident]=dict(center=center,width=w,time=t,patch=patch,activity=activity,area=w*h,x=x,y=y,h=h)
   tracks={ident:tr for ident,tr in tracks.items() if t-tr['time']<=1};tracks.update(visible)
   if visible:
    face_frames+=1
    if active not in visible and not(active in tracks and t-tracks[active]['time']<.75):
     active=max(visible,key=lambda ident:visible[ident]['area']);challenger=None;streak=0
    if speaking and active in visible:
     speaking_frames+=1
     best=max(visible,key=lambda ident:visible[ident]['activity'])
     # A stable lead is required to avoid cutting on every small facial motion.
     if best!=active and visible[best]['activity']>.08 and visible[best]['activity']>visible[active]['activity']*1.3+.025:
      streak=streak+1 if challenger==best else 1;challenger=best
      if streak>=2:active=best;changes+=1;challenger=None;streak=0
     else:challenger=None;streak=0
    if active in visible:
     face=visible[active];target_x,target_y=position(face['center'][0]/ratio,face['center'][1]*height/small_height,width,height)
     if not has_position:current_x,current_y=target_x,target_y;has_position=True
     else:
      current_x+=max(-20,min(20,(target_x-current_x)*.55));current_y+=max(-12,min(12,(target_y-current_y)*.55))
   points.append(dict(time=round(t,3),x=round(current_x,3),y=round(current_y,3)))
   if index%4==0:progress(round(100*t/duration))
 finally:
  frames.stdout.close()
  if frames.poll() is None:frames.terminate()
  try:frames.wait(timeout=5)
  except subprocess.TimeoutExpired:frames.kill();frames.wait()
 if not face_frames:raise ValueError('No se detectaron rostros en este clip. Usa el encuadre manual; prueba un fragmento donde se vean las caras.')
 # If the first face appears late, use its first confident framing from the start.
 first=next((p for p in points if p['x']!=50 or p['y']!=50),None)
 if first:
  for p in points:
   if p['time']>=first['time']:break
   p['x'],p['y']=first['x'],first['y']
 return dict(points=points,width=width,height=height,face_frames=face_frames,speaking_frames=speaking_frames,speaker_changes=changes,method='Rostros, movimiento de boca y detección de voz. Estimación visual; revisa los cambios de hablante.')

def commands(result,path,duration):
 points=result['points'];scale=max(1080/result['width'],1920/result['height'])
 extra_x=max(0,round(result['width']*scale)-1080);extra_y=max(0,round(result['height']*scale)-1920)
 lines=[]
 times=np.array([p['time'] for p in points]);xs=np.array([p['x'] for p in points]);ys=np.array([p['y'] for p in points])
 for t in np.arange(0,duration,1/12):
  x=round(float(np.interp(t,times,xs))*extra_x/100);y=round(float(np.interp(t,times,ys))*extra_y/100)
  lines.append(f'{t:.6f} crop@follow x {x}, crop@follow y {y};')
 path.write_text('\n'.join(lines),encoding='utf-8')
 return f'setpts=PTS-STARTPTS,sendcmd=f={path.name},scale=1080:1920:force_original_aspect_ratio=increase,crop@follow=1080:1920:0:0'
