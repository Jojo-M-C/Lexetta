import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  List,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { api, type Chapter, type Page } from "../../api";
import { streamDifficulty } from "../../lib/difficultyStream";
import OutageBanner from "../../components/OutageBanner";
import { tokenize } from "../../lib/tokenize";
import { usePageReadTimer } from "../../lib/usePageReadTimer";
import Token from "../../components/Token";
import WordTooltip from "../../components/WordTooltip";
import PageInput from "../../components/PageInput";

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 3;
const ZOOM_STEP = 0.25;
// Sheet width at 100% zoom (Tailwind max-w-3xl). The sheet widens with zoom up
// to the screen; past that it stays full-width and only the text keeps growing.
const BASE_SHEET_WIDTH = 768;

// Like TxtReader, but for EPUB documents: adds a chapter table-of-contents
// drawer and renders images interleaved with the text. The reading mechanics
// (difficulty, prefetch, tooltip lookup, zoom, pagination) are identical.
export default function EpubReader() {
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

  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [tocOpen, setTocOpen] = useState(false);
  // Maps each page image's endpoint path to a fetched object URL (auth-headed).
  const [imageUrls, setImageUrls] = useState<Record<string, string>>({});

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

  // Table of contents is fixed for the document; fetch it once.
  useEffect(() => {
    if (!documentId) return;
    api
      .getChapters(Number(documentId))
      .then((res) => setChapters(res.chapters))
      .catch(() => setChapters([]));
  }, [documentId]);

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
            onWords: (words) => {
              const lowered = words.map((w) => w.toLowerCase());
              setDifficultWords((prev) => new Set([...prev, ...lowered]));

              // Warm the translation cache for the words that just lit up, so
              // clicking one hits the cache instead of OpenAI.
              const pairs = lowered.flatMap((word) => {
                const para = pageData.paragraphs.find((p) =>
                  p.text.toLowerCase().includes(word)
                );
                return para ? [{ paragraph_id: para.id, word }] : [];
              });
              if (pairs.length > 0) api.prefetch(pairs).catch(() => {});
            },
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

  // Load page images as auth-headed object URLs, revoking them when the page
  // changes or the component unmounts so blobs don't leak.
  useEffect(() => {
    if (!page) return;
    let cancelled = false;
    const created: string[] = [];

    Promise.all(
      page.images.map(async (img) => {
        const objectUrl = await api.fetchImageObjectUrl(img.url);
        created.push(objectUrl);
        return [img.url, objectUrl] as const;
      })
    )
      .then((entries) => {
        if (cancelled) {
          created.forEach(URL.revokeObjectURL);
          return;
        }
        setImageUrls(Object.fromEntries(entries));
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      created.forEach(URL.revokeObjectURL);
      setImageUrls({});
    };
  }, [page]);

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
      if (e.key === "Escape") {
        closeTooltip();
        setTocOpen(false);
      }
      // Don't hijack arrow keys while the user is typing in the page-jump field.
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") goToPrev();
      if (e.key === "ArrowRight") goToNext();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goToPrev, goToNext]);

  const canGoPrev = currentPage > 1;
  const canGoNext = page ? currentPage < page.total_pages : false;

  // Once the reader has dwelled on this page long enough, commit its words to
  // read_words as training data.
  usePageReadTimer({
    documentId: Number(documentId),
    pageNumber: currentPage,
    wordCount: page
      ? page.paragraphs.reduce((n, p) => n + tokenize(p.text).length, 0)
      : 0,
    enabled: !!page,
  });

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

  const goToChapter = (pageNumber: number) => {
    setCurrentPage(pageNumber);
    setTocOpen(false);
  };

  // Images keyed by the paragraph they follow (-1 = before the first paragraph).
  const imagesAfter = (index: number) =>
    page?.images.filter((img) => img.after_paragraph_index === index) ?? [];

  const renderImage = (url: string, alt: string | null, key: string) => {
    const objectUrl = imageUrls[url];
    if (!objectUrl) return null;
    return (
      <img
        key={key}
        src={objectUrl}
        alt={alt ?? ""}
        className="my-6 mx-auto max-w-full rounded-lg"
      />
    );
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {mlOutage && <OutageBanner />}
      <div className="p-4 flex items-center gap-3">
        <button
          onClick={() => navigate("/library")}
          className="bg-white shadow-sm rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2 hover:shadow-md transition"
        >
          <ArrowLeft size={16} />
          Back to Library
        </button>
        <button
          onClick={() => setTocOpen(true)}
          className="bg-white shadow-sm rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2 hover:shadow-md transition"
        >
          <List size={16} />
          Contents
        </button>
      </div>

      <div className="flex-1 flex justify-center px-4">
        <article
          className="bg-white rounded-2xl shadow-sm p-12 mb-32 min-h-[calc(100vh-13rem)]"
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
                {imagesAfter(-1).map((img, i) =>
                  renderImage(img.url, img.alt, `top-${i}`)
                )}
                {page.paragraphs.map((p, idx) => (
                  <div key={p.id}>
                    <p>
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
                    {imagesAfter(idx).map((img, i) =>
                      renderImage(img.url, img.alt, `${p.id}-${i}`)
                    )}
                  </div>
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
          <p className="text-center truncate max-w-[12rem]">
            {page?.chapter?.title ?? "Progress"}
          </p>
          <div className="font-semibold text-gray-900 normal-case text-center">
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

      {tocOpen && (
        <div className="fixed inset-0 z-40 flex">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setTocOpen(false)}
          />
          <aside className="relative z-50 w-72 max-w-[80vw] bg-white shadow-xl h-full flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <span className="font-semibold text-gray-900">Contents</span>
              <button
                onClick={() => setTocOpen(false)}
                aria-label="Close contents"
                className="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center"
              >
                <X size={18} />
              </button>
            </div>
            <nav className="flex-1 overflow-y-auto py-2">
              {chapters.length === 0 && (
                <p className="px-4 py-2 text-sm text-gray-400">No chapters</p>
              )}
              {chapters.map((ch) => {
                const active = page?.chapter?.index === ch.index;
                return (
                  <button
                    key={ch.index}
                    onClick={() => goToChapter(ch.page_number)}
                    className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${
                      active ? "bg-blue-50 font-medium text-gray-900" : "text-gray-700"
                    }`}
                  >
                    {ch.title}
                  </button>
                );
              })}
            </nav>
          </aside>
        </div>
      )}

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