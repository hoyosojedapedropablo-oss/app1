import test from 'node:test';
import assert from 'node:assert/strict';
import {transformSource} from './head-fallback.mjs';
test('unexpected upstream source is rejected instead of applying an unchecked patch',()=>{
  for(const kind of ['internal','proxy','youtube','response','other'])assert.throws(()=>transformSource('changed upstream',kind),/SOURCE_MISMATCH/);
});
