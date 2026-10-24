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
    throw Error(
      response.status >= 500
        ? `The market server returned an error (${response.status}). Please retry shortly.`
        : "The market API returned an unexpected response. Please retry shortly.",
    );
  }
  if (!response.ok)
    throw Error(
      typeof data.detail === "string" ? data.detail : "Request failed",
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
