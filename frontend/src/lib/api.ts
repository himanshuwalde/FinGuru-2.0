import { supabase } from "@/lib/supabase";

export const API_BASE_URL: string =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

export interface ApiErrorShape {
  error: { code: string; message: string };
}

export class ApiError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
      ...(await authHeaders()),
    },
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const shaped = body as ApiErrorShape | null;
    throw new ApiError(
      shaped?.error?.code ?? "network_error",
      shaped?.error?.message ?? `Request failed (${response.status})`,
    );
  }
  return body as T;
}
