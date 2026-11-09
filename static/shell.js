// ClipStudio 5 · shell: side menu, Inicio, Biblioteca, Proyectos, Clips en vivo history and Configuración.
// It reuses the existing analysis, live and editor screens (app.js) — nothing they do is replaced.
// All text coming from videos, streams or the AI is inserted with textContent (never innerHTML).
(() => {
const $ = (id) => document.getElementById(id);
function h(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'style') node.style.cssText = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k === 'text') node.textContent = v;
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return node;
}
const svg = (d, size = 18) => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('width', size); s.setAttribute('height', size); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '1.8'); s.setAttribute('aria-hidden', 'true'); s.innerHTML = d; return s; };
const STAR = '<path d="M12 3l2.6 5.6 6.1.6-4.6 4.1 1.3 6-5.4-3.1-5.4 3.1 1.3-6L3.3 9.2l6.1-.6z"></path>';
const TRASH = '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"></path>';
const STATUS = { detected: 'Detectado', draft: 'Borrador', edited: 'Editado', exported: 'Exportado' };
const fmtDur = (s) => s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')} min` : `${(Math.round(s * 10) / 10).toLocaleString('es')} s`;
const fmtDate = (iso) => { const d = new Date(iso); return isNaN(d) ? '' : d.toLocaleDateString('es', { day: 'numeric', month: 'short' }) + ' · ' + d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' }); };
const ago = (t) => { const s = (Date.now() - t) / 1000; return s < 90 ? 'hace un momento' : s < 3600 ? `hace ${Math.round(s / 60)} min` : s < 86400 ? `hace ${Math.round(s / 3600)} h` : `hace ${Math.round(s / 86400)} días`; };
const platformLogo = (p) => p === 'kick' ? h('img', { src: '/static/img/kick.png', alt: 'Kick', style: 'height:12px;width:auto;display:block' }) : p === 'youtube' ? h('img', { src: '/static/img/youtube.png', alt: 'YouTube', style: 'height:13px;width:auto;display:block' }) : null;
// replaceChildren would print 'null' for skipped blocks
const put = (root, ...kids) => root.replaceChildren(...kids.flat().filter((k) => k != null && k !== false));
async function api(url, options) { const r = await request(url, options); return r.status === 204 ? null : r.json(); }
function toast(title, text, action) {
  const t = h('div', { class: 'toast', role: 'status' }, h('div', { style: 'display:flex;flex-direction:column;gap:2px;flex:1' }, h('b', { text: title, style: 'font-size:14px' }), text ? h('span', { class: 'muted', text }) : null), action || null);
  $('toasts').append(t); setTimeout(() => t.remove(), 7000);
}

// --- navigation ---------------------------------------------------------------------------------------------------
const VIEWS = ['home', 'analysis', 'live', 'library', 'editor', 'projects', 'settings'];
let current = 'home';
function navigate(name) {
  if (!VIEWS.includes(name)) name = 'home';
  if (name === 'editor' && !job) { toast('Abre un clip primero', 'Elige uno en la biblioteca o en proyectos.'); name = 'library'; }
  current = name;
  for (const v of VIEWS) $(v + 'View')?.classList.toggle('hidden', v !== name);
  for (const b of document.querySelectorAll('#sideNav button')) b.classList.toggle('on', b.dataset.view === name);
  window.scrollTo({ top: 0 });
  ({ home: renderHome, library: renderLibrary, projects: renderProjects, live: () => { buildLiveLayout(); renderLiveHistory(); if (liveId) followLive(); }, settings: renderSettings })[name]?.();
  if (name === 'editor') requestAnimationFrame(() => { try { paint(); } catch {} });
  try { localStorage.setItem('cs.view', name); } catch {}
}
// app.js calls showView('analysis' | 'editor'); route it through the new menu.
window.showView = (name) => navigate(name === 'analysis' ? 'analysis' : name === 'editor' ? 'editor' : name);
showView = window.showView;
for (const b of document.querySelectorAll('#sideNav button')) b.addEventListener('click', () => navigate(b.dataset.view));

// Existing panels move into their sections (same elements, same handlers).
const livePanel = $('livePanel');
if (livePanel) { livePanel.open = true; livePanel.querySelector('summary').style.display = 'none'; livePanel.classList.add('card'); $('liveHost').append(livePanel); }
$('perfToggle').onclick = () => navigate('settings');

// --- opening projects and clips -----------------------------------------------------------------------------------
async function openProject(id, clipRef, view) {
  const select = $('recentJob');
  if (![...select.options].some((o) => o.value === id)) select.append(h('option', { value: id, text: id }));
  select.value = id;
  await $('reuseJob').onclick();
  if (!job || job.id !== id) throw Error('No se pudo abrir el proyecto.');
  const clip = clipRef ? job.clips.find((c) => c.id === clipRef) : job.clips[0];
  if (clip && view !== 'analysis') { choose(clip); navigate('editor'); } else navigate('analysis');
}
async function openLibraryClip(item) {
  if (item.missing) { toast('Este clip no tiene su video', 'El archivo ya no está en el PC. Puedes quitarlo de la biblioteca.'); return; }
  try {
    // Live moments always go through «open»: it reuses their project, or rebuilds it if it is missing.
    if (item.origin === 'live') {
      const opened = await api(`/api/live/${item.session_id}/moments/${item.clip_ref}/open`, { method: 'POST' });
      item.project_id = opened.id;
    }
    await openProject(item.project_id, item.origin === 'live' ? null : item.clip_ref);
  } catch (e) { toast('No se pudo abrir el clip', e.message); }
}

// --- hover preview: starts after a short pause, muted, scrubbable with the mouse -------------------------------------
function previewBox(img, videoUrl, start, length, ratio) {
  const box = h('div', { class: 'hv' }, img ? h('img', { src: img, alt: '', loading: 'lazy', onerror: (e) => { e.target.remove(); } }) : h('span', { class: 'noimg', text: 'Sin miniatura' }));
  const bar = h('span', { class: 'bar' }, h('i')); box.append(bar);
  let video = null, timer = null;
  const begin = start || 0, span = Math.max(1, length || 10);
  box.addEventListener('mouseenter', () => {
    if (!videoUrl) return;
    timer = setTimeout(() => {
      if (!video) { video = h('video', { muted: true, playsinline: true, preload: 'auto' }); video.muted = true; video.src = videoUrl; box.insertBefore(video, bar);
        video.addEventListener('timeupdate', () => { const f = Math.max(0, Math.min(1, (video.currentTime - begin) / span)); bar.firstChild.style.width = (f * 100) + '%'; if (video.currentTime > begin + span) video.currentTime = begin; }); }
      video.currentTime = begin; video.play().then(() => box.classList.add('playing')).catch(() => {});
    }, 220);
  });
  box.addEventListener('mousemove', (e) => { if (!video || !box.classList.contains('playing')) return; const r = box.getBoundingClientRect(); if (e.shiftKey) video.currentTime = begin + span * ((e.clientX - r.left) / r.width); });
  box.addEventListener('mouseleave', () => { clearTimeout(timer); if (video) { video.pause(); box.classList.remove('playing'); } });
  return box;
}
const clipVideoUrl = (c) => `/api/library/${encodeURIComponent(c.id)}/video`;
const clipStart = (c) => c.origin === 'live' ? 3 : c.start;

function clipCard(c, onChange) {
  const box = previewBox(c.thumb_url, c.missing ? null : clipVideoUrl(c), clipStart(c), c.duration);
  box.addEventListener('click', () => openLibraryClip(c));
  const star = h('button', { class: 'star', type: 'button', 'aria-label': c.favorite ? 'Quitar de favoritos' : 'Añadir a favoritos', 'aria-pressed': String(c.favorite),
    onclick: async (e) => { e.stopPropagation(); await api(`/api/library/${encodeURIComponent(c.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ favorite: !c.favorite }) }); c.favorite = !c.favorite; onChange?.(); } });
  const s = svg(STAR, 18); s.setAttribute('stroke', '#ffd27a'); s.setAttribute('fill', c.favorite ? '#ffd27a' : 'none'); star.append(s); box.append(star);
  box.append(h('span', { class: 'ov' }, h('span', { class: 'chip status-' + c.status, text: c.missing ? 'Archivo no encontrado' : STATUS[c.status] || c.status }), h('span', { class: 'chip', style: 'background:rgba(10,10,12,.82);color:#f2f2f4', text: fmtDur(c.duration || 0) })));
  const tags = h('div', { class: 'tags' }, (c.tags || []).map((t) => h('span', { class: 'tag', text: t })),
    h('button', { class: 'tagadd', type: 'button', text: '+ etiqueta', onclick: async () => { const t = prompt('Etiqueta para este clip (por ejemplo: humor, top, polémica):'); if (!t) return;
      await api(`/api/library/${encodeURIComponent(c.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tags: [...(c.tags || []), t] }) }); c.tags = [...(c.tags || []), t.trim()]; onChange?.(); } }));
  const del = h('button', { class: 'btn ghost', type: 'button', 'aria-label': 'Eliminar clip', onclick: () => askRemove(c, onChange) }, svg(TRASH, 16));
  return h('article', { class: 'clipcard' }, box, h('span', { class: 't', text: c.title }), h('span', { class: 'm', text: [fmtDate(c.created), c.score ? `relevancia ${Math.round(c.score)}` : ''].filter(Boolean).join(' · ') }), tags,
    h('div', { class: 'acts' }, h('button', { class: 'btn ghost', type: 'button', style: 'flex:1', text: 'Editar', onclick: () => openLibraryClip(c) }), del));
}

