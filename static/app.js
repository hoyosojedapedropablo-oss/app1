const $=id=>document.getElementById(id);
let titleImageSignature='',titleImageURL=null,titleImageVersion=0,titleImageTimer;

let trackingPoints=[],trackingRange=null,trackingRequest=0;
let job=null,selected=null,cues=[],cueVersion=0,captionPending=false,captionTimer,pollToken=0;
const edits=new Map();
const numeric=['title_padding_x','title_padding_y','title_size','title_outline_width','title_x','title_y','caption_x','caption_y','caption_size','outline_width','focus_x','focus_y','start','end','logo_width','logo_x','logo_y','logo_start','logo_end'];
const styleKeys=['title_padding_x','title_padding_y','title_bg_color','title_text_color','auto_follow','style','font','title_font','title_outline_color','title_size','title_outline_width','title_x','title_y','caption_x','caption_y','caption_size','caption_color','outline_color','outline_width','logo','framing','focus_x','focus_y','logo_width','logo_x','logo_y','logo_start','logo_end'];
async function request(url,options={}){const r=await fetch(url,options);if(!r.ok){let e;try{e=await r.json()}catch{e={detail:r.statusText}}throw Error(typeof e.detail==='string'?e.detail:'Revisa los campos y el rango de tiempos.')}return r;}
const jsonOptions=value=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
function showView(name){$('analysisView').classList.toggle('hidden',name!=='analysis');$('editorView').classList.toggle('hidden',name!=='editor');$('goAnalyze').classList.toggle('active',name==='analysis');$('goEditor').classList.toggle('active',name==='editor');if(name==='editor')requestAnimationFrame(paint);}
$('goAnalyze').onclick=()=>showView('analysis');$('goEditor').onclick=()=>showView('editor');
for(const button of document.querySelectorAll('[data-tab]'))button.onclick=()=>{for(const b of document.querySelectorAll('[data-tab]')){b.classList.toggle('active',b===button);b.setAttribute('aria-selected',String(b===button));}for(const panel of document.querySelectorAll('.tab-panel'))panel.classList.toggle('hidden',panel.id!=='tab-'+button.dataset.tab);};
function say(text){$('status').textContent=text;}
function styles(){return Object.fromEntries(styleKeys.map(k=>[k,k==='auto_follow'?$('auto_follow').checked:k==='logo_end'&&!$(k).value?null:numeric.includes(k)?Number($(k).value):$(k).value]));}
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
 $('video').style.objectFit=$('framing').value==='crop'?'cover':'contain';$('video').style.objectPosition=`${$('focus_x').value}% ${$('focus_y').value}%`;
 paintLogo();
 if(job&&selected){const duration=Number($('end').value)-Number($('start').value);$('duration').textContent=`${duration.toFixed(1)} s · formato 9:16`;$('seek').max=Math.max(0,duration);}
 paintTime();
}
function paintTime(){
 const t=$('video').currentTime-Number($('start').value),duration=Number($('end').value)-Number($('start').value);
 applyTracking(t);
 const editing=$('video').paused&&$('editLayers').checked&&selected;const active=cues.find(c=>t>=c.start&&t<c.end);$('previewCaption').textContent=active?.text||(editing?cues[0]?.text||'Subtítulos de ejemplo':'');
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
$('analyze').onclick=async()=>{
 const minimum=Number($('minimum').value),maximum=Number($('maximum').value);
 if(minimum>maximum||minimum<5||maximum>180){say('Elige un rango válido entre 5 y 180 segundos.');return;}
 try{await request(`/api/jobs/${job.id}/analyze`,jsonOptions({minimum,maximum,speaker:$('speaker').value,context:$('videoContext').value,quality:$('quality').value,engine:$('engine').value,transcribe_gpu:$('transcribe_gpu').checked,max_clips:Number($('maxClips').value)}));edits.clear();selected=null;cues=[];$('export').disabled=true;$('analyze').disabled=true;$('source').disabled=true;$('manual').disabled=true;$('all').classList.add('hidden');$('clips').replaceChildren();$('video').pause();paint();$('cancelAnalysis').classList.remove('hidden');poll(++pollToken,job.id);}catch(e){say(e.message);}
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
 const e=edits.get(c.id)||{title:c.title,subtitles:c.text,start:c.start,end:c.end};for(const [k,v]of Object.entries(e))if($(k)){if(k==='auto_follow')$(k).checked=!!v;else $(k).value=v;}
 if($('auto_follow').checked)prepareTracking().catch(e=>say(e.message));
 cues=(e.captions||c.captions||[]).map(cue=>({...cue}));$('video').pause();$('video').currentTime=Number($('start').value);$('play').textContent='▶ Reproducir clip';$('export').disabled=false;
 $('titleChoices').replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent=c.titles?.length?'Elegir otra propuesta':'Sin propuestas automáticas';$('titleChoices').append(placeholder);$('titleChoices').disabled=!(c.titles?.length);for(const title of c.titles||[]){const option=document.createElement('option');option.value=title;option.textContent=title;$('titleChoices').append(option);}
 document.querySelectorAll('.clip').forEach(el=>el.classList.toggle('active',el.dataset.id===c.id));renderCueEditor();paint();saveCurrent();
}
async function download(opts){
 const duration=validRange(opts);if(opts.auto_follow)await ensureExportTracking(opts);say(`Exportando ${duration.toFixed(1)} segundos en 1080 × 1920…`);
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
$('reuseJob').onclick=async()=>{try{++pollToken;++cueVersion;job=await(await request('/api/jobs/'+$('recentJob').value)).json();selected=null;cues=[];edits.clear();$('filename').textContent=job.name;if(job.youtube)paintYoutube({...job.youtube,status:'ready',progress:100});else $('youtubeCard').classList.add('hidden');if(job.analysis_options){const opts=job.analysis_options;$('videoContext').value=opts.context||'';$('speaker').value=opts.speaker||'';$('minimum').value=opts.minimum;$('maximum').value=opts.maximum;}$('video').src=`/api/jobs/${job.id}/video`;$('analyze').disabled=false;$('manual').disabled=false;$('goEditor').disabled=false;say('Video recuperado. Si tiene transcripción completa, no se volverá a transcribir.');if(job.status==='ready'&&job.clips.length)render();}catch(e){say(e.message);}};
aiState().catch(e=>say(e.message));

function displayGPU(info){$('gpuState').textContent=info.message+(info.gpu_bytes?` · ${(info.gpu_bytes/1024**3).toFixed(2)} GB GPU`:'');}
request('/api/gpu').then(r=>r.json()).then(info=>{displayGPU(info);$('transcribe_gpu').checked=!!info.transcription_ready;}).catch(e=>{$('gpuState').textContent=e.message;});
$('checkGPU').onclick=async()=>{$('checkGPU').disabled=true;$('gpuState').textContent='Cargando modelo y comprobando GPU…';try{const info=await(await request('/api/gpu/check',{method:'POST'})).json();displayGPU(info);}catch(e){$('gpuState').textContent=e.message;}finally{$('checkGPU').disabled=false;}};

function useImportedVideo(videoJob){
 if(videoJob.youtube)paintYoutube({...videoJob.youtube,status:'ready',progress:100});else $('youtubeCard').classList.add('hidden');
 ++pollToken;++cueVersion;clearTimeout(captionTimer);job=videoJob;selected=null;cues=[];captionPending=false;edits.clear();$('clips').replaceChildren();$('all').classList.add('hidden');$('video').src=`/api/jobs/${job.id}/video`;$('filename').textContent=job.name;$('end').value=Math.min(30,job.duration);$('analyze').disabled=false;$('manual').disabled=false;$('goEditor').disabled=false;paint();say(`Video listo · ${(job.duration/60).toFixed(1)} minutos`);
}
$('downloadYoutube').onclick=async()=>{
 $('youtubeCard').classList.add('hidden');$('youtubeLocalFallback').classList.add('hidden');
 const requestedMode=$('youtubeBrowser').value;
 const button=$('downloadYoutube');button.disabled=true;$('source').disabled=true;
 const locked=['analyze','manual','reuseJob','export'];const before=locked.map(id=>$(id).disabled);locked.forEach(id=>$(id).disabled=true);let importedOK=false;
 try{
  const imported=await(await request('/api/youtube',jsonOptions({url:$('youtubeUrl').value,quality:$('youtubeQuality').value,browser:requestedMode}))).json();
  while(true){
   const state=await(await request('/api/youtube/'+imported.id)).json();
   paintYoutube(state);paintYoutubeAccess(state);
   $('youtubeState').textContent=state.status==='error'?youtubeFriendlyError(state):state.message+(state.status==='downloading'?` ${state.progress}%`:'');
   $('youtubeDiagnostics').textContent=state.status==='error'?state.message:'';
   if(state.status==='error'){$('youtubeLocalFallback').classList.remove('hidden');throw Error(youtubeFriendlyError(state));}
   if(state.status==='ready'){useImportedVideo(state.job);importedOK=true;break;}
   await new Promise(resolve=>setTimeout(resolve,1500));
  }
 }catch(e){$('youtubeState').textContent=e.message;}finally{button.disabled=false;$('source').disabled=false;$('reuseJob').disabled=before[2];if(!importedOK)locked.forEach((id,i)=>$(id).disabled=before[i]);}
};

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
 trackingPoints=[];trackingRange=null;$('framing').value='crop';$('trackingState').textContent='Detectando rostros, voz y movimiento de boca…';
 let state=await(await request(`/api/jobs/${id}/tracking`,jsonOptions({start,end}))).json();
 while(token===trackingRequest&&selected?.id===clip&&job?.id===id){
  if(state.status==='error')throw Error(state.message);
  if(state.status==='ready'){trackingPoints=state.points;trackingRange={start,end};$('trackingState').textContent='Seguimiento listo. '+state.method;saveCurrent();paint();return;}
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
 const fields=['title','title_font','title_size','title_padding_x','title_padding_y','title_bg_color','title_text_color','title_outline_color','title_outline_width'];
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
 const names={none:'Sin sesión · descarga pública',firefox:'Firefox',chrome:'Chrome',edge:'Edge',brave:'Brave',cached:'Video ya guardado'};
 if(state.access_mode===undefined){$('youtubeAccessState').textContent='El servidor no informó el modo de sesión. Cierra la ventana negra y vuelve a abrir INICIAR_WINDOWS para cargar la versión actualizada.';return;}
 let message='Modo usado por la app: '+(names[state.access_mode]||'Desconocido');
 if(state.browser_cookies_read)message+=state.youtube_login_cookie_present?' · cookies de inicio de sesión de YouTube encontradas (no confirma que YouTube las acepte).':' · cookies leídas; no se detectó una sesión iniciada de YouTube.';
 $('youtubeAccessState').textContent=message;
}
$('youtubeBrowser').onchange=()=>{$('youtubeAccessState').textContent='Alternativa autorizada si YouTube la exige: '+$('youtubeBrowser').selectedOptions[0].textContent;};
$('youtubeLocalFallback').onclick=()=>{$('source').click();};

function youtubeFriendlyError(state){
 if(state.error_code==='YT-SESION'||state.error_code==='YT-403')return 'YouTube no autorizó importar este enlace automáticamente. Puedes ingresar el archivo original desde tu PC.';
 if(state.error_code?.startsWith('YT-COOKIES'))return 'No se pudo completar el acceso a YouTube con la alternativa autorizada. Puedes ingresar el archivo original desde tu PC.';
 return state.message;
}
