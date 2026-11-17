import test from 'node:test';
import assert from 'node:assert/strict';
import {stateCounts,armRows} from '../src/tapi_gate0/web/evidence_lab.mjs';

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
