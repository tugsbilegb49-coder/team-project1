import { useState } from 'react';
import { api } from './api';
import { passwordFeedback } from './passwordFeedback';

function feedback(failure) {
  const code = failure.details?.code;
  if (code) return { field: 'code', message: Array.isArray(code) ? code.join(' ') : code };
  return passwordFeedback(failure);
}

/** Нэвтрэх хуудсан дээр: админаас авсан нэг удаагийн кодоор шинэ нууц үг тохируулах. */
export function ResetWithCode({ onDone, onCancel }) {
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (data.new_password !== data.confirm_password) {
      setError({ field: 'confirm_password', message: 'Шинэ нууц үгүүд ижил байх ёстой.' });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api('/api/auth/reset-password/', { method: 'POST', body: JSON.stringify(data) });
      onDone(data.username.trim());
    } catch (failure) {
      setError(feedback(failure));
      setBusy(false);
    }
  }
  const described = (field) => (error?.field === field ? 'reset-error' : undefined);
  return (
    <main className="main">
      <form className="task-form" onSubmit={submit}>
        <h1>Нууц үг шинэчлэх</h1>
        <p>
          Админаасаа <strong>нууц үг сэргээх код</strong> аваарай. Код 24 цаг хүчинтэй, нэг л удаа
          ажиллана. Админ таны шинэ нууц үгийг мэдэхгүй.
        </p>
        <fieldset disabled={busy}>
          <label htmlFor="reset-username">Хэрэглэгчийн нэр</label>
          <input id="reset-username" name="username" autoComplete="username" required />
          <label htmlFor="reset-code">Сэргээх код</label>
          <input
            id="reset-code"
            name="code"
            required
            autoComplete="one-time-code"
            autoCapitalize="characters"
            spellCheck={false}
            placeholder="ABCD-EFGH-JKLM"
            maxLength={40}
            aria-invalid={error?.field === 'code'}
            aria-describedby={described('code')}
          />
          <label htmlFor="reset-new">Шинэ нууц үг</label>
          <input
            id="reset-new"
            name="new_password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            maxLength={256}
            required
            aria-invalid={error?.field === 'new_password'}
            aria-describedby={described('new_password')}
          />
          <label htmlFor="reset-confirm">Шинэ нууц үг давтах</label>
          <input
            id="reset-confirm"
            name="confirm_password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            maxLength={256}
            required
            aria-invalid={error?.field === 'confirm_password'}
            aria-describedby={described('confirm_password')}
          />
          {error && (
            <p id="reset-error" className="field-error" role="alert">
              {error.message}
            </p>
          )}
          <div className="desktop-actions">
            <button type="submit">{busy ? 'Хадгалж байна…' : 'Шинэ нууц үг хадгалах'}</button>
            <button type="button" className="secondary-button" onClick={onCancel}>
              Нэвтрэх хуудас руу буцах
            </button>
          </div>
        </fieldset>
      </form>
    </main>
  );
}

/** Админд: ажилтанд өгөх нэг удаагийн сэргээх код. */
export function MemberResetCode({ member, busy }) {
  const [issued, setIssued] = useState(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  async function create() {
    if (issued && !window.confirm('Шинэ код үүсгэвэл өмнөх код ажиллахаа болино. Үргэлжлүүлэх үү?'))
      return;
    setWorking(true);
    setError('');
    try {
      setIssued(await api(`/api/users/${member.id}/reset-code/`, { method: 'POST' }));
    } catch (failure) {
      setError(failure.message);
    } finally {
      setWorking(false);
    }
  }
  const until = issued && new Date(issued.expires_at);
  return (
    <div className="member-password">
      <button type="button" disabled={busy || working} onClick={create}>
        {working ? 'Үүсгэж байна…' : 'Сэргээх код үүсгэх'}
      </button>
      {error && <p role="alert">{error}</p>}
      {issued && (
        <div role="status" className="reset-code">
          <p>
            <strong>{member.username}</strong>-ийн код:{' '}
            <code className="reset-code-value">{issued.code}</code>
          </p>
          <p className="muted">
            Ажилтанд биечлэн эсвэл хувийн мессежээр өгнө. Ажилтан нэвтрэх хуудасны «Нууц үгээ
            мартсан уу?» дээр дарж шинэ нууц үгээ өөрөө тохируулна. Хүчинтэй:{' '}
            {until.toLocaleString('mn-MN', { dateStyle: 'short', timeStyle: 'short' })} хүртэл, нэг
            удаа.
          </p>
        </div>
      )}
    </div>
  );
}
