import { test } from 'node:test';
import assert from 'node:assert/strict';
let counter = 0;
async function setup(auth = null) {
  const data = new Map(auth ? [['worktrack-auth', JSON.stringify(auth)]] : []);
  globalThis.sessionStorage = {getItem:key => data.get(key) ?? null, setItem:(key,value) => data.set(key,value), removeItem:key => data.delete(key)};
  globalThis.window = {location:{origin:'http://localhost:5173'}};
  return import(`./api.js?test=${counter++}`);
}
const reply = (data, status=200) => new Response(status === 204 ? null : JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
test('login persists JWT and authenticated writes use it', async () => {
  const client = await setup();
  const calls=[];
  globalThis.fetch=async (url, options) => {calls.push([url,options]);return reply(url.endsWith('/login/') ? {access:'access',refresh:'refresh'} : {id:1});};
  await client.login('worker','password');
  await client.api('/api/tasks/',{method:'POST',body:JSON.stringify({title:'Task'})});
  assert.equal(calls[1][1].headers.Authorization,'Bearer access');
  assert.equal(JSON.parse(sessionStorage.getItem('worktrack-auth')).refresh,'refresh');
});
test('expired JWT refreshes and retries the original request',async () => {
  const client=await setup({access:'expired',refresh:'refresh'});
  const calls=[];
  globalThis.fetch=async (url,options) => {calls.push([url,options]); if(url.endsWith('/refresh/')) return reply({access:'new'}); return options.headers.Authorization === 'Bearer new' ? reply({id:1}) : reply({detail:'Expired'},401);};
  assert.deepEqual(await client.api('/api/users/me/'),{id:1});
  assert.equal(calls.length,3);
  assert.equal(calls[2][1].headers.Authorization,'Bearer new');
});
test('invalid refresh clears the session and exposes authentication error',async () => {
  const client=await setup({access:'expired',refresh:'invalid'});
  globalThis.fetch=async () => reply({detail:'Login required'},401);
  await assert.rejects(client.api('/api/users/me/'),/Login required/);
  assert.equal(sessionStorage.getItem('worktrack-auth'),null);
});
test('list retrieves every page and delete accepts 204',async () => {
  const client=await setup();
  globalThis.fetch=async url => reply(url.includes('page=2') ? {results:[{id:2}],next:null} : {results:[{id:1}],next:'http://127.0.0.1:8000/api/tasks/?page=2'});
  assert.deepEqual(await client.list('/api/tasks/'),[{id:1},{id:2}]);
  globalThis.fetch=async () => reply(null,204);
  assert.equal(await client.api('/api/tasks/1/',{method:'DELETE'}),null);
});
