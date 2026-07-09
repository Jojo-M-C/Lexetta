// Shown when the difficulty model is unreachable. Deliberately not a CEFR
// fallback: mixing rule-based highlights into an ML session would pollute the
// logged research data, so the page stays readable but unhighlighted.
export default function OutageBanner() {
  return (
    <div
      role="status"
      className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800 shadow-sm"
    >
      Highlighting is unavailable — the difficulty model is offline. You can
      still click any word to translate it.
    </div>
  );
}