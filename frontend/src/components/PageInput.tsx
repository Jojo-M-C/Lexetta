import { useEffect, useState } from "react";

interface Props {
  currentPage: number;
  totalPages: number;
  onJump: (page: number) => void;
}

// The "Page N of M" indicator, where N is an editable field: type a page and
// press Enter (or blur) to jump there. Values are clamped to a valid page.
export default function PageInput({ currentPage, totalPages, onJump }: Props) {
  const [value, setValue] = useState(String(currentPage));

  // Keep the field in sync when the page changes via arrows or chapter jumps.
  useEffect(() => {
    setValue(String(currentPage));
  }, [currentPage]);

  const commit = () => {
    const n = parseInt(value, 10);
    if (Number.isNaN(n)) {
      setValue(String(currentPage));
      return;
    }
    const clamped = Math.min(totalPages, Math.max(1, n));
    setValue(String(clamped));
    if (clamped !== currentPage) onJump(clamped);
  };

  return (
    <span className="inline-flex items-center justify-center gap-1">
      Page
      <input
        value={value}
        onChange={(e) => setValue(e.target.value.replace(/[^0-9]/g, ""))}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
        onBlur={commit}
        inputMode="numeric"
        aria-label="Go to page"
        className="w-12 text-center tabular-nums border border-gray-300 rounded px-1 py-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      of {totalPages}
    </span>
  );
}