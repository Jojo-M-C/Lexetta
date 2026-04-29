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

export interface User {
  id: number;
  username: string;
  reading_level: string | null;
  use_ml_predictions: boolean;
}

export const api = {
  listUsers: () => request<User[]>("/users"),
  me: () => request<User>("/me"),
};