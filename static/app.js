const $=id=>document.getElementById(id);
let titleImageSignature='',titleImageURL=null,titleImageVersion=0,titleImageTimer;

let overlayInfo=null,overlayWatch=0,stackPath=null,stackKey='';
let trackingPoints=[],trackingRange=null,trackingRequest=0;
let job=null,selected=null,cues=[],cueVersion=0,captionPending=false,captionTimer,pollToken=0;
const edits=new Map();
const numeric=['title_padding_x','title_padding_y','title_size','title_outline_width','title_x','title_y','caption_x','caption_y','caption_size','outline_width','focus_x','focus_y','start','end','logo_width','logo_x','logo_y','logo_start','logo_end','resolution'];
const styleKeys=['game_follow','resolution','zoom','tracking_person','tracking_motion','show_subtitles','title_corners','title_padding_x','title_padding_y','title_bg_color','title_text_color','auto_follow','style','font','title_font','title_outline_color','title_size','title_outline_width','title_x','title_y','caption_x','caption_y','caption_size','caption_color','outline_color','outline_width','logo','framing','focus_x','focus_y','logo_width','logo_x','logo_y','logo_start','logo_end'];
const OFFLINE='ClipStudio no responde: su servidor está cerrado. Abre INICIAR_WINDOWS.bat, deja abierta esa ventana y recarga la página.';
async function request(url,options={}){let r;try{r=await fetch(url,options);}catch{const e=Error(OFFLINE);e.offline=true;throw e;}if(!r.ok){let e;try{e=await r.json()}catch{e={detail:r.statusText}}throw Error(typeof e.detail==='string'?e.detail:'Revisa los campos y el rango de tiempos.')}return r;}
const jsonOptions=value=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
function showView(name){$('analysisView').classList.toggle('hidden',name!=='analysis');$('editorView').classList.toggle('hidden',name!=='editor');$('goAnalyze').classList.toggle('active',name==='analysis');$('goEditor').classList.toggle('active',name==='editor');if(name==='editor')requestAnimationFrame(paint);}
$('goAnalyze').onclick=()=>showView('analysis');$('goEditor').onclick=()=>showView('editor');
for(const button of document.querySelectorAll('[data-tab]'))button.onclick=()=>{for(const b of document.querySelectorAll('[data-tab]')){b.classList.toggle('active',b===button);b.setAttribute('aria-selected',String(b===button));}for(const panel of document.querySelectorAll('.tab-panel'))panel.classList.toggle('hidden',panel.id!=='tab-'+button.dataset.tab);};
function say(text){$('status').textContent=text;}
const CHECKS=['auto_follow','show_subtitles','game_follow'];
function styles(){return Object.fromEntries(styleKeys.map(k=>[k,CHECKS.includes(k)?$(k).checked:k==='logo_end'&&!$(k).value?null:numeric.includes(k)?Number($(k).value):$(k).value]));}
function settings(){return {...styles(),title:$('title').value,subtitles:$('subtitles').value,start:Number($('start').value),end:Number($('end').value),clip_id:selected&&selected.id!=='manual'?selected.id:null,captions:cues.map(c=>({...c}))};}
function saveCurrent(){if(selected)edits.set(selected.id,settings());}
function validRange(opts){const duration=opts.end-opts.start;if(!Number.isFinite(duration)||duration<=0||opts.start<0||opts.end>job.duration)throw Error('El inicio y final deben estar dentro del video.');if(opts.clip_id&&job.analysis_range&&(duration<job.analysis_range.minimum-.001||duration>job.analysis_range.maximum+.001))throw Error(`El clip debe durar ${job.analysis_range.minimum}–${job.analysis_range.maximum} segundos.`);return duration;}
function paint(){
 $('focus_x').disabled=$('auto_follow').checked;$('focus_y').disabled=$('auto_follow').checked;
 const preview=$('preview');if(!preview.clientWidth)return;const ratio=preview.clientWidth/1080;if(job)$('sourceSummary').textContent=job.name;
 const title=$('previewTitle');title.style.top=$('title_y').value+'%';title.style.left=$('title_x').value+'%';title.style.right='auto';title.style.padding='0';title.style.background='transparent';title.style.lineHeight='0';title.style.maxWidth='none';
 refreshTitleImage(ratio);
 $('titlePalette').value=Array.from($('titlePalette').options).some(o=>o.value===$('title_bg_color').value.toUpperCase())?$('title_bg_color').value.toUpperCase():'';
 $('title_padding_x_value').textContent=$('title_padding_x').value+' px';$('title_padding_y_value').textContent=$('title_padding_y').value+' px';
 $('titleCount').textContent=`${$('title').value.length}/96 caracteres · recomendado: hasta 80 y 2 líneas`;
 const caption=$('previewCaption');caption.style.top=$('caption_y').value+'%';caption.style.left=$('caption_x').value+'%';caption.style.fontFamily=$('font').value;caption.style.fontSize=(Number($('caption_size').value)*ratio)+'px';caption.style.color=$('caption_color').value;caption.style.webkitTextStroke=(Number($('outline_width').value)*ratio)+'px '+$('outline_color').value;
 const framing=$('framing').value,band=framing==='zoom'?ZOOM[$('zoom').value]:1;$('zoomRow')?.classList.toggle('hidden',framing!=='zoom');
 $('video').style.objectFit=framing==='fit'?'contain':'cover';$('video').style.height=(band*100)+'%';$('video').style.top=((1-band)*50)+'%';
 $('video').style.objectPosition=`${$('focus_x').value}% ${$('focus_y').value}%`;
 paintLogo();
 if(job&&selected){const duration=Number($('end').value)-Number($('start').value);$('duration').textContent=`${duration.toFixed(1)} s · formato 9:16`;$('seek').max=Math.max(0,duration);}
 paintTime();
}
function paintTime(){
 const t=$('video').currentTime-Number($('start').value),duration=Number($('end').value)-Number($('start').value);
 applyTracking(t);drawStack(t);
 const editing=$('video').paused&&$('editLayers').checked&&selected;const active=cues.find(c=>t>=c.start&&t<c.end);$('previewCaption').textContent=$('show_subtitles').checked?(active?.text||(editing?cues[0]?.text||'Subtítulos de ejemplo':'')):'';
 $('previewTitle').hidden=!selected||!$('title').value||(!editing&&(t<0||t>=duration));
 $('seek').value=Math.max(0,t);$('clock').textContent=`${Math.max(0,t).toFixed(1)} / ${Math.max(0,duration).toFixed(1)} s`;
 const logoEnd=$('logo_end').value?Number($('logo_end').value):duration;$('previewLogo').hidden=!selected||$('logo').value==='none'||(!editing&&(t<Number($('logo_start').value)||t>=logoEnd));
 if(selected&&$('video').currentTime>=Number($('end').value)&&!$('video').paused){$('video').pause();$('play').textContent='▶ Reproducir clip';}
}
function paintLogo(){
 const img=$('previewLogo'),preview=$('preview');
 if($('logo').value!=='none'){
  const path=`/api/logos/${$('logo').value}/image`;
  if(img.getAttribute('src')!==path)img.src=path;
 }
 const desired=preview.clientWidth*Number($('logo_width').value)/100;const maxWidth=img.naturalHeight?preview.clientHeight*.75*img.naturalWidth/img.naturalHeight:desired;img.style.width=Math.min(desired,maxWidth)+'px';
 img.style.left=(preview.clientWidth-img.clientWidth)*Number($('logo_x').value)/100+'px';
 img.style.top=(preview.clientHeight-img.clientHeight)*Number($('logo_y').value)/100+'px';
}
$('previewLogo').onload=paintLogo;
function renderCueEditor(){
 $('cueEditor').replaceChildren();
 cues.forEach((cue,index)=>{const row=document.createElement('div');row.className='cue-row';
 for(const key of ['start','end','text']){const input=document.createElement('input');input.value=cue[key];input.type=key==='text'?'text':'number';if(key!=='text'){input.step='.05';input.min=0;}else input.maxLength=100;input.setAttribute('aria-label',key==='text'?'Texto del subtítulo':key==='start'?'Inicio del subtítulo en segundos':'Fin del subtítulo en segundos');input.oninput=()=>{cues[index][key]=key==='text'?input.value:Number(input.value);saveCurrent();paintTime();};row.append(input);}
 $('cueEditor').append(row);});
 $('cueCount').textContent=`${cues.length} frases sincronizadas · tiempos relativos al clip`;
}
async function refreshCaptions(){
 if(!job||!selected)return;
 const version=++cueVersion,jobId=job.id,clipId=selected.id;captionPending=true;
 try{const opts=settings();opts.captions=null;const body=await(await request(`/api/jobs/${jobId}/captions`,jsonOptions(opts))).json();if(version!==cueVersion||job?.id!==jobId||selected?.id!==clipId)return;cues=body.captions;captionPending=false;renderCueEditor();saveCurrent();paintTime();}
 catch(e){if(version===cueVersion){captionPending=false;say(e.message);throw e;}}
}
styleKeys.forEach(key=>$(key).addEventListener('input',()=>{if(key==='framing'&&$('framing').value!=='crop'){$('auto_follow').checked=false;++trackingRequest;}if(key==='style'){const presets={classic:['#FFFFFF','#000000',4],bold:['#FFF200','#000000',5],mint:['#AAFF87','#18251C',4],clean:['#FFFFFF','#000000',2]};const p=presets[$('style').value];$('caption_color').value=p[0];$('outline_color').value=p[1];$('outline_width').value=p[2];}saveCurrent();paint();}));
$('titleChoices').onchange=()=>{if($('titleChoices').value){$('title').value=$('titleChoices').value;saveCurrent();paint();}};
$('title').oninput=()=>{saveCurrent();paint();};
for(const key of ['subtitles','start','end'])$(key).oninput=()=>{if(key!=='subtitles'){++trackingRequest;trackingPoints=[];trackingRange=null;if($('auto_follow').checked)$('trackingState').textContent='Los tiempos cambiaron: pulsa Calcular seguimiento de nuevo.';}clearTimeout(captionTimer);++cueVersion;captionPending=true;saveCurrent();paint();captionTimer=setTimeout(()=>refreshCaptions().catch(()=>{}),500);};
$('editLayers').onchange=paintTime;
$('video').onplay=paintTime;$('video').onpause=paintTime;
$('video').ontimeupdate=paintTime;$('video').onloadedmetadata=()=>{if(selected)$('video').currentTime=Number($('start').value);paint();};
$('play').onclick=async()=>{if(!selected)return;const v=$('video');if(v.paused){if(v.currentTime<Number($('start').value)||v.currentTime>=Number($('end').value))v.currentTime=Number($('start').value);try{await v.play();$('play').textContent='⏸ Pausar';}catch(e){say(e.message);}}else{v.pause();$('play').textContent='▶ Reproducir clip';}};
$('seek').oninput=()=>{$('video').currentTime=Number($('start').value)+Number($('seek').value);paintTime();};
$('source').onchange=async()=>{
 const f=$('source').files[0];if(!f)return;++pollToken;++cueVersion;clearTimeout(captionTimer);$('analyze').disabled=true;$('manual').disabled=true;$('export').disabled=true;say('Subiendo video…');$('filename').textContent=f.name;
 try{const body=new FormData();body.append('file',f);useImportedVideo(await(await request('/api/upload',{method:'POST',body})).json());}catch(e){say(e.message);}
};
$('manual').onclick=()=>{choose({id:'manual',title:'',text:'',start:0,end:Math.min(Number($('maximum').value),job.duration),captions:[]});say('Ajusta los tiempos y escribe los subtítulos de tu clip manual.');};
async function startAnalysis(){
 const minimum=Number($('minimum').value),maximum=Number($('maximum').value);
 if(minimum>maximum||minimum<5||maximum>180){say('Elige un rango válido entre 5 y 180 segundos.');return;}
 try{await request(`/api/jobs/${job.id}/analyze`,jsonOptions({minimum,maximum,speaker:$('speaker').value,context:$('videoContext').value,quality:$('quality').value,engine:$('engine').value,transcribe_gpu:$('transcribe_gpu').checked,max_clips:Number($('maxClips').value),clip_settings:readConfig()}));edits.clear();selected=null;cues=[];$('export').disabled=true;$('analyze').disabled=true;$('source').disabled=true;$('manual').disabled=true;$('all').classList.add('hidden');$('clips').replaceChildren();$('video').pause();paint();$('cancelAnalysis').classList.remove('hidden');poll(++pollToken,job.id);}catch(e){say(e.message);}
};
async function poll(token,jobId){
 if(token!==pollToken)return;
 try{const next=await(await request(`/api/jobs/${jobId}`)).json();if(token!==pollToken)return;job=next;const elapsed=job.started_at?Math.round((Date.now()/1000-job.started_at)/60):0;say((job.message||'Análisis en cola…')+(job.progress?` · ${job.progress}%`:'')+(elapsed?` · ${elapsed} min transcurridos`:''));$('progress').value=job.progress||0;if(['ready','error','cancelled'].includes(job.status)){$('cancelAnalysis').classList.add('hidden');$('analyze').disabled=false;$('source').disabled=false;$('manual').disabled=false;if(job.status==='ready')render();return;}}
 catch(e){say(e.message);$('analyze').disabled=false;$('source').disabled=false;return;}
 setTimeout(()=>poll(token,jobId),1500);
}
function render(){
 $('clips').replaceChildren();$('empty').textContent=job.clips.length?`${job.clips.length} momentos · rango ${job.analysis_range.minimum}–${job.analysis_range.maximum} s · selecciona uno para revisar`:'Aún no hay clips. Analiza el video para completar su cobertura.';
 for(const c of job.clips){const el=document.createElement('article');el.className='clip';el.dataset.id=c.id;
 const score=document.createElement('div');score.className='score';score.textContent=`${c.potential?'★ Mayor potencial':c.potential===false?'Para revisar':c.category}${c.score!=null?' · '+c.score+'/100':''}`;
 const h=document.createElement('h3');h.textContent=c.title;const times=document.createElement('p');times.textContent=`${c.start.toFixed(1)}–${c.end.toFixed(1)} s · ${(c.end-c.start).toFixed(1)} segundos`;
 const reason=document.createElement('p');reason.textContent=c.reason;el.append(score,h,times,reason);el.onclick=()=>choose(c);$('clips').append(el);}
 $('all').classList.toggle('hidden',!job.clips.length);if(job.clips.length)choose(job.clips[0]);
}
function choose(c){
 showView('editor');saveCurrent();
 ++trackingRequest;trackingPoints=[];trackingRange=null;$('auto_follow').checked=false;$('trackingState').textContent='';
++cueVersion;clearTimeout(captionTimer);captionPending=false;selected=c;
 const fresh=!edits.has(c.id);if(fresh)applyProjectToEditor();$('tracking_person').value='auto';
 const e=edits.get(c.id)||{title:c.title,subtitles:c.text,start:c.start,end:c.end};for(const [k,v]of Object.entries(e))if($(k)){if(CHECKS.includes(k))$(k).checked=!!v;else $(k).value=v;}
 if($('framing').value==='stack')loadStackPath().catch(e=>say(e.message));else if($('auto_follow').checked)prepareTracking().catch(e=>say(e.message));
 cues=(e.captions||c.captions||[]).map(cue=>({...cue}));$('video').pause();$('video').currentTime=Number($('start').value);$('play').textContent='▶ Reproducir clip';$('export').disabled=false;
 $('titleChoices').replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=c.titles?.length?'Elegir otra propuesta':'Sin propuestas automáticas';$('titleChoices').append(placeholder);$('titleChoices').disabled=!(c.titles?.length);for(const title of c.titles||[]){const option=document.createElement('option');option.value=title;option.textContent=title;$('titleChoices').append(option);}
 document.querySelectorAll('.clip').forEach(el=>el.classList.toggle('active',el.dataset.id===c.id));renderCueEditor();paint();saveCurrent();
}
async function download(opts){
 const duration=validRange(opts);if(opts.auto_follow&&opts.framing!=='stack')await ensureExportTracking(opts);say(`Exportando ${duration.toFixed(1)} segundos en ${opts.resolution==1440?'1440 × 2560':'1080 × 1920'}…`);
 const r=await request(`/api/jobs/${job.id}/export`,jsonOptions(opts));const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='clip-'+Math.round(opts.start)+'-'+Math.round(duration)+'s.mp4';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
$('export').onclick=async()=>{
 $('export').disabled=true;clearTimeout(captionTimer);try{if(captionPending)await refreshCaptions();saveCurrent();await download(settings());say('Clip exportado.');}catch(e){say(e.message);}finally{$('export').disabled=false;}
};
$('all').onclick=async()=>{
 $('all').disabled=true;clearTimeout(captionTimer);try{if(captionPending)await refreshCaptions();saveCurrent();const look=styles();for(let i=0;i<job.clips.length;i++){const c=job.clips[i],saved=edits.get(c.id)||{};await download({...look,title:c.title,subtitles:c.text,start:c.start,end:c.end,captions:c.captions,clip_id:c.id,...saved});}say('Clips exportados. Permite las descargas múltiples si tu navegador lo solicita.');}catch(e){say(e.message);}finally{$('all').disabled=false;}
};
$('saveLogo').onclick=async()=>{const f=$('logoFile').files[0];if(!f){say('Selecciona un archivo de logo.');return;}try{const body=new FormData();body.append('file',f);const added=await(await request('/api/logos/'+$('brand').value,{method:'POST',body})).json();addLogo(added);$('logo').value=added.id;saveCurrent();paint();say('Logo guardado. Ajusta su tamaño, posición y segundos en el editor.');}catch(e){say(e.message);}};
$('saveProfile').onclick=async()=>{try{await request('/api/profile',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({instructions:$('editorProfile').value})});say('Criterios guardados para los próximos análisis.');}catch(e){say(e.message);}};
function addLogo(logo){if(!Array.from($('logo').options).some(o=>o.value===logo.id)){const option=document.createElement('option');option.value=logo.id;option.textContent=logo.name;$('logo').append(option);}}
request('/api/logos').then(r=>r.json()).then(list=>list.forEach(addLogo)).catch(e=>say(e.message));
request('/api/profile').then(r=>r.json()).then(p=>{$('editorProfile').value=p.instructions;}).catch(e=>say(e.message));
new ResizeObserver(paint).observe($('preview'));paint();

