import test from 'node:test';
import assert from 'node:assert/strict';
import {stateCounts,armRows,initEvidenceLab,fieldPresentation,evidenceExcerpt} from '../src/tapi_gate0/web/evidence_lab.mjs';

test('candidate, measurement, abstention and unassessed stay separate',()=>{
  assert.deepEqual(stateCounts({a:{state:'candidate'},b:{state:'measurement_only'},
    c:{state:'abstained'},d:{state:'not_assessed'}}),
    {candidate:1,measurement_only:1,abstained:1,not_assessed:1});
  assert.throws(()=>stateCounts({a:{state:'approved'}}));
});
test('ablation counts sum per field without treating denominator as content count',()=>{
  const result=armRows({'caption+ocr':{
    topic:{correct_candidates:2,expected_candidates:3,wrong_nonabstained:0},
    cta:{correct_candidates:3,expected_candidates:4,wrong_nonabstained:1},
    screen:{correct_candidates:3,expected_candidates:3,wrong_nonabstained:0}
  }});
  assert.deepEqual(result,[{arm:'Legenda + OCR',correct:8,expected:10,wrong:1}]);
});

test('dashboard exposes both Studio destinations and Studio has return and evidence anchors',async()=>{
  const {readFile}=await import('node:fs/promises');
  const dashboard=await readFile(new URL('../src/tapi_gate0/web/index.html',import.meta.url),'utf8');
  const studio=await readFile(new URL('../src/tapi_gate0/web/studio.html',import.meta.url),'utf8');
  assert.match(dashboard,/href="\/app\/studio\.html"/);
  assert.match(dashboard,/href="\/app\/studio\.html\?view=evidence"/);
  assert.match(studio,/href="\/app\/"/);
  assert.match(studio,/href="#evidence-lab"/);
  assert.match(studio,/id="evidence-lab"/);
  assert.match(studio,/href="#studio-canvas"/);
  assert.match(studio,/id="studio-canvas"/);
  assert.doesNotMatch(dashboard,/Somente atividades sintéticas aparecem aqui/);
});

test('login shortcut and consult action reflect Studio authentication',()=>{
  const nodes=new Map();
  const previous=globalThis.document;
  globalThis.document={getElementById(id){
    if(!nodes.has(id))nodes.set(id,{hidden:false,disabled:false,textContent:'',
      replaceChildren(){},addEventListener(){},focus(){}});
    return nodes.get(id);
  }};
  try{
    let token=null;
    const lab=initEvidenceLab({api:()=>{throw Error('unexpected request');},getToken:()=>token});
    assert.equal(nodes.get('evidence-refresh').disabled,true);
    assert.equal(nodes.get('evidence-login-link').hidden,false);
    token='test-session';lab.controls();
    assert.equal(nodes.get('evidence-refresh').disabled,false);
    assert.equal(nodes.get('evidence-login-link').hidden,true);
    assert.match(nodes.get('evidence-status').textContent,/Sessão do Studio ativa/);
    token=null;lab.reset();
    assert.equal(nodes.get('evidence-refresh').disabled,true);
    assert.equal(nodes.get('evidence-login-link').hidden,false);
    assert.match(nodes.get('evidence-status').textContent,/Entre no Creative Studio/);
  }finally{
    if(previous===undefined)delete globalThis.document;
    else globalThis.document=previous;
  }
});

