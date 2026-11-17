import test from 'node:test';
import assert from 'node:assert/strict';
import { inventoryQuery, snapshotNotice, initInventory, rubricRows, rubricContractStatus } from '../src/tapi_gate0/web/inventory.mjs';

test('inventory query includes only permitted filters and encodes values',()=>{
  const url=new URL(inventoryQuery({search:'a & b',platform:'instagram',sector:'',tenant_id:'other',token:'secret'},25),'http://localhost');
  assert.equal(url.pathname,'/v1/corpus/inventory');
  assert.deepEqual(Object.fromEntries(url.searchParams),{limit:'25',offset:'25',search:'a & b',platform:'instagram'});
});
test('snapshot notices distinguish missing, tied and unique timestamps',()=>{
  assert.match(snapshotNotice({latest_snapshot:null}),/indisponíveis/);
  assert.match(snapshotNotice({latest_snapshot:{likes:0},latest_snapshot_timestamp_tie:true}),/sem garantia de ordem cronológica/);
  assert.equal(snapshotNotice({latest_snapshot:{likes:0}}),'Última observação disponível');
});
test('dashboard inventory reuses role state and discards a response after logout',async()=>{
  const previous=globalThis.document,nodes=new Map();
  function node(tag='div'){
    return {tag,children:[],events:{},disabled:false,textContent:'',value:'',
      append(...items){this.children.push(...items);},
      replaceChildren(...items){this.children=items;},
      addEventListener(k,fn){this.events[k]=fn;},
      reset(){},focus(){}};
  }
  globalThis.document={createElement:node,getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}};
  try{
    let principal=null,resolve,requests=[];
    const explorer=initInventory({getPrincipal:()=>principal,api:path=>{requests.push(path);return new Promise(r=>{resolve=r;});}});
    assert.equal(nodes.get('inventory-submit').disabled,true);
    await explorer.load();
    assert.equal(requests.length,0);
    principal={role:'viewer'};explorer.reset();await explorer.load();
    assert.equal(requests.length,0);
    principal={role:'admin'};explorer.reset();
    const pending=explorer.load();
    assert.equal(requests.length,1);
    principal=null;explorer.reset();
    resolve({items:[{handle:'private fixture'}],total_filtered:1,total_visible_before_filters:1,offset:0,next_offset:null});
    await pending;
    assert.equal(nodes.get('inventory-rows').children.length,0);
    assert.equal(nodes.get('inventory-count').textContent,'—');
    assert.equal(nodes.get('inventory-submit').disabled,true);
  }finally{
    if(previous===undefined)delete globalThis.document;else globalThis.document=previous;
  }
});
test('dashboard includes inventory section, form and same-document navigation',async()=>{
  const {readFile}=await import('node:fs/promises');
  const html=await readFile(new URL('../src/tapi_gate0/web/index.html',import.meta.url),'utf8');
  assert.match(html,/href="#data-explorer"/);
  for(const id of ['data-explorer','inventory-form','inventory-status','inventory-rows','inventory-detail','inventory-prev','inventory-next']){
    assert.ok(html.includes('id="'+id+'"'));
  }
});

test('historical rubric maps all 20 fields without converting abstention to false',async()=>{
  const {FIELDS}=await import('../src/tapi_gate0/web/evidence_lab.mjs');
  const fields=Object.fromEntries(Object.keys(FIELDS).map(key=>[key,{state:'abstained',value:null,modality:null,reason:'BASELINE_NOT_OBSERVABLE'}]));
  fields.tem_cta={state:'candidate',value:true,modality:'caption',reason:'HISTORICAL_LEXICAL_CANDIDATE'};
  const rows=rubricRows({fields});
  assert.equal(rows.length,20);
  assert.equal(rows.find(x=>x.key==='tem_cta').value,'Sim');
  assert.equal(rows.find(x=>x.key==='tem_cta').modality,'Legenda');
  assert.match(rows.find(x=>x.key==='tem_cta').reason,/sem revalidação semântica/);
  assert.equal(rows.find(x=>x.key==='tem_rosto').value,'—');
  assert.equal(rows.find(x=>x.key==='tem_rosto').state,'Abstenção');
});

test('rubric detail distinguishes old API, incomplete contract and all-abstained valid record',async()=>{
  const {FIELDS}=await import('../src/tapi_gate0/web/evidence_lab.mjs');
  const fields=Object.fromEntries(Object.keys(FIELDS).map(key=>[key,{state:'not_assessed',value:null,modality:null,reason:'NO_MATCHING_STORED_BASELINE'}]));
  const rubric={schema_version:'external-stored-rubric-read.v1',field_count:20,fields,canonical:false,
    state_counts:{candidate:0,measurement_only:0,abstained:0,not_assessed:20}};
  assert.equal(rubricContractStatus(undefined),'missing');
  assert.equal(rubricContractStatus({...rubric,field_count:19}),'incompatible');
  assert.equal(rubricContractStatus({...rubric,canonical:true}),'incompatible');
  assert.equal(rubricContractStatus({...rubric,state_counts:{...rubric.state_counts,not_assessed:19}}),'incompatible');
  assert.equal(rubricContractStatus(rubric),'ready');
  const previous=globalThis.document,nodes=new Map();
  function node(tag='div'){
    return {tag,children:[],events:{},disabled:false,textContent:'',value:'',
      append(...items){this.children.push(...items);},
      replaceChildren(...items){this.children=items;},
      addEventListener(k,fn){this.events[k]=fn;},reset(){},focus(){}};
  }
  globalThis.document={createElement:node,getElementById(id){if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);}};
  try{
    const item={content_id:'fixture',handle:'fixture',valid_snapshot_count:0,media_type:'imagem'};
    let stored_rubric;
    const explorer=initInventory({getPrincipal:()=>({role:'admin'}),api:async path=>
      path.includes('/fixture?')?{item,snapshots:[],snapshot_offset:0,snapshot_limit:25,next_snapshot_offset:null,stored_rubric}:
        {items:[item],total_filtered:1,total_visible_before_filters:1,offset:0,next_offset:null}});
    await explorer.load();
    const click=nodes.get('inventory-rows').children[0].children.at(-1).children[0].events.click;
    click();await new Promise(resolve=>setImmediate(resolve));
    let panel=nodes.get('inventory-detail').children.at(-1);
    assert.equal(panel.children[0].textContent,'Evidence Studio · Rubrica histórica');
    assert.match(panel.children[1].textContent,/API em execução não retornou/);
    stored_rubric=rubric;
    click();await new Promise(resolve=>setImmediate(resolve));
    panel=nodes.get('inventory-detail').children.at(-1);
    assert.equal(panel.children[0].textContent,'Evidence Studio · Rubrica histórica');
    assert.match(panel.children[3].textContent,/Nenhuma avaliação histórica compatível/);
    assert.equal(panel.children[4].children[0].children[1].children.length,20);
  }finally{
    if(previous===undefined)delete globalThis.document;else globalThis.document=previous;
  }
});
