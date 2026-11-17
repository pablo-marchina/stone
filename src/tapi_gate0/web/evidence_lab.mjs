// Read-only synthetic evidence explorer. No token persistence, media player,
// HTML from evidence, write operations or implicit promotion of candidates.
export const STATES={candidate:'Candidato',measurement_only:'Medição',abstained:'Abstenção',not_assessed:'Não avaliado'};
export const FIELDS={
  tipo_post:'Tipo de publicação',duracao_faixa:'Duração',formato_video:'Formato do vídeo',
  hook_primeiros_3s:'Abertura (0–3s)',tipo_hook:'Tipo de hook',forca_hook_0a10:'Força do hook',
  tema_principal:'Tema principal',tem_rosto:'Presença de rosto',criador_e_empreendedor_real:'Criador empreendedor',
  prova_social:'Prova social',texto_na_tela:'Texto na tela',legenda_tamanho:'Tamanho da legenda',
  ritmo_cortes_0a10:'Ritmo de cortes',tom:'Tom',usa_linguagem_regional:'Linguagem regional',
  clareza_mensagem_0a10:'Clareza',tem_cta:'Presença de CTA',tipo_cta:'Tipo de CTA',
  oferta_ou_beneficio_explicito:'Oferta ou benefício',elementos_top5:'Elementos top 5'
};
const MODALITIES={caption:'Legenda',audio:'Áudio',ocr:'OCR',vlm:'VLM'};
const CASE_LABELS={caption_only:'Somente legenda',audio_only:'Somente áudio',ocr_only:'Somente texto na tela',agreement:'Concordância entre modalidades',conflict:'CTAs conflitantes',negative:'Caso negativo',audio_topic:'Tema identificado no áudio'};
const SCENES={blank:'Fundo uniforme',geometry:'Figuras geométricas',text_card:'Texto visível',uncertain:'Indeterminado'};
const REASONS={
  DURATION_SECONDS_NOT_APPROVED_BIN:'Duração medida; faixa da rubrica ainda não atribuída.',
  CHARACTER_COUNT_NOT_APPROVED_BIN:'Contagem de caracteres; categoria ainda não atribuída.',
  OPENING_OBSERVATIONS_NOT_SEMANTIC_HOOK:'Amostras da abertura, sem avaliação semântica do hook.',
  TRANSITION_COUNT_NOT_CALIBRATED_SCORE:'Transições candidatas, sem nota de 0 a 10.',
  UNIQUE_LEXICAL_ANCHOR_ACROSS_AVAILABLE_MODALITIES:'Um único tema sustentado pelas evidências disponíveis.',
  DIRECTED_REQUEST_V2:'Solicitação dirigida ao público identificada no mesmo fragmento.',
  NO_UNAMBIGUOUS_DIRECTED_REQUEST:'Nenhum pedido inequívoco identificado; pode haver conflito ou falta de evidência.',
  OCR_POSITIVE_WITH_OPTIONAL_VLM_SUPPORT:'Texto detectado pelo OCR, com apoio visual quando disponível.',
  NO_UNCONFLICTED_POSITIVE_SCREEN_EVIDENCE:'Não há evidência positiva suficiente sem conflito. Não significa ausência de texto.',
  NO_ANCHOR:'Nenhuma âncora textual suficiente.',
  CONTEXT_VETO:'Contexto incompatível com uma classificação segura.',
  CONFLICTING_ANCHORS:'Evidências apontam para classificações diferentes.',
  metadata:'Requer metadados do conteúdo.',
  'authorized video or multimodal evidence':'Requer vídeo autorizado ou evidência multimodal suficiente.',
  'authorized opening segment and semantic evidence':'Requer segmento inicial autorizado e evidência semântica.',
  'authorized opening segment and calibrated scoring':'Requer segmento inicial autorizado e pontuação calibrada.',
  'authorized image or video':'Requer imagem ou vídeo autorizado.',
  'independent external proof':'Requer comprovação externa independente.',
  'reliable caption or authorized multimodal evidence':'Requer legenda confiável ou evidência multimodal autorizada.',
  'reliable semantic evidence':'Requer evidência semântica confiável.',
  'reliable linguistic evidence':'Requer evidência linguística confiável.',
  'calibrated semantic scoring':'Requer pontuação semântica calibrada.',
  'validated multimodal evidence and scoring':'Requer evidência multimodal validada e pontuação.'
};
export function fieldPresentation(key,field){
  const m=field.measurement;
  let value=field.value===null?'—':typeof field.value==='boolean'?(field.value?'Sim':'Não'):String(field.value);
  if(field.state==='measurement_only'&&m){
    if(key==='duracao_faixa')value=m.duration_s+' s';
    else if(key==='legenda_tamanho')value=m.characters+' caracteres';
    else if(key==='ritmo_cortes_0a10')value=m.count+' transições candidatas';
    else if(key==='hook_primeiros_3s')value=(m.opening_samples?.length??0)+' amostras · '+(m.audio_segments_overlapping_opening?.length??0)+' segmentos de áudio';
  }
  return {value,reason:REASONS[field.reason]||'Consulte a justificativa técnica para este estado.'};
}
export function evidenceExcerpt(support,fragments){
  const spans=support.directed?.spans||support.spans||support.rule?.evidence_spans||[];
  const matches=fragments.filter(f=>f.modality===support.modality&&f.text_sha256===support.text_sha256);
  if(matches.length!==1||!spans.length)return [];
  // Python offsets count Unicode code points, not JS UTF-16 code units.
  const chars=Array.from(matches[0].text);
  return spans.filter(s=>Number.isInteger(s.start)&&Number.isInteger(s.end)&&s.start>=0&&s.end>s.start&&s.end<=chars.length)
    .map(s=>chars.slice(s.start,s.end).join(''));
}
const $=id=>document.getElementById(id);
function technical(payload,label='Dados técnicos e proveniência'){
  const d=element('details',undefined,'evidence-technical');
  d.append(element('summary',label),element('pre',JSON.stringify(payload,null,2),'version-diff'));
  return d;
}
function element(tag,text,cls){
  const n=document.createElement(tag);
  if(text!==undefined)n.textContent=String(text);
  if(cls)n.className=cls;
  return n;
}
export function stateCounts(fields){
  const counts=Object.fromEntries(Object.keys(STATES).map(k=>[k,0]));
  for(const field of Object.values(fields)){
    if(!(field.state in STATES))throw Error('Estado desconhecido');
    counts[field.state]++;
  }
  return counts;
}
export function armRows(ablation){
  return Object.entries(ablation).map(([arm,fields])=>({
    arm:arm.split('+').map(m=>MODALITIES[m]||m).join(' + '),
    correct:Object.values(fields).reduce((n,f)=>n+f.correct_candidates,0),
    expected:Object.values(fields).reduce((n,f)=>n+f.expected_candidates,0),
    wrong:Object.values(fields).reduce((n,f)=>n+f.wrong_nonabstained,0)
  }));
}
export function initEvidenceLab({api,getToken}){
  if(!$('evidence-lab'))return null;
  let epoch=0,summary=null,detail=null,busy=false,wasLogged=false;
  const status=text=>{$('evidence-status').textContent=text;};
  function controls(){
    const logged=Boolean(getToken());
    $('evidence-login-link').hidden=logged;
    $('evidence-refresh').disabled=!logged||busy;
    $('evidence-case').disabled=!summary||busy||!logged;
    $('evidence-filter').disabled=!detail||!logged;
    if(logged&&!wasLogged&&!busy&&!summary)status('Sessão do Studio ativa. Clique em Consultar evidências.');
    wasLogged=logged;
  }
  function reset(){
    epoch++;summary=null;detail=null;busy=false;
    $('evidence-case').replaceChildren();
    for(const id of ['evidence-metrics','evidence-case-counts','evidence-fields','evidence-fragments','evidence-visual','evidence-ablation','evidence-provenance'])
      $(id).replaceChildren();
    status(getToken()?'Sessão do Studio ativa. Clique em Consultar evidências.':'Entre no Creative Studio para consultar as evidências sintéticas.');
    controls();
  }
  function renderSummary(data){
    const totals=Object.fromEntries(Object.keys(STATES).map(k=>[k,0]));
    for(const counts of Object.values(data.field_coverage))
      for(const [k,v] of Object.entries(counts))totals[k]+=v;
    $('evidence-metrics').replaceChildren(...Object.entries(totals).map(([k,v])=>{
      const card=element('div',undefined,'evidence-metric');
      card.append(element('strong',v),element('span',STATES[k]));return card;
    }));
    const gates=element('div',undefined,'evidence-gates');
    gates.append(element('span','Composição: '+(data.engineering_gate_passed?'PASS':'FAIL'),'evidence-state '+(data.engineering_gate_passed?'candidate':'abstained')),
      element('span','VLM: '+(data.upstream_vlm_gate_passed?'PASS':'FAIL'),'evidence-state '+(data.upstream_vlm_gate_passed?'candidate':'abstained')));
    $('evidence-provenance').replaceChildren(gates,element('p',data.cases.length+' conteúdos de teste; '+data.total_field_cells+' células da rubrica. Resultados experimentais, não canônicos.'),
      technical({report_sha256:data.report_sha256,source_report_sha256:data.source_report_sha256,visual_report_sha256:data.visual_report_sha256,policy_version:data.policy_version}));
    $('evidence-case').replaceChildren(...data.cases.map(c=>{
      const option=element('option',CASE_LABELS[c.case_id]||c.case_id);option.value=c.case_id;return option;
    }));
    $('evidence-ablation').replaceChildren(...armRows(data.ablation).map(r=>{
      const tr=element('tr');
      const heading=element('th',r.arm);heading.scope='row';
      tr.append(heading,element('td',r.correct+'/'+r.expected),element('td',r.wrong));
      return tr;
    }));
  }
  function renderFields(){
    if(!detail)return;
    const filter=$('evidence-filter').value;
    const children=[];
    for(const [key,label] of Object.entries(FIELDS)){
      const f=detail.field_evidence[key];
      if(filter!=='all'&&f.state!==filter)continue;
      const item=element('article',undefined,'evidence-field');
      const head=element('div',undefined,'evidence-field-heading');
      head.append(element('h4',label),element('span',STATES[f.state],'evidence-state '+f.state));
      const presentation=fieldPresentation(key,f);
      item.append(head,element('p',presentation.value,'evidence-value'),element('p',presentation.reason,'hint'));
      for(const support of f.supports||[]){
        const excerpts=evidenceExcerpt(support,detail.fragments);
        const words=support.words?.map(w=>w.text).join(' ');
        const when=support.timestamp_s??support.locator?.timestamp_s??support.locator?.start_s;
        const origin=element('div',undefined,'evidence-support');
        origin.append(element('strong',(MODALITIES[support.modality]||'Evidência')+(typeof when==='number'?' · '+when+' s':'')));
        for(const excerpt of excerpts)origin.append(element('blockquote',excerpt));
        if(words)origin.append(element('p',words));
        item.append(origin);
      }
      if(f.vetoes?.length)item.append(element('p',f.vetoes.length+' observações de veto ou conflito registradas.','evidence-warning'));
      item.append(technical({reason:f.reason,measurement:f.measurement,supports:f.supports,vetoes:f.vetoes,canonical:f.canonical}));
      children.push(item);
    }
    $('evidence-fields').replaceChildren(...(children.length?children:[element('p','Nenhum campo neste filtro.','hint')]));
  }
  async function loadCase(){
    if(!summary||!getToken())return;
    const active=++epoch,token=getToken(),id=$('evidence-case').value;
    detail=null;busy=true;$('evidence-case-counts').replaceChildren();$('evidence-fields').replaceChildren();$('evidence-fragments').replaceChildren();$('evidence-visual').replaceChildren();controls();
    try{
      const data=await api('/v1/studio/evidence-lab/cases/'+encodeURIComponent(id));
      if(active!==epoch||token!==getToken())return;
      detail=data;
      const counts=stateCounts(data.field_evidence);
      $('evidence-case-counts').textContent=Object.entries(counts).map(([k,v])=>v+' '+STATES[k].toLowerCase()).join(' · ');
      renderFields();
      $('evidence-fragments').replaceChildren(...data.fragments.map(f=>{
        const d=element('details',undefined,'evidence-field');
        d.append(element('summary',MODALITIES[f.modality]||f.modality),
          element('p',f.text),technical({text_sha256:f.text_sha256,locator:f.locator,semantic_eligible:f.semantic_eligible}));
        return d;
      }));
      $('evidence-visual').replaceChildren(...data.visual_observations.map(v=>{
        const d=element('details',undefined,'evidence-field');
        d.append(element('summary','Frame '+v.timestamp_s+' s · '+(SCENES[v.prediction?.scene]||'Resposta inválida')),
          technical(v));return d;
      }),element('p','Escopo: fixture autoral. Reprodução e processamento de mídia real não autorizados.','hint'),technical(data.source_rights,'Escopo técnico de direitos'));
      status((CASE_LABELS[data.case_id]||data.case_id)+' · '+Object.keys(data.field_evidence).length+' campos · Reprodução indisponível.');
      $('evidence-case-counts').append(technical({case_id:data.case_id,media_sha256:data.media_sha256},'Identidade técnica do conteúdo'));
    }catch(error){if(active===epoch&&token===getToken())status('Consulta indisponível: '+error.message);}
    finally{if(active===epoch){busy=false;controls();}}
  }
  async function load(){
    if(!getToken()||busy)return;
    reset();const active=++epoch,token=getToken();busy=true;controls();status('Consultando relatório local…');
    try{
      const data=await api('/v1/studio/evidence-lab');
      if(active!==epoch||token!==getToken())return;
      summary=data;renderSummary(data);busy=false;await loadCase();
    }catch(error){if(active===epoch&&token===getToken())status('Rubric Lab indisponível: '+error.message);}
    finally{if(active===epoch){busy=false;controls();}}
  }
  $('evidence-login-link').addEventListener('click',()=>{$('username').focus({preventScroll:true});});
  $('evidence-refresh').addEventListener('click',load);
  $('evidence-case').addEventListener('change',loadCase);
  $('evidence-filter').addEventListener('change',renderFields);
  reset();
  return {reset,controls,load};
}