for(const [element,xKey,yKey,isLogo] of [['previewTitle','title_x','title_y',false],['previewCaption','caption_x','caption_y',false],['previewLogo','logo_x','logo_y',true]]){
 const node=$(element);let dragging=null;
 node.onpointerdown=event=>{if(!selected)return;event.preventDefault();$('video').pause();const bounds=node.getBoundingClientRect();dragging={dx:event.clientX-(bounds.left+bounds.width/2),dy:event.clientY-(bounds.top+bounds.height/2)};node.setPointerCapture(event.pointerId);};
 node.onpointermove=event=>{if(!dragging)return;const rect=$('preview').getBoundingClientRect();let x=event.clientX-rect.left-dragging.dx,y=event.clientY-rect.top-dragging.dy;
 if(isLogo){x=(x-node.clientWidth/2)/Math.max(1,rect.width-node.clientWidth)*100;y=(y-node.clientHeight/2)/Math.max(1,rect.height-node.clientHeight)*100;}
 else{x=x/rect.width*100;y=y/rect.height*100;}
 $(xKey).value=Math.max(0,Math.min(100,x));$(yKey).value=Math.max(0,Math.min(100,y));saveCurrent();paint();};
 node.onpointerup=node.onpointercancel=()=>{dragging=null;};
}

