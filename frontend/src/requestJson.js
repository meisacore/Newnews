function responseError(message, response) {
  const error = new Error(message);
  error.status = response.status;
  const header = response.headers.get("Retry-After");
  const seconds = header ? Number(header) : NaN;
  const delay = Number.isFinite(seconds)
    ? seconds * 1000
    : header
      ? Date.parse(header) - Date.now()
      : 0;
  error.retryAfterMs = Number.isFinite(delay)
    ? Math.max(0, Math.min(60000, delay))
    : 0;
  return error;
}

export async function requestJson(path, world, { token, body, signal } = {}) {
  const response = await fetch("/api/" + path, {
    cache: "no-store",
    signal,
    headers: {
      "X-Norx-World": world,
      ...(token ? { Authorization: "Bearer " + token } : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    ...(body ? { method: "POST", body: JSON.stringify(body) } : {}),
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw responseError(
      response.status >= 500
        ? `The market server returned an error (${response.status}). Please retry shortly.`
        : "The market API returned an unexpected response. Please retry shortly.",
      response,
    );
  }
  if (!response.ok)
    throw responseError(
      typeof data.detail === "string" ? data.detail : "Request failed",
      response,
    );
  return data;
}

export async function requestPublic(path, world) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);
  try {
    return await requestJson(path, world, { signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted)
      throw Error("Market update took too long. Retrying shortly.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
