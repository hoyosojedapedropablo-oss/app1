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
test('mid-file socket failure retries the exact block without duplicated bytes',async()=>{
  const data=Buffer.alloc(17000000);for(let i=0;i<data.length;i++)data[i]=i%251;
  const calls=[],events=[];let failed=false;
  const request=async(url,options)=>{
    const [,a,b]=/^bytes=(\d+)-(\d+)$/.exec(options.headers.Range);const start=Number(a),end=Number(b);calls.push(start);
    const broken=start===8000000&&!failed;if(broken)failed=true;
    const body=broken?Readable.from((async function*(){yield data.subarray(start,start+40000);throw Object.assign(Error('private URL'),{code:'UND_ERR_SOCKET'});})()):Readable.from([data.subarray(start,end+1)]);
    return {statusCode:206,headers:{'content-range':`bytes ${start}-${end}/${data.length}`,'content-length':String(end-start+1)},body};
  };
  assert.deepEqual(await collect(readMediaChunks(info(),BigInt(data.length),{request,getHeaders:()=>({}),wait:async()=>{},onEvent:e=>events.push(e)})),data);
  assert.deepEqual(calls,[0,8000000,8000000,16000000]);
  assert.equal(events[0].received,40000);assert.equal(events[0].offset,8000000);
  assert.ok(!JSON.stringify(events).includes('private'));
});
test('truncated bodies recover with a bounded number of retries',async()=>{
  let calls=0;const events=[];
  const request=async()=>{calls++;return {statusCode:206,headers:{'content-range':'bytes 0-2/3','content-length':'3'},body:Readable.from(['ab'])};};
  await assert.rejects(collect(readMediaChunks(info(),3n,{request,getHeaders:()=>({}),wait:async()=>{},onEvent:e=>events.push(e)})),/MEDIA_RANGE_TRUNCATED/);
  assert.equal(calls,3);assert.equal(events.at(-1).stage,'range_failure');
});
test('mid-file 403 uses the existing renewal callback and checks renewed range identity',async()=>{
  for(const changedSize of [false,true]) {
    const data=Buffer.alloc(9000000,23),stream=info();let refreshes=0;const events=[];
    stream.transplant=async dispatcher=>{assert.equal(dispatcher,stream.dispatcher);refreshes++;stream.url='https://media.example/renewed';};
    const request=async(url,options)=>{
      const [,a,b]=/^bytes=(\d+)-(\d+)$/.exec(options.headers.Range);const start=Number(a),end=Number(b);
      if(start>0&&!refreshes)return {statusCode:403,headers:{},body:Readable.from(['private'])};
      return {statusCode:206,headers:{'content-range':`bytes ${start}-${end}/${data.length+(changedSize&&refreshes?1:0)}`,'content-length':String(end-start+1)},body:Readable.from([data.subarray(start,end+1)])};
    };
    const result=collect(readMediaChunks(stream,BigInt(data.length),{request,getHeaders:()=>({}),onEvent:e=>events.push(e)}));
    if(changedSize)await assert.rejects(result,/MEDIA_RANGE_REJECTED/);else assert.deepEqual(await result,data);
    assert.equal(refreshes,1);assert.equal(events[0].stage,'refresh');
  }
});
test('renewal that cannot restore access stops after three attempts',async()=>{
  const stream=info();let refreshes=0;stream.transplant=async()=>{refreshes++;};
  const request=async(url,options)=>{
    const [,a,b]=/^bytes=(\d+)-(\d+)$/.exec(options.headers.Range);const start=Number(a),end=Number(b);
    if(start)return {statusCode:403,headers:{},body:Readable.from(['denied'])};
    return {statusCode:206,headers:{'content-range':`bytes ${start}-${end}/9000000`,'content-length':String(end-start+1)},body:Readable.from([Buffer.alloc(end-start+1)])};
  };
  await assert.rejects(collect(readMediaChunks(stream,9000000n,{request,getHeaders:()=>({}),onEvent:()=>{}})),/MEDIA_RANGE_REJECTED/);
  assert.equal(refreshes,3);
});
test('real HTTP connection reset after the first block resumes and preserves all bytes',async()=>{
  const http=await import('node:http');const data=Buffer.alloc(9000000,61);let reset=false;const starts=[];
  const server=http.createServer((req,res)=>{
    const [,a,b]=/^bytes=(\d+)-(\d+)$/.exec(req.headers.range);const start=Number(a),end=Number(b);starts.push(start);
    res.writeHead(206,{'content-range':`bytes ${start}-${end}/${data.length}`,'content-length':String(end-start+1)});
    if(start===8000000&&!reset){reset=true;res.write(data.subarray(start,start+4096));setTimeout(()=>res.destroy(),10);}
    else res.end(data.subarray(start,end+1));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const stream=info();stream.url=`http://127.0.0.1:${server.address().port}/track`;
  const request=(url,options)=>new Promise((resolve,reject)=>{
    const req=http.get(url,{headers:options.headers,signal:options.signal},res=>resolve({statusCode:res.statusCode,headers:res.headers,body:res}));req.on('error',reject);
  });
  try {
    const result=await collect(readMediaChunks(stream,BigInt(data.length),{request,getHeaders:()=>({}),wait:async()=>{},onEvent:()=>{}}));
    assert.deepEqual(result,data);assert.deepEqual(starts,[0,8000000,8000000]);
  } finally {server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