test('measurements stay distinct from rubric scores and missing evidence never becomes No',()=>{
  assert.deepEqual(fieldPresentation('duracao_faixa',{state:'measurement_only',value:null,reason:'DURATION_SECONDS_NOT_APPROVED_BIN',measurement:{duration_s:6}}),
    {value:'6 s',reason:'Duração medida; faixa da rubrica ainda não atribuída.'});
  assert.equal(fieldPresentation('ritmo_cortes_0a10',{state:'measurement_only',value:null,reason:'TRANSITION_COUNT_NOT_CALIBRATED_SCORE',measurement:{count:0}}).value,'0 transições candidatas');
  assert.equal(fieldPresentation('texto_na_tela',{state:'abstained',value:null,reason:'NO_UNCONFLICTED_POSITIVE_SCREEN_EVIDENCE'}).value,'—');
  assert.equal(fieldPresentation('tem_cta',{state:'candidate',value:true,reason:'DIRECTED_REQUEST_V2'}).value,'Sim');
  assert.equal(fieldPresentation('tema_principal',{state:'candidate',value:'vendas',reason:'unknown'}).value,'vendas');
});
test('excerpt resolves only a unique modality/hash and uses Python code-point offsets',()=>{
  const f={modality:'caption',text_sha256:'a',text:'📌 Vendas. Comente sua dúvida abaixo.'};
  const s={modality:'caption',text_sha256:'a',directed:{spans:[{start:10,end:35}]}};
  assert.deepEqual(evidenceExcerpt(s,[f]),['Comente sua dúvida abaixo']);
  assert.deepEqual(evidenceExcerpt(s,[f,f]),[]);
  assert.deepEqual(evidenceExcerpt(s,[{...f,modality:'audio'}]),[]);
  assert.deepEqual(evidenceExcerpt({...s,directed:{spans:[{start:-1,end:2},{start:0,end:999}]}},[f]),[]);
});
test('load renders all fields, visible ablation rows, filters and clears on logout',async()=>{
  const keys='tipo_post duracao_faixa formato_video hook_primeiros_3s tipo_hook forca_hook_0a10 tema_principal tem_rosto criador_e_empreendedor_real prova_social texto_na_tela legenda_tamanho ritmo_cortes_0a10 tom usa_linguagem_regional clareza_mensagem_0a10 tem_cta tipo_cta oferta_ou_beneficio_explicito elementos_top5'.split(' ');
  const nodes=new Map();
  const previous=globalThis.document;
  function node(tag='div'){
    return {tag,hidden:false,disabled:false,textContent:'',value:'',children:[],events:{},
      append(...c){this.children.push(...c);},
      replaceChildren(...c){this.children=c;if(c[0]?.tag==='option')this.value=c[0].value;},
      addEventListener(event,fn){this.events[event]=fn;},focus(){}};
  }
  globalThis.document={createElement:node,getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}};
  try{
    let token='session';
    const fields=Object.fromEntries(keys.map(k=>[k,{state:'not_assessed',value:null,reason:'metadata',measurement:null,supports:[],vetoes:[],canonical:false}]));
    fields.tema_principal={...fields.tema_principal,state:'candidate',value:'vendas',reason:'UNIQUE_LEXICAL_ANCHOR_ACROSS_AVAILABLE_MODALITIES',supports:[{modality:'caption',text_sha256:'a',spans:[{start:0,end:6}]}]};
    fields.duracao_faixa={...fields.duracao_faixa,state:'measurement_only',reason:'DURATION_SECONDS_NOT_APPROVED_BIN',measurement:{duration_s:6}};
    const coverage=Object.fromEntries(keys.map(k=>[k,{[fields[k].state]:1}]));
    const stats={correct_candidates:1,expected_candidates:1,wrong_nonabstained:0};
    const mods=['caption','audio','ocr','vlm'];
    const ablation=Object.fromEntries(Array.from({length:15},(_,i)=>[mods.filter((_,j)=>(i+1)&(1<<j)).join('+'),{tema_principal:stats}]));
    const summary={cases:[{case_id:'caption_only'}],field_coverage:coverage,total_field_cells:20,ablation,engineering_gate_passed:true,upstream_vlm_gate_passed:false};
    const detail={case_id:'caption_only',media_sha256:'b',field_evidence:fields,fragments:[{modality:'caption',text_sha256:'a',text:'Vendas. Comente sua dúvida abaixo.'}],visual_observations:[],source_rights:{}};
    const requested=[];
    const lab=initEvidenceLab({getToken:()=>token,api:async path=>{requested.push(path);return path.endsWith('/caption_only')?detail:summary;}});
    nodes.get('evidence-filter').value='all';
    await lab.load();
    assert.deepEqual(requested,['/v1/studio/evidence-lab','/v1/studio/evidence-lab/cases/caption_only']);
    assert.equal(nodes.get('evidence-fields').children.length,20);
    const table=nodes.get('evidence-ablation').children;
    assert.equal(table.length,15);
    assert.deepEqual(table[0].children.map(c=>c.textContent),['Legenda','1/1','0']);
    const topic=nodes.get('evidence-fields').children[6];
    assert.equal(topic.children[1].textContent,'vendas');
    assert.equal(topic.children.find(c=>c.className==='evidence-support').children[1].textContent,'Vendas');
    assert.equal(topic.children.at(-1).tag,'details');
    assert.equal(topic.children.at(-1).children[1].tag,'pre');
    nodes.get('evidence-filter').value='candidate';
    nodes.get('evidence-filter').events.change();
    assert.equal(nodes.get('evidence-fields').children.length,1);
    token=null;lab.reset();
    assert.equal(nodes.get('evidence-fields').children.length,0);
    assert.equal(nodes.get('evidence-ablation').children.length,0);
    assert.equal(nodes.get('evidence-refresh').disabled,true);
  }finally{
    if(previous===undefined)delete globalThis.document;
    else globalThis.document=previous;
  }
});
