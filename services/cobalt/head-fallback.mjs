// Source-bound compatibility patches for the pinned upstream image.
// Upstream Cobalt is AGPL-3.0; source: https://github.com/imputnet/cobalt.
import {registerHooks} from 'node:module';
import {createHash} from 'node:crypto';
const modules={internal:'stream/internal.js',proxy:'stream/proxy.js',youtube:'processing/services/youtube.js',response:'processing/request.js'};
const hashes={
  youtube:'d97a39a2902db5fd1839713591e76f06a7ef861d03c61b2ba9a4b15440ca148c',
  response:'f96d5d50f1c48ce7133c8f2746138c84e9be2a953bbd0a4d7dec6a5506f8d58f',
  internal:'f7a94b5a146381e980dfc92e744c8555112182404d84d5491905cc9c47c7bdfd',
  proxy:'06bb012ed78ca51d8c6258a057f85e38809224d4b7ce27462e8af8e3648b8427',
};
const requestShim=`
// This image requires the supported redirect interceptor, not maxRedirections.
const request = (url, options) => {
  const {maxRedirections, ...rest} = options;
  if (maxRedirections) {
    rest.dispatcher = (rest.dispatcher || getGlobalDispatcher()).compose(
      interceptors.redirect({maxRedirections})
    );
  }
  return undiciRequest(url, rest);
};
`;
export function transformSource(source,kind) {
  source=Buffer.isBuffer(source)||source instanceof Uint8Array?Buffer.from(source).toString('utf8'):source;
  if(!hashes[kind]||createHash('sha256').update(source).digest('hex')!==hashes[kind]) {
    throw Error('COBALT_MEDIA_PATCH_SOURCE_MISMATCH');
  }
  if(kind==='youtube') {
    const marker='const originalRequest = {\n        ...o,';
    if(!source.includes(marker))throw Error('COBALT_SOURCE_METADATA_CONTEXT_MISMATCH');
    return source.replace(marker,marker+`
        sourceVideoId: String(basicInfo.id),
        expectedDuration: Number(basicInfo.duration),
        expectedMediaBytes: Number(video?.content_length || 0) + Number(audio?.content_length || 0),`);
  }
  if(kind==='response') {
    const marker='status: responseType,\n                ...response';
    if(!source.includes(marker))throw Error('COBALT_RESPONSE_METADATA_CONTEXT_MISMATCH');
    return source.replace(marker,marker+`,
                source_video_id: responseData?.originalRequest?.sourceVideoId,
                expected_duration: responseData?.originalRequest?.expectedDuration,
                expected_media_bytes: responseData?.originalRequest?.expectedMediaBytes`);
  }
  const originalImport=kind==='proxy'?'import { Agent, request } from "undici";':'import { request } from "undici";';
  if(!source.includes(originalImport))throw Error('COBALT_MEDIA_PATCH_IMPORT_MISMATCH');
  source=source.replace(originalImport,
    'import { '+(kind==='proxy'?'Agent, ':'')+'request as undiciRequest, getGlobalDispatcher, interceptors } from "undici";'+requestShim);
  if(kind==='internal') {
    const chunkStart=source.indexOf('async function* readChunks(');
    const chunkEnd=source.indexOf('async function handleChunkedStream(',chunkStart);
    if(chunkStart<0||chunkEnd<chunkStart)throw Error('COBALT_CHUNK_PATCH_CONTEXT_MISMATCH');
    source="import {readMediaChunks} from 'file:///bridge/media-chunks.mjs';\n"+source.slice(0,chunkStart)+
      'async function* readChunks(streamInfo,size) { yield* readMediaChunks(streamInfo,size,{request,getHeaders}); }\n\n'+source.slice(chunkEnd);
    const start=source.indexOf('let req, attempts = 3;');
    const end=source.indexOf('const generator = readChunks(streamInfo, size);',start);
    if(start<0||end<start)throw Error('COBALT_MEDIA_PATCH_CONTEXT_MISMATCH');
    source="import {probeMedia} from 'file:///bridge/media-probe.mjs';\n"+
      source.slice(0,start)+
      'const probe = await probeMedia(streamInfo, {fetch,getHeaders});\n'+
      '        if (!probe) return cleanup();\n'+
      '        const {req,size} = probe;\n\n        '+source.slice(end);
  }
  return source;
}
registerHooks({load(url,context,nextLoad){
  const loaded=nextLoad(url,context);
  for(const kind of Object.keys(hashes)) {
    if(url===`file:///app/src/${modules[kind]}`)return {...loaded,source:transformSource(loaded.source,kind)};
  }
  return loaded;
}});
