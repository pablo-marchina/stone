// A07.2 — real Studio E4 export engine under a no-network, canvas-free Node shim.
// Verifies byte-level local export manifest, draft markings and limits.
// It does NOT prove browser pixel parity, media licenses, external source rights
// or publication approval. No FFmpeg, network, workers or external assets.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createHash, webcrypto} from 'node:crypto';

const canvas = () => ({
  width: 0, height: 0,
  getContext(kind) {
    assert.equal(kind, '2d');
    return {
      canvas: this,
      measureText(text) { return {width: [...String(text)].length * 12}; },
    };
  },
});

const sandbox = {
  document: {
    createElement(kind) {
      assert.equal(kind, 'canvas', 'Unexpected external DOM element');
      return canvas();
    },
  },
  Blob, TextEncoder, Uint8Array, DataView, setTimeout,
  crypto: webcrypto,
  fetch() { throw Error('Network must never be called by draft exporter'); },
};
vm.runInNewContext(
  readFileSync(path.resolve('src/tapi_gate0/web/studio_export_e4.js'), 'utf8'),
  sandbox,
  {filename:'studio_export_e4.js'},
);
const exporter = sandbox.StoneExport;

function doc(overrides={}) {
  return {
    schema_version:'design-document.v1',
    document_id:'draft.synthetic.1', tenant_id:'test-tenant',
    spec_id:'spec.synthetic', version:1,
    canvas:{width:1080,height:1350,background:'#FFFFFF'},
    platform_intent:'instagram_feed',
    approval_status:'draft', rights_status:'pending_review',
    reference_status:'unverified', render_status:'not_implemented',
    reference_content_ids:['fictional.post'],
    pages:[{id:'page.1',layers:[
      {id:'headline',kind:'text',x:70,y:100,w:940,h:200,
       text:'Controle o estoque',style:{font_family:'sans-serif',font_size:72,color:'#171717'},
       origin:'operator_draft',editable:true},
      {id:'body',kind:'text',x:70,y:390,w:940,h:440,
       text:'Separe receitas e despesas.',style:{font_family:'sans-serif',font_size:44,color:'#171717'},
       origin:'operator_draft',editable:true},
      {id:'cta',kind:'text',x:70,y:950,w:940,h:190,
       text:'Revise este exemplo.',style:{font_family:'sans-serif',font_size:56,color:'#171717'},
       origin:'operator_draft',editable:true},
    ]}],
    ...overrides,
  };
}

async function svgExport(document=doc()) {
  return exporter.exportDocument(document, document.pages[0].id, new Map(), 'svg');
}

function sha256(data) {
  return createHash('sha256').update(data).digest('hex');
}

function zipEntries(bytes) {
  // The implementation writes uncompressed (method=0) ZIP local entries.
  const buffer=Buffer.from(bytes);
  const entries=[];
  let offset=0;
  for(;;) {
    if(offset+4>buffer.length)throw Error('Truncated ZIP');
    if(buffer.readUInt32LE(offset)!==0x04034b50)break;
    const method=buffer.readUInt16LE(offset+8);
    assert.equal(method,0,'ZIP unexpectedly uses compression');
    const size=buffer.readUInt32LE(offset+18);
    const nameLength=buffer.readUInt16LE(offset+26);
    const extraLength=buffer.readUInt16LE(offset+28);
    const start=offset+30+nameLength+extraLength;
    const filename=buffer.subarray(offset+30,offset+30+nameLength).toString('utf8');
    if(start+size>buffer.length)throw Error('Truncated ZIP member');
    entries.push({name:filename,data:buffer.subarray(start,start+size)});
    offset=start+size;
  }
  assert.equal(buffer.readUInt32LE(offset),0x02014b50,'Central ZIP directory required');
  return entries;
}

test('SVG export returns actual local bytes matching SHA-256 manifest and version', async()=>{
  const d=doc(),before=JSON.stringify(d);
  const out=await svgExport(d);
  const bytes=Buffer.from(await out.blob.arrayBuffer());
  const svg=bytes.toString('utf8');
  assert.match(svg,/<svg xmlns="http:\/\/www.w3.org\/2000\/svg"/);
  assert.match(svg,/>Controle o estoque<\/text>/);
  assert.match(svg,/RASCUNHO - NAO PUBLICAR/);
  assert.ok(out.filename.includes('v1-RASCUNHO-page-01.svg'));
  assert.equal(out.manifest.schema_version,'studio-draft-export.v1');
  assert.equal(out.manifest.document_id,d.document_id);
  assert.equal(out.manifest.spec_id,d.spec_id);
  assert.equal(out.manifest.version,1);
  assert.equal(out.manifest.approval_status,'draft');
  assert.equal(out.manifest.rights_status,'pending_review');
  assert.equal(out.manifest.render_status,'local_preview_only');
  assert.equal(out.manifest.pages.length,1);
  assert.equal(out.manifest.pages[0].page_id,'page.1');
  assert.equal(out.manifest.pages[0].sha256,sha256(bytes));
  assert.equal(out.manifest.pages[0].bytes,bytes.length);
  assert.equal(JSON.stringify(d),before,'Export must never mutate source document');
});

