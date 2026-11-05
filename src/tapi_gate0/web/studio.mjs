// C2: plain browser canvas editor. No paid dependencies, no third-party URLs.
// The only source of truth is the authenticated DesignDocument persisted server-side.
const $ = id => document.getElementById(id);
const model = {
  token: null, principal: null, doc: null, selection: null, drag: null,
  preview: null, bitmaps: new Map(), pendingImages: new Map(),
  pageId: null, dragPageId: null, undoStack: [], redoStack: [],
};
const canvas = $('canvas');
const ctx = canvas.getContext('2d');

function status(message) { $('status').textContent = message; }
function canWrite() { return ['admin','editor'].includes(model.principal?.role); }
function controls() {
  const logged = !!model.token, editing = logged && !!model.doc && canWrite();
  $('login').disabled = logged;
  $('logout').disabled = !logged;
  $('create').disabled = !logged || !canWrite();
  $('open').disabled = !logged;
  $('save-text').disabled = !editing || model.selection?.kind !== 'text';
  $('insert-image').disabled = !editing || !$('file').files?.length || !$('rights').checked;
  $('file').disabled = !editing;
  $('rights').disabled = !editing;
  $('export').disabled = !logged || !model.doc;
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
  if (model.token) headers.Authorization = 'Bearer ' + model.token;
  if (payload !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { method, headers,
    body: payload === undefined ? undefined : JSON.stringify(payload),
    cache:'no-store' });
  if (!response.ok) throw new Error('HTTP ' + response.status + ' — ' + path);
  return response.json();
}
function reset() {
  model.token = null; model.principal = null; model.doc = null;
  model.selection = null; model.drag = null; model.preview = null;
  model.pageId=null;model.dragPageId=null;model.undoStack=[];model.redoStack=[];
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
    controls();
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
  model.doc = doc; model.selection = null; model.drag = null;
  model.preview = null;
  if (!doc.pages.some(page=>page.id===model.pageId)) model.pageId=doc.pages[0].id;
  $('revision').textContent = doc.document_id + ' · versão ' + doc.version;
  $('selected').textContent = 'Clique em uma camada';
  $('layer-text').value = '';
  renderPages();controls();draw();
}
function activePage() {return model.doc?.pages.find(page=>page.id===model.pageId) || null;}
function selectPage(pageId) {
  if (!model.doc?.pages.some(page=>page.id===pageId)) return;
  model.pageId=pageId;model.selection=null;model.drag=null;model.preview=null;
  $('selected').textContent='Clique em uma camada';$('layer-text').value='';
  renderPages();controls();draw();
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
    button.addEventListener('click',()=>selectPage(page.id));
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
  try {
    const spec = {spec_id:'spec.'+crypto.randomUUID().replaceAll('-','').slice(0,18),
      tenant_id:model.principal.tenant_id,
      objective:$('objective').value.trim(),headline:$('headline').value.trim(),
      body:$('body-text').value.trim(),cta:$('cta').value.trim(),
      platform_intent:$('format').value,reference_content_ids:[]};
    const doc = await api('/v1/studio/documents', {method:'POST',
      payload:{document_id:$('document-id').value.trim(),spec}});
    showDocument(doc,{resetHistory:true}); status('Rascunho criado e persistido. Versão 1.');
  } catch(error){status('Não foi possível criar: '+error.message);}
}
async function open() {
  try {
    const doc = await api('/v1/studio/documents/'+encodeURIComponent($('document-id').value.trim()));
    showDocument(doc,{resetHistory:true});status('Rascunho aberto do banco.');
  } catch(error){status('Não foi possível abrir: '+error.message);}
}
function layerList() { return activePage()?.layers || []; }
function selectLayer(layer) {
  model.selection = layer || null;
  $('selected').textContent = layer ? layer.id+' · '+layer.kind : 'Nenhuma';
  $('layer-text').value = layer?.kind === 'text' ? layer.text : '';
  for (const [control, field] of [['geom-x','x'],['geom-y','y'],['geom-w','w'],['geom-h','h']])
    $(control).value = layer ? String(layer[field]) : '';
  controls(); draw();
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
  const w=doc?.canvas.width||1080, h=doc?.canvas.height||1350;
  if (canvas.width!==w) canvas.width=w;
  if (canvas.height!==h) canvas.height=h;
  ctx.fillStyle=doc?.canvas.background||'#FFFFFF';ctx.fillRect(0,0,w,h);
  for (const layer of layerList()) {
    const delta = model.preview?.id===layer.id ? model.preview : {dx:0,dy:0};
    const x=layer.x+delta.dx, y=layer.y+delta.dy;
    if (layer.kind==='text') {
      ctx.fillStyle=layer.style.color;
      ctx.textBaseline='top'; ctx.font=layer.style.font_size+'px sans-serif';
      wrapText(layer.text,x,y,layer.w,layer.style.font_size*1.2,layer.h);
    } else if (layer.kind==='image') {
      if (!model.bitmaps.has(layer.asset_id)) {
        void bitmapFor(layer.asset_id).catch(e=>status(e.message));
        ctx.fillStyle='#E6EFE9';ctx.fillRect(x,y,layer.w,layer.h);
      } else {
        ctx.drawImage(model.bitmaps.get(layer.asset_id),x,y,layer.w,layer.h);
      }
    }
    if (model.selection?.id===layer.id) {
      ctx.save(); ctx.lineWidth=3;ctx.strokeStyle='#158654';
      ctx.setLineDash([14,8]);ctx.strokeRect(x,y,layer.w,layer.h);
      ctx.restore();
    }
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
async function saveText() {
  if(model.selection?.kind!=='text') return;
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
    // The draft template reserves space beneath the CTA. Place new images
    // there at their intrinsic aspect ratio instead of obscuring the headline.
    // The operator can subsequently resize or drag them anywhere on canvas.
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
async function exportPNG() {
  if(!model.doc)return;
  try {
    const ids=[...new Set(layerList().filter(l=>l.kind==='image').map(l=>l.asset_id))];
    await Promise.all(ids.map(bitmapFor));
    // Render without selection outlines or UI handles.
    const current=model.selection; model.selection=null;draw();
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    model.selection=current;draw();
    if(!blob)throw new Error('Falha ao renderizar PNG');
    const url=URL.createObjectURL(blob);const link=document.createElement('a');
    link.href=url;link.download=model.doc.document_id+'-v'+model.doc.version+'.png';
    link.click();setTimeout(()=>URL.revokeObjectURL(url),5000);
    status('PNG exportado localmente. Documento persistido não foi modificado.');
  }catch(error){status('Exportação bloqueada: '+error.message);}
}
$('login').addEventListener('click',login);
$('logout').addEventListener('click',logout);
$('create').addEventListener('click',create);
$('open').addEventListener('click',open);
$('save-text').addEventListener('click',saveText);
// Also persist text on blur (the server version check prevents silent overwrites).
$('layer-text').addEventListener('change',()=>{
  if (canWrite() && model.selection?.kind==='text' &&
      $('layer-text').value!==model.selection.text) void saveText();
});
$('duplicate-page').addEventListener('click',duplicatePage);
$('delete-page').addEventListener('click',deletePage);
$('page-left').addEventListener('click',()=>reorderPage(model.doc.pages.findIndex(p=>p.id===model.pageId)-1));
$('page-right').addEventListener('click',()=>reorderPage(model.doc.pages.findIndex(p=>p.id===model.pageId)+1));
$('undo').addEventListener('click',()=>restoreRevision('undo'));
$('redo').addEventListener('click',()=>restoreRevision('redo'));
$('save-geometry').addEventListener('click',applyGeometry);
$('bring-forward').addEventListener('click',()=>reorder('forward'));
$('send-backward').addEventListener('click',()=>reorder('backward'));
$('file').addEventListener('change',controls);
$('rights').addEventListener('change',controls);
$('insert-image').addEventListener('click',insertImage);
$('export').addEventListener('click',exportPNG);
controls();draw();
