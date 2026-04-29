const DIFFICULT_WORDS = new Set(
  [
    "exploring",
    "itinerary",
    "sights",
    "incredible",
    "monument",
    "Thames",
    "Paddington",
    "carefully",
    "vibrant",
    "pierced",
    "etched",
  ].map((w) => w.toLowerCase())
);

export function isDifficult(word: string): boolean {
  return DIFFICULT_WORDS.has(word.toLowerCase());
}