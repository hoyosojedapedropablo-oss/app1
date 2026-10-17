import test from 'node:test';
import assert from 'node:assert/strict';
import {Readable} from 'node:stream';
import {readMediaChunks} from './media-chunks.mjs';
const info=()=>({url:'https://media.example/video',service:'youtube',controller:new AbortController(),dispatcher:{}});
const collect=async iterator=>{const pieces=[];for await(const piece of iterator)pieces.push(piece);return Buffer.concat(pieces);};
test('large ranges rejected, 64 KiB succeeds without gaps, duplicates or endpoint overrun',async()=>{
  const data=Buffer.alloc(150000);for(let i=0;i<data.length;i++)data[i]=i%251;
  const calls=[];const stream=info();
  const request=async(url,options)=>{
    assert.equal(options.dispatcher,stream.dispatcher);assert.equal(options.signal,stream.controller.signal);
    const [,a,b]=/^bytes=(\d+)-(\d+)$/.exec(options.headers.Range);const start=Number(a),end=Number(b);calls.push([start,end]);
    if(end-start+1>65536)return {statusCode:403,headers:{},body:Readable.from(['denied'])};
    const part=data.subarray(start,end+1);
    return {statusCode:206,headers:{'content-range':`bytes ${start}-${end}/${data.length}`,'content-length':String(part.length)},body:Readable.from([part])};
  };
  const result=await collect(readMediaChunks(stream,BigInt(data.length),{request,getHeaders:()=>({})}));
  assert.deepEqual(result,data);assert.deepEqual(calls.slice(-3),[[0,65535],[65536,131071],[131072,149999]]);
  assert.ok(calls.length<=5);
});
test('403 for smallest range stops; it does not retry endlessly or accept the error body',async()=>{
  let calls=0;
  const request=async()=>{calls++;return {statusCode:403,headers:{},body:Readable.from(['private error'])};};
  await assert.rejects(collect(readMediaChunks(info(),10000000n,{request,getHeaders:()=>({})})),/MEDIA_RANGE_REJECTED/);
  assert.equal(calls,3);
});
test('wrong range and truncated body fail instead of producing a successful transfer',async()=>{
  for(const bad of ['range','truncated']) {
    const request=async()=>({statusCode:206,headers:{'content-range':bad==='range'?'bytes 1-3/3':'bytes 0-2/3','content-length':'3'},body:Readable.from([Buffer.from('ab')])});
    await assert.rejects(collect(readMediaChunks(info(),3n,{request,getHeaders:()=>({})})),/MEDIA_RANGE_/);
  }
});
test('discarding a denied response handles its asynchronous abort error',async()=>{
  let calls=0;
  const request=async()=>{
    calls++;
    const body=new Readable({read(){},destroy(error,done){done(Object.assign(Error('aborted'),{code:'UND_ERR_ABORTED'}));}});
    return {statusCode:403,headers:{},body};
  };
  await assert.rejects(collect(readMediaChunks(info(),20000000n,{request,getHeaders:()=>({})})),/MEDIA_RANGE_REJECTED/);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(calls,3);
});
