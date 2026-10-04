// Thin fetch wrapper for the NestrisLTM REST API.

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    /** Machine-readable code of `{"detail": {"code", "message"}}` errors. */
    readonly code: string | null = null,
  ) {
    super(detail);
  }
}

function errorCode(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (detail && typeof detail === "object" && "code" in detail) {
      return String((detail as { code: unknown }).code);
    }
  }
  return null;
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
}

let onUnauthorized: () => void = () => {};

/** Called whenever the server answers 401 (session expired, logged out). */
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Turns FastAPI error bodies (string or validation list) into one message. */
export function errorDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
    if (Array.isArray(detail)) {
      return detail
        .map((d) => {
          const item = d as { loc?: unknown[]; msg?: string };
          const field = item.loc?.filter((p) => p !== "body").join(".");
          return field ? `${field}: ${item.msg}` : (item.msg ?? "");
        })
        .join("; ");
    }
  }
  return fallback;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const init: RequestInit = {
    method: options.method ?? "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  };
  if (options.body !== undefined) {
    init.body = JSON.stringify(options.body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), init);
  } catch {
    throw new ApiError(0, "server not reachable");
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  if (!response.ok) {
    if (response.status === 401) onUnauthorized();
    throw new ApiError(
      response.status,
      errorDetail(body, `${response.status} ${response.statusText}`),
      errorCode(body),
    );
  }
  return body as T;
}
