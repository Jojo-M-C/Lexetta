import { useEffect, useState } from "react";
import { api, type Document } from "../api";
import UploadButton from "../components/UploadButton";
import ConfirmDialog from "../components/ConfirmDialog";
import RenameDialog from "../components/RenameDialog";
import { Link } from "react-router-dom";
import { Pencil, Trash2 } from "lucide-react";

// How far through a document the reader has got, as a whole percent. The current
// page counts as read, so the last page reads 100%; a document that has never
// been opened sits at last_page_read 0 and so reads 0%.
function readingProgress(doc: Document): number | null {
  if (!doc.page_count) return null;
  const pct = (doc.last_page_read / doc.page_count) * 100;
  return Math.min(100, Math.max(0, Math.round(pct)));
}

export default function Library() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [docToDelete, setDocToDelete] = useState<Document | null>(null);
  const [docToRename, setDocToRename] = useState<Document | null>(null);

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

  const requestDelete = (e: React.MouseEvent, doc: Document) => {
    e.preventDefault();
    e.stopPropagation();
    setDocToDelete(doc);
  };

  const confirmDelete = async () => {
    if (!docToDelete) return;
    const id = docToDelete.id;
    setDocToDelete(null);
    try {
      await api.deleteDocument(id);
      setDocuments((docs) => docs.filter((d) => d.id !== id));
    } catch (err) {
      alert(`Delete failed: ${err instanceof Error ? err.message : err}`);
    }
  };

  const requestRename = (e: React.MouseEvent, doc: Document) => {
    e.preventDefault();
    e.stopPropagation();
    setDocToRename(doc);
  };

  const confirmRename = async (title: string) => {
    if (!docToRename) return;
    const id = docToRename.id;
    setDocToRename(null);
    try {
      const { title: newTitle } = await api.renameDocument(id, title);
      setDocuments((docs) =>
        docs.map((d) => (d.id === id ? { ...d, title: newTitle } : d))
      );
    } catch (err) {
      alert(`Rename failed: ${err instanceof Error ? err.message : err}`);
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
            No documents yet. Upload a .txt, .pdf, or .epub file to get started.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {documents.map((doc) => {
            const progress = readingProgress(doc);
            // last_page_read is 0 for a document that was never opened, so clamp:
            // a first open starts at page 1, not a nonexistent page 0.
            const openAtPage = Math.max(1, doc.last_page_read);
            return (
            <div key={doc.id} className="relative group">
              <Link
                to={`/reader/${doc.id}?page=${openAtPage}`}
                className="bg-white rounded-lg shadow p-4 hover:shadow-md transition cursor-pointer block"
              >
                <h3 className="font-bold text-lg pr-16 truncate" title={doc.title}>
                  {doc.title}
                </h3>
                <p className="text-xs text-gray-500 mt-1">
                  {doc.source_format.toUpperCase()} ·{" "}
                  {new Date(doc.uploaded_at).toLocaleDateString()}
                </p>
                {progress !== null && (
                  <div className="flex items-center gap-2 mt-4">
                    <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                      <div
                        className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500 tabular-nums">
                      {progress}%
                    </span>
                  </div>
                )}
              </Link>
              <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition">
                <button
                  onClick={(e) => requestRename(e, doc)}
                  className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-md"
                  aria-label={`Rename ${doc.title}`}
                  title="Rename document"
                >
                  <Pencil size={16} />
                </button>
                <button
                  onClick={(e) => requestDelete(e, doc)}
                  className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md"
                  aria-label={`Delete ${doc.title}`}
                  title="Delete document"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={docToDelete !== null}
        title="Delete document?"
        message={
          docToDelete
            ? `"${docToDelete.title}" will be permanently deleted. This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        destructive
        onConfirm={confirmDelete}
        onCancel={() => setDocToDelete(null)}
      />

      <RenameDialog
        open={docToRename !== null}
        initialTitle={docToRename?.title ?? ""}
        onSave={confirmRename}
        onCancel={() => setDocToRename(null)}
      />
    </div>
  );
}