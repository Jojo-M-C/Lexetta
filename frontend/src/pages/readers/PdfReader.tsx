import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { api, type PdfWord } from "../../api";
import { streamDifficulty } from "../../lib/difficultyStream";
import { usePageReadTimer } from "../../lib/usePageReadTimer";
import OutageBanner from "../../components/OutageBanner";
import WordTooltip from "../../components/WordTooltip";
import PageInput from "../../components/PageInput";

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
// How long the cursor must rest on a word before its translation is fetched.
const HOVER_DELAY_MS = 500;

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
  const [mlOutage, setMlOutage] = useState(false);

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
  // ref so the lookup always reads the latest without re-binding.
  const pageTextRef = useRef("");
  // Pending hover-intent timer; only one word can be hovered at a time.
  const hoverTimerRef = useRef<number | null>(null);

  const cancelHoverTimer = () => {
    if (hoverTimerRef.current !== null) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  };

  // Look up a word and show its translation in the tooltip.
  const runLookup = async (
    anchor: HTMLElement,
    word: string,
    wasHighlighted: boolean
  ) => {
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

  const handleWordEnter = (
    e: React.MouseEvent<HTMLElement>,
    word: string,
    wasHighlighted: boolean
  ) => {
    const anchor = e.currentTarget;
    cancelHoverTimer();
    hoverTimerRef.current = window.setTimeout(() => {
      runLookup(anchor, word, wasHighlighted);
    }, HOVER_DELAY_MS);
  };

  const handleWordLeave = () => {
    cancelHoverTimer();
    setTooltip(null);
  };

  // Clear any pending hover timer when the reader unmounts.
  useEffect(() => cancelHoverTimer, []);

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
    setMlOutage(false);

    (async () => {
      try {
        const data = await api.getPdfPageWords(documentId, currentPage);
        if (cancelled) return;
        pageTextRef.current = data.text;
        setWords(data.words);

        // Send the page text, not a bag of words: the model scores each token in
        // its sentence. No document/page context — PDFs have no page rows, so
        // there is nothing to log highlights against.
        await streamDifficulty([data.text], undefined, {
          onWords: (found) => {
            // Word boxes are matched on letters-only text; normalise to match.
            const normalized = found
              .map(normalize)
              .filter((w) => w.length > 1);
            if (normalized.length === 0) return;
            setDifficult((prev) => new Set([...prev, ...normalized]));

            // Warm the translation cache for the words that just lit up, so
            // clicking one feels instant (cache hit instead of OpenAI).
            api
              .prefetchPdf({
                document_id: documentId,
                page_number: currentPage,
                page_text: data.text,
                words: normalized,
              })
              .catch(() => {});
          },
          onOutage: () => setMlOutage(true),
          isCancelled: () => cancelled,
        });
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
    cancelHoverTimer();
    setTooltip(null);
    setCurrentPage(page);
  };

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      // Don't hijack arrow keys while the user is typing in the page-jump field.
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
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

  // Once the reader has dwelled on this page long enough, commit its words to
  // read_words as training data. PDFs have no paragraph rows server-side, so the
  // extracted page text is sent along for word enumeration.
  usePageReadTimer({
    documentId,
    pageNumber: currentPage,
    wordCount: words.length,
    pageText: pageTextRef.current,
    enabled: words.length > 0,
  });

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {mlOutage && <OutageBanner />}
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
            {/* Hover overlay: resting on a word for 500ms fetches its
                translation; difficult words also get the orange highlight,
                others a subtle hover. */}
            <div className="absolute inset-0 pointer-events-none">
              {scale > 0 &&
                words.map((w, i) => {
                  const isDifficult = difficult.has(normalize(w.text));
                  return (
                    <button
                      key={i}
                      onMouseEnter={(e) => handleWordEnter(e, w.text, isDifficult)}
                      onMouseLeave={handleWordLeave}
                      className={
                        "absolute rounded-sm cursor-default pointer-events-auto transition-colors " +
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
          <div className="font-semibold text-gray-900 normal-case">
            {totalPages > 0 ? (
              <PageInput
                currentPage={currentPage}
                totalPages={totalPages}
                onJump={goToPage}
              />
            ) : (
              <span>Page — of —</span>
            )}
          </div>
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
          zoom={zoom}
        />
      )}
    </div>
  );
}