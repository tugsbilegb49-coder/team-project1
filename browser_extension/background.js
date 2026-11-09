const SESSION_KEY = "worktrackWebsiteSession";
const TRACKER_KEY = "worktrackWebsiteTracker";
const QUEUE_KEY = "worktrackWebsiteQueue";
const NOTICE_KEY = "worktrackWebsiteNotice";
const IDLE_SECONDS = 15;
const MAX_UNOBSERVED_SECONDS = 60;
const MAX_QUEUE_SEGMENTS = 2000;
let work = Promise.resolve();

function serialize(action) {
  work = work.then(action).catch((error) => console.error("WorkTrack website tracker:", error));
  return work;
}

async function getSession() {
  const { [SESSION_KEY]: session } = await chrome.storage.local.get(SESSION_KEY);
  return session || null;
}

async function getActiveDomain() {
  if ((await chrome.idle.queryState(15)) !== "active") return null;
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.url || !Number.isInteger(tab.windowId)) return null;
  try {
    const window = await chrome.windows.get(tab.windowId);
    if (!window.focused) return null;
    const url = new URL(tab.url);
    return url.protocol === "http:" || url.protocol === "https:" ? url.hostname.toLowerCase() : null;
  } catch {
    return null;
  }
}

async function refreshAccess(session) {
  const response = await fetch(`${session.apiUrl}/api/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: session.refresh }),
  });
  if (!response.ok) throw Object.assign(new Error("Login expired. Sign in again in extension settings."), { status: response.status });
  const tokens = await response.json();
  const updated = { ...session, access: tokens.access };
  await chrome.storage.local.set({ [SESSION_KEY]: updated });
  return updated;
}

async function stopForMissingConsent() {
  await chrome.storage.local.remove(SESSION_KEY);
  await chrome.storage.local.set({
    [QUEUE_KEY]: [],
    [TRACKER_KEY]: null,
    [NOTICE_KEY]: "Monitoring зөвшөөрөл байхгүй тул вэбсайт бүртгэл зогслоо.",
  });
}

async function stopForExpiredLogin() {
  await chrome.storage.local.remove(SESSION_KEY);
  await chrome.storage.local.set({
    [QUEUE_KEY]: [],
    [TRACKER_KEY]: null,
    [NOTICE_KEY]: "Нэвтрэх хугацаа дууссан тул website бүртгэл зогслоо. Extension-ийн Options хэсэгт дахин нэвтэрнэ үү.",
  });
}

async function postSegment(segment) {
  let session = await getSession();
  if (!session) return false;
  let consentResponse = await fetch(`${session.apiUrl}/api/consents/status/`, {
    headers: { Authorization: `Bearer ${session.access}` },
  });
  if (consentResponse.status === 401) {
    try {
      session = await refreshAccess(session);
    } catch (error) {
      if ([401, 403].includes(error.status)) await stopForExpiredLogin();
      throw error;
    }
    consentResponse = await fetch(`${session.apiUrl}/api/consents/status/`, {
      headers: { Authorization: `Bearer ${session.access}` },
    });
  }
  if (consentResponse.status === 403) {
    await stopForMissingConsent();
    return false;
  }
  if (!consentResponse.ok)
    throw Object.assign(new Error(`Consent check failed (${consentResponse.status}).`), { status: consentResponse.status });
  const consent = await consentResponse.json();
  if (!consent.active) {
    await stopForMissingConsent();
    return false;
  }

  let response = await fetch(`${session.apiUrl}/api/website-activity/ingest/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access}`,
    },
    body: JSON.stringify(segment),
  });
  if (response.status === 401) {
    try {
      session = await refreshAccess(session);
    } catch (error) {
      if ([401, 403].includes(error.status)) await stopForExpiredLogin();
      throw error;
    }
    response = await fetch(`${session.apiUrl}/api/website-activity/ingest/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access}`,
      },
      body: JSON.stringify(segment),
    });
  }
  if (response.status === 403) {
    await stopForMissingConsent();
    return false;
  }
  if (!response.ok) throw Object.assign(new Error(`Website activity upload failed (${response.status}).`), { status: response.status });
  return true;
}

async function flushQueue() {
  const { [QUEUE_KEY]: storedQueue = [] } = await chrome.storage.local.get(QUEUE_KEY);
  const queue = Array.isArray(storedQueue) ? [...storedQueue] : [];
  while (queue.length) {
    if (!(await postSegment(queue[0]))) return;
    queue.shift();
    await chrome.storage.local.set({ [QUEUE_KEY]: queue });
  }
}

async function moveTo(domain, rotate = false, endAt = Date.now()) {
  const now = endAt;
  const values = await chrome.storage.local.get([TRACKER_KEY, QUEUE_KEY]);
  const current = values[TRACKER_KEY];
  if ((current?.domain || null) === (domain || null) && !rotate) {
    await flushQueue();
    return;
  }

  const queue = Array.isArray(values[QUEUE_KEY]) ? [...values[QUEUE_KEY]] : [];
  if (current?.domain && now > current.startedAt) {
    queue.push({
      domain: current.domain,
      started_at: new Date(current.startedAt).toISOString(),
      // Missing alarms can mean the browser slept or the worker was suspended.
      // Count at most one observed interval instead of crediting the whole gap.
      duration_seconds: Math.min(MAX_UNOBSERVED_SECONDS, (now - current.startedAt) / 1000),
    });
  }
  const boundedQueue = queue.slice(-MAX_QUEUE_SEGMENTS);
  await chrome.storage.local.set({
    [TRACKER_KEY]: domain ? { domain, startedAt: now } : null,
    [QUEUE_KEY]: boundedQueue,
  });
  await flushQueue();
}

async function syncActiveTab(rotate = false, idleBoundary = false) {
  if (!(await getSession())) {
    await chrome.storage.local.set({ [TRACKER_KEY]: null, [QUEUE_KEY]: [] });
    return;
  }
  if (idleBoundary) {
    const values = await chrome.storage.local.get(TRACKER_KEY);
    const current = values[TRACKER_KEY];
    if (current?.domain) {
      const stopAt = Math.max(current.startedAt, Date.now() - IDLE_SECONDS * 1000);
      await moveTo(null, false, stopAt);
    }
    return;
  }
  await moveTo(await getActiveDomain(), rotate);
}

chrome.alarms.create("worktrack-website-flush", { periodInMinutes: 1 });
chrome.idle.setDetectionInterval(IDLE_SECONDS);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "worktrack-website-flush") serialize(() => syncActiveTab(true));
});
chrome.tabs.onActivated.addListener(() => serialize(syncActiveTab));
chrome.tabs.onRemoved.addListener(() => serialize(syncActiveTab));
chrome.tabs.onUpdated.addListener((_tabId, changeInfo) => {
  if (changeInfo.url) serialize(syncActiveTab);
});
chrome.windows.onFocusChanged.addListener(() => serialize(syncActiveTab));
chrome.idle.onStateChanged.addListener((state) =>
  serialize(() => syncActiveTab(false, state !== "active")),
);
chrome.runtime.onStartup.addListener(() => serialize(syncActiveTab));
chrome.runtime.onInstalled.addListener(() => serialize(syncActiveTab));
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "worktrack-start" || message?.type === "worktrack-stop")
    serialize(syncActiveTab);
});
