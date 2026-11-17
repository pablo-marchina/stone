// A01.3: private technical inventory, no ranking, media, caption export or admission.
const ROOT='/v1/corpus/inventory';
const FORMATS={reels:'Reels',carrossel:'Carrossel',imagem:'Imagem',short:'Short'};
const SECTORS={commerce:'Comércio',food:'Alimentação',services:'Serviços',beauty:'Beleza',other:'Outros'};
const number=n=>n===null||n===undefined?'—':new Intl.NumberFormat('pt-BR').format(n);
const date=v=>{const d=new Date(v);return !v||Number.isNaN(d.valueOf())?'—':new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short'}).format(d);};
export function inventoryQuery(filters,offset=0){
  const p=new URLSearchParams({limit:'25',offset:String(offset)});
  for(const key of ['search','platform','media_type','sector','source_account_id']){
    const value=String(filters[key]??'').trim();
    if(value)p.set(key,value);
  }
  return ROOT+'?'+p.toString();
}
export function snapshotNotice(item){
  if(!item.latest_snapshot)return 'Métricas indisponíveis';
  if(item.latest_snapshot_timestamp_tie)return 'Horários iguais: desempate por ID, sem garantia de ordem cronológica';
  return 'Última observação disponível';
}
export function initInventory({api,getPrincipal}){
  const $=id=>document.getElementById(id);
  let page=null,active=null,filters={},epoch=0,detailEpoch=0;
  const permitted=()=>['admin','researcher','service'].includes(getPrincipal()?.role);
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;};
  const status=s=>$('inventory-status').textContent=s;
  function clearDetail(){
    detailEpoch++;active=null;$('inventory-detail').replaceChildren();
    $('inventory-detail-status').textContent='';
  }
  function reset(){
    epoch++;page=null;filters={};clearDetail();
    $('inventory-rows').replaceChildren();
    $('inventory-count').textContent='—';
    $('inventory-prev').disabled=$('inventory-next').disabled=true;
    $('inventory-submit').disabled=!permitted();
    $('inventory-form').reset();
    status(permitted()?'Selecione os filtros e consulte o inventário.':'Consulta disponível aos perfis de pesquisa autorizados.');
  }
  function row(item){
    const tr=el('tr'),m=item.latest_snapshot;
    for(const value of [item.handle,item.platform,FORMATS[item.media_type]||item.media_type,
      date(item.published_at),number(m?.likes),number(m?.comments),number(m?.follower_count),
      item.age_at_least_14_days?'≥ 14 dias':'Recente'])tr.append(el('td',value));
    const td=el('td'),btn=el('button','Detalhes','button outline inventory-detail-btn');
    btn.type='button';btn.addEventListener('click',()=>void detail(item.content_id,0));
    td.append(btn);tr.append(td);return tr;
  }
  async function load(offset=0){
    if(!permitted())return;
    const gen=++epoch;page=null;clearDetail();
    $('inventory-submit').disabled=true;
    $('inventory-prev').disabled=$('inventory-next').disabled=true;
    $('inventory-rows').replaceChildren();$('inventory-count').textContent='—';
    status('Consultando metadados locais…');
    try{
      const r=await api(inventoryQuery(filters,offset));
      if(gen!==epoch||!permitted())return;
      page=r;$('inventory-count').textContent=number(r.total_filtered)+' de '+number(r.total_visible_before_filters)+' registros visíveis';
      $('inventory-rows').replaceChildren(...r.items.map(row));
      if(!r.items.length){const tr=el('tr'),td=el('td','Nenhum registro visível para os filtros atuais.','empty-cell');td.colSpan=9;tr.append(td);$('inventory-rows').append(tr);}
      $('inventory-prev').disabled=r.offset===0;
      $('inventory-next').disabled=r.next_offset===null;
      status('Consulta: '+date(r.as_of)+' · Exclusões após vínculo: '+number(r.excluded_joined_records)+'. Inventário atual, não uma amostra científica.');
    }catch(e){if(gen===epoch&&permitted())status(e.message);}
    finally{if(gen===epoch)$('inventory-submit').disabled=!permitted();}
  }
  function line(dl,label,value){dl.append(el('dt',label),el('dd',value));}
  async function detail(id,offset){
    if(!permitted())return;
    const gen=++detailEpoch;active=id;$('inventory-detail').replaceChildren();
    $('inventory-detail-status').textContent='Consultando detalhes…';
    try{
      const r=await api(ROOT+'/'+encodeURIComponent(id)+'?snapshot_limit=25&snapshot_offset='+offset);
      if(gen!==detailEpoch||active!==id||!permitted())return;
      const item=r.item,dl=el('dl',undefined,'inventory-detail-grid');
      for(const [k,v] of [
        ['Perfil',item.handle],['Formato',FORMATS[item.media_type]||item.media_type],
        ['Publicação',date(item.published_at)],['Setor de cadastro',SECTORS[item.operator_sector]||item.operator_sector],
        ['ID de origem',item.source_item_id],['ID interno',item.content_id],
        ['Grant vigente até',date(item.grant_expires_at)],['Legenda',item.caption_available?'Disponível no banco; texto não exibido':'Indisponível'],
        ['Métricas',snapshotNotice(item)],['Snapshots válidos',number(item.valid_snapshot_count)],
        ['Qualidade do denominador (última ingestão)',item.denominator_quality_latest_ingestion],
        ['Admissão científica','Não avaliada neste serviço'],['Mídia','Processamento e player bloqueados']
      ])line(dl,k,v);
      const table=el('table'),thead=el('thead'),tr=el('tr'),tbody=el('tbody');
      for(const name of ['Observado em','Seguidores medidos em','Curtidas','Comentários','Seguidores','Views'])tr.append(el('th',name));
      thead.append(tr);table.append(thead,tbody);
      for(const m of r.snapshots){const row=el('tr');for(const v of [date(m.observed_at),date(m.followers_measured_at),number(m.likes),number(m.comments),number(m.follower_count),number(m.views)])row.append(el('td',v));tbody.append(row);}
      const scroll=el('div',undefined,'table-scroll');scroll.append(table);
      const controls=el('div',undefined,'inventory-controls');
      const prev=el('button','Snapshots anteriores','button outline'),next=el('button','Próximos snapshots','button outline');
      prev.type=next.type='button';prev.disabled=r.snapshot_offset===0;next.disabled=r.next_snapshot_offset===null;
      prev.addEventListener('click',()=>void detail(id,Math.max(0,r.snapshot_offset-r.snapshot_limit)));
      next.addEventListener('click',()=>void detail(id,r.next_snapshot_offset));
      controls.append(prev,next);
      $('inventory-detail').append(el('h4','Identidade e permissões'),dl,el('h4','Histórico de métricas'),scroll,controls);
      $('inventory-detail-status').textContent='Detalhes de '+item.handle+' · '+number(item.valid_snapshot_count)+' snapshots';
      $('inventory-detail-status').focus({preventScroll:false});
    }catch(e){if(gen===detailEpoch&&permitted())$('inventory-detail-status').textContent=e.message;}
  }
  $('inventory-form').addEventListener('submit',e=>{
    e.preventDefault();
    filters={search:$('inventory-search').value,platform:$('inventory-platform').value,
      media_type:$('inventory-format').value,sector:$('inventory-sector').value,
      source_account_id:$('inventory-account').value};
    void load();
  });
  $('inventory-prev').addEventListener('click',()=>{if(page)void load(Math.max(0,page.offset-page.limit));});
  $('inventory-next').addEventListener('click',()=>{if(page&&page.next_offset!==null)void load(page.next_offset);});
  reset();
  return {reset,load};
}
