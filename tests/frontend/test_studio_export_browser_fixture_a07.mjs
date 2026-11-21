// A07.3 static fixture contract: prevent premature inline-script termination.
// Does NOT establish real-browser parity; browser runner is separate.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const fixture = fs.readFileSync(
  path.resolve('tests/frontend/studio_export_browser_a07.html'),'utf8',
);

test('inline JS survives HTML tokenization with exactly two script closers',()=>{
  const closers=[...fixture.matchAll(/<\/script\s*>/gi)];
  const openers=[...fixture.matchAll(/<script(?:\s|>)/gi)];
  assert.equal(closers.length,2,'Premature HTML script close is forbidden');
  assert.equal(openers.length,2,'One external and one inline script required');
  assert.ok(fixture.includes('\\x3C/script>'));
  assert.ok(fixture.includes('studio_export_e4.js'));
});

test('extracted inline checks parse as JavaScript without browser execution',()=>{
  const start=fixture.indexOf('<script>',fixture.indexOf('</script>')+9);
  const end=fixture.lastIndexOf('</script>');
  assert.ok(start>=0 && end>start);
  const inline=fixture.slice(start+'<script>'.length,end);
  assert.doesNotThrow(()=>new vm.Script(inline,{filename:'a073-inline-fixture.js'}));
  assert.equal((inline.match(/await run\('/g)||[]).length,7);
  assert.ok(inline.includes('A073_RUNNING_CHECKS'));
  assert.ok(inline.includes('A073_BROWSER_PARITY_PASS'));
});


test('SVG uses HTMLImageElement decoder and not createImageBitmap on SVG',()=>{
  assert.match(fixture,/async function decodeSvg\(blob,width,height\)/);
  assert.match(fixture,/const img=new Image\(\)/);
  assert.match(fixture,/await img\.decode\(\)/);
  assert.match(fixture,/URL\.revokeObjectURL\(url\)/);
  assert.match(fixture,/await decodeSvg\(exported\.blob,480,600\)/);
  assert.match(fixture,/A073_SVG_DRAWN_WATERMARK/);
});

test('hostile XML text is fully visible before checking its escaped ampersand',()=>{
  assert.ok(fixture.includes('other.pages[0].layers[0].style.font_size=16'));
  assert.ok(fixture.includes('Teste \\x3Cscript>alert("x")\\x3C/script> & texto'));
  assert.match(fixture,/xml\.includes\('&lt;script&gt;'\)/);
  assert.match(fixture,/xml\.includes\('&amp;'\)/);
  assert.match(fixture,/xml\.includes\('&quot;'\)/);
  assert.equal((fixture.match(/<\/script\s*>/gi)||[]).length,2);
});
