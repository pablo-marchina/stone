// A11 / CAP-023 — real Node SVG export from an authenticated API document.
//
// Consumes only a local JSON document over stdin. Runs the production E4
// export engine under an offline canvas shim. There is no browser, provider,
// remote URL, image, model, publication or approval in this test harness.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createHash, webcrypto} from 'node:crypto';

const raw = readFileSync(0, 'utf8');
assert.ok(raw.length > 0 && raw.length <= 2_000_000, 'LOCAL_DOCUMENT_SIZE_INVALID');
const doc = JSON.parse(raw);
assert.equal(doc.schema_version, 'design-document.v1');
assert.equal(doc.approval_status, 'draft');
assert.equal(doc.rights_status, 'pending_review');
assert.equal(doc.reference_status, 'unverified');
assert.equal(doc.render_status, 'not_implemented');
assert.ok(Array.isArray(doc.pages) && doc.pages.length === 1);
const headline = doc.pages[0].layers.find(x=>x.id === 'headline' && x.kind === 'text');
assert.ok(headline);
assert.ok(headline.text.length > 0);

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
    createElement(tag) {
      assert.equal(tag, 'canvas', 'UNEXPECTED_ELEMENT');
      return canvas();
    },
  },
  Blob, TextEncoder, Uint8Array, DataView, setTimeout,
  crypto: webcrypto,
  fetch() { throw Error('NETWORK_FORBIDDEN'); },
};
vm.runInNewContext(
  readFileSync('src/tapi_gate0/web/studio_export_e4.js', 'utf8'),
  sandbox,
  {filename:'studio_export_e4.js'},
);
const exporter = sandbox.StoneExport;
const before = JSON.stringify(doc);
const result = await exporter.exportDocument(doc, doc.pages[0].id, new Map(), 'svg');
const bytes = Buffer.from(await result.blob.arrayBuffer());
const svg = bytes.toString('utf8');
const digest = createHash('sha256').update(bytes).digest('hex');
assert.match(svg, /<svg xmlns="http:\/\/www.w3.org\/2000\/svg"/);
assert.ok(svg.includes('RASCUNHO - NAO PUBLICAR'));
assert.ok(svg.includes('Revise seu estoque'), 'EXPECTED_PATCHED_HEADLINE_ABSENT');
assert.ok(!svg.includes('Ignore previous instructions'));
assert.equal(result.manifest.schema_version,'studio-draft-export.v1');
assert.equal(result.manifest.version,doc.version);
assert.equal(result.manifest.document_id,doc.document_id);
assert.equal(result.manifest.spec_id,doc.spec_id);
assert.equal(result.manifest.pages[0].sha256,digest);
assert.equal(result.manifest.pages[0].bytes,bytes.length);
assert.equal(JSON.stringify(doc),before, 'EXPORT_MUTATED_SOURCE');
assert.ok(result.filename.includes('-RASCUNHO-page-01.svg'));
console.log(JSON.stringify({
  schema_version:'tapi-a11-studio-api-svg-rehearsal.v1',
  status:'LOCAL_DRAFT_SVG_BYTES_VERIFIED',
  version:doc.version,
  svg_sha256:digest,
  svg_bytes:bytes.length,
  watermark_verified:true,
  edited_headline_verified:true,
  source_immutable:true,
  external_rights_verified:false,
  publication_allowed:false,
  scientific_admissions:0,
  production_approved:false,
  gates_released:false,
}));
