"""Speech quality of a proposed clip: a clip people watch is someone talking, not silence around a few words.

Measured on a real HotSpanish live (Nov 2026): the clips users found empty had 1.4-1.9 words per second and pauses of
5-7 s inside; normal Spanish conversation is about 2.5-3.5 words per second. A clip is kept when, after cutting at its
long pauses, the part with the most speech is still long enough and dense enough.
"""

MAX_PAUSE_S = 4.5        # a longer silence inside a clip splits it
MIN_RATE = 1.7           # words per second in the part that is kept
MIN_WORDS = 12
LEAD_S, TAIL_S = .3, .6  # air before the first word and after the last


def speech_span(words, start, end, minimum):
    """(start, end) of the part of the clip worth keeping, or None. `words` are dicts with start/end (any order)."""
    inside = sorted((w for w in words if start <= w['start'] < end), key=lambda w: w['start'])
    if len(inside) < MIN_WORDS: return None
    groups, current = [], [inside[0]]
    for prev, w in zip(inside, inside[1:]):
        if w['start'] - prev['end'] > MAX_PAUSE_S: groups.append(current); current = [w]
        else: current.append(w)
    groups.append(current)
    best = max(groups, key=len)
    a = max(start, best[0]['start'] - LEAD_S); b = min(end, best[-1]['end'] + TAIL_S)
    if b - a < minimum:
        # too short once the silence is cut: widen to the minimum within the clip, around the speech
        missing = minimum - (b - a); a = max(start, a - missing / 2); b = min(end, a + minimum); a = max(start, b - minimum)
        if b - a < minimum - .05: return None
    said = [w for w in inside if a <= w['start'] < b]
    if len(said) < MIN_WORDS or len(said) / (b - a) < MIN_RATE: return None
    gaps = [y['start'] - x['end'] for x, y in zip(said, said[1:])]
    if gaps and max(gaps) > MAX_PAUSE_S: return None
    return round(a, 3), round(b, 3)
