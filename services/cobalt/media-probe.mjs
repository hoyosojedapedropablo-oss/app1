// Compatible HTTP metadata probe for a server that rejects HEAD but serves GET.
const MAX_BYTES = 12n * 1024n ** 3n;
function positiveSize(value) {
  if (typeof value !== 'string' || !/^[0-9]{1,14}$/.test(value)) return null;
  const size = BigInt(value);
  return size > 0n && size <= MAX_BYTES ? size : null;
}
function normalize(response, size) {
  if (!size) return null;
  const headers = new Headers();
  headers.set('content-length', String(size));
  const type = response.headers.get('content-type');
  if (type) headers.set('content-type',type);
  return {req:{status:200,headers},size};
}
async function discard(response) {
  try { await response.body?.cancel(); } catch {}
}
export async function probeMedia(streamInfo, {fetch,getHeaders}) {
  for(let attempt=0;attempt<3;attempt++) {
    const options={headers:getHeaders(streamInfo.service),dispatcher:streamInfo.dispatcher,
      signal:streamInfo.controller.signal};
    const head=await fetch(streamInfo.url,{...options,method:'HEAD'});
    if (head.url) streamInfo.url=head.url;
    let result=head.status===200?normalize(head,positiveSize(head.headers.get('content-length'))):null;
    await discard(head);
    if(result)return result;
    let status=head.status;
    if([200,403,405,501].includes(head.status)) {
      const get=await fetch(streamInfo.url,{...options,method:'GET',
        headers:{...getHeaders(streamInfo.service),Range:'bytes=0-0'}});
      status=get.status;
      let size=null;
      if(get.status===206) {
        const match=/^bytes 0-0\/([0-9]+)$/.exec(get.headers.get('content-range')||'');
        if(match && get.headers.get('content-length')==='1')size=positiveSize(match[1]);
      } else if(get.status===200) {
        size=positiveSize(get.headers.get('content-length'));
      }
      if(get.url)streamInfo.url=get.url;
      result=normalize(get,size);
      await discard(get);
      if(result)return result;
    }
    // Preserve Cobalt's existing signed-link refresh, without bypassing a GET denial.
    if(status===403 && streamInfo.transplant && attempt<2) {
      await streamInfo.transplant(streamInfo.dispatcher);
    } else return null;
  }
  return null;
}