// --- delete with a clear choice -----------------------------------------------------------------------------------
async function askRemove(c, onChange) {
  const info = await api(`/api/library/${encodeURIComponent(c.id)}/files`).catch(() => ({ files: [] }));
  const mb = info.files.reduce((a, f) => a + f.mb, 0);
  $('removeTitle').textContent = `¿Eliminar «${c.title}»?`;
  $('removeFilesOpt').hidden = !info.files.length;
  $('removeFilesInfo').textContent = info.files.length ? `${info.files.length} archivo${info.files.length > 1 ? 's' : ''} · ${mb.toFixed(1)} MB. Se pueden recuperar durante 30 días; después se borran.` : '';
  $('removeNote').textContent = c.origin === 'video' ? 'El video del proyecto y su transcripción no se tocan: los usan sus otros clips.' : 'La transcripción y el resto del directo no se tocan.';
  document.querySelector('input[name="removeWhat"][value="record"]').checked = true;
  $('removeModal').hidden = false; $('removeCancel').focus();
  $('removeConfirm').onclick = async () => {
    const files = document.querySelector('input[name="removeWhat"]:checked').value === 'files';
    await api(`/api/library/${encodeURIComponent(c.id)}?files=${files}`, { method: 'DELETE' });
    $('removeModal').hidden = true;
    toast('Clip eliminado', files ? 'El archivo está en la papelera durante 30 días.' : 'Puedes recuperarlo desde «Papelera».',
      h('button', { class: 'btn ghost', type: 'button', text: 'Deshacer', onclick: async () => { await api(`/api/library/${encodeURIComponent(c.id)}/restore`, { method: 'POST' }); onChange?.(); } }));
    onChange?.();
  };
}
$('removeCancel').onclick = () => { $('removeModal').hidden = true; };
$('removeModal').addEventListener('keydown', (e) => { if (e.key === 'Escape') $('removeModal').hidden = true; });