$('engine').onchange=()=>{$('localOptions').classList.toggle('hidden',$('engine').value!=='local');$('gpuOptions').classList.toggle('hidden',$('engine').value!=='gpu');$('aiConnection').classList.toggle('hidden',$('engine').value!=='cloud');$('aiConnection').open=$('engine').value==='cloud';};
async function aiState(){const state=await(await request('/api/ai')).json();$('aiState').textContent=state.configured?'Clave conectada · '+state.model:'Sin clave de API. Configura la conexión para usar el modo rápido.';}
$('connectAI').onclick=async()=>{const button=$('connectAI');button.disabled=true;try{const state=await(await request('/api/ai',jsonOptions({key:$('apiKey').value}))).json();$('apiKey').value='';$('aiState').textContent=state.message;say('Conexión verificada. Puedes iniciar el análisis rápido.');}catch(e){$('aiState').textContent=e.message;}finally{button.disabled=false;}};
$('disconnectAI').onclick=async()=>{try{await request('/api/ai',{method:'DELETE'});await aiState();}catch(e){say(e.message);}};
$('cancelAnalysis').onclick=async()=>{try{await request(`/api/jobs/${job.id}/cancel`,{method:'POST'});say('Cancelación solicitada. El análisis en nube puede tener una solicitud en curso.');}catch(e){say(e.message);}};
request('/api/jobs').then(r=>r.json()).then(list=>{if(!list.length)return;$('recoveredPanel').classList.remove('hidden');for(const j of list){const option=document.createElement('option');option.value=j.id;option.textContent=`${j.name} · ${(j.duration/60).toFixed(1)} min${j.cached?' · transcripción lista':''}`;$('recentJob').append(option);}}).catch(e=>say(e.message));
$('reuseJob').onclick=async()=>{try{++pollToken;++cueVersion;job=await(await request('/api/jobs/'+$('recentJob').value)).json();selected=null;cues=[];edits.clear();$('filename').textContent=job.name;if(job.youtube)paintYoutube({...job.youtube,status:'ready',progress:100});else $('youtubeCard').classList.add('hidden');if(job.analysis_options){const opts=job.analysis_options;$('videoContext').value=opts.context||'';$('speaker').value=opts.speaker||'';$('minimum').value=opts.minimum;$('maximum').value=opts.maximum;}$('video').src=`/api/jobs/${job.id}/video`;$('analyze').disabled=false;$('manual').disabled=false;$('goEditor').disabled=false;loadProject(job);say('Video recuperado. Si tiene transcripción completa, no se volverá a transcribir.');if(job.status==='ready'&&job.clips.length)render();}catch(e){say(e.message);}};
aiState().catch(e=>say(e.message));

function displayGPU(info){$('gpuState').textContent=info.message+(info.gpu_bytes?` · ${(info.gpu_bytes/1024**3).toFixed(2)} GB GPU`:'');}
request('/api/gpu').then(r=>r.json()).then(info=>{displayGPU(info);$('transcribe_gpu').checked=!!info.transcription_ready;}).catch(e=>{$('gpuState').textContent=e.message;});
$('checkGPU').onclick=async()=>{$('checkGPU').disabled=true;$('gpuState').textContent='Cargando modelo y comprobando GPU…';try{const info=await(await request('/api/gpu/check',{method:'POST'})).json();displayGPU(info);}catch(e){$('gpuState').textContent=e.message;}finally{$('checkGPU').disabled=false;}};

function useImportedVideo(videoJob){
 if(videoJob.youtube)paintYoutube({...videoJob.youtube,status:'ready',progress:100});else $('youtubeCard').classList.add('hidden');
 ++pollToken;++cueVersion;clearTimeout(captionTimer);job=videoJob;selected=null;cues=[];captionPending=false;edits.clear();$('clips').replaceChildren();$('all').classList.add('hidden');$('video').src=`/api/jobs/${job.id}/video`;$('filename').textContent=job.name;$('end').value=Math.min(30,job.duration);$('analyze').disabled=false;$('manual').disabled=false;$('goEditor').disabled=false;loadProject(job);paint();say(`Video listo · ${(job.duration/60).toFixed(1)} minutos`);
}
$('downloadYoutube').onclick=()=>followImport(async()=>(await(await request('/api/youtube',jsonOptions({url:$('youtubeUrl').value,quality:$('youtubeQuality').value,browser:$('youtubeBrowser').value}))).json()).id);
// A download the server resumed after a restart continues in the page that is reloaded.
request('/api/youtube').then(r=>r.json()).then(list=>{if(list.length)followImport(async()=>list[0].id);}).catch(()=>{});
async function followImport(start){
 $('youtubeCard').classList.add('hidden');$('youtubeLocalFallback').classList.add('hidden');
 const button=$('downloadYoutube');button.disabled=true;$('source').disabled=true;
 const locked=['analyze','manual','reuseJob','export'];const before=locked.map(id=>$(id).disabled);locked.forEach(id=>$(id).disabled=true);let importedOK=false;
 try{
  const id=await start();let offline=0;
  while(true){
   let state;
   try{state=await(await request('/api/youtube/'+id)).json();offline=0;}
   catch(e){if(!e.offline||++offline>40)throw e;$('youtubeState').textContent='Reconectando con ClipStudio… la descarga se reanudará cuando vuelva a abrirse.';await new Promise(resolve=>setTimeout(resolve,3000));continue;}
   paintYoutube(state);paintYoutubeAccess(state);
   $('youtubeState').textContent=state.status==='error'?youtubeFriendlyError(state):state.message+(state.status==='downloading'?` ${state.progress}%`:'');
   $('youtubeDiagnostics').textContent=state.status==='error'?state.message:'';
   if(state.status==='error'){$('youtubeLocalFallback').classList.remove('hidden');throw Error(youtubeFriendlyError(state));}
   if(state.status==='ready'){useImportedVideo(state.job);importedOK=true;break;}
   await new Promise(resolve=>setTimeout(resolve,1500));
  }
 }catch(e){$('youtubeState').textContent=e.message;}finally{button.disabled=false;$('source').disabled=false;$('reuseJob').disabled=before[2];if(!importedOK)locked.forEach((id,i)=>$(id).disabled=before[i]);}
}
$('video').addEventListener('error',()=>{if($('video').getAttribute('src'))say('No se pudo cargar el video. Si ClipStudio se cerró, abre INICIAR_WINDOWS.bat y recarga la página.');});

