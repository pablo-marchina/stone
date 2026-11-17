import { FIELDS, STATES } from './evidence_lab.mjs?v=a01-rubric-2';
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
const RUBRIC_REASONS={
  NO_MATCHING_STORED_BASELINE:'Não há avaliação histórica correspondente ao registro atual.',
  NO_STORED_FIELD_EVIDENCE:'Não há evidência registrada para este campo.',
  BASELINE_NOT_OBSERVABLE:'O método original não conseguiu observar este atributo.',
  BASELINE_NOT_APPLICABLE:'Marcado como não aplicável no registro original.',
  STORED_METADATA_MATCH:'Valor registrado coincide com o metadado atual.',
  HISTORICAL_LEXICAL_CANDIDATE:'Resultado lexical histórico, sem revalidação semântica.',
  STORED_ASSERTION_WITHHELD:'Resultado não exibido: fora do escopo ou vínculo inconsistente.',
  INCONSISTENT_CTA_PAIR:'Presença e tipo de CTA não possuem suporte consistente.'
};
export function rubricContractStatus(rubric){
  if(!rubric)return 'missing';
  if(rubric.schema_version!=='external-stored-rubric-read.v1'||rubric.field_count!==20||
    !rubric.fields||Object.keys(rubric.fields).length!==20||
    !Object.keys(FIELDS).every(k=>rubric.fields[k]&&Object.hasOwn(STATES,rubric.fields[k].state))||
    !rubric.state_counts||!Object.keys(STATES).every(k=>Number.isInteger(rubric.state_counts[k])&&rubric.state_counts[k]>=0)||
    Object.keys(STATES).some(k=>rubric.state_counts[k]!==Object.values(rubric.fields).filter(f=>f.state===k).length)||
    rubric.canonical!==false)return 'incompatible';
  return 'ready';
}
export function rubricRows(rubric){
  return Object.entries(FIELDS).map(([key,label])=>{
    const cell=rubric.fields[key];
    return {key,label,state:STATES[cell.state]||cell.state,
      value:cell.value==null?'—':typeof cell.value==='boolean'?(cell.value?'Sim':'Não'):String(cell.value),
      reason:RUBRIC_REASONS[cell.reason]||'Consultar o estado técnico.',
      modality:({metadata:'Metadados',caption:'Legenda'})[cell.modality]||'—'};
  });
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
  function renderRubric(rubric){
    const section=el('section',undefined,'inventory-rubric');
    section.append(el('h4','Evidence Studio · Rubrica histórica'),
      el('p','Avaliações preliminares já armazenadas. Não são rótulos validados; nenhuma inferência nova ou revisão científica foi executada.','inventory-hint'));
    const counts=el('div',undefined,'inventory-rubric-counts');
    for(const [key,label] of Object.entries(STATES))counts.append(el('span',label+': '+number(rubric.state_counts[key])));
    section.append(counts,el('p',rubric.assessment_id?'Versão: '+rubric.model_version+' · '+date(rubric.recorded_at):'Nenhuma avaliação histórica compatível.','inventory-hint'));
    const table=el('table'),head=el('thead'),header=el('tr'),body=el('tbody');
    for(const label of ['Campo','Estado','Valor','Origem','Justificativa']){const th=el('th',label);th.scope='col';header.append(th);}
    head.append(header);table.append(head,body);
    for(const cell of rubricRows(rubric)){const tr=el('tr');for(const v of [cell.label,cell.state,cell.value,cell.modality,cell.reason])tr.append(el('td',v));body.append(tr);}
    const scroll=el('div',undefined,'table-scroll');scroll.append(table);section.append(scroll);
    return section;
  }
  function renderReplay(replay){
    const section=el('section',undefined,'inventory-rubric');
    section.append(el('h4','Evidence Studio · Análise fundamentada de legendas'),
      el('p','Relatórios experimentais revalidados; separados da rubrica histórica. Não constituem classificação científica.','inventory-hint'));
    const explanations={disabled:'Relatórios locais ainda não configurados para esta sessão.',
      outside_report_population:'Publicação fora da população dos relatórios (Reels e carrosséis com legenda elegível).',
      scope_blocked:'Escopo de pesquisa indisponível, revogado ou ingestão ativa.',
      stale_row:'Legenda ou snapshot mudou após a reauditoria. Resultado retido.'};
    if(replay?.status!=='ready'){
      section.append(el('p',explanations[replay?.status]||'Análise indisponível nesta versão da API.','inventory-hint'));return section;
    }
    const tiers={grounded_positive:'Candidato positivo fundamentado',semantic_consensus_only:'Somente consenso semântico',
      single_model_or_lexical_signal:'Sinal lexical ou de um modelo',unresolved:'Indeterminado',grounded_negative:'Candidato negativo fundamentado'};
    const dl=el('dl',undefined,'inventory-detail-grid');
    line(dl,'Público MPE',tiers[replay.audience_tier]||'Indeterminado');
    line(dl,'Caracteres da legenda',number(replay.caption_characters));
    line(dl,'População reauditorada',number(replay.population));
    line(dl,'Reauditoria',date(replay.reaudited_at));
    section.append(dl);
    const table=el('table'),head=el('thead'),header=el('tr'),body=el('tbody');
    for(const name of ['Campo','Estado','Valor','Âncoras lexicais'])header.append(el('th',name));
    head.append(header);table.append(head,body);
    for(const [key,cell] of Object.entries(replay.fields)){
      const tr=el('tr');
      for(const v of [FIELDS[key]||key,STATES[cell.state]||cell.state,
        cell.value===null?'—':cell.claim_only?'Alegação textual identificada':cell.value,number(cell.evidence_span_count)])tr.append(el('td',v));
      body.append(tr);
    }
    const scroll=el('div',undefined,'table-scroll');scroll.append(table);section.append(scroll,
      el('p','Abstenção não significa ausência. Alegações textuais não comprovam fatos. Predições salvas não foram reexecutadas nem verificadas independentemente.','inventory-hint'));
    const technical=el('details');technical.append(el('summary','Proveniência técnica'),el('pre',JSON.stringify({
      manifest_sha256:replay.manifest_sha256,audience_report_sha256:replay.audience_report_sha256,
      caption_sha256:replay.caption_sha256,snapshot_id:replay.snapshot_id,model_revision:replay.model_revision,
      model_weights_sha256:replay.model_weights_sha256,field_reports:Object.fromEntries(Object.entries(replay.fields).map(([k,v])=>[k,v.report_sha256]))
    },null,2)));
    section.append(technical);
    return section;
  }
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
      const rubricStatus=rubricContractStatus(r.stored_rubric);
      if(rubricStatus==='ready'){
        $('inventory-detail').append(renderRubric(r.stored_rubric));
      }else{
        const section=el('section',undefined,'inventory-rubric');
        section.append(el('h4','Evidence Studio · Rubrica histórica'),
          el('p',rubricStatus==='missing'
            ?'A API em execução não retornou a rubrica. Atualize o repositório, reinicie o servidor e recarregue a página.'
            :'A resposta da rubrica não corresponde ao contrato esperado. Consulte o diagnóstico antes de utilizar os resultados.',
            'inventory-hint'));
        $('inventory-detail').append(section);
      }
      $('inventory-detail').append(renderReplay(r.caption_replay));
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
