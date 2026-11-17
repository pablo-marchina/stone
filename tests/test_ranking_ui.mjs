import test from 'node:test';
import assert from 'node:assert/strict';
import {rankingQuery,initRanking} from '../src/tapi_gate0/web/ranking.mjs';

test('ranking query validates cohort and preserves global pagination',()=>{
  const u=new URL(rankingQuery('semantic_exploratory',true,25),'http://localhost');
  assert.equal(u.pathname,'/v1/corpus/inventory/ranking');
  assert.deepEqual(Object.fromEntries(u.searchParams),{cohort:'semantic_exploratory',top_only:'true',offset:'25',limit:'25'});
  assert.throws(()=>rankingQuery('canonical',true));
  assert.throws(()=>rankingQuery('technical_all',true,-1));
});

test('ranking role, disabled state and stale response after logout',async()=>{
  const previous=globalThis.document,nodes=new Map();
  function node(tag='div'){
    return {tag,children:[],events:{},disabled:false,textContent:'',value:'',checked:false,
      append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
      addEventListener(k,fn){this.events[k]=fn;},reset(){}};
  }
  globalThis.document={createElement:node,getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}};
  try{
    let principal=null,resolve,requests=0;
    const ui=initRanking({getPrincipal:()=>principal,api:()=>{requests++;return new Promise(r=>{resolve=r;});},openDetail:()=>{}});
    const submit=()=>nodes.get('ranking-form').events.submit({preventDefault(){}});
    assert.equal(nodes.get('ranking-submit').disabled,true);
    submit();assert.equal(requests,0);
    principal={role:'admin'};ui.reset();
    globalThis.document.getElementById('ranking-cohort').value='technical_all';
    globalThis.document.getElementById('ranking-top-only').checked=true;
    submit();assert.equal(requests,1);resolve({status:'disabled'});
    await new Promise(r=>setImmediate(r));
    assert.match(nodes.get('ranking-status').textContent,/indisponível/);
    submit();principal=null;ui.reset();resolve({status:'ready'});
    await new Promise(r=>setImmediate(r));
    assert.equal(nodes.get('ranking-rows').children.length,0);
    assert.equal(nodes.get('ranking-submit').disabled,true);
  }finally{
    if(previous===undefined)delete globalThis.document;else globalThis.document=previous;
  }
});

test('ranking navigation and panel are present',async()=>{
  const {readFile}=await import('node:fs/promises');
  const html=await readFile(new URL('../src/tapi_gate0/web/index.html',import.meta.url),'utf8');
  assert.match(html,/href="#ranking-explorer"/);
  assert.match(html,/A04-RANKING-1/);
  for(const id of ['ranking-form','ranking-summary','ranking-rows','ranking-contrasts','ranking-prev','ranking-next'])
    assert.ok(html.includes('id="'+id+'"'));
});

test('ready ranking renders metrics and drilldown to the correct content',async()=>{
  const previous=globalThis.document,nodes=new Map();
  function node(tag='div'){
    return {tag,children:[],events:{},disabled:false,textContent:'',value:'',checked:false,
      append(...items){this.children.push(...items);},replaceChildren(...items){this.children=items;},
      addEventListener(k,fn){this.events[k]=fn;},reset(){}};
  }
  globalThis.document={createElement:node,getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}};
  try{
    const group={posts:1,profiles:1,median_er_percent:3,top_decile_count:1,top_decile_median_er_percent:3,cutoff_tie:false};
    let opened=null;
    initRanking({getPrincipal:()=>({role:'admin'}),openDetail:id=>opened=id,api:async()=>({
      schema_version:'external-exploratory-ranking-read.v1',status:'ready',canonical:false,full_population_rechecked:true,
      cohort:'technical_all',cohorts:{technical_all:group},sensitivity:{within_profile_supported_posts:0,
        within_profile_supported_profiles:0,within_profile_min_posts:10,top_jaccard:null},
      items:[{rank:1,username:'fixture',format:'reels',tier:'unresolved',likes:2,comments:1,followers:100,
        er_percent:3,top_decile:true,within_profile_supported:false,within_profile_top:false,content_id:'post1'}],
      grounded_contrasts:{},total:1,population_reaudited:1,offset:0,limit:25,next_offset:null})});
    globalThis.document.getElementById('ranking-cohort').value='technical_all';
    globalThis.document.getElementById('ranking-top-only').checked=true;
    nodes.get('ranking-form').events.submit({preventDefault(){}});
    await new Promise(r=>setImmediate(r));
    const row=nodes.get('ranking-rows').children[0];
    assert.equal(row.children[7].textContent,'3%');
    assert.equal(row.children[9].textContent,'Sem cobertura');
    row.children[10].children[0].events.click();
    assert.equal(opened,'post1');
    assert.match(nodes.get('ranking-status').textContent,/1 reauditorados/);
  }finally{
    if(previous===undefined)delete globalThis.document;else globalThis.document=previous;
  }
});