function paintYoutube(state){
 if(!state.thumbnail)return;
 $('youtubeCard').classList.remove('hidden');$('youtubeThumbnail').src=state.thumbnail;
 $('youtubeTitle').textContent=state.status==='error'&&state.title?.startsWith('Preparando video')?'No se pudo descargar este video':state.title||'Video de YouTube';
 const duration=state.duration?`${Math.floor(state.duration/60)}:${String(Math.floor(state.duration%60)).padStart(2,'0')} min`:'';
 $('youtubeMeta').textContent=[state.channel,duration,state.quality].filter(Boolean).join(' · ');
 $('youtubeProgress').value=state.progress||0;
 const speed=state.speed?`${(state.speed/1024**2).toFixed(1)} MB/s`:'';
 const eta=state.eta!=null?`Aprox. ${Math.ceil(state.eta/60)} min restantes`:'';
 $('youtubeTransfer').textContent=state.status==='error'?'Importación no disponible':state.status==='ready'?'✓ Listo para cortar':[speed,eta].filter(Boolean).join(' · ')||state.message||'Preparando…';
}

$('youtubePanel').ontoggle=()=>{$('videoFileDrop').classList.toggle('hidden',$('youtubePanel').open);};

function applyTracking(t){
 if(!$('auto_follow').checked||$('framing').value!=='crop'||!trackingPoints.length||trackingRange?.start!==Number($('start').value)||trackingRange?.end!==Number($('end').value))return;
 let a=trackingPoints[0],b=a;for(const point of trackingPoints){b=point;if(point.time>=t)break;a=point;}
 const f=b.time>a.time?Math.max(0,Math.min(1,(t-a.time)/(b.time-a.time))):0;
 $('video').style.objectPosition=`${a.x+(b.x-a.x)*f}% ${a.y+(b.y-a.y)*f}%`;
}
async function prepareTracking(){
 if(!job||!selected)throw Error('Selecciona un clip primero.');
 const token=++trackingRequest,id=job.id,clip=selected.id,start=Number($('start').value),end=Number($('end').value);
 trackingPoints=[];trackingRange=null;trackingPath=null;trackingPathKey='';if($('framing').value==='fit')$('framing').value='zoom';$('trackingState').textContent='Detectando rostros…';
 let state=await(await request(`/api/jobs/${id}/tracking`,jsonOptions({start,end}))).json();
 while(token===trackingRequest&&selected?.id===clip&&job?.id===id){
  if(state.status==='error')throw Error(state.message);
  if(state.status==='ready'){trackingPoints=state.points;trackingRange={start,end};$('trackingState').textContent='Seguimiento listo. '+state.method;saveCurrent();await loadTrackingPath();paint();return;}
  $('trackingState').textContent=`Calculando seguimiento · ${state.progress||0}%`;
  await new Promise(resolve=>setTimeout(resolve,800));if(token!==trackingRequest)return;
  state=await(await request(`/api/jobs/${id}/tracking/${state.key}`)).json();
 }
}
$('auto_follow').onchange=()=>{if($('auto_follow').checked)prepareTracking().catch(e=>{say(e.message);$('trackingState').textContent=e.message;$('auto_follow').checked=false;saveCurrent();paint();});else{++trackingRequest;saveCurrent();paint();}};
$('calculateTracking').onclick=()=>{$('auto_follow').checked=true;prepareTracking().catch(e=>{$('trackingState').textContent=e.message;say(e.message);});};
document.fonts.ready.then(paint);

async function ensureExportTracking(opts){
 if(trackingRange?.start===opts.start&&trackingRange?.end===opts.end&&trackingPoints.length)return;
 const id=job.id;let state=await(await request(`/api/jobs/${id}/tracking`,jsonOptions({start:opts.start,end:opts.end}))).json();
 while(state.status!=='ready'){
  if(state.status==='error')throw Error(state.message);
  say(`Preparando seguimiento para exportar · ${state.progress||0}%`);await new Promise(resolve=>setTimeout(resolve,800));
  state=await(await request(`/api/jobs/${id}/tracking/${state.key}`)).json();
 }
}

$('improveTitles').onclick=async()=>{
 if(!job||!selected)return;
 const id=job.id,clip=selected.id,start=Number($('start').value),end=Number($('end').value),button=$('improveTitles');button.disabled=true;$('titlesState').textContent='Analizando lo que dice este clip para crear títulos…';
 try{
  const result=await(await request(`/api/jobs/${id}/titles`,jsonOptions({start,end,text:$('subtitles').value}))).json();
  if(job?.id!==id||selected?.id!==clip||Number($('start').value)!==start||Number($('end').value)!==end)return;
  selected.titles=result.titles;$('title').value=result.titles[0];$('titleChoices').replaceChildren();
  for(const title of result.titles){const option=document.createElement('option');option.value=title;option.textContent=title;$('titleChoices').append(option);}
  $('titleChoices').disabled=false;$('titlesState').textContent='Propuestas listas. Puedes elegir otra o editarla.';saveCurrent();paint();
 }catch(e){$('titlesState').textContent=e.message;}finally{button.disabled=false;}
};

$('titlePalette').onchange=()=>{if(!$('titlePalette').value)return;$('title_bg_color').value=$('titlePalette').value;if($('titlePalette').value==='#000000')$('title_text_color').value='#FFFFFF';else $('title_text_color').value='#000000';saveCurrent();paint();};

for(const id of ['title_padding_x','title_padding_y'])$(id).addEventListener('wheel',event=>{if(!event.deltaY)return;event.preventDefault();const input=$(id);input.value=Math.max(Number(input.min),Math.min(Number(input.max),Number(input.value)+(event.deltaY<0?1:-1)));input.dispatchEvent(new Event('input'));},{passive:false});

function refreshTitleImage(ratio){
 const fields=['title','title_font','title_size','title_padding_x','title_padding_y','title_bg_color','title_text_color','title_outline_color','title_outline_width','title_corners'];
 const appearance=Object.fromEntries(fields.map(key=>[key,numeric.includes(key)?Number($(key).value):$(key).value]));
 const signature=JSON.stringify(appearance),node=$('previewTitle');
 const image=node.querySelector('img');if(image)image.style.width=(image.naturalWidth*ratio)+'px';
 if(signature===titleImageSignature)return;titleImageSignature=signature;const version=++titleImageVersion;clearTimeout(titleImageTimer);
 if(!appearance.title.trim()){node.replaceChildren();return;}
 titleImageTimer=setTimeout(async()=>{try{
  const response=await request('/api/title-preview',jsonOptions({...appearance,start:0,end:1,subtitles:''}));
  const blob=await response.blob();if(version!==titleImageVersion)return;
  if(titleImageURL)URL.revokeObjectURL(titleImageURL);titleImageURL=URL.createObjectURL(blob);
  const img=new Image();img.style.width='0px';img.alt=appearance.title;img.src=titleImageURL;img.onload=()=>{if(version===titleImageVersion)img.style.width=(img.naturalWidth*$('preview').clientWidth/1080)+'px';};node.replaceChildren(img);
 }catch(e){if(version===titleImageVersion)say(e.message);}},100);
}

function paintYoutubeAccess(state){
 const names={service:'Servicio de descarga',managed:'Conexión propia de Clip Studio',none:'Sin sesión · descarga pública',firefox:'Firefox',chrome:'Chrome',edge:'Edge',brave:'Brave',cached:'Video ya guardado'};
 if(state.access_mode===undefined){$('youtubeAccessState').textContent='El servidor no informó el modo de sesión. Cierra la ventana negra y vuelve a abrir INICIAR_WINDOWS para cargar la versión actualizada.';return;}
 let message='Modo usado por la app: '+(names[state.access_mode]||'Desconocido');
 if(state.browser_cookies_read)message+=state.youtube_login_cookie_present?' · cookies de inicio de sesión de YouTube encontradas (no confirma que YouTube las acepte).':' · cookies leídas; no se detectó una sesión iniciada de YouTube.';
 $('youtubeAccessState').textContent=message;
}
$('youtubeBrowser').onchange=()=>{$('youtubeAccessState').textContent='Alternativa autorizada si YouTube la exige: '+$('youtubeBrowser').selectedOptions[0].textContent;};
$('youtubeLocalFallback').onclick=()=>{$('source').click();};

