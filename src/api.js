const base = (import.meta.env?.VITE_API_URL || "").replace(/\/$/, "");
let tokens = null;
try {
  tokens = JSON.parse(sessionStorage.getItem("worktrack-auth") || "null");
} catch {
  sessionStorage.removeItem("worktrack-auth");
}
export function clearAuth() {
  tokens = null;
  sessionStorage.removeItem("worktrack-auth");
}
function save(value) {
  tokens = value;
  sessionStorage.setItem("worktrack-auth", JSON.stringify(value));
}
export async function api(path, options = {}, retry = true) {
  const response = await fetch(base + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(tokens ? { Authorization: `Bearer ${tokens.access}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401 && tokens && retry) {
    const refreshed = await fetch(base + "/api/auth/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh: tokens.refresh }),
    });
    if (refreshed.ok) {
      save({ ...tokens, ...(await refreshed.json()) });
      return api(path, options, false);
    }
    clearAuth();
  }
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : JSON.stringify(data),
    );
  return data;
}
export async function login(username, password) {
  save(
    await api(
      "/api/auth/login/",
      { method: "POST", body: JSON.stringify({ username, password }) },
      false,
    ),
  );
}
export async function list(path) {
  const rows = [];
  while (path) {
    // Keep pagination on the configured API origin.
    const data = await api(path);
    if (Array.isArray(data)) return data;
    rows.push(...data.results);
    path = data.next
      ? new URL(data.next, window.location.origin).pathname +
        new URL(data.next, window.location.origin).search
      : null;
  }
  return rows;
}
