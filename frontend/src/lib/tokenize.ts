export interface Token {
  type: "word" | "other";
  text: string;
}

const WORD_REGEX = /[\p{L}]+(?:[''\-][\p{L}]+)*/gu;

export function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(WORD_REGEX)) {
    const start = match.index!;
    const end = start + match[0].length;

    if (start > lastIndex) {
      tokens.push({ type: "other", text: text.slice(lastIndex, start) });
    }

    tokens.push({ type: "word", text: match[0] });
    lastIndex = end;
  }

  if (lastIndex < text.length) {
    tokens.push({ type: "other", text: text.slice(lastIndex) });
  }

  return tokens;
}