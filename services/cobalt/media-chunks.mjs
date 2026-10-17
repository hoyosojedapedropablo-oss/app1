// Read validated byte ranges; never treat an upstream error page as media.
const MIN_CHUNK=65536n;
const SIZES=[8000000n,1048576n,MIN_CHUNK];
function discard(body) {
  body.on('error',()=>{});
  body.destroy();
}
export async function* readMediaChunks(streamInfo,size,{request,getHeaders}) {
  if(typeof size!=='bigint'||size<=0n||size>12n*1024n**3n)throw Error('MEDIA_SIZE_INVALID');
  let offset=0n,level=0;
  while(offset<size) {
    if(streamInfo.controller.signal.aborted)throw Error('MEDIA_ABORTED');
    const end=offset+SIZES[level]-1n<size?offset+SIZES[level]-1n:size-1n;
    const response=await request(streamInfo.url,{
      headers:{...getHeaders(streamInfo.service),Range:`bytes=${offset}-${end}`},
      dispatcher:streamInfo.dispatcher,signal:streamInfo.controller.signal,maxRedirections:4
    });
    if(response.statusCode===403 && level<SIZES.length-1 && end-offset+1n>MIN_CHUNK) {
      discard(response.body);
      do {level++;} while(level<SIZES.length-1 && SIZES[level]>=end-offset+1n);
      continue;
    }
    const match=/^bytes ([0-9]+)-([0-9]+)\/([0-9]+)$/.exec(String(response.headers['content-range']||''));
    const length=String(response.headers['content-length']||'');
    const expected=end-offset+1n;
    if(response.statusCode!==206||!match||BigInt(match[1])!==offset||BigInt(match[2])!==end||BigInt(match[3])!==size||!/^\d+$/.test(length)||BigInt(length)!==expected) {
      discard(response.body);throw Error('MEDIA_RANGE_REJECTED');
    }
    let received=0n;
    try {
      for await(const chunk of response.body) {
        received+=BigInt(chunk.length);
        if(received>expected)throw Error('MEDIA_RANGE_OVERSIZED');
        yield chunk;
      }
      if(received!==expected)throw Error('MEDIA_RANGE_TRUNCATED');
    } finally {discard(response.body);}
    offset=end+1n;
  }
}
