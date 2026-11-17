// Read-only synthetic evidence explorer. No token persistence, media player,
// HTML from evidence, write operations or implicit promotion of candidates.
const STATES={candidate:'Candidato',measurement_only:'Medição',abstained:'Abstenção',not_assessed:'Não avaliado'};
const FIELDS={
  tipo_post:'Tipo de publicação',duracao_faixa:'Duração',formato_video:'Formato do vídeo',
  hook_primeiros_3s:'Abertura (0–3s)',tipo_hook:'Tipo de hook',forca_hook_0a10:'Força do hook',
  tema_principal:'Tema principal',tem_rosto:'Presença de rosto',criador_e_empreendedor_real:'Criador empreendedor',
  prova_social:'Prova social',texto_na_tela:'Texto na tela',legenda_tamanho:'Tamanho da legenda',
  ritmo_cortes_0a10:'Ritmo de cortes',tom:'Tom',usa_linguagem_regional:'Linguagem regional',
  clareza_mensagem_0a10:'Clareza',tem_cta:'Presença de CTA',tipo_cta:'Tipo de CTA',
  oferta_ou_beneficio_explicito:'Oferta ou benefício',elementos_top5:'Elementos top 5'
};
const MODALITIES={caption:'Legenda',audio:'Áudio',ocr:'OCR',vlm:'VLM'};
const $=id=>document.getElementById(id);
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
    for(const id of ['evidence-metrics','evidence-fields','evidence-fragments','evidence-visual','evidence-ablation','evidence-provenance'])
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
    $('evidence-provenance').textContent='Relatório SHA-256: '+data.report_sha256+
      '\nGate de composição: '+(data.engineering_gate_passed?'PASS':'FAIL')+
      ' · Gate do VLM: '+(data.upstream_vlm_gate_passed?'PASS':'FAIL')+
      '\nDados sintéticos · não canônicos · sem aprovação científica ou de produção.';
    $('evidence-case').replaceChildren(...data.cases.map(c=>{
      const option=element('option',c.case_id);option.value=c.case_id;return option;
    }));
    $('evidence-ablation').replaceChildren(...armRows(data.ablation).map(r=>{
      const tr=element('tr');
      tr.append(element('th',r.arm),element('td',r.correct+'/'+r.expected),element('td',r.wrong));
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
      const item=element('details',undefined,'evidence-field');
      const head=element('summary');
      head.append(element('span',label),element('span',STATES[f.state],'evidence-state '+f.state));
      item.append(head);
      if(f.value!==null)item.append(element('p',typeof f.value==='boolean'?(f.value?'Sim':'Não'):JSON.stringify(f.value)));
      item.append(element('p',f.reason,'hint'));
      const payload={measurement:f.measurement,supports:f.supports,vetoes:f.vetoes};
      item.append(element('pre',JSON.stringify(payload,null,2),'version-diff'));
      children.push(item);
    }
    $('evidence-fields').replaceChildren(...children);
  }
  async function loadCase(){
    if(!summary||!getToken())return;
    const active=++epoch,token=getToken(),id=$('evidence-case').value;
    detail=null;busy=true;$('evidence-fields').replaceChildren();$('evidence-fragments').replaceChildren();$('evidence-visual').replaceChildren();controls();
    try{
      const data=await api('/v1/studio/evidence-lab/cases/'+encodeURIComponent(id));
      if(active!==epoch||token!==getToken())return;
      detail=data;renderFields();
      $('evidence-fragments').replaceChildren(...data.fragments.map(f=>{
        const d=element('details',undefined,'evidence-field');
        d.append(element('summary',MODALITIES[f.modality]||f.modality),
          element('p',f.text),element('pre',JSON.stringify({text_sha256:f.text_sha256,locator:f.locator,semantic_eligible:f.semantic_eligible},null,2),'version-diff'));
        return d;
      }));
      $('evidence-visual').replaceChildren(...data.visual_observations.map(v=>{
        const d=element('details',undefined,'evidence-field');
        d.append(element('summary','Frame '+v.timestamp_s+' s · '+(v.prediction?.scene||'Resposta inválida')),
          element('pre',JSON.stringify(v,null,2),'version-diff'));return d;
      }),element('pre',JSON.stringify(data.source_rights,null,2),'version-diff'));
      status('Ativo '+data.case_id+' · '+data.media_sha256+' · '+Object.keys(data.field_evidence).length+' campos. Reprodução indisponível.');
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
