// Offline end-to-end fixture: real Cobalt signed track tunnels, complete files,
// then seekable local FFmpeg remux. Neither fixture source has faststart metadata.
import http from 'node:http';
import {readFileSync,writeFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import express from 'express';
import ffmpeg from 'ffmpeg-static';
import {setupTunnelHandler} from './src/core/itunnel.js';
import {env} from './src/config.js';
import {verifyStream} from './src/stream/manage.js';
import {createResponse} from './src/processing/request.js';
import stream from './src/stream/stream.js';
await import('./src/processing/services/youtube.js');
const data={video:readFileSync('/fixtures/video.mp4'),audio:readFileSync('/fixtures/audio.m4a')};
const counts={head:0,get:0,rejected_ranges:0};
const upstream=http.createServer((req,res)=>{
  const buffer=data[req.url.slice(1)];if(!buffer){res.writeHead(404).end();return;}
  if(req.method==='HEAD'){counts.head++;res.writeHead(403,{'Content-Length':'0'}).end();return;}
  counts.get++;
  const match=/^bytes=(\d+)-(\d+)$/.exec(req.headers.range||'');
  if(!match){res.writeHead(400).end();return;}
  const start=Number(match[1]),end=Math.min(Number(match[2]),buffer.length-1);
  if(req.url==='/audio'&&end-start+1>65536){counts.rejected_ranges++;res.writeHead(403,{'Content-Length':'0'}).end();return;}
  const part=buffer.subarray(start,end+1);
  res.writeHead(206,{'Content-Length':String(part.length),'Content-Range':`bytes ${start}-${end}/${buffer.length}`,'Content-Type':req.url==='/video'?'video/mp4':'audio/mp4'});res.end(part);
});
await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));
const before=env.tunnelPort;setupTunnelHandler();while(before===env.tunnelPort)await new Promise(resolve=>setTimeout(resolve,10));
const base=`http://127.0.0.1:${upstream.address().port}`;
const app=express();
app.post('/',(req,res)=>{
  const result=createResponse('local-processing',{type:'merge',url:[base+'/video',base+'/audio'],service:'youtube',filename:'fixture.mp4',
    originalRequest:{sourceVideoId:'JCcuOv5y_9g',expectedDuration:15,expectedMediaBytes:data.video.length+data.audio.length}});
  res.status(result.status).json(result.body);
});
app.get('/tunnel',async(req,res)=>{
  const q=req.query;const value=await verifyStream(q.id,q.sig,q.exp,q.sec,q.iv);
  if(!value.service)return res.status(value.status).end();
  return stream(res,value);
});
const server=await new Promise(resolve=>{const s=app.listen(0,'127.0.0.1',()=>resolve(s));});
const origin=`http://127.0.0.1:${server.address().port}`;env.apiURL=origin+'/';
const metadata=await(await fetch(origin,{method:'POST'})).json();
if(metadata.status!=='local-processing'||metadata.expected_duration!==15||metadata.expected_media_bytes!==data.video.length+data.audio.length||metadata.source_video_id!=='JCcuOv5y_9g')throw Error('SOURCE_METADATA_LOST');
const files=[];
for(const [index,url]of metadata.tunnel.entries()){
  if(new URL(url).origin!==origin)throw Error('TUNNEL_ORIGIN');
  const response=await fetch(url,{signal:AbortSignal.timeout(15000)});
  const body=Buffer.from(await response.arrayBuffer());
  if(body.length!==Number(response.headers.get('content-length'))||!body.equals(index===0?data.video:data.audio))throw Error('INCOMPLETE_TRACK');
  const path=`/output/track-${index}.bin`;writeFileSync(path,body);files.push(path);
}
const result=spawnSync(ffmpeg,['-nostdin','-v','error','-y','-i',files[0],'-i',files[1],'-map','0:v:0','-map','1:a:0','-c','copy','-movflags','+faststart','/output/staged.mp4'],{encoding:'utf8',timeout:15000});
if(result.status!==0)throw Error('LOCAL_REMUX_FAILED');
console.log(JSON.stringify({source_duration:metadata.expected_duration,source_bytes:metadata.expected_media_bytes,track_files_match:true,output_bytes:readFileSync('/output/staged.mp4').length,...counts}));
process.exit(0);