function youtubeFriendlyError(state){
 if(state.error_code==='YT-CONEXION')return 'La conexión integrada fue retirada porque Google rechazó el navegador. No vuelvas a iniciar sesión en esa ventana.';
 if(state.error_code==='YT-SESION'||state.error_code==='YT-403')return 'YouTube no autorizó importar este enlace automáticamente. Puedes ingresar el archivo original desde tu PC.';
 if(state.error_code?.startsWith('YT-COOKIES'))return 'No se pudo completar el acceso a YouTube con la alternativa autorizada. Puedes ingresar el archivo original desde tu PC.';
 return state.message;
}

async function refreshYoutubeConnection(){
 try{
  const info=await(await request('/api/youtube-session')).json();
  $('disconnectYoutube').classList.toggle('hidden',!info.authorized&&!info.cleanup_pending);
  $('youtubeConnectionState').classList.toggle('hidden',!info.authorized&&!info.cleanup_pending);
  $('disconnectYoutube').textContent='Eliminar conexión anterior';
  $('youtubeConnectionState').textContent=info.message;
 }catch(e){$('youtubeConnectionState').textContent=e.message;}
}
$('disconnectYoutube').onclick=async()=>{
 $('disconnectYoutube').disabled=true;
 try{
  await request('/api/youtube-session/disconnect',jsonOptions({}));
  await refreshYoutubeConnection();
 }catch(e){$('youtubeConnectionState').textContent=e.message;}
 finally{$('disconnectYoutube').disabled=false;}
};
refreshYoutubeConnection();
// Rendimiento: the server detects GPU/CPU per stage at startup; the user can override transcription and export.
function paintPerformance(info){
 const s=info.stages,gpu=info.gpu;
 $('perfSummary').textContent=`Transcripción ${s.transcription.device} · IA ${s.ai.device.split(' ')[0]} · Exportar ${s.export.device.split(' ')[0]}`;
 $('perfHardware').textContent=`${gpu?`${gpu.name} · ${(gpu.vram_free_mb/1024).toFixed(1)} de ${(gpu.vram_total_mb/1024).toFixed(1)} GB de VRAM libres · `:'Sin GPU NVIDIA · '}CPU ${info.cpu.threads} hilos · RAM ${info.ram.free_gb??'?'} de ${info.ram.total_gb??'?'} GB libres`;
 $('perfTranscription').textContent=s.transcription.device;$('perfTranscriptionWhy').textContent=s.transcription.reason;
 $('perfAI').textContent=s.ai.device;$('perfAIWhy').textContent=s.ai.reason;
 $('perfExport').textContent=s.export.device;$('perfExportWhy').textContent=s.export.reason;
 $('perfTranscriptionMode').value=info.settings.transcription;$('perfExportMode').value=info.settings.export;
}
function loadPerformance(){return request('/api/capabilities').then(r=>r.json()).then(paintPerformance).catch(e=>{$('perfSummary').textContent='Rendimiento no disponible';$('perfHardware').textContent=e.message;});}
$('perfToggle').onclick=()=>{$('perfPanel').classList.toggle('hidden');if(!$('perfPanel').classList.contains('hidden'))loadPerformance();};
for(const id of ['perfTranscriptionMode','perfExportMode'])$(id).onchange=async()=>{try{paintPerformance(await(await request('/api/performance',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({transcription:$('perfTranscriptionMode').value,export:$('perfExportMode').value})})).json());}catch(e){say(e.message);}};
loadPerformance();
// Vista previa ampliada: the editor's own preview grows, so title, captions and logo keep the exact
// proportions used by the export (every layer is drawn relative to the preview width).
const previewPanel=()=>$('preview').closest('.canvas-panel');
const inTheater=()=>previewPanel().classList.contains('theater');
let renderURL=null;
function setTheater(on){
 previewPanel().classList.toggle('theater',on);document.body.classList.toggle('theater-open',on);
 if(!on){closeRender();if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});}
 updateTheater();requestAnimationFrame(paint);
}
function updateTheater(){
 const list=job?.clips||[],i=selected?list.findIndex(c=>c.id===selected.id):-1;
 $('prevClip').disabled=i<=0;$('nextClip').disabled=i<0||i>=list.length-1;
 $('theaterIndex').textContent=i>=0?`Clip ${i+1} de ${list.length}`:'Clip manual';
 $('theaterNote').textContent='Vista en vivo: el título y el logo son los mismos que se exportan; los subtítulos y sus contornos los dibuja el navegador y pueden variar ligeramente'+($('auto_follow').checked?', y el seguimiento de rostro se muestra aproximado':'')+'. Usa «Render de comprobación» para ver el MP4 exacto.';
}
function nudge(seconds){const v=$('video'),start=Number($('start').value),end=Number($('end').value);v.currentTime=Math.min(end-.05,Math.max(start,v.currentTime+seconds));paintTime();}
function stepClip(delta){
 const list=job?.clips||[],i=selected?list.findIndex(c=>c.id===selected.id):-1,next=list[i+delta];
 if(i<0||!next)return;closeRender();$('video').pause();$('play').textContent='▶ Reproducir clip';choose(next);updateTheater();requestAnimationFrame(paint);
}
function closeRender(){
 const r=$('renderVideo');r.pause();r.hidden=true;$('renderBadge').hidden=true;r.removeAttribute('src');r.load();
 if(renderURL){URL.revokeObjectURL(renderURL);renderURL=null;}$('renderCheck').textContent='Render de comprobación';
}
$('expandPreview').onclick=()=>{if(!selected){say('Elige un clip para verlo en grande.');return;}setTheater(true);};
$('closeTheater').onclick=()=>setTheater(false);
$('back5').onclick=()=>nudge(-5);$('fwd5').onclick=()=>nudge(5);
$('prevClip').onclick=()=>stepClip(-1);$('nextClip').onclick=()=>stepClip(1);
$('volume').oninput=()=>{$('video').volume=$('renderVideo').volume=Number($('volume').value);};
$('fullscreenPreview').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});else previewPanel().requestFullscreen().catch(e=>say(e.message));};
document.addEventListener('fullscreenchange',()=>{$('fullscreenPreview').textContent=document.fullscreenElement?'Salir de pantalla completa':'Pantalla completa';requestAnimationFrame(paint);});
window.addEventListener('resize',()=>{if(inTheater())paint();});
$('renderCheck').onclick=async()=>{
 if(!$('renderVideo').hidden){closeRender();return;}
 const button=$('renderCheck');button.disabled=true;button.textContent='Renderizando el MP4…';
 try{
  clearTimeout(captionTimer);if(captionPending)await refreshCaptions();saveCurrent();
  const opts=settings();validRange(opts);if(opts.auto_follow&&opts.framing!=='stack')await ensureExportTracking(opts);
  const blob=await(await request(`/api/jobs/${job.id}/export`,jsonOptions(opts))).blob();
  $('video').pause();$('play').textContent='▶ Reproducir clip';
  renderURL=URL.createObjectURL(blob);const r=$('renderVideo');r.src=renderURL;r.hidden=false;$('renderBadge').hidden=false;r.volume=Number($('volume').value);
  r.play().catch(()=>{});button.textContent='Volver a la vista en vivo';
 }catch(e){say(e.message);button.textContent='Render de comprobación';}finally{button.disabled=false;}
};
document.addEventListener('keydown',e=>{
 if(!inTheater()||(e.target instanceof Element&&e.target.closest('input,textarea,select')))return;
 const actions={Escape:()=>setTheater(false),' ':()=>$('play').click(),ArrowLeft:()=>nudge(-5),ArrowRight:()=>nudge(5),'[':()=>stepClip(-1),']':()=>stepClip(1)};
 if(actions[e.key]){e.preventDefault();actions[e.key]();}
});
// Clipping en vivo: start/stop a session, follow its status and review the moments it proposes while it runs.
let liveId=null,liveTimer=null;
const LIVE_STATES={starting:'Conectando…',live:'● EN VIVO',reconnecting:'Reconectando…',stopping:'Deteniendo…',stopped:'Detenida',ended:'Directo terminado',interrupted:'Interrumpida',error:'Error'};
const liveRunning=s=>['starting','live','reconnecting','stopping'].includes(s.status);
function mmss(s){s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return (h?h+':':'')+String(m).padStart(h?2:1,'0')+':'+String(x).padStart(2,'0');}
function paintLive(s){
 liveId=s.id;$('liveStatus').hidden=false;
 $('liveState').textContent=LIVE_STATES[s.status]||s.status;$('liveChannel').textContent=[s.channel,s.title].filter(Boolean).join(' · ');
 $('liveStats').textContent=`Analizado ${mmss(s.media_s)} · ${s.moments.length} momentos · reconexiones ${s.reconnects}${s.gaps?` · huecos ${s.gaps}`:''}${s.transcription_device?` · transcripción ${s.transcription_device}`:''} · búfer ${s.buffer_minutes} min`;
 $('liveMessage').textContent=s.message||'';$('liveRecent').textContent=s.recent_text?`«…${s.recent_text}»`:'';
 $('liveStart').hidden=liveRunning(s);$('liveStop').hidden=!['starting','live','reconnecting'].includes(s.status);$('liveResume').hidden=!['interrupted','stopped','ended','error'].includes(s.status)||s.media_s===0;
 $('liveMomentsTitle').hidden=!s.moments.length;
 const box=$('liveMoments'),seen=new Set();
 for(const m of s.moments){   // prepend in order: newest ends on top
  seen.add(m.id);let card=box.querySelector(`[data-id="${m.id}"]`);const key=m.status+m.title;
  if(card&&card.dataset.key===key)continue;
  const fresh=document.createElement('article');fresh.className='live-moment';fresh.dataset.id=m.id;fresh.dataset.key=key;
  const h=document.createElement('h4');h.textContent=m.title;
  const meta=document.createElement('div');meta.className='meta';meta.textContent=`Detectado ${m.detected_at} · minuto ${mmss(m.start)} · ${m.duration.toFixed(0)} s · ${m.source}${m.score!=null?` · ${m.score}/100`:''}${m.ready_after_s!=null?` · listo ${Math.round(m.ready_after_s)} s después`:''} · ${{rendering:'preparando…',draft:'borrador',opened:'abierto en el editor',error:'error'}[m.status]||m.status}`;
  const reason=document.createElement('p');reason.className='meta';reason.textContent=m.reason||'';
  const row=document.createElement('div');row.className='row';
  if(['draft','opened'].includes(m.status)){
   const view=document.createElement('button');view.className='secondary';view.textContent='▶ Ver';
   view.onclick=()=>{if(fresh.querySelector('video'))return;const v=document.createElement('video');v.controls=true;v.preload='metadata';v.src=`/api/live/${s.id}/moments/${m.id}/video`;fresh.insertBefore(v,row);v.play().catch(()=>{});};
   const edit=document.createElement('button');edit.textContent='✎ Abrir en el editor';
   edit.onclick=async()=>{edit.disabled=true;try{openJob(await(await request(`/api/live/${s.id}/moments/${m.id}/open`,{method:'POST'})).json());}catch(e){say(e.message);}finally{edit.disabled=false;}};
   const drop=document.createElement('button');drop.className='secondary';drop.textContent='Descartar';
   drop.onclick=async()=>{try{paintLive(await(await request(`/api/live/${s.id}/moments/${m.id}/discard`,{method:'POST'})).json());}catch(e){say(e.message);}};
   row.append(view,edit,drop);
  }
  fresh.append(h,meta,reason,row);
  if(card)card.replaceWith(fresh);else box.prepend(fresh);
 }
 for(const card of [...box.children])if(!seen.has(card.dataset.id))card.remove();
}
function openJob(j){
 ++pollToken;++cueVersion;job=j;selected=null;cues=[];edits.clear();$('filename').textContent=job.name;$('youtubeCard').classList.add('hidden');
 $('video').src=`/api/jobs/${job.id}/video`;$('analyze').disabled=false;$('manual').disabled=false;$('goEditor').disabled=false;loadProject(job);
 say('Momento del directo abierto en el editor. La sesión en vivo sigue analizando.');render();
}
async function followLive(){
 clearTimeout(liveTimer);if(!liveId)return;
 try{const s=await(await request('/api/live/'+liveId)).json();paintLive(s);if(liveRunning(s))liveTimer=setTimeout(followLive,3000);}
 catch(e){$('liveMessage').textContent=e.message;if(e.offline)liveTimer=setTimeout(followLive,5000);}
}
async function startLive(){
 const button=$('liveStart');button.disabled=true;
 try{paintLive(await(await request('/api/live',jsonOptions({url:$('liveUrl').value,minimum:Number($('liveMin').value),maximum:Number($('liveMax').value),buffer_minutes:Number($('liveBuffer').value),height:Number($('liveHeight').value),language:$('liveLanguage').value,clip_settings:readConfig()}))).json());followLive();}
 catch(e){$('liveStatus').hidden=false;$('liveState').textContent='No se pudo iniciar';$('liveMessage').textContent=e.message;}finally{button.disabled=false;}
};
$('liveStop').onclick=async()=>{try{paintLive(await(await request(`/api/live/${liveId}/stop`,{method:'POST'})).json());followLive();}catch(e){say(e.message);}};
$('liveResume').onclick=async()=>{try{paintLive(await(await request(`/api/live/${liveId}/resume`,{method:'POST'})).json());followLive();}catch(e){$('liveMessage').textContent=e.message;}};
// Show the latest session after a reload (also an interrupted one, with its saved moments).
request('/api/live').then(r=>r.json()).then(list=>{if(!list.length)return;liveId=list[0].id;$('livePanel').open=liveRunning(list[0])||list[0].moments.length>0;followLive();}).catch(()=>{});

