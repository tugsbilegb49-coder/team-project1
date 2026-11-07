import { useEffect, useState } from 'react';
import { api } from './api';
import { passwordFeedback } from './passwordFeedback';
import { launcherName } from './platform';
import { forgetSetupToken } from './setupToken';

function fieldError(failure) {
  const username = failure.details?.username;
  if (username) return { field: 'username', message: [].concat(username).join(' ') };
  return passwordFeedback(failure);
}

/** Байгууллагын анхны админыг үүсгээд түүгээр шууд нэвтэрнэ. */
export function FirstAdminSetup({ token, onCreated, onSkip }) {
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (data.password !== data.confirm_password) {
      setError({ field: 'confirm_password', message: 'Нууц үгүүд ижил байх ёстой.' });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api('/api/setup/', { method: 'POST', body: JSON.stringify({ ...data, token }) });
    } catch (failure) {
      setError(fieldError(failure));
      setBusy(false);
      return;
    }
    forgetSetupToken();
    await onCreated(data.username.trim(), data.password);
  }
  function skip() {
    forgetSetupToken();
    onSkip();
  }
  return (
    <main className="main">
      <form className="task-form" onSubmit={submit}>
        <h1>WorkTrack — Анхны тохиргоо</h1>
        <p>
          WorkTrack энэ компьютер дээр анх удаа ажиллаж байна. Байгууллагынхаа админ бүртгэлийг
          үүсгэнэ үү. Ажилтнуудаа дараа нь «Багийн гишүүд» хэсгээс нэмнэ.
        </p>
        <fieldset disabled={busy}>
          <label htmlFor="setup-username">Админы нэвтрэх нэр</label>
          <input
            id="setup-username"
            name="username"
            autoComplete="username"
            required
            maxLength={150}
            aria-invalid={error?.field === 'username'}
          />
          <label htmlFor="setup-password">Нууц үг</label>
          <input
            id="setup-password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={256}
            aria-invalid={error?.field === 'password'}
          />
          <label htmlFor="setup-confirm">Нууц үг давтах</label>
          <input
            id="setup-confirm"
            name="confirm_password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            maxLength={256}
            aria-invalid={error?.field === 'confirm_password'}
          />
          {error && <p role="alert">{error.message}</p>}
          <button type="submit">{busy ? 'Үүсгэж байна…' : 'Админ үүсгээд нэвтрэх'}</button>
        </fieldset>
        <button type="button" className="secondary-button" onClick={skip}>
          Админ бүртгэлтэй бол нэвтрэх
        </button>
      </form>
    </main>
  );
}

/** Нэвтрэх хуудсан дээр: админ хараахан үүсээгүй бол яаж үүсгэхийг хэлнэ. */
export function FirstRunHint() {
  const [needed, setNeeded] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api('/api/setup/', { signal: controller.signal })
      .then((data) => setNeeded(Boolean(data?.needs_admin)))
      .catch(() => {});
    return () => controller.abort();
  }, []);
  if (!needed) return null;
  return (
    <p className="muted">
      Админ хараахан үүсээгүй байна. {launcherName}-аа хааж дахин нээхэд анхны тохиргооны хуудас
      өөрөө нээгдэнэ.
    </p>
  );
}
