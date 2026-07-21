import { useFloating, offset, flip, shift, autoUpdate, arrow } from "@floating-ui/react";
import { useEffect, useRef } from "react";

// Tooltip metrics at 100% zoom, in px. Everything below is derived from these so
// the pill scales in proportion to the page instead of staying a fixed size.
const BASE_ARROW_WIDTH = 12;
const BASE_ARROW_HEIGHT = 6;
const BASE_OFFSET = 8;

interface Props {
  translation: string | null;
  loading: boolean;
  anchor: HTMLElement;
  onClose: () => void;
  // The reader's zoom multiplier (1 = default). The tooltip sits outside the
  // zoomed content, so it has to be told the scale rather than inheriting it.
  zoom?: number;
}

export default function WordTooltip({
  translation,
  loading,
  anchor,
  onClose,
  zoom = 1,
}: Props) {
  const arrowRef = useRef<SVGSVGElement | null>(null);

  const { refs, floatingStyles, middlewareData, placement } = useFloating({
    placement: "top",
    middleware: [
      offset(BASE_OFFSET * zoom),
      flip(),
      shift({ padding: 8 }),
      arrow({ element: arrowRef }),
    ],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    refs.setReference(anchor);
  }, [anchor, refs]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        refs.floating.current &&
        !refs.floating.current.contains(target) &&
        anchor &&
        !anchor.contains(target)
      ) {
        onClose();
      }
    };
    const timer = setTimeout(() => {
      document.addEventListener("mousedown", handleClickOutside);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [refs.floating, anchor, onClose]);

  const arrowX = middlewareData.arrow?.x;
  const isAbove = placement.startsWith("top");

  return (
    <div
      ref={refs.setFloating}
      style={{
        ...floatingStyles,
        // Base size follows the reader's zoom, exactly as the page text does.
        // Padding and radius are in em so they scale with it automatically
        // (0.375em/1em/1em reproduce py-1.5, px-4 and rounded-2xl at zoom 1).
        fontSize: `${zoom}rem`,
        padding: "0.375em 1em",
        borderRadius: "1em",
      }}
      className="bg-orange-100 text-gray-900 font-medium shadow-sm z-50 pointer-events-auto"
    >
      {loading ? <span className="text-gray-500">…</span> : translation ?? "—"}
      <svg
        ref={arrowRef}
        className="absolute fill-orange-100"
        style={{
          left: arrowX ?? 0,
          top: isAbove ? "100%" : undefined,
          bottom: !isAbove ? "100%" : undefined,
          transform: !isAbove ? "rotate(180deg)" : undefined,
        }}
        width={BASE_ARROW_WIDTH * zoom}
        height={BASE_ARROW_HEIGHT * zoom}
        viewBox={`0 0 ${BASE_ARROW_WIDTH} ${BASE_ARROW_HEIGHT}`}
      >
        <path d="M6 6L0 0H12L6 6Z" />
      </svg>
    </div>
  );
}