// --- Configura tus clips: per-project framing, zoom, tracking, subtitles and title corners -------------------------------
// Same proportions as tracking.ZOOM on the server: the video band uses this share of the 9:16 height.
const ZOOM={soft:.5,balanced:.6,close:.72};
const NEW_DEFAULTS={framing:'zoom',zoom:'balanced',tracking:true,tracking_motion:'balanced',subtitles:true,title_corners:'rounded',auto_stack:true,resolution:1080};
let projectConfig={...NEW_DEFAULTS},configTimer=null;
const radio=name=>document.querySelector(`input[name="${name}"]:checked`)?.value;
const setRadio=(name,value)=>{const el=document.querySelector(`input[name="${name}"][value="${value}"]`);if(el)el.checked=true;};
function readConfig(){return {framing:radio('cfgFraming')||'zoom',zoom:radio('cfgZoom')||'balanced',tracking:$('cfgTracking').checked,tracking_motion:radio('cfgMotion')||'balanced',subtitles:radio('cfgSubtitles')!=='off',title_corners:radio('cfgCorners')||'rounded',auto_stack:$('cfgAutoStack').checked,resolution:Number(radio('cfgResolution')||1080)};}
function paintConfig(){
 const c=readConfig();$('cfgZoomGroup').classList.toggle('is-off',c.framing!=='zoom');$('cfgMotionGroup').classList.toggle('is-off',!c.tracking);
 document.querySelector('.mini916[data-style="zoom"]').style.setProperty('--band',(ZOOM[c.zoom]*100)+'%');
}
function showConfig(c){
 // "fit" (old big-bands layout) is still available in the editor; the two styles offered here are zoom and full screen.
 setRadio('cfgFraming',['crop','stack'].includes(c.framing)?c.framing:'zoom');$('cfgAutoStack').checked=c.auto_stack!==false;setRadio('cfgResolution',String(c.resolution||1080));setRadio('cfgZoom',c.zoom);$('cfgTracking').checked=!!c.tracking;setRadio('cfgMotion',c.tracking_motion);
 setRadio('cfgSubtitles',c.subtitles?'on':'off');setRadio('cfgCorners',c.title_corners);paintConfig();
}
function applyProjectToEditor(){
 const c=projectConfig,framing=effectiveFraming(c);$('framing').value=framing;$('zoom').value=c.zoom;$('tracking_motion').value=c.tracking_motion;$('resolution').value=String(c.resolution||1080);
 if(framing==='stack')stackDom();
 $('show_subtitles').checked=!!c.subtitles;$('title_corners').value=c.title_corners;$('auto_follow').checked=!!c.tracking&&c.framing!=='fit';
}
function loadProject(j){
 projectConfig={...NEW_DEFAULTS,...(j.clip_settings||{})};delete projectConfig.legacy;showConfig(projectConfig);
 const t=Math.max(0,Math.min((j.duration||0)/3,(j.duration||0)-1));
 document.querySelectorAll('.cfg-frame').forEach(img=>{img.src=`/api/jobs/${j.id}/frame?t=${t.toFixed(1)}`;});
 watchOverlay(j,t).catch(()=>{});
 if(!selected)applyProjectToEditor();
}
function saveProjectConfig(){
 clearTimeout(configTimer);if(!job)return;
 configTimer=setTimeout(()=>request(`/api/jobs/${job.id}/clip-settings`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(projectConfig)}).catch(e=>say(e.message)),400);
}
document.querySelectorAll('#configure input').forEach(input=>input.addEventListener('change',()=>{
 projectConfig=readConfig();paintConfig();saveProjectConfig();
 // Applies to every clip of the project, including ones already adjusted in the editor.
 for(const [id,e] of edits)edits.set(id,{...e,framing:effectiveFraming(projectConfig),zoom:projectConfig.zoom,tracking_motion:projectConfig.tracking_motion,show_subtitles:projectConfig.subtitles,title_corners:projectConfig.title_corners,resolution:projectConfig.resolution});
 if(selected){applyProjectToEditor();saveCurrent();if($('framing').value==='stack')loadStackPath().catch(e=>say(e.message));else if($('auto_follow').checked)prepareTracking().catch(e=>say(e.message));else paint();}
}));
// Editor changes to these options also become the project's preference.
const EDITOR_TO_PROJECT={framing:'framing',zoom:'zoom',tracking_motion:'tracking_motion',show_subtitles:'subtitles',title_corners:'title_corners',auto_follow:'tracking',resolution:'resolution'};
for(const [id,keyName] of Object.entries(EDITOR_TO_PROJECT))$(id).addEventListener('change',()=>{
 projectConfig[keyName]=CHECKS.includes(id)?$(id).checked:id==='resolution'?Number($(id).value):$(id).value;
 // Choosing another format by hand for a stream video means: stop switching to «Cámara + juego» automatically.
 if(id==='framing'&&$(id).value!=='stack'&&overlayInfo?.found)projectConfig.auto_stack=false;
 showConfig(projectConfig);saveProjectConfig();saveCurrent();
 if(id==='framing'&&$(id).value==='stack'){stackDom();saveCurrent();loadStackPath().catch(e=>say(e.message));}
 if(id==='tracking_motion')loadStackPath().catch(()=>{});
 if(['framing','zoom','tracking_motion'].includes(id))loadTrackingPath().catch(()=>{});
 paint();
});
$('tracking_person').addEventListener('change',()=>{saveCurrent();loadTrackingPath().catch(e=>say(e.message));});
$('focus_y').addEventListener('change',()=>loadTrackingPath().catch(()=>{}));
paintConfig();

