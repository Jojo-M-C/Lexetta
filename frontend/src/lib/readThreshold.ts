// How long a reader must actively dwell on a page before we treat it as "read"
// and commit its words to read_words as training data. The threshold scales with
// the page's word count (a longer page needs proportionally more time), bounded
// so a tiny page can't auto-commit instantly and a walk-away isn't punished
// forever. Tune these from thesis reading-behaviour data.
const WPM = 150; // assumed L2 reading speed, words per minute
const FLOOR_MS = 4000; // minimum dwell, even for a near-empty page
const CAP_MS = 120000; // maximum dwell we'll ever wait for

export function readThresholdMs(wordCount: number): number {
  const raw = (wordCount / WPM) * 60000;
  return Math.min(CAP_MS, Math.max(FLOOR_MS, raw));
}
