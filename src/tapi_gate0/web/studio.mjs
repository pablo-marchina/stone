import {initEvidenceLab} from "./evidence_lab.mjs";
// C2: plain browser canvas editor. No paid dependencies, no third-party URLs.
// The only source of truth is the authenticated DesignDocument persisted server-side.
const $ = id => document.getElementById(id);
const model = {
  token: null, principal: null, doc: null, selection: null, drag: null,
  preview: null, bitmaps: new Map(), pendingImages: new Map(),
  pageId: null, dragPageId: null, undoStack: [], redoStack: [],
  libraryAfter:null, libraryBusy:false, libraryEpoch:0, opening:false,
  etag: null, pendingText: null, saveTimer: null, saving: false, proposal:null,
};
const canvas = $('canvas');
const ctx = canvas.getContext('2d');

// Tab-scoped recovery (not cross-session storage): only an uncommitted text draft,
// never OAuth/session tokens or media. Entries expire after 24h.
function recoveryKey() {
  if (!model.principal || !model.doc) return null;
  return 'stone-draft-v1:'+model.principal.tenant_id+':'+model.doc.document_id;
}
function recoveryStore(value) {
  const key=recoveryKey();if(!key)return;
  try {
    if(value)sessionStorage.setItem(key,JSON.stringify({ ...value,at:Date.now() }));
    else sessionStorage.removeItem(key);
  }catch(_){ /* private browsing can disable sessionStorage; server saves remain primary */ }
}
function recoverUnsavedText() {
  const key=recoveryKey();if(!key)return;
  try {
    const raw=sessionStorage.getItem(key);if(!raw)return;
    const previous=JSON.parse(raw);
    if(Date.now()-previous.at>86400000){sessionStorage.removeItem(key);return;}
    const page=model.doc.pages.find(x=>x.id===previous.page_id);
    const layer=page?.layers.find(x=>x.id===previous.layer_id && x.kind==='text');
    if(layer && model.doc.version===previous.version && canWrite()) {
      model.pageId=page.id;renderPages();selectLayer(layer);
      $('layer-text').value=previous.text;
      model.pendingText=previous;
      status('Texto local não salvo recuperado. Confira e clique Salvar texto.');
    } else status('Existe texto local anterior, mas a versão mudou. Não será aplicado automaticamente.');
  }catch(_) { /* corrupt local recovery entry never bypasses server validation */ }
}
function status(message) { $('status').textContent = message; }
function canWrite() { return ['admin','editor'].includes(model.principal?.role); }
function controls() {
  evidenceLab?.controls();
  const logged = !!model.token, editing = logged && !!model.doc && canWrite() && !model.opening;
  $('login').disabled = logged;
  $('logout').disabled = !logged;
  $('create').disabled = !logged || !canWrite() || model.opening;
  $('open').disabled = !logged || model.opening;
  $('library-refresh').disabled = !logged || model.libraryBusy;
  $('library-next').disabled = !logged || model.libraryBusy || !model.libraryAfter;
  $('save-text').disabled = !editing || model.selection?.kind !== 'text';
  $('insert-image').disabled = !editing || !$('file').files?.length || !$('rights').checked;
  $('file').disabled = !editing;
  $('rights').disabled = !editing;
  $('export').disabled = !logged || !model.doc;
  $('export-zip').disabled = !logged || !model.doc || model.doc.platform_intent!=='instagram_carousel';
  $('preview-proposal').disabled=!editing || model.selection?.kind!=='text';
  $('confirm-proposal').disabled=!editing || !model.proposal;
  $('apply-proposal').disabled=!editing || !model.proposal || !$('confirm-proposal').checked;
  $('storyboard-create').disabled=!editing;
  const pages=model.doc?.pages || [], index=pages.findIndex(page=>page.id===model.pageId);
  const carousel=editing && model.doc.platform_intent==='instagram_carousel';
  $('duplicate-page').disabled = !carousel || pages.length>=10;
  $('delete-page').disabled = !carousel || pages.length<2;
  $('page-left').disabled = !carousel || index<=0;
  $('page-right').disabled = !carousel || index<0 || index>=pages.length-1;
  $('undo').disabled = !editing || !model.undoStack.length;
  $('redo').disabled = !editing || !model.redoStack.length;
  $('layer-text').disabled = !editing || model.selection?.kind !== 'text';
  for (const id of ['geom-x','geom-y','geom-w','geom-h','save-geometry','bring-forward','send-backward'])
    $(id).disabled = !editing || !model.selection;
}
async function api(path, { method = 'GET', payload } = {}) {
  const headers = { Accept:'application/json' };
  if (method !== 'GET' && payload?.expected_version && model.etag &&
      path.startsWith('/v1/studio/documents/')) headers['If-Match']=model.etag;
  if (model.token) headers.Authorization = 'Bearer ' + model.token;
  if (payload !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { method, headers,
    body: payload === undefined ? undefined : JSON.stringify(payload),
    cache:'no-store' });
  if (!response.ok) {
    let detail='';try {detail=(await response.json()).detail||'';}catch(_){}
    throw new Error('HTTP '+response.status+(detail?' — '+detail:'')+' — '+path);
  }
  const data=await response.json();
  if (data?.document_id && data?.version && response.headers.get('ETag')) {
    model.etag=response.headers.get('ETag');
  }
  return data;
}
function reset() {
  recoveryStore(null);
  timelineEditor?.reset();
  model.token = null; model.principal = null; model.doc = null;
  evidenceLab?.reset();
  model.libraryEpoch++;model.libraryAfter=null;model.libraryBusy=false;model.opening=false;
  $('draft-library').replaceChildren();$('library-next').hidden=true;
  $('library-status').textContent='Entre para consultar seus documentos.';
  $('library-provenance').textContent='';
  model.selection = null; model.drag = null; model.preview = null;
  model.pageId=null;model.dragPageId=null;model.undoStack=[];model.redoStack=[];
  model.etag=null;model.pendingText=null;model.proposal=null;clearTimeout(model.saveTimer);model.saveTimer=null;
  for (const bitmap of model.bitmaps.values()) bitmap.close?.();
  model.bitmaps.clear(); model.pendingImages.clear();
  $('password').value = ''; $('selected').textContent = 'Nenhuma';
  $('layer-text').value = ''; $('revision').textContent = 'Sem documento';
  controls(); draw();
}
async function login() {
  try {
    const session = await api('/v1/auth/sessions', {method:'POST',payload: {
      username:$('username').value.trim(),
      password:$('password').value, tenant_id:$('tenant').value.trim(),
    }});
    model.token = session.access_token;
    model.principal = await api('/v1/auth/me');
    $('password').value = '';
    status('Autenticado como ' + model.principal.role);
    controls();void loadLibrary();
  } catch (error) { reset(); status('Falha de autenticação: '+error.message); }
}
async function logout() {
  const token = model.token;
  reset();
  if (token) {
    await fetch('/v1/auth/logout', {method:'POST',
      headers:{Authorization:'Bearer '+token}}).catch(()=>{});
  }
  status('Sessão encerrada.');
}
function showDocument(doc, {history=true, resetHistory=false}={}) {
  const previous=model.doc;
  if (resetHistory || !previous || previous.document_id!==doc.document_id) {
    model.undoStack=[];model.redoStack=[];model.pageId=null;
  } else if (history && previous.version!==doc.version) {
    model.undoStack.push(previous.version);model.redoStack=[];
  }
  model.pendingText=null;model.proposal=null;$('confirm-proposal').checked=false;
  $('proposal-preview').textContent='';clearTimeout(model.saveTimer);model.saveTimer=null;
  model.doc = doc; model.selection = null; model.drag = null;
  model.preview = null;
  if (!doc.pages.some(page=>page.id===model.pageId)) model.pageId=doc.pages[0].id;
  $('revision').textContent = doc.document_id + ' · versão ' + doc.version;
  $('diff-from').value=String(Math.max(1,doc.version-1));
  $('diff-to').value=String(doc.version);
  $('selected').textContent = 'Clique em uma camada';
  $('layer-text').value = '';
  renderPages();renderLayerNavigation();controls();draw();
}
function activePage() {return model.doc?.pages.find(page=>page.id===model.pageId) || null;}
async function selectPage(pageId) {
  if (!model.doc?.pages.some(page=>page.id===pageId)) return;
  if (model.pendingText && !(await flushText())) return;
  model.pageId=pageId;model.selection=null;model.drag=null;model.preview=null;
  $('selected').textContent='Clique em uma camada';$('layer-text').value='';
  renderPages();renderLayerNavigation();controls();draw();
}
function renderPages() {
  const host=$('pages');host.replaceChildren();
  if (!model.doc) return;
  model.doc.pages.forEach((page,index)=>{
    const button=document.createElement('button');
    button.type='button';button.textContent='Página '+(index+1);
    button.className='page-chip'+(page.id===model.pageId?' is-active':'');
    button.setAttribute('aria-current',page.id===model.pageId?'page':'false');
    button.draggable=canWrite() && model.doc.platform_intent==='instagram_carousel';
    button.addEventListener('click',()=>{void selectPage(page.id);});
    button.addEventListener('dragstart',event=>{
      if (!button.draggable) {event.preventDefault();return;}
      model.dragPageId=page.id;event.dataTransfer.effectAllowed='move';
      event.dataTransfer.setData('text/plain',page.id);
    });
    button.addEventListener('dragover',event=>{
      if (model.dragPageId && model.dragPageId!==page.id) event.preventDefault();
    });
    button.addEventListener('drop',event=>{
      event.preventDefault();const dragged=model.dragPageId;model.dragPageId=null;
      if (dragged && dragged!==page.id) void reorderPage(index,dragged);
    });
    button.addEventListener('dragend',()=>{model.dragPageId=null;});
    host.appendChild(button);
  });
}
function docPath() {return '/v1/studio/documents/'+encodeURIComponent(model.doc.document_id);}
async function duplicatePage() {
  if (!activePage())return;
  const newId='page.'+crypto.randomUUID().replaceAll('-','').slice(0,16);
  try {
    const doc=await api(docPath()+'/pages/duplicate',{method:'POST',payload:{
      expected_version:model.doc.version,page_id:model.pageId,new_page_id:newId}});
    showDocument(doc);selectPage(newId);status('Página duplicada. Versão '+doc.version);
  }catch(error){status('Não foi possível duplicar: '+error.message);}
}
async function deletePage() {
  if (!activePage())return;
  try {
    const doc=await api(docPath()+'/pages/delete',{method:'POST',payload:{
      expected_version:model.doc.version,page_id:model.pageId}});
    showDocument(doc);status('Página excluída. Versão '+doc.version);
  }catch(error){status('Não foi possível excluir: '+error.message);}
}
async function reorderPage(targetIndex,pageId=model.pageId) {
  if (!model.doc || !pageId)return;
  try {
    const doc=await api(docPath()+'/pages/reorder',{method:'POST',payload:{
      expected_version:model.doc.version,page_id:pageId,target_index:targetIndex}});
    showDocument(doc);selectPage(pageId);status('Ordem das páginas salva. Versão '+doc.version);
  }catch(error){status('Não foi possível reordenar: '+error.message);}
}
async function restoreRevision(direction) {
  if (!model.doc)return;
  if (model.pendingText && !(await flushText()))return;
  const undo=direction==='undo', stack=undo?model.undoStack:model.redoStack;
  if (!stack.length)return;
  const target=stack[stack.length-1],previous=model.doc.version;
  try {
    const doc=await api(docPath()+'/versions/restore',{method:'POST',payload:{
      expected_version:previous,restore_version:target}});
    stack.pop();(undo?model.redoStack:model.undoStack).push(previous);
    showDocument(doc,{history:false});status((undo?'Desfeito':'Refeito')+' na versão '+doc.version);
  }catch(error){status('Histórico indisponível: '+error.message);}
}
async function create() {
  if (!model.token || model.opening || model.saving) return;
  if (model.pendingText && !(await flushText())) return;
  try {
    const spec = {spec_id:'spec.'+crypto.randomUUID().replaceAll('-','').slice(0,18),
      tenant_id:model.principal.tenant_id,
      objective:$('objective').value.trim(),headline:$('headline').value.trim(),
      body:$('body-text').value.trim(),cta:$('cta').value.trim(),
      platform_intent:$('format').value,reference_content_ids:[]};
    const doc = await api('/v1/studio/documents', {method:'POST',
      payload:{document_id:$('document-id').value.trim(),spec}});
    showDocument(doc,{resetHistory:true}); status('Rascunho criado e persistido. Versão 1.');
    $('library-provenance').textContent='';void loadLibrary();
  } catch(error){status('Não foi possível criar: '+error.message);}
}
async function open() {
  if (!model.token || model.opening || model.saving) {
    if(model.saving)status('Aguarde o salvamento antes de trocar de documento.');
    return false;
  }
  const token=model.token, id=$('document-id').value.trim();
  model.opening=true;controls();
  try {
    if(model.pendingText && !(await flushText()))return false;
    if(model.token!==token)return false;
    // Fetch directly here so stale responses cannot replace the current ETag.
    const response=await fetch('/v1/studio/documents/'+encodeURIComponent(id),{
      headers:{Accept:'application/json',Authorization:'Bearer '+token},cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const doc=await response.json();
    if(model.token!==token)return false;
    model.etag=response.headers.get('ETag');
    showDocument(doc,{resetHistory:true});$('library-provenance').textContent='';
    status('Rascunho aberto do banco.');recoverUnsavedText();return true;
  } catch(error){if(model.token===token)status('Não foi possível abrir: '+error.message);return false;}
  finally{if(model.token===token){model.opening=false;controls();}}
}
async function loadLibrary(more=false) {
  if(!model.token || model.libraryBusy || (more && !model.libraryAfter))return;
  const token=model.token, epoch=++model.libraryEpoch;
  const after=more?model.libraryAfter:null;
  model.libraryBusy=true;controls();
  $('library-status').textContent='Consultando rascunhos…';
  try {
    const data=await api('/v1/studio/documents?limit=20'+(after?'&after='+encodeURIComponent(after):''));
    if(model.token!==token || epoch!==model.libraryEpoch)return;
    const host=$('draft-library');
    if(!more)host.replaceChildren();
    for(const item of data.items){
      const button=document.createElement('button');button.type='button';button.className='library-draft';
      const title=document.createElement('strong');title.textContent=item.title;
      const meta=document.createElement('span');
      meta.textContent=item.pages+' pág. · v'+item.version+' · '+(item.historical_provenance==='recorded'?'Hipótese exploratória':'Rascunho');
      button.append(title,meta);
      button.addEventListener('click',async()=>{
        if(model.token!==token || model.opening)return;
        $('document-id').value=item.document_id;
        if(await open() && model.token===token && model.doc?.document_id===item.document_id){
          $('library-provenance').textContent=item.historical_provenance==='recorded'
            ? 'Proveniência histórica registrada: vendas · '+item.historical_reference_count+' referências. Escopo atual não verificado; sem validação científica ou aprovação de publicação.'
            : item.historical_provenance==='invalid'
              ? 'Proveniência histórica inconsistente ou indisponível. Não utilizar como evidência.'
              : 'Sem recibo exploratório registrado. Rascunho não aprovado.';
        }
      });
      host.append(button);
    }
    model.libraryAfter=data.next_after;$('library-next').hidden=!data.next_after;
    $('library-status').textContent=host.children.length?host.children.length+' rascunho(s) listado(s).':'Nenhum rascunho disponível.';
  }catch(error){if(model.token===token && epoch===model.libraryEpoch){
    $('library-status').textContent='Falha ao consultar biblioteca: '+error.message;
  }}finally{if(model.token===token && epoch===model.libraryEpoch){model.libraryBusy=false;controls();}}
}
function layerList() { return activePage()?.layers || []; }
function renderLayerNavigation() {
  const host=$('layer-nav');host.replaceChildren();
  for(const layer of layerList()) {
    const button=document.createElement('button');
    button.type='button';
    button.className='layer-nav-button';
    button.textContent=(layer.kind==='text'?'Texto: ':'Imagem: ')+layer.id;
    button.setAttribute('aria-pressed', String(model.selection?.id===layer.id));
    button.addEventListener('click',()=>{selectLayer(layer);canvas.focus();});
    host.appendChild(button);
  }
}

function selectLayer(layer) {
  model.proposal=null;$('confirm-proposal').checked=false;$('proposal-preview').textContent='';
  model.selection = layer || null;
  $('selected').textContent = layer ? layer.id+' · '+layer.kind : 'Nenhuma';
  $('layer-text').value = layer?.kind === 'text' ? layer.text : '';
  for (const [control, field] of [['geom-x','x'],['geom-y','y'],['geom-w','w'],['geom-h','h']])
    $(control).value = layer ? String(layer[field]) : '';
  renderLayerNavigation(); controls(); draw();
}
function wrapText(text, x, y, width, lineHeight, maxHeight) {
  let offset=0;
  for (const paragraph of text.split('\n')) {
    let line='';
    for (const word of paragraph.split(/\s+/)) {
      const candidate = line ? line+' '+word : word;
      if (line && ctx.measureText(candidate).width > width) {
        if (offset+lineHeight > maxHeight) return;
        ctx.fillText(line,x,y+offset);
        offset+=lineHeight;line=word;
      } else line=candidate;
    }
    if (offset+lineHeight > maxHeight) return;
    if (line) ctx.fillText(line,x,y+offset);
    offset+=lineHeight;
  }
}
async function bitmapFor(assetId) {
  if (model.bitmaps.has(assetId)) return model.bitmaps.get(assetId);
  if (model.pendingImages.has(assetId)) return model.pendingImages.get(assetId);
  const token=model.token;
  const promise=(async()=>{
    const response=await fetch('/v1/studio/assets/'+encodeURIComponent(assetId)+'/binary',
      {headers:{Authorization:'Bearer '+token},cache:'no-store'});
    if (!response.ok) throw new Error('Ativo inacessível: HTTP '+response.status);
    const bmp=await createImageBitmap(await response.blob());
    if (token !== model.token) {bmp.close(); throw new Error('Sessão alterada');}
    model.bitmaps.set(assetId,bmp); draw();
    return bmp;
  })();
  model.pendingImages.set(assetId,promise);
  try {return await promise;} finally {model.pendingImages.delete(assetId);}
}
function draw() {
  const doc=model.doc;
  if(!doc){ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);return;}
  for(const layer of layerList())if(layer.kind==='image'&&!model.bitmaps.has(layer.asset_id))
    void bitmapFor(layer.asset_id).catch(e=>status(e.message));
  StoneExport.drawTo(ctx,doc,activePage(),model.bitmaps,model.preview);
  const layer=model.selection;
  if(layer){
    const move=model.preview?.id===layer.id?model.preview:{dx:0,dy:0};
    ctx.save();ctx.lineWidth=3;ctx.strokeStyle='#158654';ctx.setLineDash([14,8]);
    ctx.strokeRect(layer.x+move.dx,layer.y+move.dy,layer.w,layer.h);ctx.restore();
  }
}
function canvasPoint(evt) {
  const rect=canvas.getBoundingClientRect();
  return {x:(evt.clientX-rect.left)*canvas.width/rect.width,
          y:(evt.clientY-rect.top)*canvas.height/rect.height};
}
canvas.addEventListener('pointerdown', event => {
  if (!model.doc) return;
  const p=canvasPoint(event);
  const picked=[...layerList()].reverse().find(layer=>p.x>=layer.x && p.x<=layer.x+layer.w &&
                                                        p.y>=layer.y && p.y<=layer.y+layer.h);
  selectLayer(picked);
  if (!picked || !canWrite()) return;
  model.drag={id:picked.id,start:p,layer:picked};
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => {
  if (!model.drag) return;
  const p=canvasPoint(event), layer=model.drag.layer;
  const dx=Math.round(Math.min(Math.max(p.x-model.drag.start.x,-layer.x),
                              model.doc.canvas.width-layer.x-layer.w));
  const dy=Math.round(Math.min(Math.max(p.y-model.drag.start.y,-layer.y),
                              model.doc.canvas.height-layer.y-layer.h));
  model.preview={id:layer.id,dx,dy};draw();
});
canvas.addEventListener('pointerup', async event => {
  if (!model.drag) return;
  const drag=model.drag, d=model.preview;
  model.drag=null;model.preview=null;draw();
  if (!d || (!d.dx&&!d.dy)) return;
  try {
    const doc=await api('/v1/studio/documents/'+encodeURIComponent(model.doc.document_id)+'/geometry',
      {method:'POST',payload:{page_id:model.pageId,layer_id:drag.id,
        expected_version:model.doc.version,x:drag.layer.x+d.dx,y:drag.layer.y+d.dy}});
    showDocument(doc); status('Posição persistida na versão '+doc.version);
  } catch(error){status('Edição rejeitada: '+error.message);}
});
canvas.addEventListener('pointercancel',()=>{model.drag=null;model.preview=null;draw();});
// Accessible alternative to pointer drag. One deliberate keypress = one
// optimistic versioned mutation; held keys do not flood the backend.
canvas.addEventListener('keydown', async event => {
  const dirs={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
  const delta=dirs[event.key];
  if (!delta || !canWrite() || !model.doc || !model.selection) return;
  event.preventDefault();
  if (event.repeat || model.saving) return;
  const layer=model.selection,step=event.shiftKey?1:10;
  const x=Math.min(model.doc.canvas.width-layer.w,Math.max(0,layer.x+delta[0]*step));
  const y=Math.min(model.doc.canvas.height-layer.h,Math.max(0,layer.y+delta[1]*step));
  if (x===layer.x && y===layer.y)return;
  model.saving=true;
  try {
    const doc=await api(docPath()+'/geometry',{method:'POST',payload:{
      expected_version:model.doc.version,page_id:model.pageId,
      layer_id:layer.id,x,y}});
    showDocument(doc);
    selectLayer(layerList().find(item=>item.id===layer.id));
    canvas.focus();status('Camada movida por teclado. Versão '+doc.version);
  }catch(error){status('Movimento não aplicado: '+error.message);}
  finally{model.saving=false;}
});

function trackTextInput() {
  if (!model.doc || model.selection?.kind!=='text' || !canWrite())return;
  const text=$('layer-text').value;
  if (text===model.selection.text){model.pendingText=null;clearTimeout(model.saveTimer);return;}
  model.pendingText={document_id:model.doc.document_id,page_id:model.pageId,
    layer_id:model.selection.id,version:model.doc.version,text};
  recoveryStore(model.pendingText);
  clearTimeout(model.saveTimer);
  model.saveTimer=setTimeout(()=>{void flushText();},800);
  status('Edição pendente; salvamento automático…');
}
async function flushText() {
  if (!model.pendingText)return true;
  if (model.saving)return false;
  const pending=model.pendingText;
  if (!model.doc || pending.document_id!==model.doc.document_id ||
      pending.version!==model.doc.version) {
    status('Conflito: edição local preservada no campo; reabra a versão.');return false;
  }
  model.saving=true;clearTimeout(model.saveTimer);
  try {
    const doc=await api('/v1/studio/documents/'+encodeURIComponent(pending.document_id)+'/text-patches',
      {method:'POST',payload:{page_id:pending.page_id,layer_id:pending.layer_id,
        expected_version:pending.version,text:pending.text}});
    recoveryStore(null);showDocument(doc);
    status('Salvamento automático confirmado. Versão '+doc.version);
    return true;
  }catch(error){
    status('Edição NÃO salva: '+error.message+' — texto mantido no campo.');
    return false;
  }finally{model.saving=false;}
}
async function saveText() {
  if(model.selection?.kind!=='text') return;
  if (model.pendingText) {await flushText();return;}
  if ($('layer-text').value===model.selection.text)return;
  try {
    const doc=await api('/v1/studio/documents/'+encodeURIComponent(model.doc.document_id)+'/text-patches',
      {method:'POST',payload:{page_id:model.pageId,layer_id:model.selection.id,
        expected_version:model.doc.version,text:$('layer-text').value}});
    showDocument(doc);status('Texto persistido na versão '+doc.version);
  } catch(error){status('Edição rejeitada: '+error.message);}
}
async function applyGeometry() {
  if (!model.doc || !model.selection) return;
  const numbers = {};
  for (const [name, control] of [['x','geom-x'],['y','geom-y'],['w','geom-w'],['h','geom-h']]) {
    const text = $(control).value.trim();
    if (!/^[0-9]+$/.test(text)) { status('Geometria deve conter números inteiros não negativos.'); return; }
    numbers[name] = Number(text);
  }
  try {
    const doc = await api('/v1/studio/documents/'+encodeURIComponent(model.doc.document_id)+'/geometry',
      {method:'POST',payload:{expected_version:model.doc.version,page_id:model.pageId,
         layer_id:model.selection.id,...numbers}});
    showDocument(doc); status('Geometria salva. Versão '+doc.version);
  } catch (error) {status('Geometria rejeitada: '+error.message);}
}
async function reorder(direction) {
  if (!model.doc || !model.selection) return;
  try {
    const doc = await api('/v1/studio/documents/'+encodeURIComponent(model.doc.document_id)+'/order',
      {method:'POST',payload:{expected_version:model.doc.version,page_id:model.pageId,
        layer_id:model.selection.id,direction}});
    showDocument(doc);status('Ordem das camadas salva. Versão '+doc.version);
  } catch(error) {status('Ordem não alterada: '+error.message);}
}

async function insertImage() {
  const file=$('file').files?.[0];
  if (!file || file.type!=='image/png' || file.size>524288 || !$('rights').checked) {
    status('Escolha PNG de até 512 KiB e confirme o direito de uso.');return;
  }
  try {
    const data=await new Promise((resolve,reject)=>{
      const reader=new FileReader();
      reader.onload=()=>resolve(String(reader.result).split(',')[1]);
      reader.onerror=reject;reader.readAsDataURL(file);
    });
    const asset=await api('/v1/studio/assets/png',{method:'POST',
      payload:{data_base64:data,rights_attested:true}});
    // Preserve the intrinsic aspect ratio and initially place the asset below CTA.
    const availableWidth=Math.max(1,model.doc.canvas.width-140);
    const scale=Math.min(1,availableWidth/asset.width,160/asset.height);
    const imageWidth=Math.max(1,Math.round(asset.width*scale));
    const imageHeight=Math.max(1,Math.round(asset.height*scale));
    const initialX=Math.floor((model.doc.canvas.width-imageWidth)/2);
    const initialY=Math.max(0,model.doc.canvas.height-imageHeight-20);
    const doc=await api('/v1/studio/documents/'+encodeURIComponent(model.doc.document_id)+'/image-layers',
      {method:'POST',payload:{page_id:model.pageId,
        layer_id:'image.'+crypto.randomUUID().replaceAll('-','').slice(0,14),
        asset_id:asset.asset_id,expected_version:model.doc.version,
        x:initialX,y:initialY,w:imageWidth,h:imageHeight}});
    showDocument(doc);$('file').value='';$('rights').checked=false;controls();
    status('Imagem validada e inserida. Hash SHA-256: '+asset.sha256.slice(0,12)+'…');
  }catch(error){status('Não foi possível salvar a imagem: '+error.message);}
}
async function exportSelection(archive=false) {
  if(!model.doc)return;
  if(model.pendingText && !(await flushText())) {
    status('Salve o texto pendente antes de exportar.');return;
  }
  const doc=structuredClone(model.doc),pageId=model.pageId;
  const pages=archive?doc.pages:doc.pages.filter(p=>p.id===pageId);
  const ids=[...new Set(pages.flatMap(p=>p.layers.filter(l=>l.kind==='image').map(l=>l.asset_id)))];
  const fmt=$('export-format').value;
  const buttons=['export','export-zip'].map($);
  buttons.forEach(b=>b.disabled=true);
  $('export-progress').textContent='Preparando '+pages.length+' página(s) da versão '+doc.version;
  try {
    await Promise.all(ids.map(bitmapFor));
    const result=await StoneExport.exportDocument(doc,pageId,model.bitmaps,fmt,archive);
    const url=URL.createObjectURL(result.blob),link=document.createElement('a');
    link.href=url;link.download=result.filename;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
    $('export-progress').textContent=result.manifest.pages.length+' arquivo(s) gerado(s)';
    status('Prévia RASCUNHO exportada com hashes. Não há aprovação de publicação.');
  }catch(error){status('Exportação bloqueada: '+error.message);}
  finally{controls();}
}
async function previewProposal() {
  if(!model.doc || model.selection?.kind!=='text')return;
  if(model.pendingText && !(await flushText()))return;
  const proposal={expected_version:model.doc.version,page_id:model.pageId,
    layer_id:model.selection.id,text:$('proposal-text').value,origin:'operator'};
  try {
    const preview=await api(docPath()+'/edit-proposals/preview',{method:'POST',payload:proposal});
    model.proposal={...proposal,preview_sha256:preview.preview_sha256};
    $('confirm-proposal').checked=false;
    $('proposal-preview').textContent=preview.changes.map(c=>c.path+' : '+JSON.stringify(c.before)+' → '+JSON.stringify(c.after)).join('\n');
    status('Proposta em prévia. Nenhuma edição foi aplicada.');controls();
  }catch(error){model.proposal=null;status('Prévia rejeitada: '+error.message);controls();}
}
async function applyProposal() {
  if(!model.proposal || !$('confirm-proposal').checked)return;
  try {
    const doc=await api(docPath()+'/edit-proposals/apply',{method:'POST',
      payload:{...model.proposal,operator_confirmed:true}});
    showDocument(doc);status('Patch confirmado e salvo na versão '+doc.version);
  }catch(error){status('Patch não aplicado: '+error.message);}
}
async function createStoryboard() {
  if(!model.doc)return;
  if(model.pendingText && !(await flushText()))return;
  try {
    const identifier='story.'+crypto.randomUUID().replaceAll('-','').slice(0,18);
    const sb=await api('/v1/studio/storyboards',{method:'POST',payload:{
      storyboard_id:identifier,source_document_id:model.doc.document_id,
      platform_intent:$('storyboard-format').value}});
    timelineEditor?.setStoryboard(sb);
    $('storyboard-preview').textContent='Storyboard '+sb.storyboard_id+' · v'+sb.version+' · '+sb.scenes.length+' cena(s) · '+sb.clips.reduce((sum,c)=>sum+c.duration_ms,0)+' ms';
    status('Storyboard versionado criado; abra a timeline e vincule mídias autorizadas.');
  }catch(error){status('Storyboard rejeitado: '+error.message);}
}
const evidenceLab = initEvidenceLab({api,getToken:()=>model.token});
const timelineEditor = window.StoneTimelineE8?.initTimelineEditor({api, canWrite, getDocument:()=>model.doc, getToken:()=>model.token, status});
$('login').addEventListener('click',login);
$('logout').addEventListener('click',logout);
$('create').addEventListener('click',create);
$('open').addEventListener('click',open);
$('library-refresh').addEventListener('click',()=>loadLibrary());
$('library-next').addEventListener('click',()=>loadLibrary(true));
$('save-text').addEventListener('click',saveText);
// Save edited text on blur as well as explicit Save, without silently overwriting
// concurrent edits: the version check in the server remains authoritative.
$('layer-text').addEventListener('input', trackTextInput);
$('layer-text').addEventListener('blur',()=>{if(model.pendingText)void flushText();});
document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState==='hidden' && model.pendingText)void flushText();
});
$('duplicate-page').addEventListener('click',duplicatePage);
$('delete-page').addEventListener('click',deletePage);
$('page-left').addEventListener('click',()=>reorderPage(model.doc.pages.findIndex(p=>p.id===model.pageId)-1));
$('page-right').addEventListener('click',()=>reorderPage(model.doc.pages.findIndex(p=>p.id===model.pageId)+1));
$('undo').addEventListener('click',()=>restoreRevision('undo'));
$('redo').addEventListener('click',()=>restoreRevision('redo'));
$('version-diff').addEventListener('click',async()=>{
  if (!model.doc)return;
  const left=Number($('diff-from').value),right=Number($('diff-to').value);
  if (!Number.isInteger(left)||left<1||!Number.isInteger(right)||right<1)return;
  try {
    const diff=await api(docPath()+'/versions/diff?from_version='+left+'&to_version='+right);
    const paths=diff.changes.map(c=>c.path+' : '+JSON.stringify(c.before)+' → '+JSON.stringify(c.after));
    $('diff-result').textContent=paths.join('\n')||'Nenhuma diferença';
  }catch(error){status('Falha ao comparar versões: '+error.message);}
});
$('save-geometry').addEventListener('click',applyGeometry);
$('bring-forward').addEventListener('click',()=>reorder('forward'));
$('send-backward').addEventListener('click',()=>reorder('backward'));
$('file').addEventListener('change',controls);
$('rights').addEventListener('change',controls);
$('insert-image').addEventListener('click',insertImage);
$('preview-proposal').addEventListener('click',previewProposal);
$('proposal-text').addEventListener('input',()=>{
  model.proposal=null;$('confirm-proposal').checked=false;controls();
});
$('confirm-proposal').addEventListener('change',controls);
$('apply-proposal').addEventListener('click',applyProposal);
$('storyboard-create').addEventListener('click',createStoryboard);
$('export').addEventListener('click',()=>exportSelection(false));
$('export-zip').addEventListener('click',()=>exportSelection(true));
controls();draw();
