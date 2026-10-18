// Read validated byte ranges; commit each block only after its body is complete.
import {setTimeout as delay} from 'node:timers/promises';
const MIN_CHUNK=65536n;
const SIZES=[8000000n,1048576n,MIN_CHUNK];
const transient=new Set(['UND_ERR_SOCKET','UND_ERR_CONNECT_TIMEOUT','UND_ERR_HEADERS_TIMEOUT','UND_ERR_BODY_TIMEOUT','ECONNRESET','ETIMEDOUT','EPIPE','MEDIA_RANGE_TRUNCATED']);
function discard(body) {
  body.on('error',()=>{});
  body.destroy();
}
function errorCode(error) {
  const code=error?.code||error?.message;
  return transient.has(code)||['MEDIA_RANGE_REJECTED','MEDIA_RANGE_OVERSIZED'].includes(code)?code:'MEDIA_RANGE_FAILED';
}
function report(event) {
  // Numeric positions and fixed labels only; no URLs, response bodies or tokens.
  process.stderr.write('CLIP_MEDIA_EVENT:'+JSON.stringify(event)+'\n');
}
export async function* readMediaChunks(streamInfo,size,{request,getHeaders,wait=delay,onEvent=report}) {
  if(typeof size!=='bigint'||size<=0n||size>12n*1024n**3n)throw Error('MEDIA_SIZE_INVALID');
  let offset=0n,level=0,refreshes=0,retries=0,totalRetries=0;
  while(offset<size) {
    if(streamInfo.controller.signal.aborted)throw Error('MEDIA_ABORTED');
    const end=offset+SIZES[level]-1n<size?offset+SIZES[level]-1n:size-1n;
    let response,parts=[],received=0n;
    try {
      response=await request(streamInfo.url,{
        headers:{...getHeaders(streamInfo.service),Range:`bytes=${offset}-${end}`},
        dispatcher:streamInfo.dispatcher,signal:streamInfo.controller.signal,maxRedirections:4
      });
      if(response.statusCode===403 && level<SIZES.length-1 && end-offset+1n>MIN_CHUNK) {
        do {level++;} while(level<SIZES.length-1 && SIZES[level]>=end-offset+1n);
        continue;
      }
      if(response.statusCode===403 && offset>0n && refreshes<3 && streamInfo.transplant) {
        refreshes++;
        onEvent({stage:'refresh',offset:Number(offset),status:403,attempt:refreshes});
        discard(response.body);response=undefined;
        await streamInfo.transplant(streamInfo.dispatcher);
        continue;
      }
      const match=/^bytes ([0-9]+)-([0-9]+)\/([0-9]+)$/.exec(String(response.headers['content-range']||''));
      const length=String(response.headers['content-length']||'');
      const expected=end-offset+1n;
      if(response.statusCode!==206||!match||BigInt(match[1])!==offset||BigInt(match[2])!==end||BigInt(match[3])!==size||!/^\d+$/.test(length)||BigInt(length)!==expected) {
        throw Error('MEDIA_RANGE_REJECTED');
      }
      for await(const chunk of response.body) {
        received+=BigInt(chunk.length);
        if(received>expected)throw Error('MEDIA_RANGE_OVERSIZED');
        parts.push(Buffer.from(chunk));
      }
      if(received!==expected)throw Error('MEDIA_RANGE_TRUNCATED');
    } catch(error) {
      const code=errorCode(error);
      const event={stage:'range_failure',offset:Number(offset),end:Number(end),received:Number(received),error:code};
      if(response)event.status=response.statusCode;
      if(!streamInfo.controller.signal.aborted && transient.has(code) && retries<2 && totalRetries<12) {
        retries++;totalRetries++;
        onEvent({...event,stage:'retry',attempt:retries});
        if(response){discard(response.body);response=undefined;}
        await wait(250*retries,undefined,{signal:streamInfo.controller.signal});
        continue;
      }
      onEvent(event);
      throw error;
    } finally {if(response)discard(response.body);}
    // Buffer at most 8 MB. A failed block never reaches the downstream consumer.
    yield Buffer.concat(parts);
    offset=end+1n;retries=0;
  }
}
