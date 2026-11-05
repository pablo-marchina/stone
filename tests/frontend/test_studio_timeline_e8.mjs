import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';

const scope={window:{}};
vm.runInNewContext(fs.readFileSync(path.resolve('src/tapi_gate0/web/studio_timeline_e8.js'),'utf8'),scope);
const {updateTimeline,formatTime}=scope.window.StoneTimelineE8;
function doc(){return {version:2,scenes:[
  {scene_id:'scene.1',duration_ms:1200,narration:'Primeira',overlays:[
    {text:'Primeiro',start_ms:0,end_ms:1200,keyframes:[]}]},
  {scene_id:'scene.2',duration_ms:1800,narration:'Segunda',overlays:[]}],
  clips:[{scene_id:'scene.1',start_ms:0,duration_ms:1200,transition:'crossfade',transition_ms:200},
    {scene_id:'scene.2',start_ms:1200,duration_ms:1800,transition:'cut',transition_ms:0}]};}

test('timeline update creates contiguous clips without mutating source',()=>{
  const before=doc(),source=JSON.stringify(before);
  const output=updateTimeline(before,'scene.1',{duration_ms:1300,narration:'Texto revisado',
    overlay_text:'Revisar caixa',keyframes:[
      {at_ms:0,x:100,y:100,opacity:0},{at_ms:1200,x:350,y:100,opacity:100}],
    transition:'crossfade',transition_ms:250});
  assert.equal(output.expected_version,2);
  assert.equal(output.clips[1].start_ms,1300);
  assert.equal(output.scenes[0].overlays[0].keyframes.length,2);
  assert.equal(JSON.stringify(before),source);
});

test('drag order remaps clip start times and last transition to cut',()=>{
  const out=updateTimeline(doc(),'scene.2',null,['scene.2','scene.1']);
  assert.equal(out.clips[0].start_ms,0);
  assert.equal(out.clips[1].start_ms,1800);
  assert.equal(out.clips[1].transition,'cut');
  assert.equal(out.clips[1].transition_ms,0);
});

test('invalid transitions, keyframes and order fail closed',()=>{
  assert.throws(()=>updateTimeline(doc(),'scene.1',{transition:'crossfade',transition_ms:5000}),/VALOR_FORA_DOS_LIMITES/);
  assert.throws(()=>updateTimeline(doc(),'scene.1',{overlay_text:'n',keyframes:[{at_ms:10000,x:0,y:0,opacity:100}]}),/KEYFRAME_FORA_DOS_LIMITES/);
  assert.throws(()=>updateTimeline(doc(),'scene.1',null,['scene.1','scene.1']),/ORDEM_INVALIDA/);
  assert.throws(()=>updateTimeline(doc(),'missing',{}),/CENA_NAO_ENCONTRADA/);
});

test('times are displayed as seconds for pt-BR',()=>{
  assert.equal(formatTime(2500),'2,5s');
});
