import test from 'node:test';
import assert from 'node:assert/strict';
import { inventoryQuery, snapshotNotice, initInventory } from '../src/tapi_gate0/web/inventory.mjs';

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
