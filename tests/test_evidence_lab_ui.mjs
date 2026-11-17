import test from 'node:test';
import assert from 'node:assert/strict';
import {stateCounts,armRows,initEvidenceLab} from '../src/tapi_gate0/web/evidence_lab.mjs';

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
