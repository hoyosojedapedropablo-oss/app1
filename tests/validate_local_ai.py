"""Opt-in editorial checks with real local inference on synthetic transcripts."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from intelligence import select_clips

SAMPLES={
 'filler':[
  dict(start=0,end=10,text='Voy a abrir el juego. Esperen un segundo mientras carga la pantalla.'),
  dict(start=10,end=20,text='A ver dónde dejé el cable. Voy a conectar el micrófono y ajustar el volumen.'),
  dict(start=20,end=30,text='Ya está conectado. Ahora abro el menú y espero a que los demás entren.'),
  dict(start=30,end=40,text='No pasa nada. Todavía están entrando. Mientras tanto, voy a revisar la configuración.')],
 'health':[
  dict(start=0,end=6,text='Antes pensaba que los creadores tenían que hacer directos todos los días.'),
  dict(start=6,end=13,text='Pero llegó un punto en que dormía cuatro horas y ni siquiera disfrutaba el stream.'),
  dict(start=13,end=21,text='Por eso ahora prefiero hacer tres directos buenos a siete por obligación. Gané menos dinero, pero recuperé mi salud.'),
  dict(start=21,end=28,text='La gente cree que descansar es ser flojo, cuando seguir así era lo que me estaba destruyendo.'),
  dict(start=28,end=35,text='Bueno, voy a abrir el juego. A ver si me deja entrar. Un segundo, está cargando.')]
}

if __name__=='__main__':
 for label,transcript in SAMPLES.items():
  clips=select_clips(transcript,20,60,transcript[-1]['end'],speaker='Westcol',context='Opinión sobre reducir directos para cuidar la salud.' if label=='health' else 'Configuración rutinaria del stream.',quality='quality')
  if label=='filler':assert not clips,'No debe recomendar conversación rutinaria.'
  else:
   assert clips,'Debe reconocer la historia sobre salud y directos.'
   assert all(20<=c['end']-c['start']<=60 for c in clips)
   assert all(len(c['title'])<=80 and len(c['title'].split())<=14 for c in clips)
   assert all('salud' in c['title'].lower() or 'directos' in c['title'].lower() for c in clips)
  print(label,json.dumps([dict(start=c['start'],end=c['end'],title=c['title']) for c in clips],ensure_ascii=False),flush=True)
