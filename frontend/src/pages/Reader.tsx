import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, type Document } from "../api";
import PdfReader from "../components/PdfReader";
import TxtReader from "./TxtReader";

// Dispatches to the right reader based on the document's source format. There is
// no single-document endpoint, so the format comes from the document list.
export default function Reader() {
  const { documentId } = useParams();
  const [searchParams] = useSearchParams();
  const [doc, setDoc] = useState<Document | null | undefined>(undefined);

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    api
      .listDocuments()
      .then((docs) => {
        if (!cancelled) {
          setDoc(docs.find((d) => d.id === Number(documentId)) ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) setDoc(null);
      });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  if (doc === undefined) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500">Loading…</p>
      </div>
    );
  }

  if (doc?.source_format === "pdf") {
    const initialPage = Math.max(1, Number(searchParams.get("page")) || 1);
    return <PdfReader documentId={doc.id} initialPage={initialPage} />;
  }

  return <TxtReader />;
}