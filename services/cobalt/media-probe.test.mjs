import test from 'node:test';
import assert from 'node:assert/strict';
import {probeMedia} from './media-probe.mjs';
const info=()=>({url:'https://media.example/video',service:'youtube',controller:new AbortController(),dispatcher:{}});
const headers=()=>({'User-Agent':'test'});

test('HEAD 403 then GET 206 uses Content-Range total, not one-byte response size',async()=>{
  const stream=info(),calls=[];
  const result=await probeMedia(stream,{getHeaders:headers,fetch:async(url,options)=>{
    calls.push(options);
    return options.method==='HEAD'?new Response(null,{status:403}):new Response(new Uint8Array(1),{status:206,headers:{'Content-Range':'bytes 0-0/123456','Content-Length':'1','Content-Type':'video/mp4'}});
  }});
  assert.equal(result.size,123456n);assert.equal(result.req.headers.get('content-length'),'123456');
  assert.equal(result.req.headers.get('content-type'),'video/mp4');
  assert.deepEqual(calls.map(x=>x.method),['HEAD','GET']);
  assert.equal(calls[1].headers.Range,'bytes=0-0');
  assert.equal(calls[1].dispatcher,stream.dispatcher);assert.equal(calls[1].signal,stream.controller.signal);
});
test('valid HEAD keeps the original single-request path',async()=>{
  let calls=0;
  const result=await probeMedia(info(),{getHeaders:headers,fetch:async()=>{calls++;return new Response(null,{headers:{'content-length':'88'}});}});
  assert.equal(result.size,88n);assert.equal(calls,1);
});
test('GET denial, malformed ranges, and oversized media are not accepted',async()=>{
  for(const response of [
    ()=>new Response(null,{status:403}),
    ()=>new Response('x',{status:206,headers:{'content-range':'bytes 0-0/*','content-length':'1'}}),
    ()=>new Response('x',{status:206,headers:{'content-range':'bytes 1-1/500','content-length':'1'}}),
    ()=>new Response('x',{status:206,headers:{'content-range':'bytes 0-0/99999999999999','content-length':'1'}}),
  ]){
    const result=await probeMedia(info(),{getHeaders:headers,fetch:async(_,options)=>options.method==='HEAD'?new Response(null,{status:403}):response()});
    assert.equal(result,null);
  }
});
test('a server ignoring Range with a valid full length is supported and body cancelled',async()=>{
  let cancelled=false;
  const result=await probeMedia(info(),{getHeaders:headers,fetch:async(_,options)=>options.method==='HEAD'?new Response(null,{status:405}):new Response(new ReadableStream({cancel(){cancelled=true;}}),{headers:{'content-length':'900'}})});
  assert.equal(result.size,900n);assert.equal(cancelled,true);
});
test('GET 403 retains at most three existing signed-link refresh attempts',async()=>{
  const stream=info();let refresh=0,calls=0;stream.transplant=async()=>{refresh++;};
  const result=await probeMedia(stream,{getHeaders:headers,fetch:async()=>{calls++;return new Response(null,{status:403});}});
  assert.equal(result,null);assert.equal(calls,6);assert.equal(refresh,2);
});
