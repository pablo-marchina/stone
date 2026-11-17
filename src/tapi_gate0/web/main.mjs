import { SSEParser } from './events.mjs';
import { initInventory } from './inventory.mjs';

const $ = id => document.getElementById(id);
const state = { token: null, principal: null, overview: null, controller: null, events: new Map(), connected: false, retry: 0, refreshPending: false, generation: 0 };
const stages = [
  ['Coleta', 'creators', 'Fontes autorizadas'],
  ['Corpus', 'posts', 'Conteúdos registrados'],
  ['Evidências', 'assessments', 'Registros de avaliação, não validações'],
  ['Insights', 'insights', 'Análise fundamentada'],
  ['Criação', 'creatives', 'Produção editorial'],
  ['Publicação', null, 'Pendente de habilitação'],
  ['Conversão', null, 'Pendente de habilitação'],
];
const fmt = n => new Intl.NumberFormat('pt-BR').format(n ?? 0);
const when = s => {
  const dt = new Date(s);
  return Number.isNaN(dt.valueOf()) ? 'Data indisponível' : new Intl.DateTimeFormat('pt-BR', {dateStyle:'short',timeStyle:'short'}).format(dt);
};
function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = String(content); // Never render arbitrary API data as HTML.
  return node;
}
function setConnection(connected) {
  state.connected = connected;
  $('connection-dot').classList.toggle('online', connected);
  $('connection-label').textContent = connected ? 'Eventos conectados' : 'Eventos desconectados';
  $('live-tag').textContent = connected ? 'LIVE' : 'OFFLINE';
  $('live-tag').classList.toggle('online', connected);
}
async function api(path, options = {}) {
  const headers = { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers };
  const requestToken = state.token;
  if (requestToken) headers.Authorization = `Bearer ${requestToken}`;
  const response = await fetch(path, { ...options, headers, cache: 'no-store' });
  if (response.status === 401 && path !== '/v1/auth/sessions') { if (requestToken && state.token === requestToken) logout(); throw new Error('Sua sessão expirou. Entre novamente.'); }
  if (!response.ok) throw new Error(response.status === 403 ? 'Operação negada pela política de acesso.' : `Falha na operação (HTTP ${response.status}).`);
  return response.status === 204 ? null : response.json();
}
function authenticatedView(show) {
  $('login-view').classList.toggle('hidden', show);
  $('dashboard').classList.toggle('hidden', !show);
  $('logout').classList.toggle('hidden', !show);
}
async function login(evt) {
  evt.preventDefault(); $('login-error').textContent = '';
  $('login-submit').disabled = true;
  try {
    const input = { tenant_id: $('tenant').value.trim(), username: $('username').value.trim(), password: $('password').value };
    const session = await api('/v1/auth/sessions', { method: 'POST', body: JSON.stringify(input) });
    state.token = session.access_token;
    $('password').value = '';
    state.principal = await api('/v1/auth/me');
    authenticatedView(true);
    inventory.reset();
    void inventory.load();
    await refresh();
    void connectEvents();
  } catch (error) { $('login-error').textContent = error.message; }
  finally { $('login-submit').disabled = false; }
}
function logout() {
  const oldToken = state.token;
  state.generation++;
  state.controller?.abort(); state.controller = null;
  state.token = null; state.principal = null; state.overview = null; state.events.clear(); state.retry = 0;
  $('kpis').replaceChildren(); $('events').replaceChildren(); $('posts-table').replaceChildren(); $('pipeline-graph').replaceChildren();
  inventory.reset();
  authenticatedView(false); setConnection(false);
  if (oldToken) void fetch('/v1/auth/logout', { method:'POST', headers:{Authorization:`Bearer ${oldToken}`} }).catch(() => {});
}
function renderOverview() {
  const data = state.overview;
  if (!data) return;
  $('tenant-label').textContent = `Organização ${data.tenant_id} · Perfil ${state.principal?.role ?? '—'} · Origem ${data.data_scope}`;
  const cards = [['Criadores', 'creators', 'Perfis no corpus'], ['Conteúdos', 'posts', 'Posts registrados'], ['Snapshots', 'metrics_snapshots', 'Métricas históricas'], ['Avaliações', 'assessments', 'Registros, não validações científicas'], ['Insights', 'insights', 'Evidências fundamentadas'], ['Criativos', 'creatives', 'Versões editoriais (fora da biblioteca Studio)']];
  $('kpis').replaceChildren(...cards.map(([name, key, description], i) => {
    const card = el('article', 'kpi-card');
    card.append(el('span', 'kpi-label', name), el('strong', 'kpi-number', fmt(data.counts[key])), el('span', 'kpi-desc', description));
    card.dataset.index = String(i);
    return card;
  }));
  const graph = $('pipeline-graph'); graph.replaceChildren();
  stages.forEach(([name, countKey, desc], index) => {
    const stage = el('div', `stage ${countKey ? '' : 'stage-pending'}`);
    stage.append(el('span','stage-index',String(index+1).padStart(2,'0')), el('strong','stage-title',name), el('span','stage-count',countKey ? fmt(data.counts[countKey]) : '—'), el('span','stage-desc',desc));
    graph.append(stage);
    if (index !== stages.length - 1) graph.append(el('span','stage-arrow','→'));
  });
  const posts = $('posts-table');posts.replaceChildren();
  if (!data.recent_posts.length) {
    const tr = el('tr'); const td = el('td','empty-cell','Nenhum conteúdo registrado.'); td.colSpan = 5;tr.append(td);posts.append(tr);
  } else data.recent_posts.forEach(post => {
    const tr = el('tr'); [post.content_id,post.creator_id,post.media_type,when(post.published_at),post.origin].forEach(v=>tr.append(el('td','',v)));posts.append(tr);
  });
  for (const event of data.recent_events) state.events.set(event.event_id, event);
  renderEvents();
  $('footer-status').textContent = `${fmt(data.counts.events)} eventos persistidos · último cursor ${data.last_event_seq}`;
  $('cursor-caption').textContent = `Último cursor persistido: ${data.last_event_seq}`;
}
function renderEvents() {
  const rows = [...state.events.values()].sort((a,b)=>b.seq-a.seq).slice(0,18);
  $('events').replaceChildren(...(rows.length ? rows.map(event => {
    const item=el('div','event-item');
    item.append(el('span','event-time',when(event.occurred_at)), el('span','event-kind',event.event_type),el('span','event-subject',`${event.aggregate_type} · ${event.aggregate_id}`));
    return item;
  }) : [el('p','empty-state','Ainda não há eventos persistidos nesta organização.') ]));
}
async function refresh() {
  if (!state.token) return;
  const expectedToken = state.token;
  const data = await api('/v1/ui/overview');
  if (!state.token || state.token !== expectedToken) return;
  state.overview = data;
  renderOverview();
}
function scheduleRefresh() {
  if (state.refreshPending || !state.token) return;
  state.refreshPending=true;
  queueMicrotask(async () => {
    try { await refresh(); }
    catch (err) { $('footer-status').textContent = err.message; }
    finally { state.refreshPending=false; }
  });
}
async function connectEvents() {
  const gen = ++state.generation;
  while (state.token && gen === state.generation) {
    const controller = new AbortController(); state.controller = controller;
    try {
      let lastSeq = state.overview?.last_event_seq ?? 0;
      const response = await fetch(`/v1/events/stream?after_seq=${lastSeq}`, {
        headers:{ Authorization:`Bearer ${state.token}`, Accept:'text/event-stream' }, signal:controller.signal, cache:'no-store'
      });
      if (response.status === 401) { logout(); return; }
      if (!response.ok || !response.body) throw new Error(`SSE HTTP ${response.status}`);
      setConnection(true); state.retry=0;
      const parser = new SSEParser(item => {
        if (item.event !== 'domain_event') return;
        try {
          const raw = JSON.parse(item.data);
          if (!Number.isSafeInteger(raw.seq) || raw.seq <= lastSeq) return;
          lastSeq=raw.seq;
          const safe = {seq:raw.seq,event_id:raw.event_id,event_type:raw.event_type,aggregate_type:raw.aggregate_type,aggregate_id:raw.aggregate_id,occurred_at:raw.occurred_at};
          state.events.set(safe.event_id,safe);renderEvents();
          $('cursor-caption').textContent = `Evento recebido: ${lastSeq}`;
          scheduleRefresh();
        } catch (_) { $('cursor-caption').textContent = 'Evento inválido ignorado'; }
      });
      const reader = response.body.getReader(); const decoder = new TextDecoder();
      while (state.token && gen === state.generation) {
        const {value,done}=await reader.read();if(done)break;
        parser.feed(decoder.decode(value,{stream:true}));
      }
    } catch (err) {
      if (!controller.signal.aborted) $('footer-status').textContent = 'Fluxo interrompido; reconexão em andamento.';
    } finally { setConnection(false); }
    if (!state.token || gen !== state.generation) break;
    state.retry=Math.min(state.retry+1,5);
    await new Promise(resolve=>setTimeout(resolve,Math.min(1000*2**(state.retry-1),10000)));
  }
}
const inventory = initInventory({api,getPrincipal:()=>state.principal});
$('login-form').addEventListener('submit',login);
$('logout').addEventListener('click',logout);
$('refresh').addEventListener('click',()=>refresh().catch(err=>{$('footer-status').textContent=err.message;}));
setConnection(false);
