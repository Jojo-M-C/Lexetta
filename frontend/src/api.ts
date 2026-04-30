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
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json();
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
}

export interface Document {
  id: number;
  title: string;
  source_format: string;
  uploaded_at: string;
  last_page_read: number;
}

export interface Page {
  document_id: number;
  title: string;
  page_number: number;
  total_pages: number;
  paragraphs: { id: number; text: string }[];
}

export const api = {
  listUsers: () => request<User[]>("/users"),
  me: () => request<User>("/me"),
  listDocuments: () => request<Document[]>("/documents"),
  uploadDocument: (file: File) =>
    uploadFile<{ id: number; title: string; page_count: number }>(
      "/documents",
      file
    ),
  getPage: (documentId: number, pageNumber: number) =>
  request<Page>(`/documents/${documentId}/pages/${pageNumber}`),
  logLookup: (params: {
  paragraph_id: number;
  word: string;
  was_highlighted: boolean;
  mode?: string;
}) =>
  request<{ id: number; occurred_at: string }>("/lookups", {
    method: "POST",
    body: JSON.stringify(params),
  }),
  getDifficulty: (words: string[]) =>
  request<{ difficult: string[] }>("/difficulty", {
    method: "POST",
    body: JSON.stringify({ words }),
  }),
};