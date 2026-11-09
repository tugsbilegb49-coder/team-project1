/** Нэг удаагийн нууц түлхүүр: launcher анх удаа browser-ийг `#setup=...` хаягаар нээнэ. */
export function readSetupToken() {
  const match = window.location.hash.match(/^#setup=([\w-]+)$/);
  return match ? match[1] : '';
}

/** Түлхүүрийг хаягаас арилгана (browser-ийн түүх болон хуваалцсан холбоосонд үлдэхгүй). */
export function forgetSetupToken() {
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
}
