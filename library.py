"""Permanent clip library: one index of every clip, from analysed videos and from live sessions.

Safety rules (Nov 2026):
- The index is ADDITIVE. Building or refreshing it only reads job.json / state.json and never moves, rewrites or
  deletes a video, transcript or project. A row the sources no longer list stays in the library (marked missing).
- Fields the user sets (favourite, tags, title override, status 'edited'/'exported', removal) are never overwritten
  by a refresh.
- Removing a clip hides it (recoverable). "Also the file" moves only files that belong to that clip alone (a live
  moment's MP4, its exports) into data/papelera/<date>/, kept 30 days; a video shared by several clips is never moved.
- Before the first index build a backup of every job.json and state.json goes to data/backups/.
SQLite (Python standard library) in WAL mode: crash-safe, no new dependency.
"""
import json, os, shutil, sqlite3, subprocess, threading, time, zipfile
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ('detected', 'draft', 'edited', 'exported')
TRASH_DAYS = 30
SCHEMA = """
CREATE TABLE IF NOT EXISTS clips(
  id TEXT PRIMARY KEY, origin TEXT, channel TEXT, platform TEXT, session_id TEXT, project_id TEXT, clip_ref TEXT,
  title TEXT, user_title TEXT, start REAL, end REAL, duration REAL, score REAL, category TEXT, text TEXT,
  created TEXT, updated TEXT, status TEXT DEFAULT 'detected', favorite INTEGER DEFAULT 0, tags TEXT DEFAULT '[]',
  file TEXT, thumb TEXT, missing INTEGER DEFAULT 0, removed INTEGER DEFAULT 0, removed_at TEXT, trashed TEXT);
CREATE INDEX IF NOT EXISTS clips_channel ON clips(channel);
CREATE INDEX IF NOT EXISTS clips_created ON clips(created);
CREATE TABLE IF NOT EXISTS exports(id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id TEXT, path TEXT, created TEXT, resolution INTEGER);
CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, kind TEXT, text TEXT, ref TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def platform_of(url):
    url = (url or '').lower()
    return 'kick' if 'kick.com' in url else 'youtube' if 'youtu' in url else 'local'


class Library:
    def __init__(self, data):
        self.data = Path(data); self.data.mkdir(parents=True, exist_ok=True); self.path = self.data / 'library.db'; self.lock = threading.RLock()
        first = not self.path.exists()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript(SCHEMA)
        if first: self.backup('antes-de-la-biblioteca')

    # --- safety -----------------------------------------------------------------------------------------------------
    def backup(self, label):
        """Zip of every job.json / state.json (small files), before changing how data is organised."""
        folder = self.data / 'backups'; folder.mkdir(exist_ok=True)
        target = folder / f'{datetime.now():%Y%m%d-%H%M%S}-{label}.zip'
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in list(self.data.glob('*/job.json')) + list((self.data / 'live').glob('*/state.json')):
                z.write(p, p.relative_to(self.data))
        return target

    def log(self, kind, text, ref=''):
        with self.lock: self.db.execute('INSERT INTO activity(at,kind,text,ref) VALUES(?,?,?,?)', (now(), kind, text, ref))

    # --- building the index from what is already on disk --------------------------------------------------------------
    def _upsert(self, row):
        """Insert a new clip, or refresh only the fields the sources own (never the user's)."""
        with self.lock:
            old = self.db.execute('SELECT status,missing FROM clips WHERE id=?', (row['id'],)).fetchone()
            if old is None:
                row.setdefault('created', now()); row['updated'] = row['created']
                cols = ','.join(row); self.db.execute(f'INSERT INTO clips({cols}) VALUES({",".join("?" * len(row))})', tuple(row.values()))
                return True
            keep = {k: v for k, v in row.items() if k in ('channel', 'platform', 'session_id', 'project_id', 'clip_ref', 'title', 'start', 'end', 'duration', 'score', 'category', 'text', 'file')}
            keep['missing'] = 0
            # Status only moves forward from the source (detected -> draft); the user's edited/exported stays.
            if row.get('status') == 'draft' and old['status'] == 'detected': keep['status'] = 'draft'
            self.db.execute(f'UPDATE clips SET {",".join(k + "=?" for k in keep)} WHERE id=?', (*keep.values(), row['id']))
            return False

    def sync_job(self, job):
        """Clips of an analysed video. A job opened from a live moment belongs to that moment's row."""
        added = 0
        live = job.get('live')
        if live:
            with self.lock:
                self.db.execute("UPDATE clips SET project_id=?, status=CASE WHEN status='detected' THEN 'draft' ELSE status END WHERE id=?",
                                (job['id'], f"live:{live['session']}:{live['moment']}"))
            return 0
        youtube = job.get('youtube') or {}
        channel = youtube.get('channel') or 'Mis videos'
        platform = 'youtube' if youtube else 'local'
        for clip in job.get('clips', []):
            added += self._upsert(dict(id=f"job:{job['id']}:{clip['id']}", origin='video', channel=channel, platform=platform, session_id='',
                                      project_id=job['id'], clip_ref=clip['id'], title=clip.get('title') or 'Clip', start=clip['start'], end=clip['end'],
                                      duration=round(clip['end'] - clip['start'], 2), score=clip.get('score'), category=clip.get('category', ''),
                                      text=(clip.get('text') or '')[:2000], file=str(self.data / job['id'] / 'source'),
                                      created=job.get('created') or _mtime(self.data / job['id'] / 'job.json')))
        return added

    def sync_session(self, state, folder):
        """Moments of a live session (state.json). Discarded moments stay hidden but are kept."""
        added = 0
        sid = state.get('id') or Path(folder).name
        channel = state.get('channel') or (state.get('url') or '').rstrip('/').split('/')[-1] or 'Directo'
        for m in state.get('moments', []):
            mp4 = Path(folder) / 'moments' / f"{m['id']}.mp4"
            row = dict(id=f"live:{sid}:{m['id']}", origin='live', channel=channel, platform=platform_of(state.get('url')), session_id=sid,
                       project_id=m.get('job_id') or '', clip_ref=m['id'], title=m.get('title') or 'Momento del directo',
                       start=m.get('start', 0), end=m.get('end', 0), duration=m.get('duration') or round(m.get('end', 0) - m.get('start', 0), 1),
                       score=m.get('score'), category=m.get('category', ''), text=(m.get('text') or '')[:2000], file=str(mp4),
                       status='draft' if m.get('job_id') else 'detected', created=_session_time(state, m, mp4))
            added += self._upsert(row)
            if m.get('status') == 'discarded':
                with self.lock: self.db.execute("UPDATE clips SET removed=1, removed_at=COALESCE(removed_at,?) WHERE id=? AND removed=0", (now(), row['id']))
        return added

    def sync_all(self, jobs, live_dir):
        added = 0
        for job in jobs:
            try: added += self.sync_job(job)
            except (KeyError, TypeError, ValueError): continue
        live_dir = Path(live_dir)
        if live_dir.exists():
            for folder in live_dir.iterdir():
                f = folder / 'state.json'
                if not f.exists(): continue
                try: added += self.sync_session(json.loads(f.read_text(encoding='utf-8')), folder)
                except (OSError, ValueError, KeyError, TypeError): continue
        with self.lock:
            for r in self.db.execute('SELECT id,file FROM clips WHERE removed=0').fetchall():
                gone = 0 if (r['file'] and Path(r['file']).exists()) else 1
                self.db.execute('UPDATE clips SET missing=? WHERE id=?', (gone, r['id']))
        return added

    # --- reading ----------------------------------------------------------------------------------------------------
    def list(self, q='', origin='', status='', platform='', channel='', favorite=False, removed=False, sort='recent', min_score=None,
             min_dur=None, max_dur=None, limit=500):
        where, args = ['removed=?'], [1 if removed else 0]
        if q:
            where.append('(COALESCE(user_title,title) LIKE ? OR text LIKE ? OR channel LIKE ? OR tags LIKE ?)'); args += [f'%{q}%'] * 4
        for col, val in (('origin', origin), ('status', status), ('platform', platform), ('channel', channel)):
            if val: where.append(f'{col}=?'); args.append(val)
        if favorite: where.append('favorite=1')
        if min_score is not None: where.append('COALESCE(score,0)>=?'); args.append(min_score)
        if min_dur is not None: where.append('duration>=?'); args.append(min_dur)
        if max_dur is not None: where.append('duration<=?'); args.append(max_dur)
        order = {'recent': 'created DESC', 'score': 'COALESCE(score,0) DESC, created DESC', 'duration': 'duration DESC', 'title': 'COALESCE(user_title,title)'}.get(sort, 'created DESC')
        with self.lock:
            rows = self.db.execute(f'SELECT * FROM clips WHERE {" AND ".join(where)} ORDER BY {order} LIMIT ?', (*args, limit)).fetchall()
        return [self.public(r) for r in rows]

    def public(self, r):
        d = dict(r); d['tags'] = json.loads(d.get('tags') or '[]'); d['favorite'] = bool(d['favorite']); d['missing'] = bool(d['missing'])
        d['title'] = d.pop('user_title') or d['title']; d['thumb_url'] = f"/api/library/{d['id']}/thumb"; d.pop('file', None); d.pop('trashed', None)
        return d

    def get(self, cid):
        with self.lock: r = self.db.execute('SELECT * FROM clips WHERE id=?', (cid,)).fetchone()
        return r

    def summary(self):
        """Counts for the filters and the streamer row: how often each streamer is clipped comes first."""
        with self.lock:
            total = self.db.execute('SELECT origin, COUNT(*) n FROM clips WHERE removed=0 GROUP BY origin').fetchall()
            channels = self.db.execute('SELECT channel, platform, COUNT(*) n, COUNT(DISTINCT session_id) sessions, MAX(created) last '
                                       'FROM clips WHERE removed=0 GROUP BY channel, platform ORDER BY n DESC').fetchall()
            removed = self.db.execute('SELECT COUNT(*) FROM clips WHERE removed=1').fetchone()[0]
            activity = self.db.execute('SELECT at,kind,text,ref FROM activity ORDER BY id DESC LIMIT 12').fetchall()
        by = {r['origin']: r['n'] for r in total}
        return dict(total=sum(by.values()), live=by.get('live', 0), video=by.get('video', 0), removed=removed,
                    channels=[dict(r) for r in channels], activity=[dict(r) for r in activity])

    # --- changes the user makes ----------------------------------------------------------------------------------------
    def update(self, cid, favorite=None, tags=None, title=None, status=None):
        sets, args = ['updated=?'], [now()]
        if favorite is not None: sets.append('favorite=?'); args.append(1 if favorite else 0)
        if tags is not None: sets.append('tags=?'); args.append(json.dumps(sorted({t.strip()[:24] for t in tags if t.strip()})[:12], ensure_ascii=False))
        if title is not None: sets.append('user_title=?'); args.append(title.strip()[:120] or None)
        if status is not None:
            if status not in STATUSES: raise ValueError('Estado no válido.')
            sets.append('status=?'); args.append(status)
        with self.lock:
            if not self.db.execute('UPDATE clips SET ' + ','.join(sets) + ' WHERE id=?', (*args, cid)).rowcount: raise KeyError(cid)

    def mark(self, cid, status):
        """Status moves forward only: detected < draft < edited < exported."""
        with self.lock:
            r = self.get(cid)
            if r and STATUSES.index(status) > STATUSES.index(r['status'] or 'detected'):
                self.db.execute('UPDATE clips SET status=?, updated=? WHERE id=?', (status, now(), cid))

    def record_export(self, cid, path, resolution):
        with self.lock:
            self.db.execute('INSERT INTO exports(clip_id,path,created,resolution) VALUES(?,?,?,?)', (cid, str(path), now(), resolution))
        self.mark(cid, 'exported')

    def exports(self, cid):
        with self.lock: return [dict(r) for r in self.db.execute('SELECT path,created,resolution FROM exports WHERE clip_id=? ORDER BY id DESC', (cid,))]

    def owned_files(self, cid):
        """Files that belong to this clip alone: a live moment's MP4 (not if a project uses it) and its exports."""
        r = self.get(cid)
        if r is None: return []
        files = [Path(e['path']) for e in self.exports(cid)]
        if r['origin'] == 'live' and r['file']: files.append(Path(r['file']))
        return [f for f in files if f.exists() and f.is_file()]

    def remove(self, cid, files=False):
        r = self.get(cid)
        if r is None: raise KeyError(cid)
        moved = []
        if files:
            trash = self.data / 'papelera' / f'{datetime.now():%Y-%m-%d}'; trash.mkdir(parents=True, exist_ok=True)
            for f in self.owned_files(cid):
                target = trash / f'{cid.replace(":", "_")}--{f.name}'
                shutil.move(str(f), target); moved.append(dict(original=str(f), trash=str(target)))
        with self.lock:
            self.db.execute('UPDATE clips SET removed=1, removed_at=?, trashed=? WHERE id=?', (now(), json.dumps(moved) if moved else None, cid))
        self.log('remove', f"Clip quitado de la biblioteca{' (archivo en la papelera)' if moved else ''}: {r['user_title'] or r['title']}", cid)
        return moved

    def restore(self, cid):
        r = self.get(cid)
        if r is None: raise KeyError(cid)
        for item in json.loads(r['trashed'] or '[]'):
            src, dst = Path(item['trash']), Path(item['original'])
            if src.exists() and not dst.exists(): dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), dst)
        with self.lock: self.db.execute('UPDATE clips SET removed=0, removed_at=NULL, trashed=NULL WHERE id=?', (cid,))

    def empty_trash(self, days=TRASH_DAYS):
        """Delete trash folders older than `days` (called at startup)."""
        root = self.data / 'papelera'
        if not root.exists(): return 0
        limit = time.time() - days * 86400; n = 0
        for folder in root.iterdir():
            if folder.is_dir() and folder.stat().st_mtime < limit: shutil.rmtree(folder, ignore_errors=True); n += 1
        return n

    # --- thumbnails (background, one at a time, low priority) ---------------------------------------------------------
    def thumb_path(self, cid):
        return self.data / 'thumbs' / (cid.replace(':', '_') + '.jpg')

    def make_thumb(self, cid):
        r = self.get(cid)
        if r is None or not r['file'] or not Path(r['file']).exists(): return None
        target = self.thumb_path(cid); target.parent.mkdir(exist_ok=True)
        if target.exists(): return target
        if r['origin'] == 'live':
            base = 3.0; t = base + max(0.5, (r['duration'] or 10) * .35)        # moment files start 3 s before the moment
        else:
            t = (r['start'] or 0) + max(0.5, (r['duration'] or 10) * .35)
        flags = 0x00004000 if os.name == 'nt' else 0                            # BELOW_NORMAL_PRIORITY_CLASS
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', r['file'], '-frames:v', '1', '-vf', 'scale=480:-2', '-q:v', '5', str(target)],
                       capture_output=True, timeout=60, creationflags=flags)
        return target if target.exists() else None


def _mtime(path):
    try: return datetime.fromtimestamp(Path(path).stat().st_mtime, timezone.utc).isoformat(timespec='seconds')
    except OSError: return now()


def _session_time(state, moment, mp4):
    if Path(mp4).exists(): return _mtime(mp4)
    return state.get('created') or now()