// --- Inicio -------------------------------------------------------------------------------------------------------
async function renderHome() {
  const root = $('homeView'); put(root, h('p', { class: 'muted', text: 'Cargando…' }));
  const [lib, jobs, sessions] = await Promise.all([api('/api/library?sort=recent').catch(() => ({ items: [], channels: [], activity: [], total: 0 })), api('/api/jobs').catch(() => []), api('/api/live').catch(() => [])]);
  const hour = new Date().getHours();
  const hello = hour < 12 ? 'Buenos días' : hour < 19 ? 'Buenas tardes' : 'Buenas noches';
  const search = h('input', { 'aria-label': 'Buscar clips, streamers o proyectos', placeholder: 'Buscar clips, streamers o proyectos' });
  search.addEventListener('keydown', (e) => { if (e.key === 'Enter') { libState.q = search.value; navigate('library'); } });
  const running = sessions.filter((s) => ['starting', 'live', 'reconnecting'].includes(s.status));
  $('navLiveDot').hidden = !running.length;
  const thumbs = lib.items.slice(0, 4).map((c) => c.thumb_url);
  const pic = (urls) => h('div', { class: 'pic' }, urls.length ? urls.map((u) => h('img', { src: u, alt: '' })) : h('span', { class: 'noimg', text: '' }));
  put(root, 
    h('div', { class: 'home-hello' }, h('h1', {}, h('span', { class: 'hi', text: hello }), '¿Qué vamos a crear hoy?'), h('label', { class: 'search' }, svg('<circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path>', 16), search)),
    running.length ? h('div', {}, h('div', { class: 'section-head' }, h('span', { style: 'width:9px;height:9px;border-radius:50%;background:var(--live);animation:pulse 1.8s infinite' }), h('h2', { text: 'Directos en curso' }), h('span', { class: 'muted', text: 'ClipStudio los está siguiendo ahora mismo.' }), h('button', { class: 'btn ghost', type: 'button', text: 'Abrir clipping en vivo', onclick: () => navigate('live') })),
      h('div', { class: 'rail' }, running.map((s) => liveCard(s)))) : null,
    h('div', { class: 'grid quick' },
      h('button', { class: 'card hero', type: 'button', onclick: () => navigate('live') }, h('div', { class: 'pic one' }, h('img', { src: '/static/img/clipping-en-vivo.webp', alt: 'Clipping en vivo en YouTube y Kick' })), h('b', { text: 'Clipping en vivo' }), h('span', { text: 'Conecta un directo de Kick o YouTube Live y la IA encuentra los momentos mientras ocurren.' })),
      h('button', { class: 'card', type: 'button', onclick: () => navigate('analysis') }, pic(jobs.filter((j) => j.kind !== 'live').slice(0, 1).map((j) => `/api/jobs/${j.id}/frame?t=${Math.round(j.duration / 3)}`).concat(thumbs.slice(0, 1))), h('b', { text: 'Video largo a clips' }), h('span', { text: 'Importa de YouTube (hasta 200 min) o desde tu PC (hasta 120 min) y genera clips verticales.' })),
      h('button', { class: 'card', type: 'button', onclick: () => navigate('library') }, pic(thumbs), h('b', { text: 'Biblioteca' }), h('span', { text: `${lib.total} clips guardados de tus directos y videos.` })),
      h('button', { class: 'card', type: 'button', onclick: () => navigate('projects') }, pic(jobs.slice().sort((a, b) => b.updated - a.updated).slice(0, 4).map((j) => `/api/jobs/${j.id}/frame?t=${Math.round(j.duration / 3)}`)), h('b', { text: 'Proyectos' }), h('span', { text: `${jobs.length} proyectos. Retoma uno justo donde lo dejaste.` }))),
    continueCard(lib.items),
    lib.items.length ? h('div', {}, h('div', { class: 'section-head' }, h('h2', { text: 'Últimos clips' }), h('span', { class: 'muted', text: 'Pasa el cursor para ver la vista previa.' }), h('button', { class: 'btn ghost', type: 'button', text: 'Ver toda la biblioteca', onclick: () => navigate('library') })),
      h('div', { class: 'grid clips5' }, lib.items.slice(0, 5).map((c) => clipCard(c, renderHome)))) : h('div', { class: 'empty', text: 'Aún no hay clips. Empieza con un directo o un video largo.' }),
    h('div', { class: 'grid home-row', style: 'grid-template-columns:repeat(2,minmax(0,1fr))' },
      h('div', { class: 'card', style: 'padding:20px' }, h('h2', { text: 'Proyectos recientes', style: 'margin:0 0 12px;font-size:20px' }), jobs.slice().sort((a, b) => b.updated - a.updated).slice(0, 3).map(projectRow)),
      h('div', { class: 'card', style: 'padding:20px' }, h('h2', { text: 'Actividad', style: 'margin:0 0 12px;font-size:20px' }), lib.activity.length ? lib.activity.slice(0, 6).map((a) => h('div', { style: 'display:flex;gap:12px;margin-bottom:12px' }, h('span', { style: `width:8px;height:8px;border-radius:50%;margin-top:6px;flex:none;background:${a.kind === 'export' ? 'var(--blue)' : a.kind === 'remove' ? 'var(--amber)' : 'var(--green)'}` }), h('span', { style: 'display:flex;flex-direction:column;gap:2px' }, h('span', { text: a.text }), h('span', { class: 'muted', text: fmtDate(a.at) })))) : h('p', { class: 'muted', text: 'Aquí aparecerán tus análisis terminados, exportaciones y cambios.' })))
  );
}
function continueCard(items) {
  const last = items.filter((c) => c.status === 'edited' || c.status === 'draft').sort((a, b) => (b.updated || '').localeCompare(a.updated || ''))[0];
  if (!last) return null;
  return h('div', { class: 'card', style: 'padding:20px;display:flex;gap:18px;margin-bottom:30px;align-items:center' },
    h('div', { style: 'width:110px;flex:none;border-radius:12px;overflow:hidden;aspect-ratio:9/16' }, h('img', { src: last.thumb_url, alt: '', style: 'width:100%;height:100%;object-fit:cover' })),
    h('div', { style: 'display:flex;flex-direction:column;gap:8px;min-width:0' }, h('span', { class: 'muted', text: 'CONTINUAR DONDE LO DEJASTE', style: 'font-weight:600;letter-spacing:.06em' }), h('b', { text: last.title, style: 'font:600 22px var(--head)' }), h('span', { class: 'muted', text: `${last.channel} · ${fmtDur(last.duration || 0)} · ${STATUS[last.status]}` }),
      h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap' }, h('button', { class: 'btn primary', type: 'button', text: 'Seguir editando', onclick: () => openLibraryClip(last) }))));
}
function liveCard(s) {
  return h('article', { class: 'card livecard' },
    h('div', { style: 'position:relative;aspect-ratio:16/9;background:var(--panel2);overflow:hidden' }, h('img', { src: `/api/live/${s.id}/frame?t=${Date.now()}`, alt: `Imagen actual del directo de ${s.channel || ''}`, style: 'width:100%;height:100%;object-fit:cover;display:block', onerror: (e) => e.target.remove() }),
      h('span', { class: 'chip live', style: 'position:absolute;left:10px;top:10px', text: '● EN VIVO' }), h('span', { style: 'position:absolute;right:10px;top:12px' }, platformLogo(s.platform))),
    h('div', { style: 'padding:14px;display:flex;flex-direction:column;gap:4px' }, h('b', { text: s.channel || 'Directo', style: 'font:600 16px var(--head)' }), h('span', { class: 'muted', text: s.title || '' }), h('span', { class: 'muted', style: 'color:var(--green)', text: `${(s.moments || []).length} momentos detectados` })),
    h('div', { style: 'padding:0 14px 14px' }, h('button', { class: 'btn primary', type: 'button', style: 'width:100%', text: 'Abrir', onclick: () => { liveId = s.id; followLive(); navigate('live'); } })));
}
function projectRow(j) {
  const t = Math.round((j.duration || 0) / 3);
  const box = previewBox(`/api/jobs/${j.id}/frame?t=${t}`, `/api/jobs/${j.id}/video`, t, 8);
  return h('button', { class: 'list-row', type: 'button', onclick: () => openProject(j.id, null, j.clips ? 'editor' : 'analysis').catch((e) => toast('No se pudo abrir', e.message)) }, box,
    h('span', { style: 'display:flex;flex-direction:column;gap:4px;min-width:0' }, h('b', { text: j.title || j.name, style: 'font-size:14px' }), h('span', { class: 'muted', text: [j.channel, `${j.clips} clips`, j.updated ? ago(j.updated * 1000) : ''].filter(Boolean).join(' · ') })));
}

// --- Biblioteca -----------------------------------------------------------------------------------------------------
const libState = { q: '', origin: '', status: '', platform: '', channel: '', favorite: false, removed: false, sort: 'recent', dur: '', score: '' };
let libTimer = null;
async function renderLibrary() {
  const root = $('libraryView');
  const p = new URLSearchParams({ q: libState.q, origin: libState.origin, status: libState.status, platform: libState.platform, channel: libState.channel, favorite: libState.favorite, removed: libState.removed, sort: libState.sort });
  if (libState.dur === 'short') p.set('max_dur', 30); if (libState.dur === 'mid') { p.set('min_dur', 30); p.set('max_dur', 60); } if (libState.dur === 'long') p.set('min_dur', 60);
  if (libState.score) p.set('min_score', libState.score);
  const lib = await api('/api/library?' + p).catch((e) => ({ items: [], channels: [], total: 0, live: 0, video: 0, removed: 0, error: e.message }));
  const search = h('input', { value: libState.q, 'aria-label': 'Buscar en la biblioteca', placeholder: 'Buscar por título, lo que se dice o etiqueta' });
  search.addEventListener('input', () => { clearTimeout(libTimer); libTimer = setTimeout(() => { libState.q = search.value; renderLibrary().then(() => { const s = document.querySelector('#libraryView .search input'); s?.focus(); s?.setSelectionRange(s.value.length, s.value.length); }); }, 300); });
  const set = (k, v) => () => { libState[k] = v; renderLibrary(); };
  const pill = (label, k, v) => h('button', { class: 'pill' + (libState[k] === v ? ' on' : ''), type: 'button', text: label, onclick: set(k, v) });
  const select = (label, k, options) => { const s = h('select', { 'aria-label': label }, options.map(([v, t]) => h('option', { value: v, text: t, selected: libState[k] === v }))); s.onchange = () => { libState[k] = s.value; renderLibrary(); }; return s; };
  const people = h('div', { class: 'people' }, lib.channels.map((c) => {
    const sample = lib.items.find((i) => i.channel === c.channel);
    return h('button', { class: 'person' + (libState.channel === c.channel ? ' on' : ''), type: 'button', onclick: set('channel', libState.channel === c.channel ? '' : c.channel) },
      sample ? h('img', { class: 'av', src: sample.thumb_url, alt: '' }) : h('span', { class: 'av', text: (c.channel || '?').slice(0, 2).toUpperCase() }), h('span', { text: c.channel }), h('small', { text: `${c.n} clips` }));
  }));
  const groups = {};
  for (const c of lib.items) (groups[c.channel] ||= []).push(c);
  put(root, 
    h('div', { class: 'page-title' }, h('h1', { text: libState.removed ? 'Papelera' : 'Biblioteca de clips' }), h('span', { class: 'sub', text: libState.removed ? 'Clips quitados de la biblioteca. Puedes recuperarlos.' : `${lib.total} clips de directos y videos · guardados en tu PC, también después de cerrar la app` }), h('label', { class: 'search' }, search)),
    libState.removed ? null : people,
    h('div', { class: 'filters' },
      pill(`Todos · ${lib.total}`, 'origin', ''), pill(`Directos · ${lib.live}`, 'origin', 'live'), pill(`Videos · ${lib.video}`, 'origin', 'video'),
      select('Estado', 'status', [['', 'Estado: todos'], ['detected', 'Detectados'], ['draft', 'Borradores'], ['edited', 'Editados'], ['exported', 'Exportados']]),
      select('Plataforma', 'platform', [['', 'Plataforma: todas'], ['kick', 'Kick'], ['youtube', 'YouTube'], ['local', 'Archivos del PC']]),
      select('Duración', 'dur', [['', 'Duración: todas'], ['short', 'Hasta 30 s'], ['mid', '30–60 s'], ['long', 'Más de 60 s']]),
      select('Relevancia', 'score', [['', 'Relevancia: todas'], ['70', '70 o más'], ['80', '80 o más']]),
      h('button', { class: 'pill' + (libState.favorite ? ' on' : ''), type: 'button', text: 'Solo favoritos', onclick: set('favorite', !libState.favorite) }),
      select('Ordenar', 'sort', [['recent', 'Más recientes'], ['score', 'Más relevantes'], ['duration', 'Más largos'], ['title', 'Por título']]),
      h('span', { style: 'flex:1' }), h('button', { class: 'pill' + (libState.removed ? ' on' : ''), type: 'button', text: libState.removed ? '← Volver a la biblioteca' : `Papelera · ${lib.removed}`, onclick: set('removed', !libState.removed) })),
    lib.error ? h('div', { class: 'empty', text: lib.error }) : !lib.items.length ? h('div', { class: 'empty', text: libState.removed ? 'La papelera está vacía.' : 'No hay clips con estos filtros.' }) :
      Object.entries(groups).map(([name, items]) => h('section', { class: 'card lib-group' },
        h('div', { class: 'head' }, h('img', { src: items[0].thumb_url, alt: '', style: 'width:46px;height:46px;border-radius:50%;object-fit:cover;box-shadow:0 0 0 2px var(--green-line)' }), h('span', { style: 'display:flex;flex-direction:column' }, h('b', { text: name }), h('span', { class: 'muted', text: `${items.length} clips` })), platformLogo(items[0].platform)),
        h('div', { class: 'grid lib-grid' }, items.map((c) => libState.removed ? restoreCard(c) : clipCard(c, renderLibrary)))))
  );
}
function restoreCard(c) {
  return h('article', { class: 'clipcard' }, h('div', { class: 'hv', style: 'aspect-ratio:9/16;border-radius:12px' }, h('img', { src: c.thumb_url, alt: '' })), h('span', { class: 't', text: c.title }),
    h('button', { class: 'btn ghost', type: 'button', text: 'Recuperar', onclick: async () => { await api(`/api/library/${encodeURIComponent(c.id)}/restore`, { method: 'POST' }); toast('Clip recuperado', c.title); renderLibrary(); } }));
}

// --- Proyectos ------------------------------------------------------------------------------------------------------
const projState = { kind: '' };
async function renderProjects() {
  const root = $('projectsView');
  const jobs = (await api('/api/jobs').catch(() => [])).filter((j) => j.duration > 1).sort((a, b) => b.updated - a.updated);
  const shown = jobs.filter((j) => !projState.kind || (projState.kind === 'live' ? j.kind === 'live' : j.kind !== 'live'));
  const pill = (label, v) => h('button', { class: 'pill' + (projState.kind === v ? ' on' : ''), type: 'button', text: label, onclick: () => { projState.kind = v; renderProjects(); } });
  put(root, 
    h('div', { class: 'page-title' }, h('h1', { text: 'Proyectos' }), h('span', { class: 'sub', text: `${jobs.length} proyectos · pasa el cursor sobre uno para ver una vista previa` }), h('button', { class: 'btn primary', type: 'button', text: 'Nuevo proyecto', onclick: () => navigate('analysis') })),
    h('div', { class: 'filters' }, pill('Todos', ''), pill('Videos largos', 'video'), pill('Directos', 'live')),
    shown.length ? h('div', { class: 'grid projects' }, shown.map((j) => {
      const t = Math.round((j.duration || 0) / 3);
      const box = previewBox(`/api/jobs/${j.id}/frame?t=${t}`, `/api/jobs/${j.id}/video`, t, 8);
      box.append(h('span', { class: 'chip', style: 'position:absolute;left:12px;top:12px;z-index:2;background:rgba(10,10,12,.82);color:#f2f2f4' }, platformLogo(j.kind === 'live' ? 'kick' : j.kind), j.kind === 'live' ? 'Directo' : 'Video'),
        h('span', { class: 'chip', style: 'position:absolute;right:12px;top:12px;z-index:2;background:rgba(10,10,12,.82);color:#f2f2f4', text: fmtDur(j.duration) }),
        h('span', { class: 'hint', text: '▶ Vista previa · sin sonido' }));
      return h('button', { class: 'card pcard', type: 'button', onclick: () => openProject(j.id, null, j.clips ? 'editor' : 'analysis').catch((e) => toast('No se pudo abrir', e.message)) }, box,
        h('div', { class: 'body' }, h('b', { text: j.title || j.name }), h('span', { class: 'muted', text: [j.channel, j.updated ? ago(j.updated * 1000) : ''].filter(Boolean).join(' · ') }),
          h('span', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, h('span', { class: 'chip', style: 'background:var(--green-tint);color:#e2ffad', text: `${j.clips} clips` }), j.edited ? h('span', { class: 'chip', style: 'background:var(--raise);color:var(--muted)', text: `${j.edited} editados` }) : null)));
    })) : h('div', { class: 'empty', text: 'Todavía no hay proyectos de este tipo.' })
  );
}

// --- Clips en vivo: sessions per streamer ----------------------------------------------------------------------------
async function renderLiveHistory() {
  const sessions = await api('/api/live').catch(() => []);
  const byChannel = {};
  for (const s of sessions) (byChannel[s.channel || s.url] ||= []).push(s);
  put($('liveHistory'), 
    h('div', { class: 'section-head', style: 'margin-top:26px' }, h('h2', { text: 'Tus streamers y sesiones' }), h('span', { class: 'muted', text: 'Cada directo es una sesión independiente. Sus momentos siguen en la biblioteca aunque empieces otro.' })),
    Object.keys(byChannel).length ? h('div', { class: 'grid', style: 'grid-template-columns:repeat(auto-fill,minmax(280px,1fr))' }, Object.entries(byChannel).map(([name, list]) => {
      const total = list.reduce((a, s) => a + (s.moments || []).length, 0), active = list.find((s) => ['starting', 'live', 'reconnecting'].includes(s.status));
      return h('div', { class: 'card', style: 'padding:16px;display:flex;flex-direction:column;gap:10px' },
        h('div', { style: 'display:flex;align-items:center;gap:10px' }, h('b', { text: name, style: 'font:600 17px var(--head);flex:1' }), platformLogo(list[0].platform), active ? h('span', { class: 'chip live', text: 'EN VIVO' }) : null),
        h('span', { class: 'muted', text: `${list.length} sesiones · ${total} momentos` }),
        list.slice(0, 4).map((s) => h('button', { class: 'list-row', type: 'button', style: 'padding:8px 10px', onclick: () => { liveId = s.id; followLive(); window.scrollTo({ top: 0, behavior: 'smooth' }); } },
          h('span', { style: 'display:flex;flex-direction:column;gap:2px' }, h('span', { text: s.title || 'Directo', style: 'font-size:13px;font-weight:600' }), h('span', { class: 'muted', text: `${fmtDate(s.created)} · ${(s.moments || []).length} momentos · ${({ live: 'en vivo', stopped: 'detenida', interrupted: 'interrumpida', ended: 'terminada' })[s.status] || s.status}` })))),
        h('button', { class: 'btn ghost', type: 'button', text: 'Ver sus clips en la biblioteca', onclick: () => { libState.channel = list[0].channel || ''; navigate('library'); } }));
    })) : h('div', { class: 'empty', text: 'Todavía no has hecho clipping en vivo.' }));
}

// --- Clips en vivo (prototype layout) ---------------------------------------------------------------------------
// The existing controls (link field, start/stop/resume, the config modal) move into the new layout; their handlers in
// app.js keep working. paintLive(s) from app.js still runs and also feeds this view.
const liveUI = { view: 'grid', sort: 'recent', picked: new Set(), session: null, frameTimer: null };
function buildLiveLayout() {
  if ($('liveConnect')) return;
  const host = $('liveHost'); $('livePanel').style.display = 'none';
  const url = $('liveUrl'); url.placeholder = 'Pega el enlace del directo: kick.com/canal o youtube.com/@canal/live';
  const connect = h('div', { id: 'liveConnect', class: 'card live-connect' },
    h('label', { class: 'search big' }, svg('<circle cx="12" cy="12" r="2.5"></circle><path d="M7.5 7.5a6.4 6.4 0 0 0 0 9M16.5 7.5a6.4 6.4 0 0 1 0 9"></path>', 20), url),
    h('div', { class: 'live-buttons' }, $('liveStart'), $('liveStop'), $('liveResume')),
    h('p', { class: 'muted', style: 'margin:0', text: 'Usa directos públicos y respeta los derechos del creador y las normas de Kick y YouTube. ClipStudio no evita restricciones de acceso, inicios de sesión ni DRM.' }));
  const now = h('div', { id: 'liveNow', class: 'live-now', hidden: true },
    h('div', { class: 'card live-stage' },
      h('div', { class: 'live-frame' }, h('img', { id: 'liveFrame', alt: 'Imagen actual del directo' }), h('span', { class: 'scan', 'aria-hidden': 'true' }),
        h('div', { class: 'live-chips' }, h('span', { id: 'liveBadge', class: 'chip live', text: 'EN VIVO' }), h('span', { id: 'livePlatform' }), h('span', { id: 'liveClock', class: 'chip glass' })),
        h('span', { class: 'chip glass live-note', text: 'Imagen de la grabación local · se actualiza cada pocos segundos' })),
      h('div', { class: 'live-who' }, h('b', { id: 'liveWho' }), h('span', { id: 'liveTitle', class: 'muted' }), h('span', { id: 'liveConn', class: 'live-conn' }))),
    h('div', { class: 'live-side' },
      h('div', { class: 'card live-stats' }, ['liveStatMoments:momentos detectados', 'liveStatReady:clips listos', 'liveStatBuffer:búfer guardado', 'liveStatLang:subtítulos'].map((x) => { const [id, label] = x.split(':'); return h('div', {}, h('b', { id }), h('span', { text: label })); })),
      h('div', { class: 'card live-ai' }, h('span', { class: 'lbl', text: 'Actividad de la IA' }), h('div', { class: 'live-ai-row' }, h('span', { class: 'bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i')), h('span', { id: 'liveAiDevice' })),
        h('span', { id: 'liveAiMessage', class: 'muted' }), h('span', { id: 'liveAiText', class: 'live-quote' }))));
  const moments = h('section', { id: 'liveMomentsBox', hidden: true },
    h('div', { class: 'section-head', style: 'margin-top:26px' }, h('h2', { text: 'Momentos de esta sesión' }), h('span', { id: 'liveMomentsCount', class: 'muted' }),
      h('div', { class: 'seg', role: 'group', 'aria-label': 'Ordenar' }, [['recent', 'Recientes'], ['score', 'Relevancia'], ['duration', 'Duración']].map(([v, t]) => h('button', { type: 'button', 'data-sort': v, text: t, onclick: () => { liveUI.sort = v; paintLiveMoments(); } }))),
      h('div', { class: 'seg', role: 'group', 'aria-label': 'Vista' }, [['grid', 'Cuadrícula'], ['list', 'Lista']].map(([v, t]) => h('button', { type: 'button', 'data-lview': v, text: t, onclick: () => { liveUI.view = v; paintLiveMoments(); } })))),
    h('div', { id: 'liveBatch', class: 'card live-batch', hidden: true }, h('b', { id: 'liveBatchLabel' }), h('span', { style: 'flex:1' }),
      h('button', { class: 'btn ghost', type: 'button', text: 'Añadir etiqueta', onclick: () => batchLive('tag') }), h('button', { class: 'btn ghost', type: 'button', text: 'Favoritos', onclick: () => batchLive('fav') }),
      h('button', { class: 'btn danger', type: 'button', text: 'Descartar', onclick: () => batchLive('discard') }), h('button', { class: 'btn ghost', type: 'button', text: 'Cancelar', onclick: () => { liveUI.picked.clear(); paintLiveMoments(); } })),
    h('div', { id: 'liveMomentGrid' }));
  host.prepend(connect, now, moments);
}
const momentId = (sid, mid) => `live:${sid}:${mid}`;
function paintLiveView(s) {
  buildLiveLayout(); liveUI.session = s;
  const running = ['starting', 'live', 'reconnecting'].includes(s.status);
  $('liveNow').hidden = false; $('liveMomentsBox').hidden = !s.moments.length;
  $('liveBadge').textContent = running ? 'EN VIVO' : ({ stopped: 'DETENIDA', ended: 'TERMINADO', interrupted: 'INTERRUMPIDA', error: 'ERROR', stopping: 'DETENIENDO' })[s.status] || s.status.toUpperCase();
  $('liveBadge').className = 'chip ' + (running ? 'live' : 'glass');
  $('livePlatform').replaceChildren(platformLogo(s.platform) || ''); $('livePlatform').className = 'chip glass logo';
  $('liveClock').textContent = mmss(s.media_s);
  $('liveWho').textContent = s.channel || 'Directo'; $('liveTitle').textContent = s.title || '';
  $('liveConn').textContent = running ? (s.status === 'reconnecting' ? 'Reconectando…' : `Conexión estable · ${s.reconnects} reconexiones`) : 'Sesión guardada · sus momentos siguen en la biblioteca';
  $('liveConn').classList.toggle('ok', running && s.status !== 'reconnecting');
  const ready = s.moments.filter((m) => ['draft', 'opened'].includes(m.status)).length;
  $('liveStatMoments').textContent = s.moments.length; $('liveStatReady').textContent = ready;
  $('liveStatBuffer').textContent = `${s.buffer_minutes} min`; $('liveStatLang').textContent = ({ es: 'Español', en: 'Inglés', pt: 'Portugués', fr: 'Francés', it: 'Italiano', de: 'Alemán' })[s.language] || s.language;
  $('liveAiDevice').textContent = !running ? 'Sin actividad: la sesión no está en curso' : s.transcription_device ? `Transcribiendo · ${s.transcription_device}` : 'Preparando la transcripción…';
  document.querySelector('.live-ai .bars').classList.toggle('paused', !running);
  $('liveAiMessage').textContent = s.message || ''; $('liveAiText').textContent = s.recent_text ? `«…${s.recent_text}»` : '';
  clearTimeout(liveUI.frameTimer);
  const refresh = () => { const img = $('liveFrame'); const next = new Image(); next.onload = () => { img.src = next.src; }; next.src = `/api/live/${s.id}/frame?t=${Date.now()}`; if (running && current === 'live') liveUI.frameTimer = setTimeout(refresh, 5000); };
  refresh();
  paintLiveMoments();
}
function paintLiveMoments() {
  const s = liveUI.session; if (!s) return;
  for (const b of document.querySelectorAll('[data-sort]')) b.classList.toggle('on', b.dataset.sort === liveUI.sort);
  for (const b of document.querySelectorAll('[data-lview]')) b.classList.toggle('on', b.dataset.lview === liveUI.view);
  const list = s.moments.slice();
  if (liveUI.sort === 'recent') list.reverse(); else if (liveUI.sort === 'score') list.sort((a, b) => (b.score || 0) - (a.score || 0)); else list.sort((a, b) => b.duration - a.duration);
  $('liveMomentsCount').textContent = `${s.moments.length} momentos · pasa el cursor para verlos, toca uno para seleccionarlo`;
  for (const id of [...liveUI.picked]) if (!s.moments.some((m) => m.id === id)) liveUI.picked.delete(id);
  $('liveBatch').hidden = !liveUI.picked.size; $('liveBatchLabel').textContent = liveUI.picked.size === 1 ? '1 clip seleccionado' : `${liveUI.picked.size} clips seleccionados`;
  const grid = $('liveMomentGrid'); grid.className = liveUI.view === 'grid' ? 'grid live-grid' : 'live-list';
  put(grid, list.map((m) => liveUI.view === 'grid' ? momentCard(s, m) : momentRow(s, m)));
}
function momentCard(s, m) {
  if (m.status === 'rendering') return h('div', { class: 'card mcard preparing' }, h('div', { class: 'thumb9' }, h('span', { class: 'bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i')), h('span', { class: 'muted', text: 'Preparando el clip…' })), h('b', { class: 't', text: m.title }), h('span', { class: 'muted', text: `Detectado ${m.detected_at}` }));
  const id = momentId(s.id, m.id), picked = liveUI.picked.has(m.id);
  const box = previewBox(`/api/library/${encodeURIComponent(id)}/thumb`, `/api/live/${s.id}/moments/${m.id}/video`, 3, m.duration);
  box.classList.add('thumb9');
  if (m.score != null) box.append(h('span', { class: 'chip score', text: String(Math.round(m.score)) }));
  box.append(h('span', { class: 'chip glass dur', text: fmtDur(m.duration) }));
  const card = h('div', { class: 'card mcard' + (picked ? ' sel' : ''), role: 'button', tabindex: '0', 'aria-pressed': String(picked),
    onclick: () => { picked ? liveUI.picked.delete(m.id) : liveUI.picked.add(m.id); paintLiveMoments(); },
    onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.click(); } } }, box,
    h('b', { class: 't', text: m.title }), h('span', { class: 'muted', text: `${m.detected_at} · ${m.status === 'opened' ? 'Abierto en el editor' : 'Listo'}` }),
    h('div', { class: 'acts' }, h('button', { class: 'btn primary', type: 'button', text: 'Editar', onclick: (e) => { e.stopPropagation(); openMoment(s, m); } }),
      h('button', { class: 'btn ghost', type: 'button', text: 'Descartar', onclick: (e) => { e.stopPropagation(); discardMoment(s, m); } })));
  return card;
}
function momentRow(s, m) {
  return h('div', { class: 'live-row' }, h('img', { src: `/api/library/${encodeURIComponent(momentId(s.id, m.id))}/thumb`, alt: '', loading: 'lazy' }), h('b', { text: m.title, style: 'flex:1;min-width:0' }),
    h('span', { class: 'muted', text: fmtDur(m.duration) }), h('span', { class: 'muted', text: m.detected_at }), h('span', { class: 'muted', text: m.score != null ? `relevancia ${Math.round(m.score)}` : '' }),
    m.status === 'rendering' ? h('span', { class: 'muted', text: 'Preparando…' }) : h('button', { class: 'btn ghost', type: 'button', text: 'Editar', onclick: () => openMoment(s, m) }));
}
async function openMoment(s, m) {
  try { const j = await api(`/api/live/${s.id}/moments/${m.id}/open`, { method: 'POST' }); await openProject(j.id); } catch (e) { toast('No se pudo abrir el momento', e.message); }
}
async function discardMoment(s, m) {
  try { paintLive(await api(`/api/live/${s.id}/moments/${m.id}/discard`, { method: 'POST' })); toast('Momento descartado', 'Sigue guardado en la papelera de la biblioteca.'); } catch (e) { toast('No se pudo descartar', e.message); }
}
async function batchLive(action) {
  const s = liveUI.session; const ids = [...liveUI.picked]; if (!s || !ids.length) return;
  let tag = null; if (action === 'tag') { tag = prompt('Etiqueta para los clips seleccionados:'); if (!tag) return; }
  for (const mid of ids) {
    const cid = encodeURIComponent(momentId(s.id, mid));
    if (action === 'discard') await api(`/api/live/${s.id}/moments/${mid}/discard`, { method: 'POST' }).catch(() => {});
    else { await api('/api/library?origin=live').catch(() => {}); await api(`/api/library/${cid}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(action === 'fav' ? { favorite: true } : { tags: [tag] }) }).catch(() => {}); }
  }
  liveUI.picked.clear(); toast(action === 'discard' ? 'Momentos descartados' : 'Clips actualizados', `${ids.length} clips`);
  followLive();
}
const basePaintLive = paintLive;
window.paintLive = (s) => { basePaintLive(s); try { paintLiveView(s); } catch (e) { console.warn(e); } };
paintLive = window.paintLive;
// openJob (used by the old live cards) now lands in the editor with the moment selected.
const baseOpenJob = openJob;
window.openJob = (j) => { baseOpenJob(j); if (job?.clips?.length) { choose(job.clips[0]); navigate('editor'); } };
openJob = window.openJob;

// --- Editor (prototype layout) ----------------------------------------------------------------------------------
// Same controls and handlers as before; the layout is rearranged: breadcrumb header with the main actions, tabs in the
// order Formato · Título · Subtítulos · Logo · Exportar, clips with thumbnails and a subtitle timeline.
function buildEditorLayout() {
  if ($('editorCrumb')) return;
  const heading = document.querySelector('#editorView .editor-heading');
  heading.querySelector('h1').remove();
  heading.firstElementChild.prepend(h('span', { id: 'editorCrumb', class: 'muted' }), h('h1', { id: 'editorClipTitle', text: 'Editor' }));
  const actions = h('div', { class: 'editor-actions' },
    h('button', { class: 'btn ghost', type: 'button', text: 'Ver en grande', onclick: () => $('expandPreview').click() }),
    h('button', { class: 'btn ghost', type: 'button', text: 'Comprobar MP4', onclick: () => $('renderCheck').click() }),
    h('button', { class: 'btn primary', type: 'button', id: 'headExport', text: 'Exportar clip', onclick: () => $('export').click() }));
  heading.append(actions);
  // Tabs: «Encuadre» becomes «Formato» and goes first; a new «Exportar» tab gathers resolution and download.
  const tabs = document.querySelector('#editorView [data-tab="frame"]').parentElement;
  const frame = tabs.querySelector('[data-tab="frame"]'); frame.textContent = 'Formato'; tabs.prepend(frame);
  const exportTab = h('button', { 'data-tab': 'export', type: 'button', role: 'tab', 'aria-selected': 'false', text: 'Exportar' });
  exportTab.className = [...frame.classList].filter((c) => c !== 'active').join(' '); tabs.append(exportTab);
  const framePanel = $('tab-frame');
  const panel = h('div', { id: 'tab-export', class: 'tab-panel hidden' }, h('h2', { text: 'Exportar el clip' }));
  const res = $('resolution'); const resLabel = res.previousElementSibling;
  panel.append(resLabel, res, h('p', { class: 'muted', id: 'exportWhere' }),
    h('button', { class: 'btn primary', type: 'button', style: 'width:100%;margin-top:10px', text: '↓ Exportar ahora', onclick: () => $('export').click() }),
    h('button', { class: 'btn ghost', type: 'button', style: 'width:100%;margin-top:8px', text: 'Comprobar el MP4 antes', onclick: () => $('renderCheck').click() }),
    h('p', { class: 'muted', text: 'Se guarda en la carpeta de exportados con un nombre legible y la biblioteca lo marca como «Exportado».' }));
  framePanel.parentElement.append(panel);
  exportTab.addEventListener('click', () => {
    for (const b of document.querySelectorAll('[data-tab]')) { b.classList.toggle('active', b === exportTab); b.setAttribute('aria-selected', String(b === exportTab)); }
    for (const p of document.querySelectorAll('.tab-panel')) p.classList.toggle('hidden', p.id !== 'tab-export');
  });
  // Subtitle timeline under the preview: click to jump; the playhead follows playback.
  $('seek').after(h('div', { id: 'cueTimeline', class: 'cue-timeline', 'aria-label': 'Línea de tiempo de subtítulos',
    onclick: (e) => { const r = e.currentTarget.getBoundingClientRect(); const d = Number($('end').value) - Number($('start').value); $('video').currentTime = Number($('start').value) + d * (e.clientX - r.left) / r.width; } }));
  new MutationObserver(decorateClipList).observe($('clips'), { childList: true });
}
function libraryIdFor(clipId) { return job?.live ? `live:${job.live.session}:${job.live.moment}` : `job:${job?.id}:${clipId}`; }
function decorateClipList() {
  for (const el of document.querySelectorAll('#clips .clip')) {
    if (el.querySelector('.clip-thumb') || !el.dataset.id) continue;
    el.prepend(h('img', { class: 'clip-thumb', src: `/api/library/${encodeURIComponent(libraryIdFor(el.dataset.id))}/thumb`, alt: '', loading: 'lazy', onerror: (e) => e.target.remove() }));
  }
}
let cueSignature = '';
function paintTimeline() {
  const box = $('cueTimeline'); if (!box || !selected) return;
  const d = Math.max(.1, Number($('end').value) - Number($('start').value));
  const sig = d + '|' + cues.map((c) => c.start + ':' + c.end + ':' + c.text).join('|');
  if (sig !== cueSignature) {
    cueSignature = sig;
    put(box, cues.map((c) => h('span', { class: 'cue', title: c.text, text: c.text, style: `left:${(c.start / d) * 100}%;width:${Math.max(.8, ((c.end - c.start) / d) * 100)}%` })), h('span', { class: 'playhead' }));
  }
  const t = Math.max(0, Math.min(d, $('video').currentTime - Number($('start').value)));
  box.querySelector('.playhead').style.left = (t / d * 100) + '%';
}
function paintEditorHeader() {
  if (!job || !selected) return;
  const channel = job.live?.channel || job.youtube?.channel || 'Mis videos';
  $('editorCrumb').textContent = `Biblioteca › ${channel} · se guarda automáticamente`;
  $('editorClipTitle').textContent = $('title').value || selected.title || 'Clip';
  $('exportWhere').textContent = `Destino: exportados › ${channel}`;
}
const baseChoose = choose;
window.choose = (c) => { buildEditorLayout(); baseChoose(c); cueSignature = ''; paintEditorHeader(); paintTimeline(); };
choose = window.choose;
const basePaintTime = paintTime;
window.paintTime = () => { basePaintTime(); try { paintTimeline(); } catch {} };
paintTime = window.paintTime;
$('title').addEventListener('input', () => paintEditorHeader());
buildEditorLayout();

// --- Configuración --------------------------------------------------------------------------------------------------
function renderSettings() {
  const host = $('settingsHost'); const panel = $('perfPanel');
  if (panel && panel.parentElement !== host) { host.append(panel); }
  panel?.classList.remove('hidden'); try { loadPerformance(); } catch {}
}

// --- side panel: GPU status -----------------------------------------------------------------------------------------
api('/api/capabilities').then((c) => { const gpu = c?.gpu?.name || c?.gpu_name || ''; $('sideEquipText').textContent = gpu ? `${gpu} · IA local` : 'Procesamiento local'; }).catch(() => {});

// New moments while clipping: a discreet notification, without polling more than the live panel already does.
let knownMoments = null;
setInterval(async () => {
  if (document.hidden) return;
  const sessions = await api('/api/live').catch(() => null); if (!sessions) return;
  const running = sessions.filter((s) => ['starting', 'live', 'reconnecting'].includes(s.status));
  $('navLiveDot').hidden = !running.length;
  const ids = new Set(running.flatMap((s) => (s.moments || []).map((m) => s.id + m.id)));
  if (knownMoments) for (const s of running) for (const m of s.moments || []) if (!knownMoments.has(s.id + m.id))
    toast('Nuevo candidato a clip', `${s.channel || 'Directo'} · ${m.title || ''}`, h('button', { class: 'btn primary', type: 'button', text: 'Ver', onclick: () => { liveId = s.id; followLive(); navigate('live'); } }));
  knownMoments = ids;
}, 15000);

let start = 'home'; try { start = localStorage.getItem('cs.view') || 'home'; } catch {}
navigate(start === 'editor' ? 'home' : start);
})();