// --- Smooth tracking preview: the server returns the exact per-frame path the export uses ----------------------------------
let trackingPath=null,trackingPathKey='';
async function loadTrackingPath(){
 if(!job||!trackingRange||!$('auto_follow').checked||$('framing').value==='fit')return;
 const body={start:trackingRange.start,end:trackingRange.end,person:$('tracking_person').value,motion:$('tracking_motion').value,framing:$('framing').value,zoom:$('zoom').value,focus_y:Number($('focus_y').value)};
 const keyText=JSON.stringify(body);if(keyText===trackingPathKey&&trackingPath)return;trackingPathKey=keyText;
 const path=await(await request(`/api/jobs/${job.id}/tracking/path`,jsonOptions(body))).json();
 if(keyText!==trackingPathKey)return;trackingPath=path;
 const select=$('tracking_person'),current=select.value;select.replaceChildren();
 const auto=document.createElement('option');auto.value='auto';auto.textContent='Automático · quien habla';select.append(auto);
 for(const p of path.persons||[]){const o=document.createElement('option');o.value=String(p.id);o.textContent=`${p.label} · visible ${Math.round(p.presence*100)}%`;select.append(o);}
 select.value=[...select.options].some(o=>o.value===current)?current:'auto';
 $('trackingState').textContent=(path.static?'Encuadre fijo: la persona cabe sin mover la cámara. ':'Seguimiento suave listo. ')+((path.persons||[]).length>1?`${path.persons.length} personas detectadas: elige a quién seguir.`:'');
 paint();
}
applyTracking=function(t){
 const fr=$('framing').value;
 if(!$('auto_follow').checked||!['crop','zoom'].includes(fr)||!trackingPath||trackingRange?.start!==Number($('start').value)||trackingRange?.end!==Number($('end').value))return;
 const i=Math.max(0,t)*trackingPath.fps,a=Math.min(trackingPath.x.length-1,Math.floor(i)),b=Math.min(trackingPath.x.length-1,a+1),f=i-a;
 let x=trackingPath.x[a]+(trackingPath.x[b]-trackingPath.x[a])*f;
 // Same even-pixel rounding as the export (FFmpeg crops yuv420p at even offsets).
 if(trackingPath.extra>0)x=Math.round(x*trackingPath.extra/200)*200/trackingPath.extra;
 $('video').style.objectPosition=`${x}% ${trackingPath.y}%`;
};
// Repaint every displayed frame while playing (timeupdate fires only ~4 times per second).
function frameLoop(){if(!$('video').paused){paintTime();requestAnimationFrame(frameLoop);}}
$('video').addEventListener('play',()=>requestAnimationFrame(frameLoop));

// --- "Configura tus clips" is asked before anything starts, for a video and for a live stream ----------------------------
let configMode=null;
function openConfig(mode){
 configMode=mode;const modal=$('configModal');modal.classList.toggle('live-mode',mode==='live');modal.classList.toggle('video-mode',mode==='video');
 $('configTitle').textContent=mode==='live'?'Configura tus clips · Clipping en vivo':'Configura tus clips · Video';
 $('configIntro').textContent=mode==='live'?'Elige cómo quieres los clips del directo. Los momentos se abrirán en el editor con esta configuración.':'Elige cómo quieres los clips. Se guarda en este proyecto y puedes cambiarlo después en el editor sin repetir el análisis.';
 $('cfgStart').textContent=mode==='live'?'● Comenzar clipping en vivo':'✦ Comenzar análisis';
 if(mode==='live'&&!job)document.querySelectorAll('.cfg-frame').forEach(img=>img.removeAttribute('src'));
 paintConfig();modal.classList.remove('hidden');$('cfgStart').focus();
}
function closeConfig(){$('configModal').classList.add('hidden');configMode=null;}
$('analyze').onclick=()=>{if(job)openConfig('video');};
$('liveStart').onclick=()=>{if(!$('liveUrl').value.trim()){$('liveStatus').hidden=false;$('liveState').textContent='Falta el enlace';$('liveMessage').textContent='Pega el enlace del directo antes de iniciar.';return;}openConfig('live');};
$('cfgCancel').onclick=closeConfig;
$('configModal').addEventListener('keydown',e=>{if(e.key==='Escape')closeConfig();});
$('cfgStart').onclick=async()=>{
 const mode=configMode;projectConfig=readConfig();
 const [min,max]=mode==='live'?[Number($('liveMin').value),Number($('liveMax').value)]:[Number($('minimum').value),Number($('maximum').value)];
 if(!(min>=5&&max<=180&&min<=max)){say('Elige una duración válida: mínimo ≤ máximo, entre 5 y 180 segundos.');return;}
 closeConfig();
 if(mode==='live')await startLive();else{saveProjectConfig();await startAnalysis();}
};


