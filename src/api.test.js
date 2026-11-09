import { test } from 'node:test';
import assert from 'node:assert/strict';
let counter = 0;
async function setup(auth = null) {
  const data = new Map(auth ? [['worktrack-auth', JSON.stringify(auth)]] : []);
  globalThis.sessionStorage = {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
  globalThis.window = { location: { origin: 'http://localhost:5173' } };
  return import(`./api.js?test=${counter++}`);
}
const reply = (data, status = 200) =>
  new Response(status === 204 ? null : JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
test('field validation keeps structured details for inline password feedback', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' });
  const { passwordFeedback } = await import('./passwordFeedback.js');
  const details = { password: ['This password is too common.'] };
  globalThis.fetch = async () => reply(details, 400);
  await assert.rejects(
    client.api('/api/users/2/', {
      method: 'PATCH',
      body: JSON.stringify({ password: 'password' }),
    }),
    (error) => {
      assert.equal(error.status, 400);
      assert.deepEqual(error.details, details);
      assert.deepEqual(passwordFeedback(error), {
        field: 'password',
        message: 'Энэ нууц үг хэт түгээмэл байна. Таахад хэцүү, өөр нууц үг сонгоно уу.',
      });
      return true;
    },
  );
});
test('login persists JWT and authenticated writes use it', async () => {
  const client = await setup();
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return reply(url.endsWith('/login/') ? { access: 'access', refresh: 'refresh' } : { id: 1 });
  };
  await client.login('worker', 'password');
  await client.api('/api/tasks/', {
    method: 'POST',
    body: JSON.stringify({ title: 'Task' }),
  });
  assert.equal(calls[1][1].headers.Authorization, 'Bearer access');
  assert.equal(JSON.parse(sessionStorage.getItem('worktrack-auth')).refresh, 'refresh');
});
test('expired JWT refreshes and retries the original request', async () => {
  const client = await setup({ access: 'expired', refresh: 'refresh' });
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    if (url.endsWith('/refresh/')) return reply({ access: 'new' });
    return options.headers.Authorization === 'Bearer new'
      ? reply({ id: 1 })
      : reply({ detail: 'Expired' }, 401);
  };
  assert.deepEqual(await client.api('/api/users/me/'), { id: 1 });
  assert.equal(calls.length, 3);
  assert.equal(calls[2][1].headers.Authorization, 'Bearer new');
});
test('invalid refresh clears the session and exposes authentication error', async () => {
  const client = await setup({ access: 'expired', refresh: 'invalid' });
  globalThis.fetch = async () => reply({ detail: 'Login required' }, 401);
  await assert.rejects(client.api('/api/users/me/'), /Нэвтрэх хугацаа дууссан/);
  assert.equal(sessionStorage.getItem('worktrack-auth'), null);
});
test('desktop bridge unauthorized response does not clear the web login', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' });
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return reply({ detail: 'Desktop bridge login required' }, 401);
  };
  await assert.rejects(client.desktop('status'), (error) => error.status === 401);
  assert.equal(calls, 1);
  assert.equal(client.hasAuth(), true);
  assert.equal(JSON.parse(sessionStorage.getItem('worktrack-auth')).refresh, 'refresh');
});

test('list retrieves every page and delete accepts 204', async () => {
  const client = await setup();
  globalThis.fetch = async (url) =>
    reply(
      url.includes('page=2')
        ? { results: [{ id: 2 }], next: null }
        : {
            results: [{ id: 1 }],
            next: 'http://127.0.0.1:8000/api/tasks/?page=2',
          },
    );
  assert.deepEqual(await client.list('/api/tasks/'), [{ id: 1 }, { id: 2 }]);
  globalThis.fetch = async () => reply(null, 204);
  assert.equal(await client.api('/api/tasks/1/', { method: 'DELETE' }), null);
});

test('offline backend proxy response shows an actionable error', async () => {
  const client = await setup();
  globalThis.fetch = async () => new Response('Proxy error', { status: 500 });
  await assert.rejects(client.login('worker', 'password'), /Backend сервертэй холбогдож чадсангүй/);
});

function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test('report download refreshes authentication and returns actual CSV bytes', async () => {
  const client = await setup({ access: 'expired', refresh: 'refresh' });
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    if (url.endsWith('/refresh/')) return reply({ access: 'new' });
    if (options.headers.Authorization !== 'Bearer new') return reply({ detail: 'Expired' }, 401);
    return new Response('date,username\n2026-11-05,worker\n', {
      headers: { 'Content-Type': 'text/csv' },
    });
  };
  const blob = await client.downloadReport('/api/reports/export/?file_type=csv');
  assert.equal(await blob.text(), 'date,username\n2026-11-05,worker\n');
  assert.equal(calls.length, 3);
});

