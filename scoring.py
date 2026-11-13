"""Final clip note: the judge's view, measured signals of the clip itself, and its place in its own video.

Why (Nov 2026): clips of a whole video averaged about 40/100 and almost all read as «flojo», so clippers took the tool
for a weak one. Three causes: the judge was told most moments are weak and boxed them at 40-64, filler segments kept to
cover 75% of the video sat in the same list, and the note only came from the text. The note is now

    note = 60% judge + 25% signals + 15% place in the video      (a live moment: 70% judge + 30% signals)

- judge: judge.score() for the clips it reviewed; otherwise the selector's own 0-100 score.
- signals: measured from the words' timestamps, no AI: it starts talking straight away (hook), it keeps a lively
  rhythm, and it has few dead pauses.
- place: the best clip of the video gets the full 15 points, the last one none. «Top 1 de este video» is a fact a
  clipper can use: which one to post first.

Filler kept only for coverage (no score) never gets a note: it goes to «Para revisar», out of the main list.
"""

BEST_FROM = 55            # from this note a clip is shown in the main list («Los mejores»); the top 3 always are
POTENTIAL_FROM = 70       # «Mayor potencial»
MARK_REASONS = (('gancho', 'Gancho fuerte'), ('desenlace', 'Remate claro'), ('humor', 'Humor'), ('polemica', 'Polémica'),
                ('conflicto', 'Conflicto'), ('emocion', 'Emoción'), ('suspenso', 'Suspenso'))


def signals(words, duration):
    """0-100 from the clip's words (times relative to the clip start), with what was measured.
    hook: the first words come early and the first 3 s say something; rhythm: 1.8-4.5 words/s; pauses: share of the
    clip in gaps longer than 0.7 s (0 best)."""
    duration = max(float(duration or 0), .1)
    ws = sorted((w for w in words or [] if str(w.get('text', '')).strip()), key=lambda w: w['start'])
    if not ws: return {'score': 0, 'hook': 0., 'rate': 0., 'pauses': 1.}
    first = max(0., ws[0]['start'])
    early = sum(1 for w in ws if w['start'] < 3)
    hook = max(0., 1 - first / 2.) * .5 + min(1., early / 6) * .5
    rate = len(ws) / duration
    rhythm = 1. if 1.8 <= rate <= 4.5 else max(0., 1 - (1.8 - rate) / 1.8) if rate < 1.8 else max(0., 1 - (rate - 4.5) / 3)
    gaps = [b['start'] - a['end'] for a, b in zip(ws, ws[1:])] + [first, max(0., duration - ws[-1]['end'])]
    pauses = min(1., sum(g for g in gaps if g > .7) / duration)
    score = round(100 * (.4 * hook + .35 * rhythm + .25 * (1 - pauses)))
    return {'score': max(0, min(100, score)), 'hook': round(hook, 2), 'rate': round(rate, 2), 'pauses': round(pauses, 2)}


def reasons(marks=None, sig=None, rank=None):
    """Up to four short reasons shown on the card: why this note."""
    out = []
    if rank == 1: out.append('Top 1 de este video')
    elif rank and rank <= 3: out.append(f'Top {rank} de este video')
    for key, label in sorted(MARK_REASONS, key=lambda kl: -int((marks or {}).get(kl[0]) or 0)):
        if int((marks or {}).get(key) or 0) >= 7 and len(out) < 3: out.append(label)
    if sig:
        if sig.get('hook', 0) >= .8 and len(out) < 4: out.append('Arranca al grano')
        if sig.get('pauses', 1) <= .08 and len(out) < 4: out.append('Sin silencios')
    return out[:4]


def base(judged, sig_score, live=False):
    """The note before its place in the video (all a live moment gets)."""
    return round(.7 * judged + .3 * sig_score) if live else round((.60 * judged + .25 * sig_score) / .85)


def judge_order(clips, limit):
    """The clips the viral judge reviews, at most `limit`: the AI's own picks by their score first, then coverage clips
    (no score yet) in time order. When the AI marks no moment, every clip is coverage and all of them still get a note
    (E-20c: a real Ibai video had 20 coverage clips, none judged, and «Los mejores» came out empty)."""
    picked = sorted((c for c in clips if c.get('score') is not None), key=lambda c: -c['score'])
    coverage = sorted((c for c in clips if c.get('score') is None), key=lambda c: c['start'])
    return (picked + coverage)[:limit]


def rank_video(clips, words_of):
    """Final notes, ranks, reasons and sections for the clips of one video, best first; filler (no score) after them in
    time order. `words_of(clip)` gives the clip's words with times relative to its start."""
    scored, filler = [], []
    for c in clips:
        # Unjudged coverage, or what the judge itself called filler, waits in «Para revisar».
        if c.get('score') is None or c.get('verdict') == 'descartar': filler.append(dict(c, section='review', reasons=[])); continue
        sig = signals(words_of(c), c['end'] - c['start'])
        scored.append(dict(c, judge_score=c['score'], signals=sig, _base=base(c['score'], sig['score'])))
    scored.sort(key=lambda c: -c['_base'])
    n = len(scored)
    for i, c in enumerate(scored):
        place = 100 if n == 1 else 100 * (1 - i / (n - 1))
        note = int(round(max(0, min(99, .85 * c.pop('_base') + .15 * place))))
        c.update(score=note, rank=i + 1, rank_total=n, potential=note >= POTENTIAL_FROM,
                 section='best' if note >= BEST_FROM or (i < 3 and note >= 35) else 'review', reasons=reasons(c.get('marks'), c['signals'], i + 1))
    filler.sort(key=lambda c: c['start'])
    return scored + filler
