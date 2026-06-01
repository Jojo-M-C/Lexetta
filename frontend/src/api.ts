const BASE = "http://localhost:8000";

function getUserId(): number | null {
  const stored = localStorage.getItem("lexetta_user");
  if (!stored) return null;
  try {
    return JSON.parse(stored).id;
  } catch {
    return null;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  const userId = getUserId();
  if (userId !== null) {
    headers["X-User-Id"] = String(userId);
  }
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function authHeaders(): Record<string, string> {
  const userId = getUserId();
  return userId !== null ? { "X-User-Id": String(userId) } : {};
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const headers: Record<string, string> = {};
  const userId = getUserId();
  if (userId !== null) {
    headers["X-User-Id"] = String(userId);
  }
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export interface User {
  id: number;
  username: string;
  reading_level: string | null;
  use_ml_predictions: boolean;
  calibration_done: boolean;
}

export interface CalibrationItem {
  id: number;
  word: string;
  sentence: string;
}

export interface Document {
  id: number;
  title: string;
  source_format: string;
  uploaded_at: string;
  last_page_read: number;
}

export interface PageImage {
  url: string;
  alt: string | null;
  after_paragraph_index: number;
}

export interface Page {
  document_id: number;
  title: string;
  page_number: number;
  total_pages: number;
  paragraphs: { id: number; text: string }[];
  ml_highlights: string[] | null;
  // EPUB-only; null/empty for txt and pdf pages.
  chapter: { index: number; title: string } | null;
  images: PageImage[];
}

export interface Chapter {
  index: number;
  title: string;
  page_number: number;
}

// A word's bounding box on a PDF page, in PDF points (top-left origin).
export interface PdfWord {
  text: string;
  x0: number;
  top: number;
  x1: number;
  bottom: number;
}

export interface PdfPageWords {
  page: number;
  width: number;
  height: number;
  text: string;
  words: PdfWord[];
}

export interface TranslationResult {
  target: string;
  source: string | null;
}

export interface VocabularyCard {
  id: number;
  word: string;
  context: string;
  translation: string | null;
  created_at: string;
}

export const api = {
  listUsers: () => request<User[]>("/users"),
  me: () => request<User>("/me"),
  updateMe: (settings: { use_ml_predictions: boolean }) =>
    request<User>("/users/me", {
      method: "PATCH",
      body: JSON.stringify(settings),
    }),
  listDocuments: () => request<Document[]>("/documents"),
  uploadDocument: (file: File) =>
    uploadFile<{ id: number; title: string; page_count: number }>(
      "/documents",
      file
    ),
  getPage: (documentId: number, pageNumber: number) =>
    request<Page>(`/documents/${documentId}/pages/${pageNumber}`),
  getChapters: (documentId: number) =>
    request<{ chapters: Chapter[] }>(`/documents/${documentId}/chapters`),
  // EPUB images live inside the stored zip behind an auth-checked endpoint, so
  // <img src> can't load them directly (no custom headers). Fetch as a blob with
  // the user header and return an object URL the caller must revoke when done.
  fetchImageObjectUrl: async (path: string) => {
    const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return URL.createObjectURL(await res.blob());
  },
  // Source params for PDF.js getDocument(): the streamed PDF endpoint plus the
  // X-User-Id auth header, since PDF.js issues the request itself (not request()).
  pdfDocumentSource: (documentId: number) => ({
    url: `${BASE}/documents/${documentId}/pdf`,
    httpHeaders: authHeaders(),
  }),
  getPdfPageText: (documentId: number, page: number) =>
    request<{ page: number; text: string }>(
      `/documents/${documentId}/pages/${page}/text`
    ),
  getPdfPageWords: (documentId: number, page: number) =>
    request<PdfPageWords>(`/documents/${documentId}/pages/${page}/words`),
  logLookup: (params: {
    word: string;
    was_highlighted: boolean;
    paragraph_id?: number;
    document_id?: number;
    page_number?: number;
    page_text?: string;
  }) =>
    request<{
      id: number;
      occurred_at: string;
      word: string;
      translation: TranslationResult | null;
    }>("/lookups", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  getDifficulty: (words: string[]) =>
    request<{ difficult: string[] }>("/difficulty", {
      method: "POST",
      body: JSON.stringify({ words }),
    }),
  prefetch: (words: { paragraph_id: number; word: string }[]) =>
    request<{ queued: number }>("/prefetch", {
      method: "POST",
      body: JSON.stringify({ words }),
    }),
  prefetchPdf: (params: {
    document_id: number;
    page_number: number;
    page_text: string;
    words: string[];
  }) =>
    request<{ queued: number }>("/prefetch/pdf", {
      method: "POST",
      body: JSON.stringify(params),
    }),
  listVocabulary: () => request<VocabularyCard[]>("/vocabulary"),
  deleteVocabulary: (id: number) =>
    request<{ id: number; deleted: boolean }>(`/vocabulary/${id}`, {
      method: "DELETE",
    }),
  exportVocabulary: () => {
    const userId = getUserId();
    const url = `${BASE}/vocabulary/export`;
    // Use fetch to attach the user header, then trigger a download
    fetch(url, {
      headers: userId !== null ? { "X-User-Id": String(userId) } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.blob();
      })
      .then((blob) => {
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = `lexetta_vocab_${new Date().toISOString().slice(0, 10)}.tsv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(downloadUrl);
      });
  },
  deleteDocument: (id: number) =>
    request<{ id: number; deleted: boolean }>(`/documents/${id}`, {
      method: "DELETE",
    }),
  renameDocument: (id: number, title: string) =>
    request<{ id: number; title: string }>(`/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  getCalibrationWords: () => request<CalibrationItem[]>("/calibration/words"),
  submitCalibration: (ratings: { item_id: number; difficulty_rating: number }[]) =>
    request<{ calibration_done: boolean }>("/calibration", {
      method: "POST",
      body: JSON.stringify({ ratings }),
    }),
};