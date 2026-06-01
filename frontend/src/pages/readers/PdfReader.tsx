import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { api, type PdfWord } from "../../api";
import WordTooltip from "../../components/WordTooltip";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).href;

interface PdfReaderProps {
  documentId: number;
  initialPage?: number;
}

interface TooltipState {
  anchor: HTMLElement;
  translation: string | null;
  loading: boolean;
}

// Strip to a bare lowercase a–z token, matching the difficulty endpoint's input.
function normalize(token: string): string {
  return token.toLowerCase().replace(/[^a-z]/g, "");
}

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;
// Fit-to-width target at 100% zoom (Tailwind max-w-4xl), and horizontal padding.
const MAX_WIDTH = 896;
const PAGE_PADDING = 32;

export default function PdfReader({ documentId, initialPage = 1 }: PdfReaderProps) {
  const navigate = useNavigate();

  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [totalPages, setTotalPages] = useState(0);
  const [rendering, setRendering] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  // CSS-pixels-per-PDF-point for the current render, plus the page's word boxes
  // (in points) and the set of difficult words. Highlights are positioned by
  // scaling each box by `scale`, so they line up exactly with the canvas glyphs.
  const [scale, setScale] = useState(0);
  const [words, setWords] = useState<PdfWord[]>([]);
  const [difficult, setDifficult] = useState<Set<string>>(new Set());

  // User zoom, a multiplier on the fit-to-width base scale (1 = fit to width).
  const [zoom, setZoom] = useState(1);
  const zoomIn = () =>
    setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)));
  const zoomOut = () =>
    setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)));

  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderTaskRef = useRef<RenderTask | null>(null);
  // Extracted text of the current page, used as translation context. Held in a
  // ref so the click handler always reads the latest without re-binding.
  const pageTextRef = useRef("");

  // Look up a clicked word and show its translation in the tooltip.
  const handleWordClick = async (
    e: React.MouseEvent<HTMLElement>,
    word: string,
    wasHighlighted: boolean
  ) => {
    e.stopPropagation();
    const anchor = e.currentTarget;
    setTooltip({ anchor, translation: null, loading: true });
    try {
      const result = await api.logLookup({
        word: normalize(word),
        was_highlighted: wasHighlighted,
        document_id: documentId,
        page_number: currentPage,
        page_text: pageTextRef.current,
      });
      setTooltip((prev) =>
        prev && prev.anchor === anchor
          ? { ...prev, translation: result.translation?.target ?? null, loading: false }
          : prev
      );
    } catch (err) {
      console.error("lookup failed:", err);
      setTooltip((prev) =>
        prev && prev.anchor === anchor ? { ...prev, loading: false } : prev
      );
    }
  };

  // Load the PDF document once.
  useEffect(() => {
    let cancelled = false;
    setError(null);
    const loadingTask = pdfjsLib.getDocument(api.pdfDocumentSource(documentId));
    loadingTask.promise
      .then((pdf) => {
        if (cancelled) return;
        setPdfDoc(pdf);
        setTotalPages(pdf.numPages);
        setCurrentPage((p) => Math.min(Math.max(1, p), pdf.numPages));
      })
      .catch((e) => {
        if (!cancelled) {
          console.error("PDF load failed:", e);
          setError("Failed to load PDF.");
          setRendering(false);
        }
      });
    return () => {
      cancelled = true;
      loadingTask.destroy();
    };
  }, [documentId]);

  // Fetch the page's word boxes and difficulty. Independent of zoom, so zooming
  // re-renders the canvas without re-hitting these endpoints.
  useEffect(() => {
    if (!pdfDoc) return;
    let cancelled = false;
    setWords([]);
    setDifficult(new Set());

    (async () => {
      try {
        const data = await api.getPdfPageWords(documentId, currentPage);
        if (cancelled) return;
        pageTextRef.current = data.text;
        setWords(data.words);

        const uniq = new Set<string>();
        for (const w of data.words) {
          const clean = normalize(w.text);
          if (clean.length > 1) uniq.add(clean);
        }

        let diff = new Set<string>();
        if (uniq.size > 0) {
          try {
            const res = await api.getDifficulty([...uniq]);
            diff = new Set(res.difficult.map((w) => w.toLowerCase()));
          } catch (e) {
            console.error("difficulty lookup failed:", e);
          }
        }
        if (cancelled) return;
        setDifficult(diff);

        // Warm the translation cache for highlighted words so clicking them
        // feels instant (the lookup then hits the cache instead of OpenAI).
        if (diff.size > 0) {
          api
            .prefetchPdf({
              document_id: documentId,
              page_number: currentPage,
              page_text: data.text,
              words: [...diff],
            })
            .catch(() => {});
        }
      } catch (e) {
        if (!cancelled) console.error("word fetch failed:", e);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pdfDoc, currentPage, documentId]);

  // Render the current page to the canvas. Re-runs on page or zoom change; the
  // resulting `scale` repositions the highlight boxes to match.
  useEffect(() => {
    if (!pdfDoc) return;
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    let cancelled = false;

    (async () => {
      setRendering(true);
      try {
        if (renderTaskRef.current) {
          renderTaskRef.current.cancel();
          renderTaskRef.current = null;
        }

        const page = await pdfDoc.getPage(currentPage);
        if (cancelled) return;

        const baseWidth = Math.min(container.clientWidth - PAGE_PADDING, MAX_WIDTH);
        const s = (baseWidth / page.getViewport({ scale: 1 }).width) * zoom;
        const viewport = page.getViewport({ scale: s });

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        // Render at device pixel ratio for crisp text, but keep the CSS size at
        // the viewport size so highlight boxes (in CSS px) line up.
        const outputScale = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;

        const renderTask = page.render({
          canvas,
          canvasContext: ctx,
          viewport,
          transform:
            outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined,
        });
        renderTaskRef.current = renderTask;
        await renderTask.promise;
        if (cancelled) return;
        setScale(s);
      } catch (e) {
        if (
          !cancelled &&
          (e as { name?: string })?.name !== "RenderingCancelledException"
        ) {
          console.error("PDF render failed:", e);
          setError("Failed to render PDF page.");
        }
      } finally {
        if (!cancelled) setRendering(false);
      }
    })();

    return () => {
      cancelled = true;
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
        renderTaskRef.current = null;
      }
    };
  }, [pdfDoc, currentPage, zoom]);

  const goToPage = (page: number) => {
    if (page < 1 || (totalPages && page > totalPages)) return;
    setTooltip(null);
    setCurrentPage(page);
  };

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") goToPage(currentPage - 1);
      if (e.key === "ArrowRight") goToPage(currentPage + 1);
      if (e.key === "Escape") setTooltip(null);
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, totalPages]);

  const canGoPrev = currentPage > 1;
  const canGoNext = totalPages > 0 && currentPage < totalPages;

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <div className="p-4">
        <button
          onClick={() => navigate("/library")}
          className="bg-white shadow-sm rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2 hover:shadow-md transition"
        >
          <ArrowLeft size={16} />
          Back to Library
        </button>
      </div>

      {/* Scroll viewport: measured for fit-to-width, scrolls when zoomed in. */}
      <div ref={containerRef} className="flex-1 overflow-auto pb-32 relative">
        {error && (
          <p className="absolute top-4 left-1/2 -translate-x-1/2 text-red-600 z-10">
            Error: {error}
          </p>
        )}
        {rendering && !error && (
          <p className="absolute top-4 left-1/2 -translate-x-1/2 text-gray-500 z-10">
            Loading…
          </p>
        )}
        {/* min-w-fit keeps the page centered when it fits and scrollable when not. */}
        <div className="min-w-fit flex justify-center px-4">
          <div className="relative w-fit">
            <canvas ref={canvasRef} className="block shadow-md rounded" />
            {/* Click overlay: every word is clickable for translation; difficult
                words also get the orange highlight, others a subtle hover. */}
            <div className="absolute inset-0 pointer-events-none">
              {scale > 0 &&
                words.map((w, i) => {
                  const isDifficult = difficult.has(normalize(w.text));
                  return (
                    <button
                      key={i}
                      onClick={(e) => handleWordClick(e, w.text, isDifficult)}
                      className={
                        "absolute rounded-sm cursor-pointer pointer-events-auto transition-colors " +
                        (isDifficult
                          ? // mix-blend-multiply puts the highlight behind the
                            // text: it tints the white page but leaves the black
                            // glyphs black, matching the txt reader's orange-100/200.
                            "bg-orange-100 mix-blend-multiply hover:bg-orange-200"
                          : "hover:bg-[rgba(0,0,0,0.08)]")
                      }
                      style={{
                        left: w.x0 * scale,
                        top: w.top * scale,
                        width: (w.x1 - w.x0) * scale,
                        height: (w.bottom - w.top) * scale,
                      }}
                    />
                  );
                })}
            </div>
          </div>
        </div>
      </div>

      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-white shadow-lg rounded-2xl px-6 py-3 flex items-center gap-6">
        <div className="flex items-center gap-2">
          <button
            onClick={zoomOut}
            disabled={zoom <= MIN_ZOOM}
            aria-label="Zoom out"
            className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ZoomOut size={18} />
          </button>
          <span className="text-sm text-gray-600 tabular-nums w-11 text-center">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={zoomIn}
            disabled={zoom >= MAX_ZOOM}
            aria-label="Zoom in"
            className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ZoomIn size={18} />
          </button>
        </div>

        <div className="text-xs text-gray-500 uppercase tracking-wide">
          <p className="text-center">Progress</p>
          <p className="font-semibold text-gray-900 normal-case">
            Page {currentPage} of {totalPages || "—"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={!canGoPrev}
            className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={!canGoNext}
            className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      {tooltip && (
        <WordTooltip
          translation={tooltip.translation}
          loading={tooltip.loading}
          anchor={tooltip.anchor}
          onClose={() => setTooltip(null)}
        />
      )}
    </div>
  );
}