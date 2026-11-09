const SESSION_KEY = "worktrackWebsiteSession";
const NOTICE_KEY = "worktrackWebsiteNotice";
const apiInput = document.querySelector("#api");
const usernameInput = document.querySelector("#username");
const passwordInput = document.querySelector("#password");
const statusElement = document.querySelector("#status");
const logoutButton = document.querySelector("#logout");

function showSession(session) {
  logoutButton.hidden = !session;
  statusElement.textContent = session
    ? "Нэвтэрсэн. Зөвшөөрөл идэвхтэй үед домэйны хугацаа бүртгэгдэнэ."
    : "Нэвтрээгүй байна.";
}

document.querySelector("#login").addEventListener("click", async () => {
  statusElement.textContent = "Нэвтрэлт болон monitoring consent шалгаж байна…";
  const apiUrl = apiInput.value.trim().replace(/\/$/, "");
  try {
    await chrome.storage.local.remove([SESSION_KEY, "worktrackWebsiteQueue", "worktrackWebsiteTracker"]);
    const origin = new URL(apiUrl).origin;
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] });
    if (!granted) throw new Error("Backend хаягт холбогдох зөвшөөрөл олгогдсонгүй.");

    const loginResponse = await fetch(`${apiUrl}/api/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: usernameInput.value.trim(),
        password: passwordInput.value,
      }),
    });
    const tokens = await loginResponse.json();
    if (!loginResponse.ok) throw new Error(tokens.detail || "Нэвтрэхэд алдаа гарлаа.");

    const consentResponse = await fetch(`${apiUrl}/api/consents/status/`, {
      headers: { Authorization: `Bearer ${tokens.access}` },
    });
    const consent = await consentResponse.json();
    if (!consentResponse.ok || !consent.active)
      throw new Error("Эхлээд ажилтны account-аар monitoring consent өгнө үү.");

    const session = { apiUrl, access: tokens.access, refresh: tokens.refresh };
    await chrome.storage.local.set({ [SESSION_KEY]: session, [NOTICE_KEY]: "" });
    passwordInput.value = "";
    showSession(session);
    chrome.runtime.sendMessage({ type: "worktrack-start" });
  } catch (error) {
    statusElement.textContent = error.message;
  }
});

logoutButton.addEventListener("click", async () => {
  await chrome.storage.local.remove([SESSION_KEY, "worktrackWebsiteQueue", "worktrackWebsiteTracker"]);
  chrome.runtime.sendMessage({ type: "worktrack-stop" });
  showSession(null);
});

chrome.storage.local.get([SESSION_KEY, NOTICE_KEY]).then((values) => {
  const session = values[SESSION_KEY] || null;
  if (session) apiInput.value = session.apiUrl;
  showSession(session);
  if (values[NOTICE_KEY]) statusElement.textContent = values[NOTICE_KEY];
});
