import type { Token as TokenData } from "../lib/tokenize";

interface Props {
  token: TokenData;
  paragraphId: number;
  difficultWords: Set<string>;
  onWordClick: (
    word: string,
    paragraphId: number,
    wasHighlighted: boolean,
    anchor: HTMLElement
  ) => void;
}

export default function Token({ token, paragraphId, difficultWords, onWordClick }: Props) {
  if (token.type === "other") {
    return <span>{token.text}</span>;
  }

  const difficult = difficultWords.has(token.text.toLowerCase());

  const handleClick = (e: React.MouseEvent<HTMLSpanElement>) => {
    onWordClick(token.text, paragraphId, difficult, e.currentTarget);
  };

  return (
    <span
      onClick={handleClick}
      className={
        difficult
          ? "bg-orange-100 rounded px-1 cursor-pointer hover:bg-orange-200"
          : "cursor-pointer hover:bg-gray-100 rounded"
      }
    >
      {token.text}
    </span>
  );
}