import { useEffect, useState } from "react";
import { api, type Document } from "../api";
import UploadButton from "../components/UploadButton";
import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";

export default function Library() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      const docs = await api.listDocuments();
      setDocuments(docs);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleDelete = async (
    e: React.MouseEvent,
    doc: Document
  ) => {
    e.preventDefault();
    e.stopPropagation();
    const ok = window.confirm(
      `Delete "${doc.title}"? This cannot be undone.`
    );
    if (!ok) return;
    try {
      await api.deleteDocument(doc.id);
      setDocuments((docs) => docs.filter((d) => d.id !== doc.id));
    } catch (err) {
      alert(`Delete failed: ${err instanceof Error ? err.message : err}`);
    }
  };

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold">My Library</h1>
        <div className="w-48">
          <UploadButton onUploaded={refresh} />
        </div>
      </div>

      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : documents.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-500">
            No documents yet. Upload a .txt file to get started.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {documents.map((doc) => (
            <div key={doc.id} className="relative group">
              <Link
                to={`/reader/${doc.id}`}
                className="bg-white rounded-lg shadow p-4 hover:shadow-md transition cursor-pointer block"
              >
                <h3 className="font-bold text-lg pr-8">{doc.title}</h3>
                <p className="text-xs text-gray-500 mt-1">
                  {doc.source_format.toUpperCase()} ·{" "}
                  {new Date(doc.uploaded_at).toLocaleDateString()}
                </p>
              </Link>
              <button
                onClick={(e) => handleDelete(e, doc)}
                className="absolute top-2 right-2 p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md opacity-0 group-hover:opacity-100 transition"
                aria-label={`Delete ${doc.title}`}
                title="Delete document"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}