test('logout prevents a delayed private report from being delivered', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' }),
    pending = deferred();
  globalThis.fetch = () => pending.promise;
  const download = client.downloadReport('/api/reports/export/');
  client.clearAuth();
  pending.resolve(new Response('private report', { headers: { 'Content-Type': 'text/csv' } }));
  await assert.rejects(download, (error) => error.name === 'AbortError');
});
test('temporary refresh server error preserves saved login', async () => {
  const client = await setup({ access: 'expired', refresh: 'valid-refresh' });
  globalThis.fetch = async (url) =>
    url.endsWith('/refresh/')
      ? reply({ detail: 'Maintenance' }, 503)
      : reply({ detail: 'Expired' }, 401);
  await assert.rejects(client.api('/api/users/me/'), (error) => error.status === 503);
  assert.equal(JSON.parse(sessionStorage.getItem('worktrack-auth')).refresh, 'valid-refresh');
});
test('network failure during refresh preserves saved login', async () => {
  const client = await setup({ access: 'expired', refresh: 'valid-refresh' });
  globalThis.fetch = async (url) => {
    if (url.endsWith('/refresh/')) throw new TypeError('Network down');
    return reply({ detail: 'Expired' }, 401);
  };
  await assert.rejects(client.api('/api/users/me/'), (error) => error.status === 0);
  assert.equal(client.hasAuth(), true);
});
test('simultaneous expired requests share one refresh', async () => {
  const client = await setup({ access: 'expired', refresh: 'valid' });
  const started = deferred(),
    release = deferred();
  let refreshes = 0;
  globalThis.fetch = async (url, options) => {
    if (url.endsWith('/refresh/')) {
      refreshes++;
      started.resolve();
      await release.promise;
      return reply({ access: 'new' });
    }
    return options.headers.Authorization === 'Bearer new'
      ? reply({ id: 1 })
      : reply({ detail: 'Expired' }, 401);
  };
  const requests = Promise.all([client.api('/api/users/me/'), client.api('/api/tasks/')]);
  await started.promise;
  release.resolve();
  await requests;
  assert.equal(refreshes, 1);
});
test('logout revokes the refresh before clearing local login', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' });
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    assert.equal(client.hasAuth(), true);
    return reply(null, 204);
  };
  await client.logout();
  assert.equal(request.url, '/api/auth/logout/');
  assert.equal(JSON.parse(request.options.body).refresh, 'refresh');
  assert.equal(request.options.headers.Authorization, 'Bearer access');
  assert.equal(client.hasAuth(), false);
});
test('failed server logout keeps credentials for retry', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' });
  globalThis.fetch = async () => reply({ detail: 'Unavailable' }, 503);
  await assert.rejects(client.logout(), (error) => error.status === 503);
  assert.equal(client.hasAuth(), true);
});
test('data response arriving after logout is cancelled', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' });
  const gate = deferred();
  globalThis.fetch = () => gate.promise;
  const pending = client.api('/api/users/me/');
  const rejected = assert.rejects(pending, { name: 'AbortError' });
  client.clearAuth();
  gate.resolve(reply({ id: 1 }));
  await rejected;
  assert.equal(client.hasAuth(), false);
});
test('login response arriving after logout cannot restore a session', async () => {
  const client = await setup();
  const gate = deferred();
  globalThis.fetch = () => gate.promise;
  const pending = client.login('old', 'password');
  const rejected = assert.rejects(pending, { name: 'AbortError' });
  client.clearAuth();
  gate.resolve(reply({ access: 'late', refresh: 'late' }));
  await rejected;
  assert.equal(sessionStorage.getItem('worktrack-auth'), null);
});
test('refresh response arriving after logout cannot restore a session', async () => {
  const client = await setup({ access: 'expired', refresh: 'refresh' });
  const started = deferred(),
    gate = deferred();
  globalThis.fetch = async (url) => {
    if (url.endsWith('/refresh/')) {
      started.resolve();
      return gate.promise;
    }
    return reply({ detail: 'Expired' }, 401);
  };
  const pending = client.api('/api/users/me/');
  const rejected = assert.rejects(pending, { name: 'AbortError' });
  await started.promise;
  client.clearAuth();
  gate.resolve(reply({ access: 'late' }));
  await rejected;
  assert.equal(client.hasAuth(), false);
});
test('aborted pagination stops without clearing login', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' });
  const controller = new AbortController();
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    controller.abort();
    return reply({ results: [], next: '/api/tasks/?page=2' });
  };
  await assert.rejects(client.list('/api/tasks/', { signal: controller.signal }), {
    name: 'AbortError',
  });
  assert.equal(calls, 1);
  assert.equal(client.hasAuth(), true);
});
test('rate limit exposes retry wait to the login form', async () => {
  const client = await setup();
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: 'Throttled' }), {
      status: 429,
      headers: { 'Retry-After': '30' },
    });
  await assert.rejects(
    client.login('worker', 'password'),
    (error) =>
      error.status === 429 && error.retryAfter === 30 && error.message.includes('30 секунд'),
  );
});

test('logout with an already-invalid refresh still clears the local session', async () => {
  const client = await setup({ access: 'access', refresh: 'already-revoked' });
  globalThis.fetch = async () =>
    reply({ refresh: ['Invalid, expired or revoked refresh token.'] }, 400);
  await client.logout();
  assert.equal(client.hasAuth(), false);
});
test('a forbidden logout does not discard credentials or pretend to revoke another user token', async () => {
  const client = await setup({ access: 'access', refresh: 'refresh' });
  globalThis.fetch = async () => reply({ detail: 'Only your own refresh is allowed.' }, 403);
  await assert.rejects(client.logout(), (error) => error.status === 403);
  assert.equal(client.hasAuth(), true);
});
