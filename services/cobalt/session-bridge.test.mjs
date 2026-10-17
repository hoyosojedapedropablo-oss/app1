import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

const token = 'a'.repeat(120);
let calls = 0, fail = false;
const provider = http.createServer(async (req,res) => {
  calls++;
  let body=''; for await (const chunk of req) body+=chunk;
  assert.equal(req.method,'POST'); assert.equal(req.url,'/get_pot');
  assert.equal(req.headers['content-type'],'application/json'); assert.equal(body,'{}');
  res.setHeader('Content-Type','application/json');
  res.end(JSON.stringify(fail ? {error:'PRIVATE_PROVIDER_DIAGNOSTIC'} : {poToken:token,contentBinding:'visitor',expiresAt:new Date(Date.now()+600000).toISOString()}));
});
await new Promise(resolve=>provider.listen(0,'127.0.0.1',resolve));
process.env.POT_PROVIDER_URL=`http://127.0.0.1:${provider.address().port}`;
const {normalize,createServer}=await import('./session-bridge.mjs');
const bridge=createServer();
await new Promise(resolve=>bridge.listen(0,'127.0.0.1',resolve));
const url=`http://127.0.0.1:${bridge.address().port}`;

test('protocol, cache, origins and health do not expose session material',async t=>{
  t.after(()=>{bridge.close();provider.close();});
  assert.deepEqual(await (await fetch(url+'/health')).json(),{reachable:true,attestation_ready:false});
  fail=true;
  const unavailable=await fetch(url+'/get_pot',{method:'POST'});
  assert.equal(unavailable.status,503);assert.deepEqual(await unavailable.json(),{error:'POT_UNAVAILABLE'});
  fail=false;
  const responses=await Promise.all([fetch(url+'/get_pot',{method:'POST'}),fetch(url+'/get_pot',{method:'POST'})]);
  for(const response of responses){const value=await response.json();assert.equal(value.potoken,token);assert.equal(value.visitor_data,'visitor');}
  assert.equal(calls,2);
  assert.deepEqual(await (await fetch(url+'/health')).json(),{reachable:true,attestation_ready:true});
  assert.equal((await fetch(url+'/get_pot',{method:'POST',headers:{Origin:'https://example.com'}})).status,403);
  assert.equal((await fetch(url+'/get_pot')).status,404);
});
test('reject invalid or expired tokens and cap cache lifetime',()=>{
  const now=Date.now(),payload={poToken:token,contentBinding:'visitor',expiresAt:new Date(now+600000).toISOString()};
  assert.equal(normalize(payload,now).expires,now+240000);
  assert.throws(()=>normalize({...payload,poToken:'short'},now));
  assert.throws(()=>normalize({...payload,expiresAt:new Date(now-1).toISOString()},now));
});
