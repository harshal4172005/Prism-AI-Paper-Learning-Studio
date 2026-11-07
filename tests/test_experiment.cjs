const assert = require('node:assert/strict');
const {simulate, softmax} = require('../app/frontend/experiment.js');
for (const dimension of [4, 16, 64, 128, 256, 512]) {
  const result = simulate(dimension, 42);
  assert.deepEqual(result, simulate(dimension, 42), 'same seed must reproduce all results');
  assert(Math.abs(result.raw.reduce((a,b) => a+b, 0)-1) < 1e-12);
  assert(Math.abs(result.scaled.reduce((a,b) => a+b, 0)-1) < 1e-12);
  assert(result.scaled_entropy >= result.raw_entropy - 1e-12);
  assert.deepEqual(result.scaled, softmax(result.logits.map(x => x/Math.sqrt(dimension))));
  assert.notDeepEqual(result.logits, simulate(dimension, 43).logits);
}
assert(softmax([10000, 9999]).every(Number.isFinite));
assert.throws(() => simulate(0,42));
console.log('Attention experiment checks passed for all six vector sizes.');

const lessons = require('../app/frontend/more-labs.js');
const base=lessons.softmax([1,2,3]);
assert.deepEqual(base,lessons.softmax([101,102,103]));
const mask=lessons.masked([1,2,3,4],1);
assert.equal(mask[2],0);assert.equal(mask[3],0);
assert(Math.abs(mask[0]+mask[1]-1)<1e-12);
assert.deepEqual(lessons.positional(0,4),[0,1,0,1]);
for(const count of [1,2,4,8]) {const values=lessons.heads(count);assert.equal(values.length,count);for(const weights of values)assert(Math.abs(weights.reduce((a,b)=>a+b,0)-1)<1e-12);}
assert.throws(()=>lessons.softmax([1,2],0));
console.log('Softmax, masking, positional encoding and toy head checks passed.');
