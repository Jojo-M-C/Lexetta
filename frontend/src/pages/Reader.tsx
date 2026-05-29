import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { api, type Page } from "../api";
import { tokenize } from "../lib/tokenize";
import Token from "../components/Token";
import WordTooltip from "../components/WordTooltip";

export default function Reader() {
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

  const [activeAnchor, setActiveAnchor] = useState<HTMLElement | null>(null);
  const [activeTranslation, setActiveTranslation] = useState<string | null>(null);
  const [translationLoading, setTranslationLoading] = useState(false);

  useEffect(() => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    setDifficultWords(new Set());

    api
      .getPage(Number(documentId), currentPage)
      .then(async (pageData) => {
        setPage(pageData);

        let difficult: Set<string>;
        if (pageData.ml_highlights !== null) {
          difficult = new Set(pageData.ml_highlights);
        } else {
          const allWords = new Set<string>();
          for (const para of pageData.paragraphs) {
            for (const tok of tokenize(para.text)) {
              if (tok.type === "word") allWords.add(tok.text);
            }
          }
          const { difficult: diff } = await api.getDifficulty([...allWords]);
          difficult = new Set(diff.map((w) => w.toLowerCase()));
        }

        setDifficultWords(difficult);

        const pairs = [...difficult].flatMap((word) => {
          const para = pageData.paragraphs.find((p) =>
            p.text.toLowerCase().includes(word)
          );
          return para ? [{ paragraph_id: para.id, word }] : [];
        });
        if (pairs.length > 0) api.prefetch(pairs).catch(() => {});
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [documentId, currentPage]);

  const goToPrev = useCallback(() => {
    setCurrentPage((p) => Math.max(1, p - 1));
  }, []);

  const goToNext = useCallback(() => {
    if (!page) return;
    setCurrentPage((p) => Math.min(page.total_pages, p + 1));
  }, [page]);

  const closeTooltip = () => {
    setActiveAnchor(null);
    setActiveTranslation(null);
    setTranslationLoading(false);
  };

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") goToPrev();
      if (e.key === "ArrowRight") goToNext();
      if (e.key === "Escape") closeTooltip();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [goToPrev, goToNext]);

  const canGoPrev = currentPage > 1;
  const canGoNext = page ? currentPage < page.total_pages : false;

  const handleWordClick = async (
    word: string,
    paragraphId: number,
    wasHighlighted: boolean,
    anchor: HTMLElement
  ) => {
    setActiveAnchor(anchor);
    setActiveTranslation(null);
    setTranslationLoading(true);

    try {
      const result = await api.logLookup({
        paragraph_id: paragraphId,
        word,
        was_highlighted: wasHighlighted,
      });
      setActiveTranslation(result.translation?.target ?? null);
    } catch (e) {
      console.error("lookup failed:", e);
    } finally {
      setTranslationLoading(false);
    }
  };

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

      <div className="flex-1 flex justify-center px-4">
        <article className="bg-white rounded-2xl shadow-sm w-full max-w-3xl p-12 mb-32">
          {loading && <p className="text-gray-500">Loading...</p>}
          {error && <p className="text-red-600">Error: {error}</p>}
          {page && (
            <>
              {page.page_number === 1 && (
                <h1 className="text-4xl font-serif font-bold mb-8">
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
                        onWordClick={handleWordClick}
                      />
                    ))}
                  </p>
                ))}
              </div>
            </>
          )}
        </article>
      </div>

      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-white shadow-lg rounded-2xl px-6 py-3 flex items-center gap-6">
        <div className="text-xs text-gray-500 uppercase tracking-wide">
          <p className="text-center">Progress</p>
          <p className="font-semibold text-gray-900 normal-case">
            Page {page?.page_number ?? "—"} of {page?.total_pages ?? "—"}
          </p>
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