test('markup in untrusted draft text is escaped and cannot inject SVG elements', async()=>{
  const d=doc();
  const payload='Teste <script>alert("x")</script> & "texto"';
  d.pages[0].layers[0].text=payload;
  const out=await svgExport(d);
  const xml=await out.blob.text();
  assert.equal(xml.includes('<script>'),false);
  assert.equal(xml.includes('</script>'),false);
  assert.match(xml,/&lt;script&gt;/);
  assert.match(xml,/&amp;/);
  assert.match(xml,/&quot;/);
  assert.match(xml,/RASCUNHO - NAO PUBLICAR/);
});

test('immutable edited version yields different byte digest and version receipt',async()=>{
  const first=await svgExport();
  const revised=doc({version:2});
  revised.pages[0].layers[0].text='Revise o controle de estoque';
  revised.pages[0].layers[0].origin='operator_edit';
  const second=await svgExport(revised);
  assert.equal(first.manifest.version,1);
  assert.equal(second.manifest.version,2);
  assert.notEqual(first.manifest.pages[0].sha256,second.manifest.pages[0].sha256);
  assert.match(await second.blob.text(),/Revise o controle de estoque/);
  assert.match(await first.blob.text(),/Controle o estoque/);
  assert.equal(second.manifest.rights_status,'pending_review');
  assert.equal(second.manifest.approval_status,'draft');
});

test('repeat export of fixed typed draft is byte-deterministic in fixture',async()=>{
  const d=doc();
  const a=await svgExport(d),b=await svgExport(d);
  assert.equal(a.manifest.pages[0].sha256,b.manifest.pages[0].sha256);
  assert.equal(await a.blob.text(),await b.blob.text());
});

test('carousel ZIP contains each SVG byte hash and exact JSON manifest',async()=>{
  const d=doc({platform_intent:'instagram_carousel'});
  d.pages=[
    {id:'page.1',layers:doc().pages[0].layers},
    {id:'page.2',layers:[{...doc().pages[0].layers[0],text:'Segundo slide'}]},
    {id:'page.3',layers:[{...doc().pages[0].layers[0],text:'Terceiro slide'}]},
  ];
  const out=await exporter.exportDocument(d,'page.1',new Map(),'svg',true);
  const files=zipEntries(await out.blob.arrayBuffer());
  assert.deepEqual(files.map(f=>f.name),[
    'page-01.svg','page-02.svg','page-03.svg','manifest.json',
  ]);
  const manifest=JSON.parse(files[3].data.toString('utf8'));
  assert.equal(manifest.pages.length,3);
  assert.equal(manifest.version,1);
  assert.equal(manifest.rights_status,'pending_review');
  assert.equal(manifest.approval_status,'draft');
  for(let i=0;i<3;i++){
    assert.equal(manifest.pages[i].page_id,d.pages[i].id);
    assert.equal(manifest.pages[i].sha256,sha256(files[i].data));
    assert.equal(manifest.pages[i].bytes,files[i].data.length);
    assert.match(files[i].data.toString('utf8'),/RASCUNHO - NAO PUBLICAR/);
  }
});

test('missing image asset is rejected rather than inserting an external reference',async()=>{
  const d=doc();
  d.pages[0].layers.push({
    id:'image.1',kind:'image',x:40,y:40,w:100,h:100,asset_id:'unlicensed.1',
  });
  await assert.rejects(svgExport(d),/Ativo de mídia não carregado/);
});

test('format, page selection and archive intent are deny-by-default',async()=>{
  const d=doc();
  await assert.rejects(exporter.exportDocument(d,'page.1',new Map(),'html'),/Formato inválido/);
  await assert.rejects(exporter.exportDocument(d,'nonexistent',new Map(),'svg'),/Página inválida/);
  await assert.rejects(exporter.exportDocument(d,'page.1',new Map(),'svg',true),/ZIP somente carrossel/);
});

test('no global network access or authorization state is needed for synthetic SVG',async()=>{
  const d=doc();
  const out=await svgExport(d);
  assert.equal(out.manifest.rights_status,'pending_review');
  assert.equal(out.manifest.approval_status,'draft');
  assert.equal(sandbox.StoneExport,exporter);
  assert.equal(out.manifest.pages.length,1);
  // This is a browser export-shape test; it does not authenticate the draft,
  // attest external rights, compare pixels or authorize a render worker.
});
