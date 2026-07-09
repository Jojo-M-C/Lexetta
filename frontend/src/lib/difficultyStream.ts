import { api } from "../api";
import { tokenize } from "./tokenize";

// Two sentences is roughly one batch of model work (~1s), so highlights appear
// in visible steps instead of one long stall.
const SENTENCES_PER_CHUNK = 2;

// Deliberately crude. The server re-segments each chunk with spaCy before
// scoring, so this only decides how the page is sliced into progressive updates
// — never what context the model actually sees.
function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function sentenceChunks(
  texts: string[],
  perChunk: number = SENTENCES_PER_CHUNK
): string[][] {
  const sentences = texts.flatMap(splitSentences);
  const chunks: string[][] = [];
  for (let i = 0; i < sentences.length; i += perChunk) {
    chunks.push(sentences.slice(i, i + perChunk));
  }
  return chunks;
}

/**
 * Score a page's text in reading order, reporting each chunk's difficult words
 * as soon as they land so the reader can highlight progressively.
 *
 * Chunks are requested sequentially on purpose: the Modal GPU container handles
 * one input at a time, so overlapping requests would only queue behind each
 * other while making cancellation harder.
 *
 * `ctx` is omitted for PDFs, which have no page rows to log highlights against.
 */
export async function streamDifficulty(
  texts: string[],
  ctx: { documentId: number; pageNumber: number } | undefined,
  onWords: (words: string[]) => void,
  isCancelled: () => boolean
): Promise<void> {
  // Highlights are decided per word type, not per occurrence, so a word already
  // sent in an earlier chunk must not be scored again. On a typical page most
  // surviving tokens are repeats, so this is the difference between scoring ~200
  // tokens and ~60.
  const alreadySent = new Set<string>();

  for (const chunk of sentenceChunks(texts)) {
    if (isCancelled()) return;

    const exclude = [...alreadySent];
    for (const text of chunk) {
      for (const tok of tokenize(text)) {
        if (tok.type === "word") alreadySent.add(tok.text.toLowerCase());
      }
    }

    let difficult: string[];
    try {
      ({ difficult } = await api.getDifficulty(chunk, ctx, exclude));
    } catch (e) {
      // One bad chunk shouldn't stop the rest of the page from highlighting.
      console.error("difficulty chunk failed:", e);
      continue;
    }
    if (isCancelled()) return;
    if (difficult.length > 0) onWords(difficult);
  }
}