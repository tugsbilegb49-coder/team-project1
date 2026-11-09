const SESSION_KEY = "worktrackWebsiteSession";
const NOTICE_KEY = "worktrackWebsiteNotice";
const apiInput = document.querySelector("#api");
const usernameInput = document.querySelector("#username");
const passwordInput = document.querySelector("#password");
const statusElement = document.querySelector("#status");
const logoutButton = document.querySelector("#logout");
const loginButton = document.querySelector("#login");
const consentPanel = document.querySelector("#consent-panel");
const consentInput = document.querySelector("#consent");
const grantButton = document.querySelector("#grant");
let pendingSession = null;
const WEBSITE_CONSENT_POLICY = "website-domain-2026-11";

async function activateSession(session) {
  await chrome.storage.local.remove([SESSION_KEY, "worktrackWebsiteQueue", "worktrackWebsiteTracker"]);
  await chrome.storage.local.set({ [SESSION_KEY]: session, [NOTICE_KEY]: "" });
  passwordInput.value = "";
  showSession(session);
  chrome.runtime.sendMessage({ type: "worktrack-start" });
}

function showSession(session) {
  logoutButton.hidden = !session;
  loginButton.hidden = Boolean(session);
  consentPanel.hidden = true;
  statusElement.textContent = session
    ? "Нэвтэрсэн. Зөвшөөрөл идэвхтэй үед домэйны хугацаа бүртгэгдэнэ."
    : "Нэвтрээгүй байна.";
}

loginButton.addEventListener("click", async () => {
  statusElement.textContent = "Нэвтрэлтийг шалгаж байна…";
  const apiUrl = apiInput.value.trim().replace(/\/$/, "");
  try {
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

    const session = { apiUrl, access: tokens.access, refresh: tokens.refresh };
    const consentResponse = await fetch(`${apiUrl}/api/consents/status/`, {
      headers: { Authorization: `Bearer ${tokens.access}` },
    });
    const consent = await consentResponse.json();
    if (!consentResponse.ok) throw new Error(consent.detail || "Зөвшөөрлийн төлөвийг шалгаж чадсангүй.");
    if (consent.active && consent.latest?.policy_version === WEBSITE_CONSENT_POLICY) {
      await activateSession(session);
      return;
    }

    pendingSession = session;
    loginButton.hidden = true;
    consentPanel.hidden = false;
    consentInput.checked = false;
    grantButton.disabled = true;
    statusElement.textContent = "Нэвтэрлээ. Вэбсайт бүртгэл эхлүүлэхийн тулд доорх мэдээлэлтэй танилцаж зөвшөөрнө үү.";
  } catch (error) {
    pendingSession = null;
    statusElement.textContent = error.message;
  }
});

consentInput.addEventListener("change", () => {
  grantButton.disabled = !consentInput.checked || !pendingSession;
});

grantButton.addEventListener("click", async () => {
  if (!pendingSession || !consentInput.checked) return;
  grantButton.disabled = true;
  statusElement.textContent = "Зөвшөөрлийг хадгалж, Chrome бүртгэлийг эхлүүлж байна…";
  try {
    const response = await fetch(`${pendingSession.apiUrl}/api/consents/grant/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${pendingSession.access}`,
      },
      body: JSON.stringify({ policy_version: WEBSITE_CONSENT_POLICY }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Зөвшөөрлийг хадгалж чадсангүй.");

    const session = pendingSession;
    await activateSession(session);
    pendingSession = null;
  } catch (error) {
    statusElement.textContent = error.message;
    grantButton.disabled = !consentInput.checked || !pendingSession;
  }
});

logoutButton.addEventListener("click", async () => {
  await chrome.storage.local.remove([SESSION_KEY, "worktrackWebsiteQueue", "worktrackWebsiteTracker"]);
  chrome.runtime.sendMessage({ type: "worktrack-stop" });
  pendingSession = null;
  loginButton.hidden = false;
  consentPanel.hidden = true;
  showSession(null);
});

chrome.storage.local.get([SESSION_KEY, NOTICE_KEY]).then((values) => {
  const session = values[SESSION_KEY] || null;
  if (session) apiInput.value = session.apiUrl;
  showSession(session);
  if (values[NOTICE_KEY]) statusElement.textContent = values[NOTICE_KEY];
});
