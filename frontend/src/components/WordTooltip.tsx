import { useFloating, offset, flip, shift, autoUpdate, arrow } from "@floating-ui/react";
import { useEffect, useRef } from "react";

interface Props {
  translation: string | null;
  loading: boolean;
  anchor: HTMLElement;
  onClose: () => void;
}

export default function WordTooltip({ translation, loading, anchor, onClose }: Props) {
  const arrowRef = useRef<SVGSVGElement | null>(null);

  const { refs, floatingStyles, middlewareData, placement } = useFloating({
    placement: "top",
    middleware: [
      offset(8),
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
      style={floatingStyles}
      className="bg-orange-100 text-gray-900 rounded-2xl px-4 py-1.5 text-base font-medium shadow-sm z-50 pointer-events-auto"
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
        width="12"
        height="6"
        viewBox="0 0 12 6"
      >
        <path d="M6 6L0 0H12L6 6Z" />
      </svg>
    </div>
  );
}