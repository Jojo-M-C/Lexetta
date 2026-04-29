import { isDifficult } from "../lib/difficult-words";
import type { Token as TokenData } from "../lib/tokenize";

interface Props {
  token: TokenData;
  paragraphId: number;
  onWordClick: (word: string, paragraphId: number, wasHighlighted: boolean) => void;
}

export default function Token({ token, paragraphId, onWordClick }: Props) {
  if (token.type === "other") {
    return <span>{token.text}</span>;
  }

  const difficult = isDifficult(token.text);

  const handleClick = () => {
    onWordClick(token.text, paragraphId, difficult);
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