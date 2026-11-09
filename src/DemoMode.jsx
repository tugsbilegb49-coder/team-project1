import { useEffect, useState } from 'react';
import { api } from './api';

/** Демо database-тай сервер л эдгээр бүртгэлийг зарладаг (worktrack.py --demo). */
function useDemo() {
  const [demo, setDemo] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    api('/api/health/', { signal: controller.signal })
      .then((data) => setDemo(data?.demo || null))
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return demo;
}

/** Нэвтрэх хуудсанд: нэг товчоор админ, менежер, ажилтнаар орох. */
export function DemoLogin({ busy, onLogin }) {
  const demo = useDemo();
  if (!demo) return null;
  return (
    <section className="demo-box" aria-label="Демо горим">
      <p>
        <strong>Демо горим</strong> · жишээ өгөгдөл (7 хүн, сүүлийн 30 хоног). Нэг дарж орно:
      </p>
      <div className="demo-accounts">
        {demo.accounts.map((account) => (
          <button
            type="button"
            key={account.username}
            disabled={busy}
            onClick={() => onLogin(account.username, demo.password)}
          >
            {account.label} — {account.name}
          </button>
        ))}
      </div>
    </section>
  );
}

/** Апп дотор: демо гэдгийг сануулж, өөр эрхээр шууд шилжинэ. */
export function DemoBanner({ user, busy, onSwitch }) {
  const demo = useDemo();
  if (!demo) return null;
  return (
    <section className="demo-banner" aria-label="Демо горим">
      <span>
        <strong>ДЕМО</strong> · жишээ өгөгдөл. Өөр эрхээр харах:
      </span>
      {demo.accounts.map((account) => (
        <button
          type="button"
          key={account.username}
          disabled={busy || account.username === user.username}
          aria-pressed={account.username === user.username}
          onClick={() => onSwitch(account.username, demo.password)}
        >
          {account.label}
        </button>
      ))}
    </section>
  );
}
