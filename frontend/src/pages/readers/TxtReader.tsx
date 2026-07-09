import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { api, type Page } from "../../api";
import { streamDifficulty } from "../../lib/difficultyStream";
import { tokenize } from "../../lib/tokenize";
import OutageBanner from "../../components/OutageBanner";
import Token from "../../components/Token";
import WordTooltip from "../../components/WordTooltip";
import PageInput from "../../components/PageInput";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;
// Sheet width at 100% zoom (Tailwind max-w-3xl). The sheet widens with zoom up
// to the screen; past that it stays full-width and only the text keeps growing.
const BASE_SHEET_WIDTH = 768;

export default function TxtReader() {
  const { documentId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [page, setPage] = useState<Page | null>(null);
  const [currentPage, setCurrentPage] = useState(
    Math.max(1, Number(searchParams.get("page")) || 1)
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [difficultWords, setDifficultWords] = useState<Set<string>>(new Set());
  const [mlOutage, setMlOutage] = useState(false);

  const [activeAnchor, setActiveAnchor] = useState<HTMLElement | null>(null);
  const [activeTranslation, setActiveTranslation] = useState<string | null>(null);
  const [translationLoading, setTranslationLoading] = useState(false);
  // Mirrors activeAnchor synchronously so an in-flight lookup can tell whether
  // the cursor has already moved off the word it was fetched for.
  const activeAnchorRef = useRef<HTMLElement | null>(null);

  // User zoom, a multiplier on the base text size (1 = default reading size).
  const [zoom, setZoom] = useState(1);
  const zoomIn = () =>
    setZoom((z) => Math.min(MAX_ZOOM, +(z + ZOOM_STEP).toFixed(2)));
  const zoomOut = () =>
    setZoom((z) => Math.max(MIN_ZOOM, +(z - ZOOM_STEP).toFixed(2)));

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDifficultWords(new Set());
    setMlOutage(false);

    api
      .getPage(Number(documentId), currentPage)
      .then((pageData) => {
        if (cancelled) return;
        setPage(pageData);
        // Show the text straight away; highlights arrive chunk by chunk after.
        setLoading(false);

        return streamDifficulty(
          pageData.paragraphs.map((p) => p.text),
          { documentId: Number(documentId), pageNumber: currentPage },
          {
            onWords: (words) =>
              setDifficultWords(
                (prev) => new Set([...prev, ...words.map((w) => w.toLowerCase())])
              ),
            onOutage: () => setMlOutage(true),
            isCancelled: () => cancelled,
          }
        );
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [documentId, currentPage]);

  // Start each page at the top instead of wherever the reader left off scrolling,
  // and drop any tooltip left over from the previous page.
  useEffect(() => {
    window.scrollTo({ top: 0 });
    closeTooltip();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage]);

  const goToPrev = useCallback(() => {
    setCurrentPage((p) => Math.max(1, p - 1));
  }, []);

  const goToNext = useCallback(() => {
    if (!page) return;
    setCurrentPage((p) => Math.min(page.total_pages, p + 1));
  }, [page]);

  const closeTooltip = () => {
    activeAnchorRef.current = null;
    setActiveAnchor(null);
    setActiveTranslation(null);
    setTranslationLoading(false);
  };

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      // Don't hijack arrow keys while the user is typing in the page-jump field.
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") goToPrev();
      if (e.key === "ArrowRight") goToNext();
      if (e.key === "Escape") closeTooltip();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goToPrev, goToNext]);

  const canGoPrev = currentPage > 1;
  const canGoNext = page ? currentPage < page.total_pages : false;

  const handleWordHover = async (
    word: string,
    paragraphId: number,
    wasHighlighted: boolean,
    anchor: HTMLElement
  ) => {
    activeAnchorRef.current = anchor;
    setActiveAnchor(anchor);
    setActiveTranslation(null);
    setTranslationLoading(true);

    try {
      const result = await api.logLookup({
        paragraph_id: paragraphId,
        word,
        was_highlighted: wasHighlighted,
      });
      // The cursor may have moved to another word (or off the page) while the
      // translation was in flight; only apply it if this word is still active.
      if (activeAnchorRef.current !== anchor) return;
      setActiveTranslation(result.translation?.target ?? null);
      setTranslationLoading(false);
    } catch (e) {
      console.error("lookup failed:", e);
      if (activeAnchorRef.current === anchor) setTranslationLoading(false);
    }
  };

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

      <div className="flex-1 flex justify-center px-4">
        <article
          className="bg-white rounded-2xl shadow-sm p-12 mb-32"
          style={{ width: `min(${Math.round(BASE_SHEET_WIDTH * zoom)}px, 100%)` }}
        >
          {loading && <p className="text-gray-500">Loading...</p>}
          {error && <p className="text-red-600">Error: {error}</p>}
          {page && (
            <div style={{ fontSize: `${zoom}rem` }}>
              {page.page_number === 1 && (
                <h1 className="text-[2.25em] font-serif font-bold mb-8">
                  {page.title}
                </h1>
              )}
              <div className="space-y-4 text-gray-800 leading-relaxed">
                {page.paragraphs.map((p) => (
                  <p key={p.id}>
                    {tokenize(p.text).map((tok, i) => (
                      <Token
                        key={i}
                        token={tok}
                        paragraphId={p.id}
                        difficultWords={difficultWords}
                        onWordHover={handleWordHover}
                        onWordLeave={closeTooltip}
                      />
                    ))}
                  </p>
                ))}
              </div>
            </div>
          )}
        </article>
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
            {page ? (
              <PageInput
                currentPage={currentPage}
                totalPages={page.total_pages}
                onJump={setCurrentPage}
              />
            ) : (
              <span>Page — of —</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={goToPrev}
            disabled={!canGoPrev}
            className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            onClick={goToNext}
            disabled={!canGoNext}
            className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      {activeAnchor && (
        <WordTooltip
          translation={activeTranslation}
          loading={translationLoading}
          anchor={activeAnchor}
          onClose={closeTooltip}
        />
      )}
    </div>
  );
}