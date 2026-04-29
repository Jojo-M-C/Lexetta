import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { api, type Page } from "../api";

export default function Reader() {
  const { documentId } = useParams();
  const navigate = useNavigate();

  const [page, setPage] = useState<Page | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    api
      .getPage(Number(documentId), 1)
      .then(setPage)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [documentId]);

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Top bar */}
      <div className="p-4">
        <button
          onClick={() => navigate("/library")}
          className="bg-white shadow-sm rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2 hover:shadow-md transition"
        >
          <ArrowLeft size={16} />
          Back to Library
        </button>
      </div>

      {/* Content card */}
      <div className="flex-1 flex justify-center px-4">
        <article className="bg-white rounded-2xl shadow-sm w-full max-w-3xl p-12 mb-32">
          {loading && <p className="text-gray-500">Loading...</p>}

          {error && (
            <p className="text-red-600">Error: {error}</p>
          )}

          {page && (
            <>
              <h1 className="text-4xl font-serif font-bold mb-8">
                {page.title}
              </h1>
              <div className="space-y-4 text-gray-800 leading-relaxed">
                {page.paragraphs.map((p) => (
                  <p key={p.id}>{p.text}</p>
                ))}
              </div>
            </>
          )}
        </article>
      </div>

      {/* Bottom navigation bar */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-white shadow-lg rounded-2xl px-6 py-3 flex items-center gap-6">
        <div className="text-xs text-gray-500 uppercase tracking-wide">
          <p className="text-center">Progress</p>
          <p className="font-semibold text-gray-900 normal-case">
            Page {page?.page_number ?? "—"} of {page?.total_pages ?? "—"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center">
            <ChevronLeft size={18} />
          </button>
          <button className="w-9 h-9 rounded-full hover:bg-gray-100 flex items-center justify-center">
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}