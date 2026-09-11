export class APIError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "",
    readonly requestId = "",
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    signal?: AbortSignal;
    key?: string;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { "X-Control-Plane": "browser" };
  if (options.key) headers["Idempotency-Key"] = options.key;
  const body =
    options.body instanceof URLSearchParams
      ? options.body
      : options.body === undefined
        ? undefined
        : JSON.stringify(options.body);
  if (options.body !== undefined && !(options.body instanceof URLSearchParams))
    headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      body,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.any([
        AbortSignal.timeout(10_000),
        ...(options.signal ? [options.signal] : []),
      ]),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new APIError(
      "Unable to reach the API. Check your connection and try again.",
      0,
    );
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const code = data.error?.code || "";
    if (
      (response.status === 401 || code === "inactive_actor") &&
      path !== "/auth/session" &&
      path !== "/auth/me"
    )
      window.dispatchEvent(new Event("session-expired"));
    let message =
      data.error?.message ||
      (typeof data.detail === "string"
        ? data.detail
        : "The request could not be completed.");
    if (code === "stale_version")
      message =
        "This record changed since you opened it. Close this form, refresh, and review the latest version before saving.";
    if (code === "validation_error") {
      const fields: string[] = (data.error?.details?.fields || []).map(
        (f: { location: (string | number)[] }) => f.location.slice(1).join("."),
      );
      message = `Check the following fields: ${[...new Set(fields)].join(", ") || "submitted values"}.`;
    }
    throw new APIError(
      message,
      response.status,
      code,
      data.error?.request_id || response.headers.get("X-Request-ID") || "",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
