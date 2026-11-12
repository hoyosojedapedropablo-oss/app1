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
// «Editor» from the menu with no clip open: the last clip you edited (or the newest one) opens in the editor.
async function openLastClip() {
  toast('Abriendo tu último clip…', 'Continúas donde lo dejaste.');
  try {
    const lib = await api('/api/library?sort=recent');
    const items = lib.items.filter((c) => !c.missing);
    const last = items.filter((c) => c.status === 'edited' || c.status === 'draft').sort((a, b) => (b.updated || '').localeCompare(a.updated || ''))[0] || items[0];
    if (!last) { toast('Aún no tienes clips', 'Empieza con un directo o un video largo.'); navigate('home'); return; }
    await openLibraryClip(last);
    if (current !== 'editor' && job) navigate('editor');
  } catch (e) { toast('No se pudo abrir el editor', e.message); navigate('library'); }
}
// «Atrás»: the sections you came through, newest last. Going to the section on top of the trail counts as going back.
const VIEW_LABEL = { home: 'Inicio', analysis: 'Videos largos', live: 'Clips en vivo', library: 'Biblioteca', editor: 'Editor', projects: 'Proyectos', settings: 'Configuración' };
const navTrail = []; let navReady = false, navBacking = false;
function navigate(name) {
  if (!VIEWS.includes(name)) name = 'home';
  if (name === 'editor' && !job) { openLastClip(); return; }      // «Editor» with nothing open: continue with the last clip
  if (navReady && !navBacking && name !== current) {
    if (navTrail[navTrail.length - 1] === name) navTrail.pop(); else { navTrail.push(current); if (navTrail.length > 40) navTrail.shift(); }
  }
  navReady = true;
  current = name;
  try { paintBack(); } catch {}
  if (name !== 'live') { try { stopLivePlayer(); } catch {} }
  try { silenceOutside(name); } catch {}
  for (const v of VIEWS) $(v + 'View')?.classList.toggle('hidden', v !== name);
  for (const b of document.querySelectorAll('#sideNav button')) b.classList.toggle('on', b.dataset.view === name);
  window.scrollTo({ top: 0 });
  ({ home: renderHome, library: renderLibrary, projects: renderProjects, live: () => { buildLiveLayout(); renderLiveHistory(); if (liveId && !liveDismissed(liveId)) followLive(); else showLiveRecs(); }, settings: renderSettings })[name]?.();
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
// The «Atrás» button, at the left of the top bar: back to the section you were in before (also Alt + ← and the mouse's
// back button). Hidden when there is nowhere to go back to.
function goBack() {
  const prev = navTrail.pop(); if (!prev) { paintBack(); return; }
  const b = $('navBack'); if (b) { b.classList.remove('pressed'); void b.offsetWidth; b.classList.add('pressed'); }
  navBacking = true; try { navigate(prev); } finally { navBacking = false; }
}
function paintBack() {
  const b = $('navBack'); if (!b) return;
  const prev = navTrail[navTrail.length - 1];
  b.hidden = !prev; document.body.classList.toggle('has-back', !!prev);
  if (!prev) return;
  if ($('navBackTo').textContent !== VIEW_LABEL[prev]) { $('navBackTo').textContent = VIEW_LABEL[prev]; b.classList.remove('swap'); void b.offsetWidth; b.classList.add('swap'); }
  b.title = `Volver a ${VIEW_LABEL[prev]} (Alt + ←)`; b.setAttribute('aria-label', `Atrás: volver a ${VIEW_LABEL[prev]}`);
}
{
  const back = h('button', { id: 'navBack', class: 'nav-back', type: 'button', hidden: true, onclick: goBack },
    h('span', { class: 'nb-orb', 'aria-hidden': 'true' }, h('span', { class: 'nb-ring' }), svg('<path d="M14.5 5.5L8 12l6.5 6.5"></path><path class="nb-tail" d="M8.5 12H19"></path>', 20)),
    h('span', { class: 'nb-text' }, h('b', { text: 'Atrás' }), h('small', {}, 'a ', h('span', { id: 'navBackTo' }))),
    h('span', { class: 'nb-sheen', 'aria-hidden': 'true' }));
  // Top-left corner of the page content, pinned while scrolling (a zero-height sticky dock: it takes no room itself).
  document.querySelector('main').prepend(h('div', { class: 'back-dock' }, back));
  document.addEventListener('keydown', (e) => {
    if (e.altKey && e.key === 'ArrowLeft' && !e.ctrlKey && !e.metaKey && !document.querySelector('.cs-modal:not([hidden]), .modal:not(.hidden)')) { e.preventDefault(); goBack(); }
  });
  // The mouse's back button: stay in the app and go back one section (instead of leaving the page).
  window.addEventListener('mouseup', (e) => { if (e.button === 3 && navTrail.length) { e.preventDefault(); goBack(); } });
}

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

// --- Sound: one thing plays with sound at a time ------------------------------------------------------------------
// Videos with sound (editor, big previews, the live preview, the official Kick/YouTube player) used to keep playing
// when another started or when you changed screen, with nothing to stop them. Now the newest one wins.
// A video that is no longer on the page can never play: it would be heard with nothing on screen to stop it (that was
// the sound left playing «por toda la app» after a preview). Stopping one also cancels its download.
function stopMedia(m) { try { m.pause(); m.removeAttribute('src'); m.load(); } catch {} }
{
  const realPlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function (...args) {
    if (!this.isConnected) { try { this.pause(); } catch {} return Promise.resolve(); }
    return realPlay.apply(this, args);
  };
  // Removed while playing (a panel closed, a list repainted): stop it at once.
  new MutationObserver((changes) => {
    for (const c of changes) for (const n of c.removedNodes) {
      if (n.nodeType !== 1) continue;
      const media = n.matches?.('video,audio') ? [n] : [...(n.querySelectorAll?.('video,audio') || [])];
      for (const m of media) if (!m.isConnected && !m.paused) m.pause();
    }
  }).observe(document.body, { childList: true, subtree: true });
}
function muteLivePlayer() { livePlayer.muted = true; paintLiveSound(); }
// The button and the videos always agree: what the button says is what you hear.
function paintLiveSound() {
  for (const v of document.querySelectorAll('.live-vid')) v.muted = livePlayer.muted;
  if ($('liveSound')) $('liveSound').textContent = livePlayer.muted ? '🔇 Activar sonido' : '🔊 Silenciar';
}
function silenceOthers(keep) {
  for (const m of document.querySelectorAll('video,audio')) {
    if (m === keep || m.paused || m.muted) continue;
    if (m.classList.contains('live-vid')) { if (!keep?.classList?.contains('live-vid')) muteLivePlayer(); continue; }   // the live chain keeps going, silent
    m.pause();
  }
  if (!keep?.closest?.('.player-box')) document.querySelectorAll('.player-box').forEach((b) => b.closest('.cs-modal')?.remove());
}
function silenceOutside(view) {
  hideBigPreview(); document.querySelectorAll('.clip-modal').forEach((m) => { m.querySelectorAll('video').forEach(stopMedia); m.remove(); });
  document.querySelectorAll('.player-box').forEach((b) => b.closest('.cs-modal')?.remove());
  const host = $(view + 'View');
  for (const m of document.querySelectorAll('video,audio')) if (!m.paused && !host?.contains(m)) m.pause();
}
for (const ev of ['play', 'volumechange']) document.addEventListener(ev, (e) => {
  const m = e.target;
  if (m instanceof HTMLMediaElement && !m.paused && !m.muted && m.volume > 0) silenceOthers(m);
}, true);
// Watchdog, every second: a preview whose card is gone closes; a video that sounds where you cannot see it (another
// screen, a closed panel, a hidden element) stops; the live preview keeps the button's choice.
setInterval(() => {
  const panel = $('bigPreview');
  if (panel && panel._card && !panel._card.isConnected) hideBigPreview();
  for (const m of document.querySelectorAll('video,audio')) {
    if (m.classList.contains('live-vid')) { if (m.muted !== livePlayer.muted) m.muted = livePlayer.muted; if (current !== 'live' && !m.paused) m.pause(); continue; }
    if (!m.paused && !m.muted && !m.getClientRects().length && !m.closest('.clip-modal')) m.pause();
  }
}, 1000);
// A covered or background window keeps its sound (you can listen to a stream while doing something else): Chrome
// reports such a window as hidden, and stopping the sound there was the «sound lost after a few minutes».

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

// The clip-like thumbnail is made in the background: until it is ready the server answers with a plain 16:9 frame,
// so a landscape image means «ask again in a few seconds».
function retryThumb(img, url) {
  let tries = 0;
  img.addEventListener('load', () => { if (img.naturalWidth > img.naturalHeight && tries < 8) { tries++; setTimeout(() => { img.src = `${url}${url.includes('?') ? '&' : '?'}r=${Date.now()}`; }, 2500 + tries * 1000); } });
}
// Big preview on hover: the whole clip as it will be published (format and title), muted, without opening the editor.
let hoverTimer = null, hoverFor = null;
function showBigPreview(c, card) {
  hideBigPreview(); hoverFor = c.id;
  // With sound: the user has already clicked in the app, so browsers allow it; if one refuses, it plays muted.
  const video = h('video', { playsinline: true, loop: true, preload: 'auto' }); video.muted = false;
  const wait = h('div', { class: 'bp-wait' }, h('span', { class: 'bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i')), h('span', { text: 'Preparando la vista previa…' }));
  const panel = h('div', { id: 'bigPreview', class: 'big-preview', role: 'dialog', 'aria-label': `Vista previa de ${c.title}` },
    h('div', { class: 'bp-frame' }, h('img', { src: c.thumb_url, alt: '' }), video, wait),
    h('div', { class: 'bp-info' }, h('b', { text: c.title }), h('span', { class: 'muted', text: `${c.channel} · ${fmtDur(c.duration || 0)}` }),
      h('div', { class: 'bp-actions' },
        h('button', { class: 'btn ghost bp-sound', type: 'button', text: '🔇 Silenciar', onclick: (e) => { e.stopPropagation(); video.muted = !video.muted; e.target.textContent = video.muted ? '🔊 Con sonido' : '🔇 Silenciar'; } }),
        h('button', { class: 'btn primary bp-big', type: 'button', text: '⤢ Ver en grande', onclick: (e) => { e.stopPropagation(); openClipModal(c); } }))));
  panel.querySelector('.bp-frame').addEventListener('click', () => openClipModal(c));
  panel.addEventListener('mouseleave', () => hideBigPreview());
  panel._card = card;
  document.body.append(panel);
  const r = card.getBoundingClientRect(), w = panel.offsetWidth, hgt = panel.offsetHeight;
  const left = r.right + 16 + w < innerWidth ? r.right + 16 : Math.max(16, r.left - 16 - w);
  panel.style.left = left + 'px'; panel.style.top = Math.max(16, Math.min(innerHeight - hgt - 16, r.top + r.height / 2 - hgt / 2)) + 'px';
  video.addEventListener('canplay', () => {
    if (!panel.isConnected) { stopMedia(video); return; }      // the cursor left before it was ready: never play it
    wait.remove(); panel.classList.add('ready');
    video.play().catch(() => { video.muted = true; panel.querySelector('.bp-sound').textContent = '🔊 Con sonido'; video.play().catch(() => {}); });
  }, { once: true });
  video.addEventListener('error', () => { wait.querySelector('span:last-child').textContent = 'No se pudo preparar la vista previa'; });
  video.src = `/api/library/${encodeURIComponent(c.id)}/preview.mp4`;
}
function hideBigPreview() { clearTimeout(hoverTimer); hoverFor = null; document.querySelectorAll('#bigPreview').forEach((p) => { p.querySelectorAll('video').forEach(stopMedia); p.remove(); }); }
// --- Clip preview, centred: the clip comes to the middle, everything behind it blurs (Biblioteca, Inicio, directo) ---
// Hover to preview, robust to lists that repaint (the live moments repaint every 3 s and used to lose the hover):
// cards only register what they show; one listener follows the pointer and opens what is under it after a short
// pause, with a ring on the card that fills while it waits.
const previewCards = new Map();
function hoverPreview(box, c, onEdit) { box.dataset.preview = c.id; previewCards.set(c.id, { c, onEdit }); }
{
  let armed = null, pointer = { x: 0, y: 0 };
  const cardAt = () => document.elementFromPoint(pointer.x, pointer.y)?.closest?.('[data-preview]');
  const disarm = () => { clearTimeout(hoverTimer); armed?.classList.remove('arming'); armed = null; };
  document.addEventListener('pointermove', (e) => {
    pointer = { x: e.clientX, y: e.clientY };
    if (document.querySelector('.clip-modal')) return;
    const card = e.target.closest?.('[data-preview]');
    if (card && armed && card.dataset.preview === armed.dataset.preview) {     // the same clip, maybe repainted: keep waiting
      if (card !== armed) { armed.classList.remove('arming'); card.classList.add('arming'); armed = card; }
      return;
    }
    if (!card && !armed) return;
    disarm(); if (!card || Date.now() - modalClosedAt < 900) return;
    armed = card; card.classList.add('arming');
    hoverTimer = setTimeout(() => {
      const now = cardAt(); const id = armed?.dataset.preview; disarm();
      if (!now || now.dataset.preview !== id || document.querySelector('.clip-modal')) return;   // the cursor moved away
      const entry = previewCards.get(id); if (entry) openClipModal(entry.c, entry.onEdit);
    }, 450);
  }, { passive: true });
  document.addEventListener('pointerdown', disarm, true);
  document.addEventListener('scroll', disarm, { passive: true, capture: true });
}
// After closing, a clip under the cursor does not open it again by itself (move to another clip, or click).
let modalClosedAt = 0;
function openClipModal(c, onEdit) {
  if (document.querySelector(`.clip-modal[data-id="${CSS.escape(c.id)}"]`)) return;      // already open for this clip
  hideBigPreview(); document.querySelectorAll('.clip-modal').forEach((m) => m.remove());
  const video = h('video', { playsinline: true, loop: true, preload: 'auto' }); video.muted = false;
  const wait = h('div', { class: 'bp-wait' }, h('span', { class: 'bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i')), h('span', { text: 'Preparando la vista previa…' }));
  const playBtn = h('button', { class: 'pv-play', type: 'button', 'aria-label': 'Reproducir' }, svg('<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"></path>', 34));
  const bar = h('i'); const progress = h('div', { class: 'cm-progress', title: 'Ir a este punto' }, bar);
  const sound = h('button', { class: 'cm-sound', type: 'button', title: 'Sonido', text: '🔊' });
  const frame = h('div', { class: 'cm-frame' }, h('img', { src: c.thumb_url, alt: '' }), video, wait, playBtn, sound, progress);
  const close = () => { modalClosedAt = Date.now(); stopMedia(video); modal.classList.remove('in'); modal.classList.add('out'); setTimeout(() => modal.remove(), 220); };
  const modal = h('div', { class: 'clip-modal', 'data-id': c.id, role: 'dialog', 'aria-modal': 'true', 'aria-label': `Vista previa de ${c.title}`, onclick: (e) => { if (e.target === modal) close(); } },
    h('div', { class: 'cm-box' },
      h('button', { class: 'theater-x', type: 'button', title: 'Cerrar (Esc)', 'aria-label': 'Cerrar la vista previa', text: '×', onclick: close }),
      frame,
      h('div', { class: 'cm-foot' }, h('span', { class: 'tf-text' }, h('b', { text: c.title }), h('span', { class: 'muted', text: [c.channel, fmtDur(c.duration || 0)].filter(Boolean).join(' · ') })),
        h('button', { class: 'btn ghost', type: 'button', text: 'Editar', onclick: () => { close(); (onEdit ? onEdit() : openLibraryClip(c))?.catch?.(() => {}); } }),
        h('button', { class: 'btn primary', type: 'button', text: '↓ Exportar', onclick: (e) => downloadClip(c, e.currentTarget) }))));
  const toggle = () => { if (video.paused) video.play().catch(() => {}); else video.pause(); };
  frame.addEventListener('click', (e) => { if (e.target === video || e.target === frame || e.target === playBtn || playBtn.contains(e.target)) toggle(); });
  sound.addEventListener('click', (e) => { e.stopPropagation(); video.muted = !video.muted; sound.textContent = video.muted ? '🔇' : '🔊'; });
  progress.addEventListener('click', (e) => { e.stopPropagation(); const r = progress.getBoundingClientRect(); if (video.duration) video.currentTime = video.duration * (e.clientX - r.left) / r.width; });
  video.addEventListener('play', () => frame.classList.add('is-playing')); video.addEventListener('pause', () => frame.classList.remove('is-playing'));
  video.addEventListener('timeupdate', () => { if (video.duration) bar.style.width = `${(video.currentTime / video.duration) * 100}%`; });
  video.addEventListener('canplay', () => {
    if (!modal.isConnected) { stopMedia(video); return; }
    wait.remove(); frame.classList.add('ready');
    video.play().catch(() => { video.muted = true; sound.textContent = '🔇'; video.play().catch(() => {}); });
  }, { once: true });
  video.addEventListener('error', () => { wait.querySelector('span:last-child').textContent = 'No se pudo preparar la vista previa'; });
  modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); else if (e.key === ' ' && !(e.target instanceof HTMLButtonElement)) { e.preventDefault(); toggle(); } });
  document.body.append(modal); modal.tabIndex = -1; modal.focus();
  requestAnimationFrame(() => requestAnimationFrame(() => modal.classList.add('in')));
  video.src = `/api/library/${encodeURIComponent(c.id)}/preview.mp4`;
}
async function downloadClip(c, button) {
  button.disabled = true; const label = button.textContent; button.textContent = '…';
  toast('Preparando la descarga', `«${c.title}» en alta calidad (1080 × 1920). Puede tardar unos segundos.`);
  try {
    const r = await request(`/api/library/${encodeURIComponent(c.id)}/export`, jsonOptions({ resolution: 1080 }));
    const blob = await r.blob(), url = URL.createObjectURL(blob), a = document.createElement('a');
    const name = decodeURIComponent((r.headers.get('content-disposition') || '').match(/filename\*?=(?:utf-8'')?"?([^";]+)/i)?.[1] || 'clip.mp4');
    a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
    toast('Clip descargado', name);
  } catch (e) { toast('No se pudo descargar', e.message); }
  finally { button.disabled = false; button.textContent = label; }
}
function clipCard(c, onChange) {
  const box = previewBox(c.thumb_url, null, clipStart(c), c.duration);
  const thumbImg = box.querySelector('img'); if (thumbImg) retryThumb(thumbImg, c.thumb_url);
  box.addEventListener('click', () => { clearTimeout(hoverTimer); hideBigPreview(); openLibraryClip(c); });
  if (!c.missing) {
    hoverPreview(box, c);
  }
  const star = h('button', { class: 'star', type: 'button', 'aria-label': c.favorite ? 'Quitar de favoritos' : 'Añadir a favoritos', 'aria-pressed': String(c.favorite),
    onclick: async (e) => { e.stopPropagation(); await api(`/api/library/${encodeURIComponent(c.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ favorite: !c.favorite }) }); c.favorite = !c.favorite; onChange?.(); } });
  const s = svg(STAR, 18); s.setAttribute('stroke', '#ffd27a'); s.setAttribute('fill', c.favorite ? '#ffd27a' : 'none'); star.append(s); box.append(star);
  box.append(h('span', { class: 'ov' }, h('span', { class: 'chip status-' + c.status, text: c.missing ? 'Archivo no encontrado' : STATUS[c.status] || c.status }), h('span', { class: 'chip', style: 'background:rgba(10,10,12,.82);color:#f2f2f4', text: fmtDur(c.duration || 0) })));
  const tags = h('div', { class: 'tags' }, (c.tags || []).map((t) => h('span', { class: 'tag', text: t })),
    h('button', { class: 'tagadd', type: 'button', text: '+ etiqueta', onclick: async () => { const t = prompt('Etiqueta para este clip (por ejemplo: humor, top, polémica):'); if (!t) return;
      await api(`/api/library/${encodeURIComponent(c.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tags: [...(c.tags || []), t] }) }); c.tags = [...(c.tags || []), t.trim()]; onChange?.(); } }));
  const del = h('button', { class: 'btn ghost', type: 'button', 'aria-label': 'Eliminar clip', onclick: () => askRemove(c, onChange) }, svg(TRASH, 16));
  if (c.score) box.append(scoreBadge(c.score, c.viral_kind, true));
  return h('article', { class: 'clipcard' + (c.score >= 85 ? ' on-fire' : '') }, box, h('span', { class: 't', text: c.title }), h('span', { class: 'm', text: fmtDate(c.created) }), tags,
    h('div', { class: 'acts' }, h('button', { class: 'btn ghost', type: 'button', style: 'flex:1', text: 'Editar', onclick: () => openLibraryClip(c) }),
      c.missing ? null : h('button', { class: 'btn primary', type: 'button', title: 'Descargar en alta calidad (1080 × 1920)', 'aria-label': 'Descargar en alta calidad', text: '↓', onclick: (e) => downloadClip(c, e.currentTarget) }), del));
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
  const [lib, jobs, sessions, people, featured] = await Promise.all([api('/api/library?sort=recent').catch(() => ({ items: [], channels: [], activity: [], total: 0 })), api('/api/jobs').catch(() => []), api('/api/live').catch(() => []), loadStreamers(), api('/api/streamers/featured').catch(() => [])]);
  const discover = (people || []).length < 4 ? await api('/api/streamers/featured?all=true').catch(() => []) : [];
  clearInterval(homeTimer); homeTimer = setInterval(refreshHomeLive, 60000);
  setTimeout(() => fillYoutubeLive(featured || []), 0);      // after the page is drawn: its search can take a few seconds
  const hour = new Date().getHours();
  const hello = hour < 12 ? 'Buenos días' : hour < 19 ? 'Buenas tardes' : 'Buenas noches';
  const search = h('input', { 'aria-label': 'Buscar clips, streamers o proyectos', placeholder: 'Buscar clips, streamers o proyectos' });
  search.addEventListener('keydown', (e) => { if (e.key === 'Enter') { libState.q = search.value; navigate('library'); } });
  const running = sessions.filter((s) => ['starting', 'live', 'reconnecting'].includes(s.status));
  $('navLiveDot').hidden = !running.length;
  const thumbs = lib.items.filter((c) => !c.missing).slice(0, 4).map((c) => c.thumb_url);
  const pic = (urls) => h('div', { class: 'pic' }, urls.length ? urls.map((u) => h('img', { src: u, alt: '', onerror: (e) => e.target.remove() })) : h('span', { class: 'noimg', text: '' }));
  put(root, 
    homeHero(hello, search, people || [], featured || [], lib, jobs),
    h('div', { id: 'homeLive' }, homeLiveSections(people || [], featured || [], discover)),
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
// --- Inicio: who is live now (people you follow + recommended), refreshed every minute ----------------------------
let homeTimer = null;
async function refreshHomeLive() {
  if (current !== 'home' || document.hidden || !$('homeLive')) return;
  const [people, featured] = await Promise.all([loadStreamers(), api('/api/streamers/featured').catch(() => [])]);
  const discover = people.length < 4 ? await api('/api/streamers/featured?all=true').catch(() => []) : [];
  if (current === 'home' && $('homeLive')) { put($('homeLive'), homeLiveSections(people, featured, discover)); fillYoutubeLive(featured); }
}
const followUrl = (url) => api('/api/streamers/follow', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) });
async function followStreamer(s, button) {
  if (button) { button.disabled = true; button.textContent = '…'; }
  try {
    await followUrl(s.url);
    toast(`Sigues a ${s.name}`, s.live ? 'Ya aparece en «En vivo ahora».' : 'Aparecerá en «En vivo ahora» cuando empiece un directo.');
    refreshHomeLive(); setTimeout(refreshHomeLive, 4000);     // the first live check runs in the background
  } catch (e) { toast('No se pudo seguir', e.message); if (button) { button.disabled = false; button.textContent = '+ Seguir'; } }
}
async function unfollowStreamer(s) {
  if (!confirm(`¿Dejar de seguir a ${s.name}? Sus clips y tu configuración para este canal se conservan.`)) return;
  try { await api(`/api/streamers/${encodeURIComponent(s.key)}`, { method: 'DELETE' }); toast(`Ya no sigues a ${s.name}`, 'Sus clips siguen en la biblioteca.'); refreshHomeLive(); }
  catch (e) { toast('No se pudo cambiar', e.message); }
}
// «En vivo en YouTube»: the Spanish-speaking live streams with the biggest audience now, plus recommended channels live.
async function fillYoutubeLive(featured, boxId = 'homeYoutube') {
  const box = $(boxId); if (!box) return;
  const found = await api('/api/streamers/youtube-live').catch(() => []);
  if (!$(boxId)) return;
  const seen = new Set(streamersCache.map((s) => s.key)), rows = [];
  for (const s of [...found, ...featured.filter((x) => x.platform === 'youtube')]) if (!seen.has(s.key)) { seen.add(s.key); rows.push(s); }
  rows.sort((a, b) => (Number(b.viewers) || 0) - (Number(a.viewers) || 0));
  box.hidden = !rows.length;
  put(box, h('div', { class: 'section-head' }, h('span', { class: 'pulse-dot' }), h('h2', { text: 'En vivo en YouTube' }),
      h('span', { class: 'muted', text: 'Los directos en español con más audiencia ahora mismo en YouTube. Clipéalos o síguelos.' }), platformLogo('youtube')),
    h('div', { class: 'rail' }, rows.map((s, i) => streamCard(s, i === 0 && Number(s.viewers) > 10000 ? '🔥 El más visto ahora' : 'En vivo · YouTube', true))));
}
const compact = (n) => Number(n) >= 1e6 ? `${(Number(n) / 1e6).toLocaleString('es', { maximumFractionDigits: 1 })} M` : Number(n) >= 1e3 ? `${Math.round(Number(n) / 1e3)} mil` : String(n);
const SEARCH_ICON = '<circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path>';
function homeHero(hello, search, people, featured, lib, jobs) {
  const live = people.filter((s) => s.live).concat(featured).filter((s) => s.thumb).slice(0, 3);
  const liveCount = people.filter((s) => s.live).length + featured.length;
  return h('section', { class: 'home-hero' },
    h('div', { class: 'hero-glow', 'aria-hidden': 'true' }),
    h('div', { class: 'hero-text' }, h('span', { class: 'hi', text: hello }),
      h('h1', {}, '¿Qué vamos a ', h('span', { class: 'grad', text: 'crear' }), ' hoy?'),
      h('p', { class: 'muted', text: 'Convierte directos y videos largos en clips verticales listos para publicar, con IA local y sin pagar APIs.' }),
      h('label', { class: 'search' }, svg(SEARCH_ICON, 16), search),
      h('div', { class: 'hero-stats' },
        h('button', { class: 'stat', type: 'button', onclick: () => $('homeLive')?.scrollIntoView({ behavior: 'smooth' }) }, h('span', { class: 'pulse-dot' }), h('b', { text: String(liveCount) }), h('span', { text: 'en directo ahora' })),
        h('button', { class: 'stat', type: 'button', onclick: () => navigate('library') }, h('b', { text: String(lib.total) }), h('span', { text: 'clips guardados' })),
        h('button', { class: 'stat', type: 'button', onclick: () => navigate('projects') }, h('b', { text: String(jobs.length) }), h('span', { text: 'proyectos' })))),
    h('div', { class: 'hero-wall' + (live.length ? '' : ' empty') }, live.length
      ? live.map((s, i) => h('button', { class: 'wall-tile t' + i, type: 'button', title: `Ver a ${s.name}`, onclick: () => watchStream(s) },
          h('img', { src: s.thumb, alt: `Directo de ${s.name}`, referrerpolicy: 'no-referrer', onerror: (e) => e.target.closest('.wall-tile')?.remove() }),
          h('span', { class: 'chip live', text: '● EN VIVO' }),
          h('span', { class: 'wall-who' }, avatarImg(s, 26, 'var(--live)'), h('b', { text: s.name }), s.viewers ? h('span', { text: compact(s.viewers) }) : null)))
      : h('img', { class: 'wall-banner', src: '/static/img/clipping-en-vivo.webp', alt: 'Clipping en vivo en YouTube y Kick' })));
}
function homeLiveSections(people, featured, discover) {
  const live = people.filter((s) => s.live);
  const head = (title, note, extra, dot) => h('div', { class: 'section-head' }, dot ? h('span', { class: 'pulse-dot' }) : null, h('h2', { text: title }), h('span', { class: 'muted', text: note }), extra || null);
  const offline = discover.filter((s) => !s.live);
  return [
    // People you follow: photo with a red ring when live; × to stop following
    h('div', { class: 'following' },
      head('Siguiendo', people.length ? `${people.length} streamers y canales · los que están en directo van primero.` : 'Sigue a tus streamers de Kick y canales de YouTube para ver aquí cuándo están en directo.',
        h('button', { class: 'btn ghost', type: 'button', text: '+ Seguir streamer o canal', onclick: followDialog })),
      h('div', { class: 'follow-strip' }, people.length
        ? people.map((s) => h('div', { class: 'follow-pill' + (s.live ? ' is-live' : '') },
            h('button', { class: 'fp-main', type: 'button', title: s.live ? `Ver a ${s.name} en directo` : `${s.name} no está en directo`, onclick: () => s.live ? watchStream(s) : toast(`${s.name} no está en directo`, 'Aparecerá en «En vivo ahora» cuando empiece.') },
              h('span', { class: 'fp-photo' }, avatarImg(s, 60, s.live ? 'var(--live)' : '#2f2f36'), s.live ? h('span', { class: 'chip live mini', text: 'EN VIVO' }) : null),
              h('b', { text: s.name }), h('span', { class: 'fp-plat' }, platformLogo(s.platform))),
            h('button', { class: 'fp-x', type: 'button', title: `Dejar de seguir a ${s.name}`, 'aria-label': `Dejar de seguir a ${s.name}`, text: '×', onclick: () => unfollowStreamer(s) })))
        : h('button', { class: 'follow-empty', type: 'button', onclick: followDialog }, h('span', { class: 'fe-plus', text: '+' }), h('b', { text: 'Sigue a tu primer streamer' }), h('span', { class: 'muted', text: 'Busca por nombre o pega su enlace de Kick o YouTube.' })))),
    // Live now among the people you follow
    live.length ? h('div', {}, head('En vivo ahora', 'Tus streamers en directo. Los que más clipeas van primero.', h('button', { class: 'btn ghost', type: 'button', text: 'Abrir clipping en vivo', onclick: () => navigate('live') }), true),
      h('div', { class: 'rail' }, live.map((s, i) => streamCard(s, i === 0 && s.clips ? '★ El que más clipeas' : '')))) : null,
    // Recommended streams live right now: Kick, and next to it YouTube (filled as soon as its search answers)
    featured.some((s) => s.platform !== 'youtube') ? h('div', {}, head('Recomendados en Kick', 'Los streamers de Kick con más audiencia que están en directo ahora. Síguelos para tenerlos siempre aquí.', platformLogo('kick'), true),
      h('div', { class: 'rail' }, featured.filter((s) => s.platform !== 'youtube').map((s) => streamCard(s, s.lang === 'es' ? 'Recomendado · Español' : 'Recomendado', true)))) : null,
    h('div', { id: 'homeYoutube', hidden: true }),
    // To follow, while you follow few
    offline.length ? h('div', {}, head('Descubre streamers', 'Los más vistos de Kick y YouTube. Síguelos y aparecerán aquí en cuanto estén en directo.'),
      h('div', { class: 'discover' }, offline.slice(0, 12).map((s) => h('div', { class: 'disc-card' }, avatarImg(s, 64), h('b', { text: s.name }),
        h('span', { class: 'muted disc-meta' }, platformLogo(s.platform), s.followers ? h('span', { text: `${compact(s.followers)} seguidores` }) : null),
        h('button', { class: 'btn ghost', type: 'button', text: '+ Seguir', onclick: (e) => followStreamer(s, e.currentTarget) }))))) : null,
  ];
}
// «Seguir streamer o canal»: search by name on Kick and YouTube, or paste a link.
function followDialog() {
  const input = h('input', { placeholder: 'Nombre del streamer o enlace de Kick / YouTube', 'aria-label': 'Nombre o enlace del streamer' });
  const list = h('div', { class: 'follow-results' }, h('p', { class: 'muted', text: 'Escribe al menos 2 letras. Se busca en Kick y en YouTube.' }));
  const modal = h('div', { class: 'cs-modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Seguir streamer o canal', onclick: (e) => { if (e.target === modal) modal.remove(); } },
    h('div', { class: 'box follow-box' },
      h('div', { style: 'display:flex;align-items:center;gap:12px' }, h('h2', { text: 'Seguir streamer o canal', style: 'margin:0;flex:1' }), h('button', { class: 'btn ghost', type: 'button', text: 'Cerrar', onclick: () => modal.remove() })),
      h('label', { class: 'search' }, svg(SEARCH_ICON, 16), input), list));
  modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') modal.remove(); });
  let timer = null, token = 0;
  input.addEventListener('input', () => {
    clearTimeout(timer); const q = input.value.trim(); if (q.length < 2) return;
    const isLink = /^https?:|kick\.com\/|youtu/i.test(q);
    timer = setTimeout(async () => {
      const mine = ++token; put(list, h('p', { class: 'muted', text: `Buscando «${q}» en Kick y YouTube…` }));
      const groups = await Promise.all((isLink ? ['link'] : ['kick', 'youtube']).map((sc) => api(`/api/streamers/search?scope=${sc}&q=${encodeURIComponent(q)}`).catch(() => [])));
      if (mine !== token) return;
      const found = groups.flat(); const known = new Set(streamersCache.map((s) => s.key));
      put(list, found.length ? found.slice(0, 10).map((s) => h('div', { class: 'streamer-row' }, avatarImg(s, 48),
          h('span', { style: 'display:flex;flex-direction:column;gap:3px;min-width:0;flex:1' },
            h('span', { style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' }, h('b', { text: s.name }), s.live ? h('span', { class: 'chip live', text: '● EN VIVO' }) : null, platformLogo(s.platform)),
            h('span', { class: 'muted', text: s.followers ? `${compact(s.followers)} seguidores` : s.platform === 'kick' ? 'Kick' : 'YouTube' })),
          known.has(s.key) ? h('span', { class: 'chip glass', text: '✓ Siguiendo' })
            : h('button', { class: 'btn primary', type: 'button', text: '+ Seguir', onclick: async (e) => { const b = e.currentTarget; await followStreamer(s, b); b.replaceWith(h('span', { class: 'chip glass', text: '✓ Siguiendo' })); loadStreamers(); } })))
        : h('p', { class: 'muted', text: 'Sin resultados. Prueba con otro nombre o pega el enlace del canal.' }));
    }, isLink ? 0 : 300);
  });
  document.body.append(modal); input.focus();
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
const libState = { q: '', origin: '', status: '', platform: '', channel: '', favorite: false, removed: false, sort: 'recent', dur: '', score: '', expanded: {} };
// One row per streamer at first (more when a single streamer is chosen); «Ver más» opens 18 more each time.
const libLimit = (name, items) => libState.expanded[name] || (libState.channel ? 12 : 6);
let libTimer = null;
async function renderLibrary() {
  const root = $('libraryView');
  const p = new URLSearchParams({ q: libState.q, origin: libState.origin, status: libState.status, platform: libState.platform, channel: libState.channel, favorite: libState.favorite, removed: libState.removed, sort: libState.sort });
  if (libState.dur === 'short') p.set('max_dur', 30); if (libState.dur === 'mid') { p.set('min_dur', 30); p.set('max_dur', 60); } if (libState.dur === 'long') p.set('min_dur', 60);
  if (libState.score) p.set('min_score', libState.score);
  const [lib] = await Promise.all([api('/api/library?' + p).catch((e) => ({ items: [], channels: [], total: 0, live: 0, video: 0, removed: 0, error: e.message })), loadStreamers()]);
  const search = h('input', { value: libState.q, 'aria-label': 'Buscar en la biblioteca', placeholder: 'Buscar por título, lo que se dice o etiqueta' });
  search.addEventListener('input', () => { clearTimeout(libTimer); libTimer = setTimeout(() => { libState.q = search.value; renderLibrary().then(() => { const s = document.querySelector('#libraryView .search input'); s?.focus(); s?.setSelectionRange(s.value.length, s.value.length); }); }, 300); });
  const set = (k, v) => () => { libState[k] = v; renderLibrary(); };
  const pill = (label, k, v) => h('button', { class: 'pill' + (libState[k] === v ? ' on' : ''), type: 'button', text: label, onclick: set(k, v) });
  const select = (label, k, options) => { const s = h('select', { 'aria-label': label }, options.map(([v, t]) => h('option', { value: v, text: t, selected: libState[k] === v }))); s.onchange = () => { libState[k] = s.value; renderLibrary(); }; return s; };
  const people = h('div', { class: 'people' }, lib.channels.map((c) => {
    const sample = lib.items.find((i) => i.channel === c.channel);
    return h('button', { class: 'person' + (libState.channel === c.channel ? ' on' : ''), type: 'button', onclick: set('channel', libState.channel === c.channel ? '' : c.channel) },
      streamerFor(c.channel)?.avatar ? h('img', { class: 'av', src: streamerFor(c.channel).avatar, alt: '' }) : sample ? h('img', { class: 'av', src: sample.thumb_url, alt: '' }) : h('span', { class: 'av', text: (c.channel || '?').slice(0, 2).toUpperCase() }),
      h('span', { text: c.channel }), h('small', { text: streamerFor(c.channel)?.live ? '● en vivo' : `${c.n} clips`, style: streamerFor(c.channel)?.live ? 'color:var(--live);font-weight:600' : '' }));
  }));
  const groups = {};
  for (const c of lib.items) (groups[c.channel] ||= []).push(c);
  if (!libState.removed) warmPreviews(Object.values(groups).flatMap((items) => items.slice(0, 6)));
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
        h('div', { class: 'head' }, h('img', { src: streamerFor(name)?.avatar || items[0].thumb_url, alt: '', style: 'width:46px;height:46px;border-radius:50%;object-fit:cover;box-shadow:0 0 0 2px var(--green-line)' }), h('span', { style: 'display:flex;flex-direction:column' }, h('b', { text: name }), h('span', { class: 'muted', text: `${items.length} clips` })), platformLogo(items[0].platform)),
        h('div', { class: 'grid lib-grid' }, items.slice(0, libLimit(name, items)).map((c) => libState.removed ? restoreCard(c) : clipCard(c, renderLibrary))),
        items.length > libLimit(name, items) ? h('div', { class: 'more-row' }, h('button', { class: 'btn ghost', type: 'button', text: `Ver más · ${items.length - libLimit(name, items)} clips más`, onclick: () => { libState.expanded[name] = libLimit(name, items) + 18; renderLibrary(); } }))
          : libState.expanded[name] ? h('div', { class: 'more-row' }, h('button', { class: 'btn ghost', type: 'button', text: 'Ver menos', onclick: () => { delete libState.expanded[name]; renderLibrary(); } })) : null))
  );
}
function warmPreviews(items) {
  const ids = items.filter((c) => !c.missing).map((c) => c.id).slice(0, 24);
  if (ids.length) api('/api/library/previews/warm', jsonOptions({ ids })).catch(() => {});
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
        list.slice(0, 4).map((s) => h('button', { class: 'list-row', type: 'button', style: 'padding:8px 10px', onclick: () => { undismissLive(s.id); liveId = s.id; followLive(); window.scrollTo({ top: 0, behavior: 'smooth' }); } },
          h('span', { style: 'display:flex;flex-direction:column;gap:2px' }, h('span', { text: s.title || 'Directo', style: 'font-size:13px;font-weight:600' }), h('span', { class: 'muted', text: `${fmtDate(s.created)} · ${(s.moments || []).length} momentos · ${({ live: 'en vivo', stopped: 'detenida', interrupted: 'interrumpida', ended: 'terminada' })[s.status] || s.status}` })))),
        h('button', { class: 'btn ghost', type: 'button', text: 'Ver sus clips en la biblioteca', onclick: () => { libState.channel = list[0].channel || ''; navigate('library'); } }));
    })) : h('div', { class: 'empty', text: 'Todavía no has hecho clipping en vivo.' }));
}

