// Read-only exploratory rankings, same dashboard session as inventory.
const BASE='/v1/corpus/inventory/ranking';
const labels={technical_all:'Técnico reauditorado',semantic_exploratory:'Semântico exploratório'};
const tiers={grounded_positive:'Positivo fundamentado',semantic_consensus_only:'Consenso semântico',
  single_model_or_lexical_signal:'Sinal lexical/modelo',unresolved:'Indeterminado',grounded_negative:'Negativo fundamentado'};
const fieldLabels={tema_principal:'Tema',tipo_cta:'CTA',prova_social:'Prova social',oferta_ou_beneficio_explicito:'Oferta/benefício'};
const num=v=>v==null?'—':new Intl.NumberFormat('pt-BR',{maximumFractionDigits:6}).format(v);
const pct=v=>v==null?'—':num(v)+'%';
export function rankingQuery(cohort,topOnly,offset=0){
  if(!Object.hasOwn(labels,cohort)||typeof topOnly!=='boolean'||!Number.isInteger(offset)||offset<0)throw Error('Filtro de ranking inválido.');
  return BASE+'?'+new URLSearchParams({cohort,top_only:String(topOnly),offset:String(offset),limit:'25'});
}
export function initRanking({api,getPrincipal,openDetail}){
  const $=id=>document.getElementById(id);
  let epoch=0,page=null,selection=null;
  const permitted=()=>['admin','researcher','service'].includes(getPrincipal()?.role);
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;};
  const status=s=>$('ranking-status').textContent=s;
  function reset(){
    epoch++;page=null;selection=null;
    $('ranking-rows').replaceChildren();$('ranking-summary').replaceChildren();$('ranking-contrasts').replaceChildren();
    $('ranking-prev').disabled=$('ranking-next').disabled=true;
    $('ranking-submit').disabled=!permitted();$('ranking-form').reset();
    status(permitted()?'Selecione a população e consulte o ranking.':'Consulta restrita aos perfis de pesquisa.');
  }
  function render(r){
    const group=r.cohorts[r.cohort],s=r.sensitivity;
    const summary=$('ranking-summary');
    for(const [label,value] of [['Publicações',num(group.posts)],['Perfis',num(group.profiles)],
      ['Mediana ER',pct(group.median_er_percent)],['Top 10%',num(group.top_decile_count)],
      ['Mediana ER do top',pct(group.top_decile_median_er_percent)],['Jaccard global × intraperfil',num(s.top_jaccard)]])
      summary.append(el('div',label+': '+value,'ranking-stat'));
    summary.append(el('p','Intraperfil: '+num(s.within_profile_supported_posts)+' publicações em '+num(s.within_profile_supported_profiles)+' perfis com pelo menos '+num(s.within_profile_min_posts)+' posts. Empate no corte: '+(group.cutoff_tie?'sim':'não')+'.','inventory-hint'));
    const body=$('ranking-rows');
    for(const item of r.items){
      const tr=el('tr');
      for(const v of [num(item.rank),item.username,item.format,tiers[item.tier]||item.tier,num(item.likes),num(item.comments),num(item.followers),pct(item.er_percent),item.top_decile?'Sim':'Não',item.within_profile_supported?(item.within_profile_top?'Sim':'Não'):'Sem cobertura'])tr.append(el('td',v));
      const td=el('td'),btn=el('button','Evidências','button outline inventory-detail-btn');
      btn.type='button';btn.addEventListener('click',()=>openDetail(item.content_id));td.append(btn);tr.append(td);body.append(tr);
    }
    if(!r.items.length){const tr=el('tr'),td=el('td','Nenhuma publicação nesta página.');td.colSpan=11;tr.append(td);body.append(tr);}
    const contrasts=$('ranking-contrasts');
    contrasts.append(el('h4','Contrastes grounded · Top 10% × restante'),
      el('p','Cobertura e limites de sensibilidade por dados desconhecidos. Não são intervalos de confiança nem efeitos causais.','inventory-hint'));
    for(const [field,entry] of Object.entries(r.grounded_contrasts)){
      const details=el('details');details.append(el('summary',fieldLabels[field]||field));
      for(const [key,label] of [['global','Global'],['within_profile','Intraperfil']]){
        const g=entry[key];
        details.append(el('p',label+': top '+num(g.top.observed)+'/'+num(g.top.posts)+' observados · restante '+num(g.rest.observed)+'/'+num(g.rest.posts)+' observados','inventory-hint'));
        const table=el('table'),head=el('thead'),header=el('tr'),tbody=el('tbody');
        for(const h of ['Candidato','Top','Restante','Diferença observada (pp)','Limites por desconhecidos (pp)'])header.append(el('th',h));
        head.append(header);table.append(head,tbody);
        for(const c of g.comparisons){
          const tr=el('tr'),bounds=c.difference_missingness_bounds_pp;
          for(const v of [c.value==='positive_claim'?'Alegação textual':c.value,num(c.top_count),num(c.rest_count),num(c.difference_percentage_points),bounds?num(bounds[0])+' a '+num(bounds[1]):'—'])tr.append(el('td',v));
          tbody.append(tr);
        }
        if(!g.comparisons.length)details.append(el('p','Nenhum candidato observado. Não significa ausência do atributo.','inventory-hint'));
        else{const scroll=el('div',undefined,'table-scroll');scroll.append(table);details.append(scroll);}
      }
      contrasts.append(details);
    }
    const provenance=el('details');provenance.append(el('summary','Proveniência e concentração por perfil'),el('pre',JSON.stringify({
      ranking_policy:r.ranking_policy,manifest_sha256:r.manifest_sha256,audience_report_sha256:r.audience_report_sha256,
      rubric_report_sha256:r.rubric_report_sha256,global_top_profiles:s.global_top_profiles,leave_one_profile_out:s.leave_one_profile_out
    },null,2)));contrasts.append(provenance);
  }
  async function load(offset=0){
    if(!permitted()||!selection)return;
    const gen=++epoch;page=null;
    $('ranking-rows').replaceChildren();$('ranking-summary').replaceChildren();$('ranking-contrasts').replaceChildren();
    $('ranking-prev').disabled=$('ranking-next').disabled=$('ranking-submit').disabled=true;
    status('Reauditando população e calculando ranking…');
    try{
      const r=await api(rankingQuery(selection.cohort,selection.topOnly,offset));
      if(gen!==epoch||!permitted())return;
      if(r.status!=='ready'){status('Ranking indisponível. Configure os relatórios de replay locais.');return;}
      if(r.schema_version!=='external-exploratory-ranking-read.v1'||r.canonical!==false||r.full_population_rechecked!==true)throw Error('Contrato de ranking incompatível.');
      render(r);page=r;$('ranking-prev').disabled=r.offset===0;$('ranking-next').disabled=r.next_offset===null;
      status(labels[r.cohort]+' · '+num(r.total)+' registros na seleção · '+num(r.population_reaudited)+' reauditorados · ER com seguidores observados, não da publicação.');
    }catch(e){if(gen===epoch&&permitted()){page=null;$('ranking-rows').replaceChildren();$('ranking-summary').replaceChildren();$('ranking-contrasts').replaceChildren();status(e.message);}}
    finally{if(gen===epoch)$('ranking-submit').disabled=!permitted();}
  }
  $('ranking-form').addEventListener('submit',e=>{e.preventDefault();selection={cohort:$('ranking-cohort').value,topOnly:$('ranking-top-only').checked};void load();});
  $('ranking-prev').addEventListener('click',()=>{if(page)void load(Math.max(0,page.offset-page.limit));});
  $('ranking-next').addEventListener('click',()=>{if(page&&page.next_offset!==null)void load(page.next_offset);});
  reset();return {reset};
}