// --- «Cámara + juego»: streamer camera on top, game below ------------------------------------------------------------------
// The server finds the camera once per video; the preview draws the same two crops the export uses on a canvas.
function effectiveFraming(c){const cam=!!overlayInfo?.found;if(c.framing==='stack')return cam?'stack':'zoom';return cam&&c.auto_stack?'stack':c.framing;}
// Centre of the line between camera and game, in % of the height (title_y centres the title there).
function seamY(){const top=stackPath?.top||Math.min(960,Math.max(768,overlayInfo?.found?Math.round(1080*overlayInfo.h/overlayInfo.w):864));return Math.round((top+3)/19.2*10)/10;}
// «Cámara + juego» defaults: the title sits on the line; subtitles go low in the game, clear of the centre where the action is.
// Only values still at their defaults move, so a position chosen by hand is kept.
const STACK_CAPTION_Y=85,OLD_SEAM=v=>Math.abs(v-seamY())<1.5;
function stackEdit(e){const t=Number(e.title_y??12),c=Number(e.caption_y??81);return {...e,title_y:t===12?seamY():t,caption_y:c===81||OLD_SEAM(c)?STACK_CAPTION_Y:c};}
function stackDom(){const e=stackEdit({title_y:$('title_y').value,caption_y:$('caption_y').value});$('title_y').value=e.title_y;$('caption_y').value=e.caption_y;}
function stackCaptionY(){return STACK_CAPTION_Y;}
async function watchOverlay(j,t){
 const token=++overlayWatch;overlayInfo=null;stackPath=null;stackKey='';
 $('cfgStackFrame').removeAttribute('src');$('cfgStackNote').textContent='Buscando la cámara del streamer en el video…';
 let state=await(await request(`/api/jobs/${j.id}/overlay`,{method:'POST'})).json();
 while(token===overlayWatch&&!['ready','error'].includes(state.status)){
  $('cfgStackNote').textContent=`Buscando la cámara del streamer… ${state.progress||0}%`;
  await new Promise(r=>setTimeout(r,1000));if(token!==overlayWatch)return;
  state=await(await request(`/api/jobs/${j.id}/overlay`)).json();
 }
 if(token!==overlayWatch)return;
 if(state.status==='error'){$('cfgStackNote').textContent='No se pudo revisar la cámara: '+state.message;return;}
 overlayInfo=state;paintOverlayInfo(j,t);
 if(state.found&&job?.id===j.id){
  // Clips not adjusted by hand follow the project choice now that we know the video has a camera.
  // Before the camera was known, clips opened with the fallback format (zoom when the project asks for «Cámara + juego»).
  const framing=effectiveFraming(projectConfig),before=projectConfig.framing==='stack'?'zoom':projectConfig.framing;
  for(const [id,e] of edits)if(e.framing===before&&framing==='stack')edits.set(id,stackEdit({...e,framing}));
  if(selected&&framing==='stack'&&$('framing').value===before){$('framing').value=framing;$('auto_follow').checked=false;++trackingRequest;$('trackingState').textContent='';stackDom();saveCurrent();}
  if($('framing').value==='stack')loadStackPath().catch(e=>say(e.message));
 }
 paint();
}
function paintOverlayInfo(j,t){
 const img=$('cfgStackFrame');
 if(overlayInfo?.found){img.src=`/api/jobs/${j.id}/layout-preview?t=${(t||0).toFixed(1)}&v=${overlayInfo.x}-${overlayInfo.y}-${overlayInfo.w}-${overlayInfo.h}`;$('cfgStackNote').textContent=(overlayInfo.manual?'Recuadro marcado a mano':'Cámara del streamer detectada')+' · arriba la cámara, abajo el juego.';}
 else{img.removeAttribute('src');$('cfgStackNote').textContent=overlayInfo?.kind==='fullcam'?'Este video es solo la cámara: se usará el encuadre elegido. Puedes marcar un recuadro a mano en el editor.':'No se encontró una cámara superpuesta. Se usará el encuadre elegido; en el editor puedes marcarla a mano.';}
}
async function loadStackPath(){
 if(!job||!selected||$('framing').value!=='stack')return;
 const body={start:Number($('start').value),end:Number($('end').value),motion:$('tracking_motion').value,follow:$('game_follow').checked};
 const keyText=JSON.stringify(body)+JSON.stringify(overlayInfo&&[overlayInfo.x,overlayInfo.y,overlayInfo.w,overlayInfo.h]);
 if(keyText===stackKey&&stackPath)return;stackKey=keyText;stackPath=null;
 $('stackState').textContent='Preparando «Cámara + juego»: cámara y movimiento del juego…';paint();
 const path=await(await request(`/api/jobs/${job.id}/layout/path`,jsonOptions(body))).json();
 if(keyText!==stackKey)return;
 const guess=seamY();stackPath={...path,start:body.start,end:body.end};
 if(path.found&&Math.abs(Number($('title_y').value)-guess)<.05&&guess!==seamY()){$('title_y').value=seamY();saveCurrent();}
 $('stackState').textContent=path.found?`${overlayInfo?.manual?'Recuadro marcado a mano':'Cámara detectada'} · ${path.game.static?'juego centrado':'sigue la acción del juego con suavidad'}.`+(path.cam_presence<.34?' ⚠ En este clip casi no se ve al streamer en el recuadro (intro o pantalla completa): revisa la vista previa o usa otro encuadre.':''):'No se encontró la cámara del streamer. Pulsa «Ajustar recuadro de cámara» para marcarla.';
 paint();
}
function drawStack(t){
 const canvas=$('stackCanvas'),video=$('video'),stack=$('framing').value==='stack';
 $('stackBox').classList.toggle('hidden',!stack);
 const p=stackPath,on=stack&&p?.found&&p.start===Number($('start').value)&&p.end===Number($('end').value);
 canvas.hidden=!on;video.style.opacity=on?'0':'';if(!on)return;
 const preview=$('preview'),dpr=window.devicePixelRatio||1,w=Math.round(preview.clientWidth*dpr),h=Math.round(preview.clientHeight*dpr);
 if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
 const ctx=canvas.getContext('2d'),r=w/1080;ctx.fillStyle='#0b0b0b';ctx.fillRect(0,0,w,h);
 if(video.readyState<2)return;
 ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
 const cam=p.cam;ctx.drawImage(video,cam.x,cam.y,cam.w,cam.h,0,0,w,p.top*r);
 // Same numbers as layout.filter_graph: the game area is cropped at even offsets and scaled to the panel.
 const g=p.game,i=Math.max(0,t)*g.fps,a=Math.min(g.left.length-1,Math.floor(i)),b=Math.min(g.left.length-1,a+1);
 const left=g.left[a]+(g.left[b]-g.left[a])*Math.max(0,i-a),x=Math.min(Math.max(0,Math.round(left/2)*2),p.width-g.w);
 ctx.drawImage(video,x,g.y,g.w,g.h,0,(p.top+p.seam)*r,w,p.bottom*r);
}
$('game_follow').addEventListener('change',()=>{saveCurrent();loadStackPath().catch(e=>say(e.message));});
for(const key of ['start','end'])$(key).addEventListener('change',()=>{if($('framing').value==='stack')loadStackPath().catch(e=>say(e.message));});
$('video').addEventListener('loadeddata',()=>paintTime());$('video').addEventListener('seeked',()=>paintTime());

// Manual correction of the camera rectangle.
let camDrag=null,camScale=1;
function placeCamBox(box){const b=$('camBox');b.style.left=box.x/camScale+'px';b.style.top=box.y/camScale+'px';b.style.width=box.w/camScale+'px';b.style.height=box.h/camScale+'px';}
function camBoxValue(){const b=$('camBox');return {x:Math.round(b.offsetLeft*camScale),y:Math.round(b.offsetTop*camScale),w:Math.round(b.offsetWidth*camScale),h:Math.round(b.offsetHeight*camScale)};}
$('adjustCam').onclick=()=>{
 if(!job)return;const img=$('camFrame');
 img.onload=()=>{
  const width=overlayInfo?.width||img.naturalWidth,height=overlayInfo?.height||img.naturalHeight;camScale=width/img.clientWidth;
  placeCamBox(overlayInfo?.found?overlayInfo:{x:width*.7,y:height*.03,w:width*.27,h:height*.34});
 };
 img.src=`/api/jobs/${job.id}/frame?t=${Math.max(0,$('video').currentTime).toFixed(1)}`;$('camModal').classList.remove('hidden');
};
$('camBox').addEventListener('pointerdown',e=>{const b=$('camBox');camDrag={resize:e.target.id==='camHandle',x:e.clientX,y:e.clientY,left:b.offsetLeft,top:b.offsetTop,w:b.offsetWidth,h:b.offsetHeight};b.setPointerCapture(e.pointerId);e.preventDefault();});
$('camBox').addEventListener('pointermove',e=>{
 if(!camDrag)return;const b=$('camBox'),stage=$('camFrame'),dx=e.clientX-camDrag.x,dy=e.clientY-camDrag.y,W=stage.clientWidth,H=stage.clientHeight;
 if(camDrag.resize){b.style.width=Math.max(24,Math.min(W-camDrag.left,camDrag.w+dx))+'px';b.style.height=Math.max(24,Math.min(H-camDrag.top,camDrag.h+dy))+'px';}
 else{b.style.left=Math.max(0,Math.min(W-camDrag.w,camDrag.left+dx))+'px';b.style.top=Math.max(0,Math.min(H-camDrag.h,camDrag.top+dy))+'px';}
});
$('camBox').addEventListener('pointerup',()=>{camDrag=null;});
$('camCancel').onclick=()=>$('camModal').classList.add('hidden');
$('camSave').onclick=async()=>{
 try{
  overlayInfo=await(await request(`/api/jobs/${job.id}/overlay`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(camBoxValue())})).json();
  $('camModal').classList.add('hidden');paintOverlayInfo(job,$('video').currentTime);
  if($('framing').value!=='stack'){$('framing').value='stack';projectConfig.framing='stack';saveProjectConfig();stackDom();saveCurrent();}
  stackKey='';await loadStackPath();
 }catch(e){say(e.message);}
};