// --- Clips en vivo: the control room -----------------------------------------------------------------------------
// The existing controls (link field, start/stop/resume, the config modal) move into the new layout; their handlers in
// app.js keep working. paintLive(s) from app.js still runs and also feeds this view.
// On air bar (who, title, live clock, signal) · stage with the «momentómetro» (every moment on the session timeline,
// coloured by its note) · the stream's temperature · the AI pipeline as it works · the best moment so far.
const liveUI = { view: 'grid', sort: 'recent', tier: 'all', picked: new Set(), session: null, frameTimer: null, feed: [], feedFor: null };
const LIVE_RUNNING = ['starting', 'live', 'reconnecting'];
const emo = (n, cls = 'em') => h('img', { class: cls, src: EMOJI(n), alt: '', 'aria-hidden': 'true' });
const HEAT_RING = '<svg viewBox="0 0 120 120" aria-hidden="true"><circle class="heat-bg" cx="60" cy="60" r="52"></circle><circle class="heat-val" cx="60" cy="60" r="52"></circle></svg>';
function buildLiveLayout() {
  if ($('liveConnect')) return;
  const host = $('liveHost'); $('livePanel').style.display = 'none';
  const url = $('liveUrl'); url.placeholder = 'Pega el enlace del directo: kick.com/canal o youtube.com/@canal/live';
  const connect = h('div', { id: 'liveConnect', class: 'card live-connect' },
    h('label', { class: 'search big' }, svg('<circle cx="12" cy="12" r="2.5"></circle><path d="M7.5 7.5a6.4 6.4 0 0 0 0 9M16.5 7.5a6.4 6.4 0 0 1 0 9"></path>', 20), url),
    h('div', { class: 'live-buttons' }, $('liveStart')),
    h('p', { class: 'muted', style: 'margin:0', text: 'Usa directos públicos y respeta los derechos del creador y las normas de Kick y YouTube. ClipStudio no evita restricciones de acceso, inicios de sesión ni DRM.' }));
  // «Detener sesión» sits in the on air bar, red, with a stop icon: the one button that ends the live session.
  $('liveStop').replaceChildren(h('span', { class: 'stop-ic', 'aria-hidden': 'true' }, h('i')), 'Detener sesión'); $('liveStop').title = 'Deja de grabar el directo. Los momentos ya encontrados se conservan.';
  $('liveResume').textContent = '↻ Reanudar';
  // Once the session is stopped: × takes it off the screen (it stays saved) and the recommended streams appear.
  const close = h('button', { id: 'liveClose', class: 'live-close', type: 'button', hidden: true, title: 'Quitar esta transmisión de la pantalla',
      'aria-label': 'Quitar esta transmisión de la pantalla. Sus momentos se conservan.', onclick: dismissLive },
    h('span', { class: 'lc-ring', 'aria-hidden': 'true' }), h('span', { class: 'lc-core' }, svg('<path d="M7 7l10 10M17 7L7 17"></path>', 18)),
    h('span', { class: 'lc-tip', 'aria-hidden': 'true', text: 'Quitar de la pantalla' }));
  const recs = h('section', { id: 'liveRecs', class: 'live-recs', hidden: true, 'aria-label': 'Directos recomendados' });
  const ring =h('div', { id: 'liveHeat', class: 'heat-ring' }); ring.innerHTML = HEAT_RING;
  ring.append(h('div', { class: 'heat-core' }, h('img', { id: 'liveHeatEmoji', class: 'em', alt: '' }), h('b', { id: 'liveHeatNum', text: '—' })));
  const tile = (icon, id, label) => h('div', { class: 'ltile' }, emo(icon), h('b', { id, text: '0' }), h('span', { text: label }));
  const now = h('div', { id: 'liveNow', class: 'live-now', hidden: true },
    h('div', { class: 'onair' },
      h('span', { id: 'liveAvatar', class: 'onair-av' }),
      h('div', { class: 'onair-who' }, h('div', { class: 'onair-name' }, h('b', { id: 'liveWho' }), h('span', { id: 'livePlatform' })), h('span', { id: 'liveTitle' })),
      h('div', { class: 'onair-meta' },
        h('span', { class: 'onair-clock' }, h('small', { id: 'liveClockLabel', text: 'En directo' }), h('b', { id: 'liveClock', text: '0:00' })),
        h('span', { id: 'liveBadge', class: 'onair-pill' }),
        h('span', { id: 'liveConn', class: 'live-conn' })),
      h('div', { class: 'onair-actions' }, $('liveStop'), $('liveResume'), close)),
    h('div', { class: 'card live-stage' },
      h('div', { class: 'live-frame' }, h('img', { id: 'liveFrame', alt: 'Imagen actual del directo' }), h('span', { class: 'scan', 'aria-hidden': 'true' }), h('span', { class: 'vignette', 'aria-hidden': 'true' }),
        h('div', { class: 'live-chips' }, h('span', { id: 'liveRec', class: 'chip glass rec' }, h('i'), 'REC'), h('span', { id: 'liveDelay', class: 'chip glass', text: 'Unos segundos de retraso' })),
        h('div', { id: 'liveFrameCtrl', class: 'frame-ctrl' })),
      h('div', { class: 'meter' },
        h('div', { class: 'meter-head' }, h('span', { class: 'lbl-s' }, emo('satellite'), 'Momentómetro'), h('span', { id: 'meterHint', class: 'muted' })),
        h('div', { id: 'liveMeter', class: 'meter-track' }),
        h('div', { class: 'meter-scale' }, h('span', { id: 'meterStart', text: '0:00' }), h('span', { id: 'meterBuffer' }), h('span', { id: 'meterEnd' })))),
    h('div', { class: 'live-side' },
      h('div', { class: 'card heat' }, ring,
        h('div', { class: 'heat-text' }, h('span', { class: 'lbl-s', text: 'Temperatura del directo' }), h('b', { id: 'liveHeatLabel' }), h('span', { id: 'liveHeatHint', class: 'muted' }))),
      h('div', { class: 'live-tiles' }, tile('clapper', 'liveStatMoments', 'momentos'), tile('check', 'liveStatReady', 'listos'), tile('fire', 'liveStatFire', 'en llamas'), tile('stopwatch', 'liveStatBuffer', 'de búfer')),
      h('div', { class: 'card live-ai' },
        h('div', { class: 'ai-head' }, h('span', { class: 'lbl-s', text: 'Así trabaja la IA ahora' }), h('span', { class: 'bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'))),
        h('div', { id: 'livePipe', class: 'pipe' }, [['mic', 'Escucha'], ['brain', 'Transcribe'], ['scale', 'Juzga'], ['clapper', 'Corta']].map(([e, t], i) => h('div', { class: 'pipe-step', 'data-step': String(i) }, h('span', { class: 'pipe-ic' }, emo(e), h('i', { class: 'pipe-check', 'aria-hidden': 'true' })), h('span', { class: 'pipe-lbl', text: t })))),
        h('span', { id: 'liveAiDevice', class: 'ai-device' }),
        h('div', { class: 'ai-quote' }, emo('speech', 'em q'), h('span', { id: 'liveAiText', class: 'live-quote' })),
        h('ul', { id: 'liveFeed', class: 'ai-feed' }),
        h('span', { id: 'liveAiMessage', hidden: true }),
        h('span', { class: 'muted ai-lang' }, 'Subtítulos en ', h('b', { id: 'liveStatLang' })))));
  const moments = h('section', { id: 'liveMomentsBox', hidden: true },
    h('div', { id: 'liveSpot' }),
    h('div', { class: 'section-head moments-head' }, h('h2', { text: 'Momentos de esta sesión' }), h('span', { id: 'liveMomentsCount', class: 'muted' })),
    h('div', { class: 'moments-tools' }, h('div', { id: 'liveTiers', class: 'tiers', role: 'group', 'aria-label': 'Filtrar por nota' }), h('span', { style: 'flex:1' }),
      h('div', { class: 'seg', role: 'group', 'aria-label': 'Ordenar' }, [['recent', 'Recientes'], ['score', 'Mejor nota'], ['duration', 'Duración']].map(([v, t]) => h('button', { type: 'button', 'data-sort': v, text: t, onclick: () => { liveUI.sort = v; paintLiveMoments(); } }))),
      h('div', { class: 'seg', role: 'group', 'aria-label': 'Vista' }, [['grid', 'Cuadrícula'], ['list', 'Lista']].map(([v, t]) => h('button', { type: 'button', 'data-lview': v, text: t, onclick: () => { liveUI.view = v; paintLiveMoments(); } })))),
    h('div', { id: 'liveBatch', class: 'card live-batch', hidden: true }, h('b', { id: 'liveBatchLabel' }), h('span', { style: 'flex:1' }),
      h('button', { class: 'btn ghost', type: 'button', text: 'Añadir etiqueta', onclick: () => batchLive('tag') }), h('button', { class: 'btn ghost', type: 'button', text: 'Favoritos', onclick: () => batchLive('fav') }),
      h('button', { class: 'btn danger', type: 'button', text: 'Descartar', onclick: () => batchLive('discard') }), h('button', { class: 'btn ghost', type: 'button', text: 'Cancelar', onclick: () => { liveUI.picked.clear(); paintLiveMoments(); } })),
    h('div', { id: 'liveMomentGrid' }));
  host.prepend(connect, recs, now, moments);
  setupStreamerSearch();
}
// Sessions taken off the screen with ×: remembered in this browser only (the session and its moments are untouched).
const DISMISS_KEY = 'cs.liveDismissed';
function dismissedLive() { try { return new Set(JSON.parse(localStorage.getItem(DISMISS_KEY) || '[]')); } catch { return new Set(); } }
function saveDismissed(ids) { try { localStorage.setItem(DISMISS_KEY, JSON.stringify([...ids].slice(-200))); } catch {} }
const liveDismissed = (id) => dismissedLive().has(id);
function undismissLive(id) { const ids = dismissedLive(); if (ids.delete(id)) saveDismissed(ids); }
function hideLiveNow() {
  for (const id of ['liveNow', 'liveMomentsBox']) { const el = $(id); if (el) { el.hidden = true; el.classList.remove('closing'); } }
  liveUI.session = null;
}
function dismissLive() {
  const s = liveUI.session; if (!s || LIVE_RUNNING.includes(s.status) || s.status === 'stopping') return;
  const ids = dismissedLive(); ids.add(s.id); saveDismissed(ids);
  clearTimeout(liveTimer); clearTimeout(liveUI.frameTimer); try { stopLivePlayer(); } catch {}
  liveId = null;
  $('liveClose').classList.add('boom');
  for (const id of ['liveNow', 'liveMomentsBox']) $(id)?.classList.add('closing');
  setTimeout(() => { hideLiveNow(); showLiveRecs(); window.scrollTo({ top: 0, behavior: 'smooth' }); }, 380);
  toast('Transmisión quitada de la pantalla', 'Sus momentos siguen en tu biblioteca y en «Tus streamers y sesiones».');
}
// The recommended streams, as on the home: your streamers live now, Kick recommendations and YouTube, each with
// «Clipear este directo». Refreshed every minute while visible.
let recsToken = 0, recsTimer = null;
async function showLiveRecs() {
  const box = $('liveRecs'); if (!box) return;
  box.hidden = false; const mine = ++recsToken; clearTimeout(recsTimer);
  if (!box.childElementCount) put(box, h('div', { class: 'recs-head' }, h('span', { class: 'recs-eyebrow', text: 'SIGUE CLIPEANDO' }), h('h2', { text: 'Buscando directos para ti…' })));
  const [people, featured] = await Promise.all([loadStreamers(), api('/api/streamers/featured').catch(() => [])]);
  if (mine !== recsToken || box.hidden) return;
  const live = (people || []).filter((s) => s.live), kick = (featured || []).filter((s) => s.platform !== 'youtube');
  const head = (title, note, extra) => h('div', { class: 'section-head' }, h('span', { class: 'pulse-dot' }), h('h2', { text: title }), h('span', { class: 'muted', text: note }), extra || null);
  put(box,
    h('div', { class: 'recs-head' }, h('span', { class: 'recs-eyebrow', text: 'SIGUE CLIPEANDO' }), h('h2', {}, '¿Qué directo ', h('span', { class: 'grad', text: 'clipeamos' }), ' ahora?'),
      h('p', { class: 'muted', text: 'Elige un directo y empieza con un clic. Las sesiones anteriores siguen guardadas en tu biblioteca.' })),
    live.length ? h('div', {}, head('En vivo ahora', 'Tus streamers en directo. Los que más clipeas van primero.'),
      h('div', { class: 'rail' }, live.map((s, i) => streamCard(s, i === 0 && s.clips ? '★ El que más clipeas' : '')))) : null,
    kick.length ? h('div', {}, head('Recomendados en Kick', 'Los streamers de Kick con más audiencia que están en directo ahora.', platformLogo('kick')),
      h('div', { class: 'rail' }, kick.map((s) => streamCard(s, s.lang === 'es' ? 'Recomendado · Español' : 'Recomendado', true)))) : null,
    h('div', { id: 'liveRecsYoutube', hidden: true }),
    !live.length && !kick.length ? h('p', { class: 'muted recs-empty', text: 'Buscando también en YouTube… Si no aparece nada, pega arriba el enlace de un directo o busca a un streamer por su nombre.' }) : null);
  fillYoutubeLive(featured || [], 'liveRecsYoutube').then(() => { if (mine === recsToken && $('liveRecsYoutube') && !$('liveRecsYoutube').hidden) box.querySelector('.recs-empty')?.remove(); });
  recsTimer = setTimeout(() => { if (current === 'live' && !box.hidden && !document.hidden) showLiveRecs(); }, 60000);
}
const momentId = (sid, mid) => `live:${sid}:${mid}`;
const liveShown = (s) => s.moments.filter((m) => m.status !== 'discarded');
const HEAT_TEXT = { fire: 'En llamas: hay clips para subir ya', great: 'Caliente: buenos momentos', good: 'Templado', weak: 'Tranquilo por ahora' };
function paintLiveView(s) {
  buildLiveLayout();
  const running = LIVE_RUNNING.includes(s.status);
  if (!running && s.status !== 'stopping' && liveDismissed(s.id)) { hideLiveNow(); showLiveRecs(); return; }   // taken off the screen with ×
  liveUI.session = s; $('liveRecs').hidden = true; ++recsToken; clearTimeout(recsTimer);
  $('liveClose').hidden = running || s.status === 'stopping'; $('liveClose').classList.remove('boom');
  $('liveNow').hidden = false; $('liveNow').classList.toggle('is-live', running); $('liveMomentsBox').hidden = !s.moments.length;
  $('liveBadge').textContent = running ? (s.status === 'reconnecting' ? 'RECONECTANDO' : 'EN EL AIRE') : ({ stopped: 'DETENIDA', ended: 'TERMINADO', interrupted: 'INTERRUMPIDA', error: 'ERROR', stopping: 'DETENIENDO' })[s.status] || s.status.toUpperCase();
  $('liveBadge').className = 'onair-pill' + (running ? ' on' : '');
  $('liveRec').hidden = !running; $('liveDelay').hidden = !running;
  $('livePlatform').replaceChildren(platformLogo(s.platform) || ''); $('livePlatform').className = 'chip logo';
  put($('liveAvatar'), avatarImg(streamerFor(s.channel) || { name: s.channel }, 58));
  $('liveClock').textContent = mmss(s.media_s); $('liveClockLabel').textContent = running ? 'En directo' : 'Grabado';
  $('liveWho').textContent = s.channel || 'Directo'; $('liveTitle').textContent = s.title || '';
  $('liveConn').textContent = running ? (s.status === 'reconnecting' ? 'Reconectando…' : `Señal estable${s.reconnects ? ` · ${s.reconnects} reconexiones` : ''}`) : 'Sesión guardada';
  $('liveConn').classList.toggle('ok', running && s.status !== 'reconnecting');
  const shown = liveShown(s), ready = s.moments.filter((m) => ['draft', 'opened'].includes(m.status)).length;
  $('liveStatMoments').textContent = s.moments.length; $('liveStatReady').textContent = ready;
  $('liveStatFire').textContent = shown.filter((m) => m.score >= 85).length;
  $('liveStatBuffer').textContent = `${s.buffer_minutes} min`; $('liveStatLang').textContent = ({ es: 'español', en: 'inglés', pt: 'portugués', fr: 'francés', it: 'italiano', de: 'alemán' })[s.language] || s.language;
  paintHeat(s, shown); paintPipe(s, running); paintMeter(s, shown, running);
  clearTimeout(liveUI.frameTimer);
  // Still image as a fallback (and for stopped sessions); while recording, the video player below takes over.
  const refresh = () => { const img = $('liveFrame'); const next = new Image(); next.onload = () => { img.src = next.src; }; next.src = `/api/live/${s.id}/frame?t=${Date.now()}`; if (running && current === 'live' && !livePlayer.playing) liveUI.frameTimer = setTimeout(refresh, 5000); };
  refresh();
  // Only on the live screen: the session keeps being followed from other screens, and the player restarting there
  // (hidden, with its sound on) was the stream heard in the background with no button to silence it.
  runLivePlayer(s, running && current === 'live');
  paintLiveMoments();
}
// The stream's temperature: the best note of the last 10 minutes, as a ring that fills and changes colour.
function paintHeat(s, shown) {
  const recent = shown.filter((m) => m.score != null && m.start >= s.media_s - 600);
  const best = recent.length ? Math.round(Math.max(...recent.map((m) => m.score))) : null, t = best == null ? null : scoreTier(best);
  const ring = $('liveHeat'); ring.className = 'heat-ring ' + (t ? t.cls : 'idle');
  ring.style.setProperty('--p', String(best == null ? 0 : best / 100));
  $('liveHeatNum').textContent = best == null ? '—' : String(best);
  $('liveHeatEmoji').src = EMOJI(t ? t.icon : 'zzz');
  $('liveHeatLabel').textContent = t ? HEAT_TEXT[t.cls] : 'Esperando el primer momento';
  $('liveHeatHint').textContent = recent.length ? `Mejor nota de los últimos 10 min · ${recent.length} ${recent.length === 1 ? 'momento' : 'momentos'}` : 'La IA escucha y avisa cuando encuentra algo';
}
// What the AI is doing, as four steps; the messages it leaves become a short feed with the time.
function paintPipe(s, running) {
  const msg = s.message || '';
  const step = !running ? -1 : s.moments.some((m) => m.status === 'rendering') ? 3 : /ronda|analiz|propuso|descart|juez/i.test(msg) ? 2 : s.transcription_device ? 1 : 0;
  for (const el of document.querySelectorAll('#livePipe .pipe-step')) { const i = +el.dataset.step; el.classList.toggle('done', i < step); el.classList.toggle('on', i === step); }
  $('livePipe').style.setProperty('--fill', String(Math.max(0, step) / 3));
  document.querySelector('.live-ai .bars').classList.toggle('paused', !running);
  $('liveAiDevice').textContent = !running ? 'Sin actividad: la sesión no está en curso' : s.transcription_device ? `Transcribiendo con ${s.transcription_device} · IA local, sin pagar API` : 'Preparando la transcripción…';
  $('liveAiMessage').textContent = msg; $('liveAiText').textContent = s.recent_text ? `«…${s.recent_text}»` : 'Aquí verás lo último que se dijo en el directo.';
  if (liveUI.feedFor !== s.id) { liveUI.feed = []; liveUI.feedFor = s.id; }
  if (msg && liveUI.feed[0]?.text !== msg) { liveUI.feed.unshift({ text: msg, at: new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' }) }); liveUI.feed.length = Math.min(liveUI.feed.length, 4); }
  put($('liveFeed'), liveUI.feed.map((f, i) => h('li', { class: i ? '' : 'now' }, h('time', { text: f.at }), h('span', { text: f.text }))));
}
// The «momentómetro»: the whole session as a bar, the part still in the buffer lit, every moment a mark of its note.
function paintMeter(s, shown, running) {
  const total = Math.max(60, s.media_s || 0), from = Math.max(0, total - s.buffer_minutes * 60);
  const pct = (x) => `${Math.max(0, Math.min(100, 100 * x / total))}%`;
  const marks = shown.filter((m) => m.start != null).map((m) => {
    const t = m.score == null ? 'none' : scoreTier(m.score).cls;
    return h('button', { type: 'button', class: `mmark ${t}${m.status === 'rendering' ? ' wait' : ''}`, style: `left:${pct(m.start)};width:max(8px,${pct(m.end - m.start)})`,
      title: `${mmss(m.start)} · ${m.title}${m.score != null ? ` · nota ${Math.round(m.score)}` : ''}`, 'aria-label': `Abrir momento: ${m.title}`,
      onclick: () => { if (m.status !== 'rendering') openMoment(s, m); } }, t === 'fire' ? emo('fire', 'em flare') : '');
  });
  put($('liveMeter'), h('span', { class: 'mbuffer', style: `left:${pct(from)};right:0` }), marks, running ? h('span', { class: 'mnow', 'aria-hidden': 'true' }) : '');
  $('meterEnd').textContent = running ? `ahora · ${mmss(total)}` : mmss(total);
  $('meterBuffer').textContent = from > 0 ? `búfer desde ${mmss(from)}` : '';
  $('meterHint').textContent = shown.length ? 'Cada marca es un momento: tócala para editarlo' : 'Aquí aparecerán los momentos que encuentre la IA';
}

// Continuous preview: the recorded 6 s segments play one after another (two video elements: while one plays, the
// next one is already loaded, so there is no pause between them). About one segment behind the stream.
const livePlayer = { sid: null, playing: false, index: -1, muted: true, token: 0 };
function liveVideos() {
  const frame = document.querySelector('.live-frame');
  if (!frame.querySelector('.live-vid')) for (const id of ['liveVidA', 'liveVidB']) { const v = h('video', { id, class: 'live-vid', playsinline: true, preload: 'auto' }); v.muted = true; frame.insertBefore(v, frame.querySelector('.scan')); }
  if (!$('liveSound')) $('liveFrameCtrl').append(h('button', { id: 'liveSound', class: 'btn glass-btn', type: 'button', text: '🔇 Activar sonido', hidden: true,
    onclick: () => { livePlayer.muted = !livePlayer.muted; paintLiveSound(); } }));
  paintLiveSound();
  return [$('liveVidA'), $('liveVidB')];
}
function stopLivePlayer() {
  livePlayer.token++; livePlayer.playing = false; livePlayer.sid = null;
  for (const v of document.querySelectorAll('.live-vid')) { v.pause(); v.removeAttribute('src'); v.load(); v.classList.remove('on'); }
  if ($('liveSound')) $('liveSound').hidden = true;
}
async function runLivePlayer(s, running) {
  if (!running) { stopLivePlayer(); return; }
  if (livePlayer.sid === s.id && livePlayer.playing) return;
  stopLivePlayer(); livePlayer.sid = s.id; const token = livePlayer.token;
  const [a, b] = liveVideos();
  const load = (video, index) => { video.muted = livePlayer.muted; video.src = `/api/live/${s.id}/segment/${index}`; video.load(); };
  const seg = await api(`/api/live/${s.id}/segments`).catch(() => ({ done: [] }));
  if (token !== livePlayer.token || seg.done.length < 1) { if (token === livePlayer.token) setTimeout(() => { if (livePlayer.sid === s.id) { livePlayer.sid = null; runLivePlayer(s, true); } }, 4000); return; }
  livePlayer.index = seg.done[seg.done.length - 1];
  let current = a, next = b;
  load(current, livePlayer.index);
  // The next segment is asked for at once: the server answers when it is finished (no timers in the page, which
  // Chrome slows down when the window is covered). A segment that is gone makes the watchdog start from the newest.
  const advance = () => { if (token !== livePlayer.token) return; livePlayer.index += 1; load(next, livePlayer.index); };
  current.oncanplay = () => { if (token !== livePlayer.token) return; current.play().catch(() => {}); current.classList.add('on'); livePlayer.playing = true; $('liveSound').hidden = false; current.oncanplay = null; advance(); };
  const swap = () => {
    if (token !== livePlayer.token || current === null) return;
    if (current.currentTime === 0 && !current.ended) return;
    next.play().then(() => { next.classList.add('on'); current.classList.remove('on'); [current, next] = [next, current]; advance(); }).catch(() => { if (token === livePlayer.token) setTimeout(swap, 500); });
  };
  for (const v of [a, b]) {
    v.onended = () => { if (v === current) swap(); };
    v.onerror = () => { if (token === livePlayer.token) restartLivePlayer('segment error'); };   // a segment that did not load
  }
  livePlayer.current = () => current; livePlayer.lastT = -1; livePlayer.lastAt = Date.now();
}
// The chain of 6 s segments must keep moving: when the picture stops advancing for 8 s (a segment that failed, a swap
// that never happened), it starts again from the newest segment, with the same sound setting. Before, it stayed
// frozen and silent while the button still said «Silenciar».
function restartLivePlayer(why) {
  const s = liveUI.session; if (!s || current !== 'live') return;
  livePlayer.restarts = (livePlayer.restarts || 0) + 1; livePlayer.lastRestart = why;
  const running = ['starting', 'live', 'reconnecting'].includes(s.status);
  stopLivePlayer(); if (running) runLivePlayer(s, true);
}
setInterval(() => {
  if (current !== 'live' || !livePlayer.playing || !livePlayer.current) return;
  const v = livePlayer.current();
  if (!v) return;
  if (v.currentTime !== livePlayer.lastT) { livePlayer.lastT = v.currentTime; livePlayer.lastAt = Date.now(); return; }
  if (Date.now() - livePlayer.lastAt > 8000) restartLivePlayer('stalled');
}, 2000);
function paintLiveMoments() {
  const s = liveUI.session; if (!s) return;
  for (const b of document.querySelectorAll('[data-sort]')) b.classList.toggle('on', b.dataset.sort === liveUI.sort);
  for (const b of document.querySelectorAll('[data-lview]')) b.classList.toggle('on', b.dataset.lview === liveUI.view);
  paintTiers(s); paintSpotlight(s);
  const tierOf = (m) => m.score == null ? 'none' : scoreTier(m.score).cls;
  const list = s.moments.filter((m) => liveUI.tier === 'all' || tierOf(m) === liveUI.tier);
  if (liveUI.sort === 'recent') list.reverse(); else if (liveUI.sort === 'score') list.sort((a, b) => (b.score || 0) - (a.score || 0)); else list.sort((a, b) => b.duration - a.duration);
  $('liveMomentsCount').textContent = `${list.length === s.moments.length ? s.moments.length : `${list.length} de ${s.moments.length}`} momentos · pasa el cursor para verlos, toca uno para seleccionarlo`;
  for (const id of [...liveUI.picked]) if (!s.moments.some((m) => m.id === id)) liveUI.picked.delete(id);
  $('liveBatch').hidden = !liveUI.picked.size; $('liveBatchLabel').textContent = liveUI.picked.size === 1 ? '1 clip seleccionado' : `${liveUI.picked.size} clips seleccionados`;
  const grid = $('liveMomentGrid'); grid.className = liveUI.view === 'grid' ? 'grid live-grid' : 'live-list';
  put(grid, list.map((m) => liveUI.view === 'grid' ? momentCard(s, m) : momentRow(s, m)));
  const ids = list.filter((m) => m.status !== 'rendering').slice(0, 12).map((m) => momentId(s.id, m.id)).join(',');
  if (ids && ids !== liveUI.warmed) { liveUI.warmed = ids; api('/api/library?origin=live').then(() => api('/api/library/previews/warm', jsonOptions({ ids: ids.split(',') }))).catch(() => {}); }
}
const TIERS = [['all', 'Todos', ''], ['fire', 'En llamas', 'fire'], ['great', 'Muy buenos', 'rocket'], ['good', 'Buenos', 'thumbs'], ['weak', 'Flojos', 'zzz']];
function paintTiers(s) {
  const count = (k) => k === 'all' ? s.moments.length : s.moments.filter((m) => m.score != null && scoreTier(m.score).cls === k).length;
  if (liveUI.tier !== 'all' && !count(liveUI.tier)) liveUI.tier = 'all';
  put($('liveTiers'), TIERS.filter(([k]) => k === 'all' || count(k)).map(([k, t, e]) => h('button', { type: 'button', class: `tier ${k}${liveUI.tier === k ? ' on' : ''}`, 'aria-pressed': String(liveUI.tier === k),
    onclick: () => { liveUI.tier = k; paintLiveMoments(); } }, e ? emo(e) : '', h('span', { text: t }), h('b', { text: String(count(k)) }))));
}
function paintSpotlight(s) {
  const best = liveShown(s).filter((m) => m.status !== 'rendering' && m.score >= 75).sort((a, b) => b.score - a.score)[0];
  const host = $('liveSpot'); if (!best) { put(host); return; }
  if (host.dataset.mid === best.id + ':' + best.score + ':' + best.status) return;     // same moment: keep its preview alive
  host.dataset.mid = best.id + ':' + best.score + ':' + best.status;
  const id = momentId(s.id, best.id), thumb = `/api/library/${encodeURIComponent(id)}/thumb`;
  const box = previewBox(thumb, null, 3, best.duration); box.classList.add('spot-thumb');
  const img = box.querySelector('img'); if (img) retryThumb(img, thumb);
  hoverPreview(box, { id, title: best.title, channel: s.channel || 'Directo', duration: best.duration, thumb_url: thumb }, () => openMoment(s, best));
  put(host, h('div', { class: 'card spot' + (best.score >= 85 ? ' on-fire' : '') }, box,
    h('div', { class: 'spot-body' }, h('span', { class: 'lbl-s' }, emo('trophy'), 'El mejor momento hasta ahora'),
      h('b', { class: 'spot-title', text: best.title }), scoreBadge(best.score, best.viral_kind),
      best.analysis?.motivo ? h('span', { class: 'why', text: best.analysis.motivo }) : '',
      h('span', { class: 'muted', text: `Minuto ${Math.floor((best.start || 0) / 60)} · ${fmtDur(best.duration)} · detectado ${best.detected_at || ''}` }),
      h('div', { class: 'acts' }, h('button', { class: 'btn primary', type: 'button', text: 'Editar y publicar', onclick: () => openMoment(s, best) })))));
}
// Score badge: the note at a glance. 85+ is on fire (post it now), then rocket, thumbs up and «flojo».
const EMOJI = (n) => `/static/img/emoji/${n}.png`;
const KIND_EMOJI = { humor: ['laugh', 'Humor'], suspenso: ['eyes', 'Suspenso'], 'polémica': ['pepper', 'Polémica'], conflicto: ['boxing', 'Conflicto'] };
function scoreTier(score) {
  const n = Math.round(score || 0);
  if (n >= 85) return { cls: 'fire', icon: 'fire', label: '¡Súbelo ya!' };
  if (n >= 75) return { cls: 'great', icon: 'rocket', label: 'Muy bueno' };
  if (n >= 60) return { cls: 'good', icon: 'thumbs', label: 'Bueno' };
  return { cls: 'weak', icon: 'zzz', label: 'Flojo' };
}
function scoreBadge(score, kind, compact) {
  const n = Math.round(score || 0), t = scoreTier(n), k = KIND_EMOJI[kind];
  const badge = h('span', { class: `sbadge ${t.cls}${compact ? ' compact' : ''}`, title: `Nota ${n} de 100 · ${t.cls === 'fire' ? 'En llamas: súbelo ya' : t.label}${k ? ' · ' + k[1] : ''}` });
  if (t.cls === 'fire') badge.append(h('span', { class: 'flames', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'), h('i')));
  badge.append(h('img', { class: 'em', src: EMOJI(n >= 95 ? 'hundred' : t.icon), alt: '' }), h('b', { text: String(n) }));
  if (!compact) badge.append(h('span', { class: 'sb-lbl', text: t.label }));
  if (k) badge.append(h('img', { class: 'em kind', src: EMOJI(k[0]), alt: k[1], title: k[1] }));
  return badge;
}
function momentCard(s, m) {
  if (m.status === 'rendering') return h('div', { class: 'card mcard preparing' }, h('div', { class: 'thumb9' }, h('span', { class: 'bars', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i')), h('span', { class: 'muted', text: 'Preparando el clip…' })), h('b', { class: 't', text: m.title }), h('span', { class: 'muted', text: `Detectado ${m.detected_at}` }));
  const id = momentId(s.id, m.id), picked = liveUI.picked.has(m.id);
  const thumb = `/api/library/${encodeURIComponent(id)}/thumb`;
  const box = previewBox(thumb, null, 3, m.duration);
  box.classList.add('thumb9');
  const img = box.querySelector('img'); if (img) retryThumb(img, thumb);
  // Same big preview with sound as in the library: the moment as it will look, without opening the editor.
  const look = { id, title: m.title, channel: s.channel || 'Directo', duration: m.duration, thumb_url: thumb };
  hoverPreview(box, look, () => openMoment(s, m));
  box.append(h('span', { class: 'chip glass dur', text: fmtDur(m.duration) }));
  const card = h('div', { class: 'card mcard' + (picked ? ' sel' : '') + (m.score >= 85 ? ' on-fire' : ''), role: 'button', tabindex: '0', 'aria-pressed': String(picked),
    onclick: () => { picked ? liveUI.picked.delete(m.id) : liveUI.picked.add(m.id); paintLiveMoments(); },
    onkeydown: (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.click(); } } }, box,
    h('b', { class: 't', text: m.title }), m.score != null ? scoreBadge(m.score, m.viral_kind) : '', h('span', { class: 'muted', text: `${m.detected_at} · ${m.status === 'opened' ? 'Abierto en el editor' : 'Listo'}` }),
    m.analysis?.motivo ? h('span', { class: 'why', text: m.analysis.motivo }) : '',
    h('div', { class: 'acts' }, h('button', { class: 'btn primary', type: 'button', onclick: (e) => { e.stopPropagation(); openMoment(s, m); } }, svg(ICON_EDIT, 16), 'Editar'),
      h('button', { class: 'btn ghost discard', type: 'button', onclick: (e) => { e.stopPropagation(); discardMoment(s, m); } }, svg(ICON_X, 15), 'Descartar')));
  return card;
}
function momentRow(s, m) {
  return h('div', { class: 'live-row' }, h('img', { src: `/api/library/${encodeURIComponent(momentId(s.id, m.id))}/thumb`, alt: '', loading: 'lazy' }), h('b', { text: m.title, style: 'flex:1;min-width:0' }),
    h('span', { class: 'muted', text: fmtDur(m.duration) }), h('span', { class: 'muted', text: m.detected_at }), m.score != null ? scoreBadge(m.score, m.viral_kind, true) : h('span'),
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
  box.querySelector('.playhead').style.left = (t / d * 100) + '%'; box.style.setProperty('--pos', (t / d * 100) + '%');
}
function paintEditorHeader() {
  if (!job || !selected) return;
  const channel = job.live?.channel || job.youtube?.channel || 'Mis videos';
  $('editorCrumb').textContent = `Biblioteca › ${channel} · se guarda automáticamente`;
  $('editorClipTitle').textContent = $('title').value || selected.title || 'Clip';
  $('exportWhere').textContent = `Destino: exportados › ${channel}`;
}
const baseChoose = choose;
window.choose = (c) => { buildEditorLayout(); titleManual.value = ''; baseChoose(c); if (overlayInfo && !overlayInfo.found) dropStack(); placeTitle(); cueSignature = ''; paintEditorHeader(); paintTimeline(); };
choose = window.choose;
// Title position by format: on the camera/game line (Cámara + juego), on the line between the top black band and the
// video (zoom), near the top (full screen). Only a position that is still a default moves; one set by hand stays.
function titleDefault(framing, zoom) {
  if (framing === 'stack') return seamY();
  // zoom: on the edge of the picture; lower when the video itself carries a black bar on top (job.letterbox)
  if (framing === 'zoom') { const band = Math.round(1920 * (ZOOM[zoom] || ZOOM.balanced) / 2) * 2, bar = Number(job?.letterbox?.top) || 0; return Math.round(((1920 - band) / 2 + bar * band) / 19.2 * 10) / 10; }
  if (framing === 'crop') return FULL_TITLE_Y;      // «Pantalla completa»: below TikTok's / Instagram's top bar
  return 12;
}
const FULL_TITLE_Y = 21;
function isAutoTitle(v, framing) {
  v = Number(v);
  return v === 12 || v === FULL_TITLE_Y || (framing !== 'stack' && v >= 40 && v <= 50.3) || Object.keys(ZOOM).some((z) => Math.abs(v - titleDefault('zoom', z)) < .6 || Math.abs(v - Math.round((1920 - Math.round(1920 * ZOOM[z] / 2) * 2) / 2 / 19.2 * 10) / 10) < .6) || (framing === 'stack' && Math.abs(v - seamY()) < 1.5);
}
// Whether the title was moved by hand (dragged, or its «Posición vertical» slider): saved with the clip's edits.
// Without that, the title always sits on its format's line, also when that line moves (a new camera detection).
const titleManual = h('input', { type: 'hidden', id: 'title_manual', value: '' });
$('title_y').after(titleManual);
{
  const baseSettings = settings;
  window.settings = () => ({ ...baseSettings(), title_manual: titleManual.value });
  settings = window.settings;
  const markManual = () => { titleManual.value = '1'; };
  $('title_y').addEventListener('input', (e) => { if (e.isTrusted) markManual(); });
  $('previewTitle').addEventListener('pointerdown', (e) => { if (e.isTrusted) markManual(); });
  // the camera/game line is known once «Cámara + juego» is prepared: put an automatic title on it then
  const baseLoadStack = loadStackPath;
  window.loadStackPath = async (...a) => { const out = await baseLoadStack(...a); placeTitle(); return out; };
  loadStackPath = window.loadStackPath;
}
function placeTitle() {
  if (!selected) return;
  if (titleManual.value === '1') return;                                  // moved by hand: it stays
  const f = $('framing').value, saved = job?.clip_edits?.[selected.id];
  // Edits saved before the flag existed: outside «Cámara + juego» keep the old rule (only defaults move).
  if (saved && !('title_manual' in saved) && f !== 'stack' && !isAutoTitle($('title_y').value, f)) return;
  const t = titleDefault(f, $('zoom').value);
  if (Math.abs(Number($('title_y').value) - t) >= .5) { $('title_y').value = t; saveCurrent(); paint(); }
}
for (const id of ['framing', 'zoom']) $(id).addEventListener('change', () => setTimeout(placeTitle, 0));
const basePaintTime = paintTime;
window.paintTime = () => { basePaintTime(); try { paintTimeline(); } catch {} };
paintTime = window.paintTime;
$('title').addEventListener('input', () => paintEditorHeader());
buildEditorLayout();
// --- Editor (parte 4): undo / redo, moments filter, slider values, shortcuts --------------------------------------
// Undo history per clip: a snapshot of the clip's settings after each change (grouped: a drag or typing is one step).
const history = new Map();   // clip id -> { past: [json], future: [json] }
let historyTimer = null, applyingHistory = false;
function histFor(id) { if (!history.has(id)) history.set(id, { past: [], future: [] }); return history.get(id); }
function snapshot() {
  if (applyingHistory || !selected || selected.id === 'manual') return;
  const hst = histFor(selected.id), now = JSON.stringify(settings());
  if (hst.past[hst.past.length - 1] !== now) { hst.past.push(now); if (hst.past.length > 80) hst.past.shift(); hst.future = []; }
  paintHistoryButtons();
}
const baseSaveCurrent = saveCurrent;
window.saveCurrent = () => { baseSaveCurrent(); clearTimeout(historyTimer); historyTimer = setTimeout(snapshot, 450); };
saveCurrent = window.saveCurrent;
function applySnapshot(json) {
  const e = JSON.parse(json), framingBefore = $('framing').value;
  applyingHistory = true;
  try {
    for (const [k, v] of Object.entries(e)) { const el = $(k); if (!el || k === 'clip_id') continue; if (el.type === 'checkbox') el.checked = !!v; else el.value = v ?? ''; }
    cues = (e.captions || []).map((c) => ({ ...c }));
    renderCueEditor();
    if ($('framing').value !== framingBefore) $('framing').dispatchEvent(new Event('change'));
    baseSaveCurrent(); paint(); paintEditorHeader(); cueSignature = ''; paintTimeline();
  } finally { applyingHistory = false; }
  paintHistoryButtons();
}
function undo() {
  if (!selected) return; const hst = histFor(selected.id);
  if (hst.past.length < 2) { toast('Nada que deshacer', 'Aún no hay cambios en este clip.'); return; }
  hst.future.push(hst.past.pop()); applySnapshot(hst.past[hst.past.length - 1]); say('Cambio deshecho.');
}
function redo() {
  if (!selected) return; const hst = histFor(selected.id);
  if (!hst.future.length) return;
  const next = hst.future.pop(); hst.past.push(next); applySnapshot(next); say('Cambio rehecho.');
}
function paintHistoryButtons() {
  const hst = selected ? histFor(selected.id) : { past: [], future: [] };
  if ($('undoBtn')) $('undoBtn').disabled = hst.past.length < 2;
  if ($('redoBtn')) $('redoBtn').disabled = !hst.future.length;
}
function shortcutsDialog() {
  const rows = [['Ctrl + Z', 'Deshacer el último cambio'], ['Ctrl + Y  ·  Ctrl + Shift + Z', 'Rehacer'], ['Espacio', 'Reproducir / pausar'], ['← / →', 'Retroceder / adelantar 5 s'], ['[ / ]', 'Clip anterior / siguiente'], ['Ctrl + E', 'Exportar el clip'], ['?', 'Ver estos atajos']];
  const modal = h('div', { class: 'cs-modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Atajos del editor', onclick: (e) => { if (e.target === modal) modal.remove(); } },
    h('div', { class: 'box', style: 'width:min(460px,92vw)' }, h('h2', { text: 'Atajos del editor', style: 'margin:0 0 12px' }),
      h('div', { class: 'shortcuts' }, rows.map(([k, t]) => h('div', {}, h('kbd', { text: k }), h('span', { text: t })))),
      h('button', { class: 'btn primary', type: 'button', style: 'width:100%;margin-top:14px', text: 'Entendido', onclick: () => modal.remove() })));
  modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') modal.remove(); });
  document.body.append(modal); modal.querySelector('button').focus();
}
function stepEditorClip(d) {
  const list = (job?.clips || []).filter((c) => !document.querySelector(`#clips .clip[data-id="${CSS.escape(c.id)}"]`)?.hidden);
  const i = list.findIndex((c) => c.id === selected?.id); const next = list[i + d]; if (next) choose(next);
}
document.addEventListener('keydown', (e) => {
  if (current !== 'editor' || document.querySelector('.cs-modal')) return;
  const typing = e.target instanceof Element && e.target.closest('input[type=text],input[type=search],input[type=number],input[type=checkbox],input:not([type]),textarea,select');
  const k = e.key.toLowerCase(), mod = e.ctrlKey || e.metaKey;
  if (mod && k === 'z' && !e.shiftKey && !typing) { e.preventDefault(); undo(); }
  else if (mod && (k === 'y' || (k === 'z' && e.shiftKey)) && !typing) { e.preventDefault(); redo(); }
  else if (mod && k === 'e') { e.preventDefault(); $('export').click(); }
  else if (typing || mod || (typeof inTheater === 'function' && inTheater())) return;   // the big view has its own keys
  else if (e.key === '?') { e.preventDefault(); shortcutsDialog(); }
  else if (e.key === ' ' && !(e.target instanceof HTMLButtonElement)) { e.preventDefault(); $('play').click(); }
  else if (e.key === '[' || e.key === ']') { e.preventDefault(); stepEditorClip(e.key === ']' ? 1 : -1); }
});
// Moments list: search, filters and a mark on the clips you already edited.
const momentFilter = { q: '', kind: 'all' };
function buildMomentsToolbar() {
  if ($('momentTools')) return;
  const q = h('input', { id: 'momentSearch', type: 'search', placeholder: 'Buscar momento…', 'aria-label': 'Buscar momento' });
  q.addEventListener('input', () => { momentFilter.q = q.value.trim().toLowerCase(); filterMoments(); });
  const chip = (kind, text) => h('button', { type: 'button', class: 'chipbtn' + (momentFilter.kind === kind ? ' on' : ''), 'data-kind': kind, text, onclick: (e) => { momentFilter.kind = kind; for (const b of e.currentTarget.parentElement.children) b.classList.toggle('on', b === e.currentTarget); filterMoments(); } });
  $('clips').before(h('div', { id: 'momentTools', class: 'moment-tools' }, q, h('div', { class: 'moment-chips' }, chip('all', 'Todos'), chip('top', '★ Potencial'), chip('edited', 'Editados'), chip('todo', 'Sin editar'))));
}
function isEdited(id) { const e = job?.clip_edits?.[id]; return !!e && !e.partial; }
function filterMoments() {
  let shown = 0;
  for (const el of document.querySelectorAll('#clips .clip')) {
    const c = job?.clips?.find((x) => x.id === el.dataset.id); if (!c) continue;
    const text = `${c.title} ${c.reason || ''} ${c.category || ''}`.toLowerCase();
    const ok = (!momentFilter.q || text.includes(momentFilter.q)) && (momentFilter.kind === 'all' || (momentFilter.kind === 'top' && c.potential) || (momentFilter.kind === 'edited' && isEdited(c.id)) || (momentFilter.kind === 'todo' && !isEdited(c.id)));
    el.hidden = !ok; if (ok) shown++;
    el.classList.toggle('is-edited', isEdited(c.id));
    if (c.score != null && !el.querySelector('.score-bar')) {
      el.append(h('span', { class: 'score-bar ' + scoreTier(c.score).cls, 'aria-hidden': 'true' }, h('i', { style: `width:${Math.max(4, Math.min(100, c.score))}%` })));
      const old = el.querySelector('.score'); if (old) old.replaceWith(h('div', { class: 'score' }, scoreBadge(c.score, c.viral_kind), c.analysis?.motivo ? h('span', { class: 'why', text: c.analysis.motivo }) : ''));
      el.classList.toggle('on-fire', c.score >= 85);
    }
  }
  if ($('empty') && job?.clips?.length) $('empty').textContent = `${shown} de ${job.clips.length} momentos · rango ${job.analysis_range?.minimum ?? ''}–${job.analysis_range?.maximum ?? ''} s`;
}
// Sliders show their value next to their name.
function decorateSliders() {
  for (const r of document.querySelectorAll('#editorView .inspector input[type=range]')) {
    if (r.dataset.out) continue; r.dataset.out = '1';
    const out = h('output', { class: 'range-val' }); const label = r.previousElementSibling?.tagName === 'LABEL' ? r.previousElementSibling : null;
    const unit = /size|width/.test(r.id) ? '' : /_x|_y|focus/.test(r.id) ? '%' : '';
    r._show = () => { out.textContent = (Math.round(Number(r.value) * 10) / 10).toLocaleString('es') + unit; const min = Number(r.min || 0), max = Number(r.max || 100); r.style.setProperty('--p', `${((Number(r.value) - min) / Math.max(1e-9, max - min)) * 100}%`); };
    if (label) label.append(out); else r.before(out);
    r.addEventListener('input', r._show); r._show();
  }
}
// Values set by code (choosing a clip, undo, dragging a layer) do not fire «input»: refresh them after those.
function refreshSliderValues() { for (const r of document.querySelectorAll('#editorView .inspector input[type=range]')) r._show?.(); }
{ const p = paint; window.paint = (...a) => { const out = p(...a); try { refreshSliderValues(); } catch {} return out; }; paint = window.paint; }
function buildEditorV4() {
  if ($('undoBtn')) return;
  const actions = document.querySelector('#editorView .editor-actions');
  actions.prepend(
    h('button', { id: 'undoBtn', class: 'btn ghost icon-btn', type: 'button', title: 'Deshacer (Ctrl + Z)', 'aria-label': 'Deshacer', text: '↶', disabled: true, onclick: undo }),
    h('button', { id: 'redoBtn', class: 'btn ghost icon-btn', type: 'button', title: 'Rehacer (Ctrl + Y)', 'aria-label': 'Rehacer', text: '↷', disabled: true, onclick: redo }),
    h('button', { class: 'btn ghost icon-btn', type: 'button', title: 'Atajos de teclado (?)', 'aria-label': 'Atajos de teclado', text: '⌨', onclick: shortcutsDialog }));
  const nav = h('div', { class: 'clip-nav' },
    h('button', { class: 'btn ghost', type: 'button', title: 'Clip anterior ( [ )', text: '‹ Anterior', onclick: () => stepEditorClip(-1) }),
    h('span', { id: 'clipIndex', class: 'muted' }),
    h('button', { class: 'btn ghost', type: 'button', title: 'Clip siguiente ( ] )', text: 'Siguiente ›', onclick: () => stepEditorClip(1) }));
  $('seek').before(nav);
  buildMomentsToolbar(); decorateSliders();
  new MutationObserver(() => filterMoments()).observe($('clips'), { childList: true });
}
function paintClipIndex() {
  const i = (job?.clips || []).findIndex((c) => c.id === selected?.id);
  if ($('clipIndex')) $('clipIndex').textContent = i >= 0 ? `Clip ${i + 1} de ${job.clips.length}` : '';
}
buildEditorV4();
// --- Vista ampliada (parte 5): centred over the app, which blurs behind it; × / click outside / Esc close it -----------
// The editor's own preview is moved into the overlay (so title, captions and logo keep the export's proportions) and
// put back exactly where it was when it closes. Before, it opened inside the editor column and could not be closed.
let theaterHost = null, theaterSpot = null;
// --- Vista ampliada: one scrubbable timeline and a floating control dock (parte 7) ---------------------------------
// Every button drives the editor's own control (same behaviour, same shortcuts); the dock only presents them.
const ICON = {
  prev: '<path d="M6 5v14M18 6l-9 6 9 6z" fill="currentColor"></path>',
  next: '<path d="M18 5v14M6 6l9 6-9 6z" fill="currentColor"></path>',
  back: '<path d="M11 7l-5 5 5 5M18 7l-5 5 5 5"></path>',
  fwd: '<path d="M13 7l5 5-5 5M6 7l5 5-5 5"></path>',
  play: '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"></path>',
  pause: '<rect x="6.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none"></rect><rect x="13.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none"></rect>',
  vol: '<path d="M4 10v4h4l5 4V6L8 10z" fill="currentColor"></path><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11"></path>',
  mute: '<path d="M4 10v4h4l5 4V6L8 10z" fill="currentColor"></path><path d="M17 9l5 6M22 9l-5 6"></path>',
  full: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"></path>',
  check: '<path d="M4 12.5l5 5L20 6.5"></path>',
};
function dockButton(cls, icon, label, onclick, size = 18) {
  const b = h('button', { class: 'dk-btn ' + cls, type: 'button', title: label, 'aria-label': label, onclick }, svg(ICON[icon], size));
  return b;
}
function buildTheaterDock(panel) {
  if (panel.querySelector('.th-dock')) return;
  const v = $('video');
  // timeline: current time · scrubber · duration
  const tNow = h('span', { class: 'tl-time', text: '0:00' }), tEnd = h('span', { class: 'tl-time', text: '0:00' });
  const timeline = h('div', { class: 'th-timeline' }, tNow, h('div', { class: 'tl-slot' }), tEnd);
  // dock
  const play = dockButton('dk-play', 'play', 'Reproducir (Espacio)', () => $('play').click(), 22);
  const prev = dockButton('', 'prev', 'Clip anterior ( [ )', () => $('prevClip').click());
  const next = dockButton('', 'next', 'Clip siguiente ( ] )', () => $('nextClip').click());
  const back = dockButton('dk-skip', 'back', 'Retroceder 5 s ( ← )', () => $('back5').click()); back.append(h('small', { text: '5' }));
  const fwd = dockButton('dk-skip', 'fwd', 'Adelantar 5 s ( → )', () => $('fwd5').click()); fwd.prepend(h('small', { text: '5' }));
  const volRange = h('input', { type: 'range', min: '0', max: '1', step: '.05', value: $('volume').value, 'aria-label': 'Volumen', class: 'dk-vol-range' });
  const volBtn = dockButton('', 'vol', 'Silenciar', () => { v.muted = !v.muted; paintVol(); });
  const paintVol = () => { const off = v.muted || Number(volRange.value) === 0; volBtn.replaceChildren(svg(ICON[off ? 'mute' : 'vol'], 18)); volBtn.title = off ? 'Activar sonido' : 'Silenciar'; volRange.style.setProperty('--p', `${(v.muted ? 0 : Number(volRange.value)) * 100}%`); };
  volRange.addEventListener('input', () => { $('volume').value = volRange.value; $('volume').dispatchEvent(new Event('input')); if (v.muted && Number(volRange.value) > 0) v.muted = false; paintVol(); });
  const index = h('span', { class: 'dk-index' });
  const full = dockButton('', 'full', 'Pantalla completa', () => $('fullscreenPreview').click());
  const render = h('button', { class: 'dk-pill', type: 'button', title: 'Renderiza el MP4 exacto que se exportará', onclick: () => $('renderCheck').click() }, svg(ICON.check, 16), h('span', { text: 'Comprobar MP4' }));
  const dock = h('div', { class: 'th-dock', role: 'toolbar', 'aria-label': 'Controles de la vista ampliada' },
    h('div', { class: 'dk-group' }, prev, back), play, h('div', { class: 'dk-group' }, fwd, next),
    h('span', { class: 'dk-sep' }), h('div', { class: 'dk-vol' }, volBtn, volRange),
    h('span', { class: 'dk-sep' }), index, full, render);
  panel.querySelector('.theater-foot').before(timeline, dock);
  // mirror the editor's state
  const paintPlay = () => { const on = !v.paused; play.replaceChildren(svg(ICON[on ? 'pause' : 'play'], 22)); play.title = on ? 'Pausar (Espacio)' : 'Reproducir (Espacio)'; play.classList.toggle('on', on); };
  v.addEventListener('play', paintPlay); v.addEventListener('pause', paintPlay); v.addEventListener('volumechange', paintVol);
  const mirror = () => {
    prev.disabled = $('prevClip').disabled; next.disabled = $('nextClip').disabled; index.textContent = $('theaterIndex').textContent;
    const r = $('renderCheck'); render.disabled = r.disabled; render.querySelector('span').textContent = /Volver/.test(r.textContent) ? 'Vista en vivo' : /Renderizando/.test(r.textContent) ? 'Renderizando…' : 'Comprobar MP4';
    render.classList.toggle('on', /Volver/.test(r.textContent));
    full.replaceChildren(svg(ICON.full, 18)); full.classList.toggle('on', !!document.fullscreenElement);
  };
  for (const id of ['prevClip', 'nextClip', 'theaterIndex', 'renderCheck']) new MutationObserver(mirror).observe($(id), { attributes: true, childList: true, characterData: true, subtree: true });
  document.addEventListener('fullscreenchange', mirror);
  const paintTimes = () => { const s = Number($('start').value), d = Math.max(0, Number($('end').value) - s); tNow.textContent = fmtClock(Math.max(0, Math.min(d, v.currentTime - s))); tEnd.textContent = fmtClock(d); };
  v.addEventListener('timeupdate', paintTimes); v.addEventListener('loadedmetadata', paintTimes);
  paintPlay(); paintVol(); mirror(); paintTimes();
}
// The subtitle timeline becomes the scrubber while enlarged: drag along it to move through the clip.
function placeTimelineInTheater(on) {
  const cue = $('cueTimeline'); if (!cue) return;
  const slot = document.querySelector('.th-timeline .tl-slot');
  if (on && slot) { if (!cue._home) { cue._home = document.createComment('cues'); cue.before(cue._home); } slot.append(cue); }
  else if (!on && cue._home) cue._home.replaceWith(cue), cue._home = null;
}
{
  let dragging = false;
  const seekAt = (e) => { const box = $('cueTimeline'); const r = box.getBoundingClientRect(); const d = Number($('end').value) - Number($('start').value);
    $('video').currentTime = Number($('start').value) + d * Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); };
  document.addEventListener('pointerdown', (e) => { if (e.target.closest?.('.th-timeline #cueTimeline')) { dragging = true; seekAt(e); e.preventDefault(); } });
  document.addEventListener('pointermove', (e) => { if (dragging) seekAt(e); });
  document.addEventListener('pointerup', () => { dragging = false; });
}
function theaterChrome(panel) {
  if (panel.querySelector('.theater-x')) return;
  panel.prepend(h('button', { class: 'theater-x', type: 'button', title: 'Cerrar (Esc)', 'aria-label': 'Cerrar la vista ampliada', text: '×', onclick: () => setTheater(false) }));
  panel.append(h('div', { class: 'theater-foot' },
    h('span', { class: 'tf-text' }, h('b', { id: 'theaterTitle' }), h('span', { id: 'theaterMeta', class: 'muted' })),
    h('button', { class: 'btn ghost', type: 'button', text: 'Volver al editor', onclick: () => setTheater(false) }),
    h('button', { class: 'btn primary', type: 'button', text: '↓ Exportar', onclick: () => { setTheater(false); $('export').click(); } })));
  buildTheaterDock(panel);
}
{
  const baseSetTheater = setTheater;
  window.setTheater = (on) => {
    const panel = previewPanel();
    if (on && !theaterHost) {
      theaterChrome(panel);
      theaterSpot = document.createComment('preview'); panel.before(theaterSpot);
      theaterHost = h('div', { class: 'theater-host', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Vista ampliada del clip', onclick: (e) => { if (e.target === theaterHost) setTheater(false); } });
      theaterHost.append(panel); document.body.append(theaterHost); placeTimelineInTheater(true);
      $('theaterTitle').textContent = $('title').value || selected?.title || 'Clip';
      $('theaterMeta').textContent = `${(Number($('end').value) - Number($('start').value)).toFixed(1).replace('.', ',')} s · ${({ stack: 'Cámara + juego', zoom: 'Zoom', crop: 'Pantalla completa', fit: 'Ajustado' })[$('framing').value] || ''}`;
      requestAnimationFrame(() => requestAnimationFrame(() => theaterHost?.classList.add('in')));
    }
    baseSetTheater(on);
    if (!on && theaterHost) {
      const host = theaterHost; theaterHost = null;
      host.classList.remove('in'); host.classList.add('out');
      setTimeout(() => { placeTimelineInTheater(false); theaterSpot.replaceWith(panel); host.remove(); requestAnimationFrame(paint); }, 220);
    }
  };
  setTheater = window.setTheater;
}

// --- Play on the clip itself, like a video player: click the picture to play / pause --------------------------------
function buildOnVideoPlay() {
  const preview = $('preview'); if (preview.querySelector('.pv-play')) return;
  const big = h('button', { class: 'pv-play', type: 'button', 'aria-label': 'Reproducir', title: 'Reproducir (Espacio)' }, svg('<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"></path>', 34));
  const flash = h('span', { class: 'pv-flash', 'aria-hidden': 'true' });
  const time = h('span', { class: 'pv-time', 'aria-hidden': 'true' });
  preview.append(big, flash, time);
  const toggle = () => { $('play').click(); };
  big.addEventListener('click', (e) => { e.stopPropagation(); toggle(); });
  // A click on the picture (not on a title, caption or logo being moved) plays or pauses.
  preview.addEventListener('click', (e) => {
    if (e.target !== $('video') && e.target !== $('stackCanvas') && e.target !== preview) return;
    if (!$('renderVideo').hidden) return;
    toggle();
  });
  const v = $('video');
  const paintState = (fromToggle) => {
    const playing = !v.paused;
    preview.classList.toggle('is-playing', playing);
    big.setAttribute('aria-label', playing ? 'Pausar' : 'Reproducir');
    if (fromToggle) {
      flash.replaceChildren(svg(playing ? '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"></path>' : '<rect x="6.5" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"></rect><rect x="13.5" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"></rect>', 30));
      flash.classList.remove('go'); void flash.offsetWidth; flash.classList.add('go');
    }
  };
  v.addEventListener('play', () => paintState(true)); v.addEventListener('pause', () => paintState(!v.ended)); paintState(false);
  v.addEventListener('timeupdate', () => {
    const t = Math.max(0, v.currentTime - Number($('start').value)), d = Math.max(0, Number($('end').value) - Number($('start').value));
    time.textContent = `${fmtClock(t)} / ${fmtClock(d)}`;
  });
  $('play').closest('.playback')?.classList.add('pv-hidden-play');
}
const fmtClock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
buildOnVideoPlay();

// --- Inspector: sliders show how far they are filled; panels slide in when you change tab ---------------------------
function fillSlider(r) { const min = Number(r.min || 0), max = Number(r.max || 100); r.style.setProperty('--p', `${((Number(r.value) - min) / Math.max(1e-9, max - min)) * 100}%`); }
document.addEventListener('input', (e) => { if (e.target instanceof HTMLInputElement && e.target.type === 'range' && e.target.closest('#editorView')) fillSlider(e.target); }, true);
{ const prev = refreshSliderValues; refreshSliderValues = () => { prev(); document.querySelectorAll('#editorView input[type=range]').forEach(fillSlider); }; }
document.querySelectorAll('#editorView input[type=range]').forEach(fillSlider);

{
  const prev = choose;
  window.choose = (c) => { prev(c); paintClipIndex(); refreshSliderValues(); filterMoments(); const hst = histFor(c.id); if (!hst.past.length) hst.past.push(JSON.stringify(settings())); paintHistoryButtons(); };
  choose = window.choose;
}


// --- Videos largos a clips (parte 4): hero, steps, drag & drop, recent videos -----------------------------------------
// Only presentation: every control of the existing screen stays the same element with the same behaviour (app.js).
const ICON_EDIT = '<path d="M4 20h4.2L19.4 8.8a2 2 0 0 0 0-2.8l-1.4-1.4a2 2 0 0 0-2.8 0L4 15.8z"></path><path d="M13.5 6.5l4 4"></path>';
const ICON_X = '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"></path>';
const ICON_CHEVRON = '<path d="M9.5 5.5L16 12l-6.5 6.5"></path>';
// The pill behind the selected tab glides to it (measured, so it fits any label).
function slideThumb(group) {
  const thumb = group?.querySelector('.seg-thumb'), on = group?.querySelector('button.on'); if (!thumb || !on) return;
  const place = () => { thumb.style.setProperty('--x', `${on.offsetLeft}px`); thumb.style.setProperty('--w', `${on.offsetWidth}px`); group.classList.add('ready'); };
  place(); requestAnimationFrame(place); setTimeout(place, 300);
}
// Rows that scroll sideways get two animated arrows instead of a scroll bar. They show only when there is more to
// see on that side, and the row's edges fade out. Trackpad, Shift + rueda and the keyboard keep working.
const ARROW_ROWS = '.rail,.people,.follow-strip,.disc-row';
function arrowize(row) {
  if (row.dataset.arrows || !row.parentNode) return; row.dataset.arrows = '1';
  const wrap = h('div', { class: 'hs-wrap' }); row.before(wrap); wrap.append(row);
  const arrow = (dir) => h('button', { type: 'button', class: `hs-arrow ${dir}`, 'aria-label': dir === 'prev' ? 'Ver anteriores' : 'Ver más', tabindex: '-1',
    onclick: () => { const by = (dir === 'prev' ? -1 : 1) * Math.max(240, row.clientWidth * .85), from = row.scrollLeft;
      row.scrollBy({ left: by, behavior: 'smooth' });
      setTimeout(() => { if (row.scrollLeft === from) { row.style.scrollBehavior = 'auto'; row.scrollLeft = from + by; row.style.scrollBehavior = ''; } }, 350); } }, h('span', { class: 'hs-ring', 'aria-hidden': 'true' }), svg(ICON_CHEVRON, 22));
  const prev = arrow('prev'), next = arrow('next'); wrap.append(prev, next);
  const update = () => {
    const max = row.scrollWidth - row.clientWidth - 2;
    wrap.classList.toggle('can-prev', row.scrollLeft > 2); wrap.classList.toggle('can-next', row.scrollLeft < max && max > 0);
  };
  row.addEventListener('scroll', update, { passive: true });
  new ResizeObserver(update).observe(row); new MutationObserver(update).observe(row, { childList: true });
  update(); setTimeout(update, 500);
}
const arrowizeAll = () => document.querySelectorAll(ARROW_ROWS).forEach((r) => { if (!r.dataset.arrows) arrowize(r); });
new MutationObserver(() => { clearTimeout(arrowizeAll.t); arrowizeAll.t = setTimeout(arrowizeAll, 60); }).observe(document.body, { childList: true, subtree: true });
setTimeout(arrowizeAll, 0);
// Popular long videos to clip (games, podcasts, entertainment), most viewed first. One click imports it from YouTube.
const DISCOVER_TABS = [['juegos', 'Juegos', 'game'], ['podcasts', 'Podcasts', 'mic'], ['entretenimiento', 'Entretenimiento', 'clapper']];
const discoverUI = { cat: 'juegos', cache: {} };
const viewsText = (n) => n >= 1e6 ? `${(n / 1e6).toLocaleString('es', { maximumFractionDigits: 1 })} M vistas` : n >= 1e3 ? `${Math.round(n / 1e3)} mil vistas` : `${n} vistas`;
function buildDiscover() {
  const box = h('section', { id: 'discoverBox', class: 'discover-box' },
    h('div', { class: 'disc-head' },
      h('div', {}, h('h2', {}, emo('fire'), 'Videos populares para clipear'), h('span', { class: 'muted', text: 'Los videos largos más vistos de grandes canales en español. Elige uno y la IA encuentra sus mejores momentos.' })),
      h('div', { id: 'discoverTabs', class: 'disc-tabs', role: 'tablist' }, h('span', { class: 'seg-thumb', 'aria-hidden': 'true' }),
        DISCOVER_TABS.map(([k, t, e]) => h('button', { type: 'button', role: 'tab', 'data-cat': k, onclick: () => { discoverUI.cat = k; paintDiscover(); } }, emo(e), h('span', { text: t }))))),
    h('div', { id: 'discoverRow', class: 'disc-row' }));
  setTimeout(paintDiscover, 0);
  return box;
}
async function paintDiscover() {
  const cat = discoverUI.cat, row = $('discoverRow'); if (!row) return;
  for (const b of document.querySelectorAll('#discoverTabs button')) { const on = b.dataset.cat === cat; b.classList.toggle('on', on); b.setAttribute('aria-selected', String(on)); }
  slideThumb($('discoverTabs'));
  if (!discoverUI.cache[cat]) {
    put(row, [0, 1, 2, 3, 4].map(() => h('div', { class: 'disc-card skeleton' }, h('span', { class: 'disc-thumb' }), h('i'), h('i'))));
    const data = await api(`/api/discover/videos?category=${cat}`).catch(() => ({ videos: [] }));
    if (data.videos?.length) discoverUI.cache[cat] = data.videos;
    if (discoverUI.cat !== cat) return;
    if (!data.videos?.length) { put(row, h('div', { class: 'empty', text: 'No se pudo leer YouTube ahora mismo. Revisa tu conexión e inténtalo más tarde.' })); return; }
  }
  put(row, discoverUI.cache[cat].map(discoverCard));
}
function discoverCard(v) {
  const hot = v.views >= 5e6;
  return h('article', { class: 'disc-card' + (hot ? ' hot' : '') },
    h('a', { class: 'disc-thumb', href: v.url, target: '_blank', rel: 'noopener', title: 'Ver en YouTube' },
      h('img', { src: v.thumb, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' }),
      h('span', { class: 'chip glass disc-views' }, hot ? emo('fire') : '', viewsText(v.views)),
      h('span', { class: 'chip glass disc-dur', text: fmtDur(v.duration) })),
    h('div', { class: 'disc-body' },
      h('span', { class: 'disc-who' }, avatarImg({ name: v.channel, avatar: v.avatar }, 28), h('span', { text: v.channel })),
      h('b', { class: 'disc-title', text: v.title, title: v.title }),
      h('button', { class: 'btn primary', type: 'button', text: 'Clipear este video', onclick: () => clipDiscovered(v) })));
}
// The latest finished streams of the Kick streamers you follow: one click imports the VOD (up to 8 h).
const vodAgo = (iso) => { const t = Date.parse((iso || '').replace(' ', 'T') + (/(Z|[+-]\d\d:?\d\d)$/.test(iso || '') ? '' : 'Z')); if (!t) return ''; const d = (Date.now() - t) / 864e5; return d < 1 ? 'hoy' : d < 2 ? 'ayer' : `hace ${Math.round(d)} días`; };
const vodHours = (s) => s >= 3600 ? `${Math.floor(s / 3600)} h ${String(Math.round(s % 3600 / 60)).padStart(2, '0')} min` : `${Math.round(s / 60)} min`;
function buildKickVods() {
  const box = h('section', { id: 'kickVodBox', class: 'discover-box kick-vods', hidden: true },
    h('div', { class: 'disc-head' },
      h('div', {}, h('h2', {}, platformLogo('kick'), 'VOD de tus streamers'), h('span', { class: 'muted', text: 'Los últimos directos que terminaron tus streamers de Kick. Clipéalos como un video largo: la IA encuentra sus mejores momentos.' }))),
    h('div', { id: 'kickVodRow', class: 'disc-row' }, [0, 1, 2, 3].map(() => h('div', { class: 'disc-card skeleton' }, h('span', { class: 'disc-thumb' }), h('i'), h('i')))));
  setTimeout(paintKickVods, 0);
  return box;
}
async function paintKickVods() {
  const box = $('kickVodBox'), row = $('kickVodRow'); if (!box) return;
  const data = await api('/api/kick/vods').catch(() => null);
  if (!data || !data.followed) { box.hidden = true; return; }       // nobody from Kick followed: the row stays out of the way
  box.hidden = false;
  if (!data.vods.length) { put(row, h('div', { class: 'empty', text: 'Tus streamers de Kick no tienen VOD públicos ahora mismo.' })); return; }
  put(row, data.vods.map((v) => h('article', { class: 'disc-card kick-vod' },
    h('a', { class: 'disc-thumb', href: v.url, target: '_blank', rel: 'noopener', title: 'Ver en Kick' },
      v.thumb ? h('img', { src: v.thumb, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer', onerror: (e) => e.target.remove() }) : null,
      h('span', { class: 'chip glass disc-views', text: vodAgo(v.created) }),
      h('span', { class: 'chip glass disc-dur', text: vodHours(v.duration) })),
    h('div', { class: 'disc-body' },
      h('span', { class: 'disc-who' }, avatarImg({ name: v.channel, avatar: v.avatar }, 28), h('span', { text: v.channel })),
      h('b', { class: 'disc-title', text: v.title, title: v.title }),
      v.duration > 8 * 3600 ? h('span', { class: 'muted kick-long', text: `Dura ${vodHours(v.duration)}: se importan 8 h desde el momento que elijas.` }) : null,
      h('button', { class: 'btn primary', type: 'button', text: 'Clipear este VOD', onclick: () => clipKickVod(v) })))));
}
function clipKickVod(v) {
  const panel = $('youtubePanel'); if (panel) panel.open = true;
  $('youtubeUrl').value = v.url; $('youtubeUrl').dispatchEvent(new Event('input', { bubbles: true }));
  $('kickStart').value = '0:00:00';
  panel?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  if (v.duration > 8 * 3600) {           // longer than 8 h: the user picks where to start, then imports
    $('kickStart').focus(); $('kickStart').select();
    toast('Elige desde dónde', `Este VOD dura ${vodHours(v.duration)}. Escribe el momento de inicio en «Desde» y pulsa «Importar VOD de Kick».`);
    return;
  }
  $('downloadYoutube').click();
}
function clipDiscovered(v) {
  const panel = $('youtubePanel'); if (panel) panel.open = true;
  $('youtubeUrl').value = v.url; $('youtubeUrl').dispatchEvent(new Event('input', { bubbles: true }));
  panel?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('downloadYoutube').click();
}
function buildAnalysisLayout() {
  const view = $('analysisView'); if (!view || view.dataset.v4) return; view.dataset.v4 = '1';
  const intro = view.querySelector('.intro');
  const thumbs = h('div', { class: 'lv-phones', 'aria-hidden': 'true' }, [0, 1, 2].map((i) => h('span', { class: 'lv-phone p' + i }, h('i'))));
  intro.replaceChildren(
    h('div', { class: 'lv-text' }, h('span', { class: 'eyebrow', text: 'ENCUENTRA UNA HISTORIA, NO SOLO UN CORTE' }),
      h('h1', {}, 'De un video largo a ', h('span', { class: 'grad', text: 'clips virales.' })),
      h('p', { text: 'Sube tu video o pega un enlace de YouTube. La IA local lo transcribe, entiende las historias y te propone los mejores momentos en vertical, con título y subtítulos.' }),
      h('div', { class: 'lv-feats' }, ['Transcripción local', 'IA sin pagar API', 'Clips 9:16 con título', 'Hasta 200 min'].map((t) => h('span', { class: 'lv-feat', text: t })))),
    h('div', { class: 'lv-visual', 'aria-hidden': 'true' },
      h('div', { class: 'lv-strip' }, h('div', { class: 'lv-frames' }), h('span', { class: 'lv-scan' })),
      h('span', { class: 'lv-arrow', text: '↓' }), thumbs));
  // Real images: frames of your latest long video on the strip, your best clips on the phones.
  api('/api/jobs').then((jobs) => {
    const long = jobs.filter((j) => j.kind !== 'live' && j.duration).sort((a, b) => b.updated - a.updated);
    const j = long[0]; const frames = intro.querySelector('.lv-frames');
    if (j) put(frames, [1, 2, 3, 4, 5, 6].map((k) => h('img', { src: `/api/jobs/${j.id}/frame?t=${Math.round(j.duration * k / 7)}`, alt: '', loading: 'lazy', onerror: (e) => e.target.remove() })));
    renderRecentVideos(long);
  }).catch(() => {});
  api('/api/library?sort=score').then((lib) => {
    const best = lib.items.filter((c) => !c.missing).slice(0, 3);
    best.forEach((c, i) => { const ph = intro.querySelector('.lv-phone.p' + i); if (ph) ph.replaceChildren(h('img', { src: c.thumb_url, alt: '', onerror: (e) => e.target.remove() })); });
  }).catch(() => {});
  // Steps
  const steps = h('ol', { class: 'lv-steps', 'aria-label': 'Pasos' }, [['Tu video', 'Archivo, YouTube o Kick'], ['Contexto', 'Opcional, mejora los títulos'], ['Motor de IA', 'Local, sin pagar'], ['Momentos', 'Revisa y edita']].map(([t, s], i) =>
    h('li', { 'data-step': String(i + 1) }, h('span', { class: 'n', text: String(i + 1) }), h('span', {}, h('b', { text: t }), h('small', { text: s })))));
  view.querySelector('.setup-grid').before(steps);
  steps.before(buildKickVods());
  steps.before(buildDiscover());
  const panels = view.querySelectorAll('.setup-grid > .panel');
  [['1', 'Tu video y su contexto'], ['2', 'Qué quieres encontrar']].forEach(([n, t], i) => { const h2 = panels[i]?.querySelector('h2'); if (h2) h2.replaceChildren(h('span', { class: 'lv-num', text: n }), t); });
  const markSteps = () => {
    const hasVideo = !!job && !$('analyze').disabled || !!job?.clips?.length;
    const running = !$('cancelAnalysis').classList.contains('hidden');
    const state = [hasVideo, !!$('videoContext').value.trim(), hasVideo, !!job?.clips?.length];
    steps.querySelectorAll('li').forEach((li, i) => { li.classList.toggle('done', state[i]); li.classList.toggle('now', !state[i] && state.slice(0, i).every(Boolean) || (i === 3 && running)); });
    view.classList.toggle('lv-running', running);
  };
  new MutationObserver(markSteps).observe($('analyze'), { attributes: true, attributeFilter: ['disabled'] });
  new MutationObserver(markSteps).observe($('cancelAnalysis'), { attributes: true, attributeFilter: ['class'] });
  $('videoContext').addEventListener('input', markSteps); markSteps();
  // Drag & drop a file onto the upload zone (same as choosing it with the button).
  const drop = $('videoFileDrop');
  for (const ev of ['dragenter', 'dragover']) drop.addEventListener(ev, (e) => { e.preventDefault(); if (!$('source').disabled) drop.classList.add('over'); });
  for (const ev of ['dragleave', 'drop']) drop.addEventListener(ev, () => drop.classList.remove('over'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault(); const f = e.dataTransfer?.files?.[0];
    if (!f || $('source').disabled) return;
    if (!/^video\//.test(f.type) && !/\.(mp4|mov|webm|mkv)$/i.test(f.name)) { toast('Ese archivo no es un video', 'Usa un MP4, MOV o WebM.'); return; }
    const dt = new DataTransfer(); dt.items.add(f); $('source').files = dt.files; $('source').dispatchEvent(new Event('change'));
  });
  drop.querySelector('h3').textContent = 'Arrastra tu video aquí';
  drop.querySelector('p').textContent = 'o elige el archivo · MP4, MOV o WebM · hasta 120 minutos · 12 GB';
  view.append(h('section', { id: 'lvRecent', class: 'lv-recent', hidden: true }));
}
function renderRecentVideos(long) {
  const box = $('lvRecent'); if (!box) return;
  const items = long.slice(0, 8); box.hidden = !items.length;
  put(box, h('div', { class: 'section-head' }, h('h2', { text: 'Tus videos recientes' }), h('span', { class: 'muted', text: 'Vuelve a uno para revisar sus clips o analizarlo otra vez. La transcripción guardada se reutiliza.' }),
      h('button', { class: 'btn ghost', type: 'button', text: 'Ver todos los proyectos', onclick: () => navigate('projects') })),
    h('div', { class: 'lv-recent-grid' }, items.map((j) => {
      const t = Math.round((j.duration || 0) / 3);
      return h('button', { class: 'card lv-video', type: 'button', onclick: () => openProject(j.id, null, j.clips ? 'editor' : 'analysis').catch((e) => toast('No se pudo abrir', e.message)) },
        h('span', { class: 'lv-thumb' }, previewBox(`/api/jobs/${j.id}/frame?t=${t}`, `/api/jobs/${j.id}/video`, t, 8), h('span', { class: 'chip glass', text: fmtDur(j.duration || 0) })),
        h('b', { text: j.title || j.name }), h('span', { class: 'muted', text: [j.clips ? `${j.clips} clips` : 'Sin analizar', j.updated ? ago(j.updated * 1000) : ''].filter(Boolean).join(' · ') }));
    })));
}
buildAnalysisLayout();

// --- Streamers: «En vivo ahora», search and profile photos -----------------------------------------------------------
let streamersCache = [];
async function loadStreamers() { streamersCache = await api('/api/streamers').catch(() => streamersCache); return streamersCache; }
function streamerFor(name) { const n = (name || '').toLowerCase(); return streamersCache.find((s) => s.name?.toLowerCase() === n || s.slug === n); }
function avatarImg(s, size, ring) {
  const style = `width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;flex:none;box-shadow:0 0 0 2px ${ring || (s?.live ? 'var(--live)' : '#2f2f36')}`;
  return s?.avatar ? h('img', { src: s.avatar, alt: '', style }) : h('span', { style: style + ';display:grid;place-items:center;background:var(--raise);color:var(--green);font:700 14px var(--head)', text: (s?.name || '?').slice(0, 2).toUpperCase() });
}
function clipThisStream(s) { $('liveUrl').value = s.url; navigate('live'); $('liveStart').click(); }
function watchStream(s) {
  // The platform's own player (the authorized way to watch), only when the user asks for it.
  const src = s.platform === 'kick' ? `https://player.kick.com/${encodeURIComponent(s.slug)}` : s.video_id ? `https://www.youtube.com/embed/${encodeURIComponent(s.video_id)}?autoplay=1` : '';
  if (!src) { window.open(s.url, '_blank', 'noopener'); return; }
  silenceOthers(null);
  const modal = h('div', { class: 'cs-modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': `Directo de ${s.name}`, onclick: (e) => { if (e.target === modal) modal.remove(); } },
    h('div', { class: 'box player-box' }, h('div', { style: 'display:flex;align-items:center;gap:12px' }, avatarImg(s, 36), h('b', { text: s.name, style: 'font:600 18px var(--head);flex:1' }), h('button', { class: 'btn ghost', type: 'button', text: 'Cerrar', onclick: () => modal.remove() })),
      h('iframe', { src, title: `Reproductor oficial de ${s.platform === 'kick' ? 'Kick' : 'YouTube'}`, allow: 'autoplay; fullscreen; picture-in-picture', allowfullscreen: true, referrerpolicy: 'strict-origin-when-cross-origin' }),
      h('div', { style: 'display:flex;gap:10px;justify-content:flex-end' }, h('button', { class: 'btn primary', type: 'button', text: 'Clipear este directo', onclick: () => { modal.remove(); clipThisStream(s); } }))));
  modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') modal.remove(); });
  document.body.append(modal);
}
function liveNowSection(list) {
  const live = list.filter((s) => s.live), off = list.filter((s) => !s.live && s.checked);
  if (!list.length) return null;
  return h('div', {}, h('div', { class: 'section-head' }, h('span', { style: 'width:9px;height:9px;border-radius:50%;background:var(--live);animation:pulse 1.8s infinite' }), h('h2', { text: 'En vivo ahora' }),
      h('span', { class: 'muted', text: live.length ? 'Primero los streamers que más clipeas. Desliza para ver más.' : 'Ninguno de tus streamers está en directo ahora. Se comprueba cada pocos minutos.' }), h('button', { class: 'btn ghost', type: 'button', text: 'Buscar otro streamer', onclick: () => { navigate('live'); $('liveUrl').focus(); } })),
    h('div', { class: 'rail' }, live.map((s, i) => streamCard(s, i === 0 && s.clips ? '★ El que más clipeas' : '')),
      off.length ? h('article', { class: 'card livecard', style: 'display:grid;place-items:center;text-align:center;padding:20px;border-style:dashed' },
        h('span', { style: 'display:flex;flex-direction:column;align-items:center;gap:10px' }, h('span', { style: 'display:flex' }, off.slice(0, 4).map((s) => h('span', { style: 'margin-left:-8px;filter:grayscale(1);opacity:.75' }, avatarImg(s, 44)))),
          h('b', { text: off.slice(0, 3).map((s) => s.name).join(', ') + (off.length > 3 ? ` y ${off.length - 3} más` : '') + (off.length === 1 ? ' no está en directo' : ' no están en directo') }), h('span', { class: 'muted', text: 'Aparecerán aquí cuando empiecen.' }))) : null));
}
// Recommended: the most relevant Kick streamers (Spanish-speaking first), shown as soon as they go live.
function featuredSection(list) {
  if (!list?.length) return null;
  return h('div', {}, h('div', { class: 'section-head' }, platformLogo('kick'), h('h2', { text: 'Recomendados en Kick' }),
      h('span', { class: 'muted', text: 'Los streamers más vistos de Kick que están en directo ahora. Desliza para ver más.' })),
    h('div', { class: 'rail' }, list.map((s) => streamCard(s, s.lang === 'es' ? 'Recomendado · Español' : 'Recomendado'))));
}
function streamCard(s, badge, canFollow) {
  return h('article', { class: 'card livecard' },
    h('div', { style: 'position:relative;aspect-ratio:16/9;background:var(--panel2);overflow:hidden;cursor:pointer', onclick: () => watchStream(s) },
      s.thumb ? h('img', { src: s.thumb, alt: `Directo de ${s.name}`, style: 'width:100%;height:100%;object-fit:cover;display:block', referrerpolicy: 'no-referrer', onerror: (e) => e.target.remove() }) : null,
      h('span', { class: 'chip live', style: 'position:absolute;left:10px;top:10px', text: '● EN VIVO' }), h('span', { class: 'chip logo', style: 'position:absolute;right:10px;top:12px' }, platformLogo(s.platform)),
      badge ? h('span', { class: 'chip', style: 'position:absolute;left:10px;bottom:10px;background:var(--green);color:var(--green-ink)', text: badge }) : null,
      s.viewers ? h('span', { class: 'chip glass', style: 'position:absolute;right:10px;bottom:10px', text: `${Number(s.viewers).toLocaleString('es')} espectadores` }) : null),
    h('div', { style: 'display:flex;align-items:center;gap:12px;padding:14px' }, avatarImg(s, 44),
      h('span', { style: 'display:flex;flex-direction:column;gap:3px;min-width:0;flex:1' }, h('b', { text: s.name, style: 'font:600 16px var(--head)' }), h('span', { class: 'muted', style: 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis', text: s.title || '' }),
        s.clips ? h('span', { style: 'font-size:12px;color:var(--green);font-weight:600', text: `${s.clips} clips tuyos de este streamer` }) : null),
      canFollow ? h('button', { class: 'btn ghost follow-mini', type: 'button', text: '+ Seguir', onclick: (e) => followStreamer(s, e.currentTarget) }) : null),
    h('div', { style: 'display:flex;gap:8px;padding:0 14px 14px' }, h('button', { class: 'btn primary', type: 'button', style: 'flex:1', text: 'Clipear este directo', onclick: () => clipThisStream(s) }), h('button', { class: 'btn ghost', type: 'button', text: 'Ver en directo', onclick: () => watchStream(s) })));
}
// Search by name in the link field of «Clips en vivo» (a link still works as before).
let searchTimer = null, searchToken = 0;
function setupStreamerSearch() {
  const input = $('liveUrl'); if (input.dataset.search) return; input.dataset.search = '1';
  input.placeholder = 'Busca a tu streamer por su nombre o pega el enlace del directo';
  const box = h('div', { id: 'streamerResults', class: 'card streamer-results', hidden: true });
  $('liveConnect').insertBefore(box, $('liveConnect').children[1]);
  input.addEventListener('focus', () => { if (!input.value.trim()) showResults('', [{ key: 'local', items: streamersCache }], true); });
  input.addEventListener('input', () => {
    clearTimeout(searchTimer); const q = input.value.trim();
    if (!q) { box.hidden = true; return; }
    const isLink = /^https?:|kick\.com\/|youtu/i.test(q);
    // Your streamers appear at once; Kick and YouTube suggestions are added as each one answers.
    searchTimer = setTimeout(() => {
      const token = ++searchToken, groups = [];
      const scopes = isLink ? ['link'] : ['local', 'kick', 'youtube'];
      let pending = scopes.length;
      showResults(q, groups, false);
      for (const scope of scopes) api(`/api/streamers/search?scope=${scope}&q=${encodeURIComponent(q)}`).catch(() => []).then((items) => {
        if (token !== searchToken) return;
        groups.push({ key: scope, items }); pending--; showResults(q, groups, pending === 0);
      });
    }, isLink ? 0 : 250);
  });
  function showResults(q, groups, finished) {
    const order = ['link', 'local', 'kick', 'youtube'], seen = new Set(), found = [];
    // The same channel can come from your list and from Kick / YouTube: keep one, and the «en vivo» one wins.
    const byKey = new Map();
    for (const g of groups.slice().sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key))) for (const s of g.items) {
      const prev = byKey.get(s.key);
      if (!prev) { byKey.set(s.key, s); found.push(s); }
      else if (s.live && !prev.live) { Object.assign(prev, s, { clips: prev.clips || s.clips, avatar: prev.avatar || s.avatar }); }
    }
    found.sort((a, b) => (b.live - a.live) || ((b.clips || 0) - (a.clips || 0)));
    box.hidden = false;
    put(box, h('span', { class: 'lbl', style: 'padding:6px 10px', text: !q ? 'Tus streamers' : found.length ? `Resultados para «${q}»${finished ? '' : ' · buscando en Kick y YouTube…'}` : finished ? 'Sin resultados: prueba con otro nombre o pega el enlace del directo' : `Buscando «${q}» en Kick y YouTube…` }),
        found.slice(0, 12).map((s) => h('div', { class: 'streamer-row' + (input.value === s.url ? ' on' : '') }, avatarImg(s, 52),
          h('span', { style: 'display:flex;flex-direction:column;gap:4px;min-width:0;flex:1' },
            h('span', { style: 'display:flex;align-items:center;gap:10px;flex-wrap:wrap' }, h('b', { text: s.name, style: 'font:600 17px var(--head)' }),
              h('span', { class: 'chip ' + (s.live ? 'live' : 'glass'), text: s.live ? '● EN VIVO' : 'Desconectado' }), platformLogo(s.platform)),
            h('span', { class: 'muted', style: 'white-space:nowrap;overflow:hidden;text-overflow:ellipsis', text: s.live ? s.title || 'En directo' : s.clips ? `${s.clips} clips tuyos` : (s.followers ? `${Number(s.followers).toLocaleString('es')} seguidores` : '') })),
          s.thumb ? h('img', { src: s.thumb, alt: '', referrerpolicy: 'no-referrer', style: 'width:120px;height:68px;object-fit:cover;border-radius:8px;flex:none', onerror: (e) => e.target.remove() }) : null,
          h('button', { class: 'btn ' + (s.live ? 'primary' : 'ghost'), type: 'button', text: s.live ? 'Elegir directo' : 'Seguir',
            onclick: async () => { input.value = s.url; box.hidden = true; await followUrl(s.url).catch(() => {}); loadStreamers();
              toast(s.live ? `${s.name} elegido` : `Sigues a ${s.name}`, s.live ? 'Pulsa «Iniciar clipping en vivo» para empezar.' : 'Te avisaremos en Inicio cuando esté en directo.'); } }))));
  }
  document.addEventListener('click', (e) => { if (!box.contains(e.target) && e.target !== input) box.hidden = true; });
}

// --- Configuración --------------------------------------------------------------------------------------------------
function renderSettings() {
  const host = $('settingsHost'); const panel = $('perfPanel');
  if (panel && panel.parentElement !== host) { host.append(panel); }
  panel?.classList.remove('hidden'); try { loadPerformance(); } catch {}
  renderStorage();
}
// Espacio en disco: temporary buffers of stopped live sessions; removed only after an explicit confirmation.
const gb = (mb) => mb >= 1000 ? `${(mb / 1000).toFixed(1).replace('.', ',')} GB` : `${Math.round(mb)} MB`;
async function renderStorage() {
  let box = $('storageBox');
  if (!box) { box = h('div', { id: 'storageBox', class: 'card', style: 'padding:20px;margin-top:18px' }); $('settingsHost').after(box); }
  put(box, h('p', { class: 'muted', text: 'Midiendo el espacio…' }));
  const st = await api('/api/storage').catch((e) => ({ error: e.message, buffers: [] }));
  const picked = new Set(st.buffers.map((b) => b.id));
  const total = () => st.buffers.filter((b) => picked.has(b.id)).reduce((a, b) => a + b.mb, 0);
  const button = h('button', { class: 'btn primary', type: 'button' });
  const refreshButton = () => { button.textContent = picked.size ? `Liberar ${gb(total())}` : 'Elige qué liberar'; button.disabled = !picked.size; };
  button.onclick = () => {
    const modal = h('div', { class: 'cs-modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Confirmar liberar espacio' },
      h('div', { class: 'box' }, h('h2', { text: `¿Liberar ${gb(total())}?` }),
        h('p', { text: `Se borran los archivos temporales de ${picked.size} directo${picked.size > 1 ? 's' : ''} detenido${picked.size > 1 ? 's' : ''}: la grabación de respaldo que se usa mientras el directo está en curso.` }),
        h('p', { text: 'Tus clips, los momentos detectados, las transcripciones y los proyectos NO se borran. Lo único que pierdes es poder buscar momentos nuevos en el pasado de esos directos.' }),
        h('p', { class: 'muted', text: 'Esto no se puede deshacer.' }),
        h('div', { class: 'acts' }, h('button', { class: 'btn ghost', type: 'button', text: 'Cancelar', onclick: () => modal.remove() }),
          h('button', { class: 'btn danger', type: 'button', text: 'Sí, liberar espacio', onclick: async () => {
            const r = await api('/api/storage/clean', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessions: [...picked], confirm: true }) }).catch((e) => ({ error: e.message }));
            modal.remove(); r.error ? toast('No se pudo liberar el espacio', r.error) : toast('Espacio liberado', `${gb(r.freed_mb)} libres. Tus clips siguen en la biblioteca.`); renderStorage(); } }))));
    modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') modal.remove(); });
    document.body.append(modal); modal.querySelector('.btn.ghost').focus();
  };
  refreshButton();
  put(box, h('h3', { text: 'Espacio en disco', style: 'font-size:20px;margin:0 0 6px' }),
    st.error ? h('p', { text: st.error }) : null,
    h('div', { class: 'storage-totals' }, [['Clips de directos', st.moments_mb], ['Exportados', st.exports_mb], ['Papelera', st.trash_mb], ['Temporales de directos', st.buffers_mb]].map(([t, v]) => h('div', {}, h('b', { text: gb(v || 0) }), h('span', { text: t })))),
    st.buffers.length ? h('div', {},
      h('p', { text: 'Temporales que se pueden liberar (directos ya detenidos):', style: 'margin:14px 0 8px' }),
      st.buffers.map((b) => { const cb = h('input', { type: 'checkbox', checked: true, onchange: () => { cb.checked ? picked.add(b.id) : picked.delete(b.id); refreshButton(); } });
        return h('label', { class: 'storage-row' }, cb, h('span', { style: 'flex:1;min-width:0' }, h('b', { text: b.channel }), h('span', { class: 'muted', text: ` · ${fmtDate(b.created)} · ${b.moments} momentos guardados` })), h('b', { text: gb(b.mb) })); }),
      h('div', { style: 'display:flex;justify-content:flex-end;margin-top:12px' }, button))
      : h('p', { class: 'muted', text: 'No hay archivos temporales de directos. Todo lo que ocupa espacio son tus clips y exportaciones.' }),
    h('p', { class: 'muted', text: `La papelera se vacía sola: lo que lleva más de ${st.trash_days || 30} días se borra al abrir la app.` }));
}

// «Configura tus clips» for a live stream starts with what was used last time for that streamer.
// «¿De cuántos segundos quieres los clips?» first thing before a live session starts (the min/max fields were easy to miss).
const CLIP_LENGTHS = [['short', 'Cortos', 15, 30, 'Reacciones rápidas'], ['medium', 'Medios', 20, 60, 'El momento con su contexto'], ['long', 'Largos', 45, 90, 'Historias completas']];
function buildDurationQuestion() {
  const box = $('cfgLiveDuration'); if (!box || box.dataset.q) return; box.dataset.q = '1';
  const inputs = [...box.children];
  const custom = h('div', { class: 'dur-custom', hidden: true }, inputs);
  const pick = (key) => {
    for (const b of box.querySelectorAll('.dur-opt')) { b.classList.toggle('on', b.dataset.key === key); b.setAttribute('aria-checked', String(b.dataset.key === key)); }
    custom.hidden = key !== 'custom';
    const preset = CLIP_LENGTHS.find((x) => x[0] === key);
    if (preset) { $('liveMin').value = preset[2]; $('liveMax').value = preset[3]; }
    paintDurationNote();
  };
  box.replaceChildren(
    h('div', { class: 'dur-head' }, h('span', { class: 'dur-eyebrow', text: 'DURACIÓN DE CADA CLIP' }), h('b', { text: '¿De cuántos segundos quieres los clips?' }), h('span', { class: 'dur-note', id: 'durNote' })),
    h('div', { class: 'dur-options', role: 'radiogroup', 'aria-label': 'Duración de los clips' },
      CLIP_LENGTHS.map(([key, name, a, b, why]) => h('button', { type: 'button', class: 'dur-opt', role: 'radio', 'data-key': key, onclick: () => pick(key) },
        key === 'medium' ? h('span', { class: 'dur-badge', text: 'Recomendado' }) : null,
        h('span', { class: 'dur-top' }, h('b', { text: name }), h('span', { class: 'dur-check', 'aria-hidden': 'true', text: '✓' })),
        h('span', { class: 'dur-range' }, h('strong', { text: `${a}–${b}` }), h('em', { text: 's' })),
        h('span', { class: 'dur-bar', 'aria-hidden': 'true' }, h('i', { style: `left:${a / 90 * 100}%;width:${(b - a) / 90 * 100}%` })),
        h('small', { text: why }))),
      h('button', { type: 'button', class: 'dur-opt', role: 'radio', 'data-key': 'custom', onclick: () => pick('custom') },
        h('span', { class: 'dur-top' }, h('b', { text: 'Personalizado' }), h('span', { class: 'dur-check', 'aria-hidden': 'true', text: '✓' })),
        h('span', { class: 'dur-range' }, h('strong', { text: '5–180' }), h('em', { text: 's' })),
        h('span', { class: 'dur-bar dashed', 'aria-hidden': 'true' }, h('i', { style: 'left:3%;width:94%' })),
        h('small', { text: 'Tú eliges mínimo y máximo' }))),
    custom);
  for (const id of ['liveMin', 'liveMax']) $(id).addEventListener('input', paintDurationNote);
  box.classList.add('dur-question');
}
function paintDurationNote() {
  const a = Number($('liveMin').value), b = Number($('liveMax').value), note = $('durNote'); if (!note) return;
  note.textContent = a >= b ? 'El máximo tiene que ser mayor que el mínimo.' : `Cada clip durará entre ${a} y ${b} segundos.`;
  note.classList.toggle('warn', a >= b);
}
// «¿Quiénes salen en el directo?»: names the transcriber should hear right and the titles should use (the stream's
// own title, description and tags are added by the app). Remembered per streamer.
function buildNamesField() {
  if ($('liveVocab')) return;
  const input = h('input', { id: 'liveVocab', type: 'text', maxlength: '600', autocomplete: 'off', placeholder: 'Ej.: JLexis, Kunno, La Mansión VIP' });
  const box = h('div', { id: 'cfgNames', class: 'cfg-group cfg-names' },
    h('span', { class: 'cfg-label', text: 'Nombres del directo' }),
    h('b', { class: 'names-q', text: '¿Quiénes salen en el directo?' }),
    h('label', { class: 'search names-input' }, svg('<path d="M20 21a8 8 0 0 0-16 0"></path><circle cx="12" cy="8" r="4"></circle>', 16), input),
    h('small', { class: 'muted', text: 'Opcional. Sepáralos con comas. La IA los escuchará bien en la transcripción y los usará en los títulos. También toma los nombres del título y la descripción del directo.' }));
  const duration = $('cfgLiveDuration')?.closest('.cfg-group');
  (duration || document.querySelector('#configModal .cfg-body'))?.after(box);
}
function syncDurationQuestion() {
  const a = Number($('liveMin').value), b = Number($('liveMax').value);
  const key = (CLIP_LENGTHS.find((x) => x[2] === a && x[3] === b) || ['custom'])[0];
  for (const btn of document.querySelectorAll('#cfgLiveDuration .dur-opt')) btn.classList.toggle('on', btn.dataset.key === key);
  const custom = document.querySelector('#cfgLiveDuration .dur-custom'); if (custom) custom.hidden = key !== 'custom';
  paintDurationNote();
}
// «Configura tus clips», ordered by what matters (parte 8): a fixed header, the essentials first (how long, which
// format, subtitles), the rest folded in «Opciones avanzadas» with a summary of what is set, and the buttons always
// in view. It used to be one long column that opened scrolled to the bottom (the start button took the focus), so
// the clip length — the first question — was hidden above.
function structureConfig() {
  const modal = $('configModal'), card = modal?.querySelector('.modal-card');
  if (!card || card.classList.contains('cfg-structured')) return;
  const groups = [...card.querySelectorAll(':scope > .cfg-group, :scope > div > .cfg-group')];
  const byLabel = (re) => groups.find((g) => re.test(g.querySelector(':scope > .cfg-label')?.textContent || ''));
  const duration = byLabel(/Duraci/), framing = byLabel(/Encuadre/), zoom = $('cfgZoomGroup'), subtitles = byLabel(/Subt/);
  const advanced = [byLabel(/Captura/), byLabel(/Idioma/), byLabel(/Seguimiento/), byLabel(/Calidad de exp/), byLabel(/Fondo del t/)].filter(Boolean);
  const head = h('div', { class: 'cfg-head' }), body = h('div', { class: 'cfg-body' });
  const actions = card.querySelector('.modal-actions');
  head.append($('configTitle'), $('configIntro'));
  if ($('cfgPrefsNote')) head.append($('cfgPrefsNote'));
  if ($('cfgNote') && subtitles) subtitles.append($('cfgNote'));          // the subtitles note belongs to subtitles
  const summary = h('span', { class: 'adv-summary' });
  const details = h('details', { class: 'cfg-advanced' },
    h('summary', {}, h('span', { class: 'adv-title' }, h('b', { text: 'Opciones avanzadas' }), summary), h('span', { class: 'adv-chev', 'aria-hidden': 'true', text: '⌄' })),
    h('div', { class: 'adv-body' }, advanced));
  body.append(...[duration, framing, zoom, subtitles].filter(Boolean), details);
  card.replaceChildren(head, body, actions);
  card.classList.add('cfg-structured'); card.tabIndex = -1;
  // what the advanced options are set to, without opening them
  const paintSummary = () => {
    const pick = (g) => { const i = g?.querySelector('.segmented input:checked'); return (i?.closest('label')?.textContent || i?.nextElementSibling?.textContent || '').trim(); };
    const sel = (id) => $(id)?.selectedOptions?.[0]?.textContent?.split('·')[0].trim() || '';
    const parts = modal.classList.contains('live-mode') ? [sel('liveHeight'), sel('liveBuffer'), sel('liveLanguage')] : [];
    parts.push($('cfgTracking')?.checked ? `seguimiento ${pick(byLabel(/Seguimiento/)).toLowerCase()}` : 'sin seguimiento', pick(byLabel(/Calidad de exp/))?.split('·')[0].trim(), pick(byLabel(/Fondo del t/))?.toLowerCase());
    summary.textContent = parts.filter(Boolean).join(' · ');
  };
  card.addEventListener('click', () => setTimeout(paintSummary, 0)); card.addEventListener('change', paintSummary);
  card._paintSummary = paintSummary;
}
const baseOpenConfig = openConfig;
window.openConfig = (mode) => {
  structureConfig();
  baseOpenConfig(mode);
  // always opens at the top, on the first question (the app's own code gave the focus to the start button)
  const card = $('configModal').querySelector('.modal-card');
  $('cfgStart').blur(); card.focus({ preventScroll: true }); card.querySelector('.cfg-body').scrollTop = 0;
  setTimeout(() => card._paintSummary?.(), 0);
  if (mode === 'live') { buildDurationQuestion(); syncDurationQuestion(); buildNamesField(); $('liveVocab').value = ''; }
  if ($('cfgNames')) $('cfgNames').hidden = mode !== 'live';
  if (mode === 'live') $('cfgStackNote').textContent = 'Para streams: la cámara del streamer arriba y el juego o la reacción abajo. Si el directo no tiene cámara, se usa Zoom.';
  const note = $('cfgPrefsNote') || h('p', { id: 'cfgPrefsNote', class: 'prefs-note', hidden: true });
  if (!note.parentElement) $('configIntro').after(note);
  note.hidden = true;
  if (mode !== 'live') return;
  const url = $('liveUrl').value.trim();
  api('/api/streamers/prefs?url=' + encodeURIComponent(url)).then((p) => {
    if (!p || !p.clip_settings) return;
    showConfig({ ...NEW_DEFAULTS, ...p.clip_settings });
    for (const [id, k] of [['liveMin', 'minimum'], ['liveMax', 'maximum'], ['liveHeight', 'height'], ['liveBuffer', 'buffer_minutes'], ['liveLanguage', 'language'], ['liveVocab', 'vocabulary']]) if (p[k] != null && $(id)) $(id).value = String(p[k]);
    note.textContent = `Usando la configuración que elegiste la última vez para ${p.name}. Puedes cambiarla.`; note.hidden = false; syncDurationQuestion();
  }).catch(() => {});
};
openConfig = window.openConfig;
// A live session never starts with a minimum longer than the maximum.
$('cfgStart').addEventListener('click', (e) => {
  if ($('cfgLiveDuration')?.offsetParent && Number($('liveMin').value) >= Number($('liveMax').value)) {
    e.stopImmediatePropagation(); e.preventDefault(); paintDurationNote(); toast('Revisa la duración', 'El máximo tiene que ser mayor que el mínimo.');
  }
}, true);

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
