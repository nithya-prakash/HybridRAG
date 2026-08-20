import { API_BASE_URL, ApiError, parseErrorDetail } from "./api";

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

async function authFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await parseErrorDetail(res));
  }
  return res;
}

export async function register(email: string, password: string): Promise<User> {
  const res = await authFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return res.json();
}

export async function login(email: string, password: string): Promise<User> {
  const res = await authFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return res.json();
}

export async function logout(): Promise<void> {
  await authFetch("/auth/logout", { method: "POST" });
}

export async function fetchMe(): Promise<User | null> {
  const res = await fetch(`${API_BASE_URL}/auth/me`, {
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new ApiError(res.status, await parseErrorDetail(res));
  return res.json();
}
