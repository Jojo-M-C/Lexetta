// The CEFR reading levels a user can pick, in order. Held here rather than
// fetched from the backend (the way languages are) because the CEFR scale is
// fixed — the backend validates against the same six codes in difficulty.py.
export const READING_LEVELS: { code: string; label: string }[] = [
  { code: "A1", label: "A1 — Beginner" },
  { code: "A2", label: "A2 — Elementary" },
  { code: "B1", label: "B1 — Intermediate" },
  { code: "B2", label: "B2 — Upper intermediate" },
  { code: "C1", label: "C1 — Advanced" },
  { code: "C2", label: "C2 — Proficient" },
];

export const DEFAULT_READING_LEVEL = "B1";