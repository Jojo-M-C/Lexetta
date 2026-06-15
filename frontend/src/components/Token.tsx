import { useEffect, useRef } from "react";
import type { Token as TokenData } from "../lib/tokenize";

// How long the cursor must rest on a word before its translation is fetched.
const HOVER_DELAY_MS = 500;

interface Props {
  token: TokenData;
  paragraphId: number;
  difficultWords: Set<string>;
  onWordHover: (
    word: string,
    paragraphId: number,
    wasHighlighted: boolean,
    anchor: HTMLElement
  ) => void;
  onWordLeave: () => void;
}

export default function Token({
  token,
  paragraphId,
  difficultWords,
  onWordHover,
  onWordLeave,
}: Props) {
  // Pending hover-intent timer for this word, cleared if the cursor leaves
  // before it fires (or the component unmounts on page change).
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, []);

  if (token.type === "other") {
    return <span>{token.text}</span>;
  }

  const difficult = difficultWords.has(token.text.toLowerCase());

  const handleMouseEnter = (e: React.MouseEvent<HTMLSpanElement>) => {
    const anchor = e.currentTarget;
    timerRef.current = window.setTimeout(() => {
      onWordHover(token.text, paragraphId, difficult, anchor);
    }, HOVER_DELAY_MS);
  };

  const handleMouseLeave = () => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    onWordLeave();
  };

  return (
    <span
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={
        difficult
          ? "bg-orange-100 rounded px-1 cursor-default hover:bg-orange-200"
          : "cursor-default hover:bg-gray-100 rounded"
      }
    >
      {token.text}
    </span>
  );
}