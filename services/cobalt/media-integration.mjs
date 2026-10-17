// Offline integration fixture, executed in the pinned Cobalt image.
import http from 'node:http';
import {readFileSync,writeFileSync} from 'node:fs';
import express from 'express';
import {setupTunnelHandler} from './src/core/itunnel.js';
import {env} from './src/config.js';
import {createInternalStream} from './src/stream/manage.js';
import ffmpeg from './src/stream/ffmpeg.js';
import proxy from './src/stream/proxy.js';
const media={video:readFileSync('/fixtures/video.mp4'),audio:readFileSync('/fixtures/audio.m4a')};
const counts={head:0,get:0};
const upstream=http.createServer((req,res)=>{
  if(req.url==='/redirect'){res.writeHead(302,{Location:'/video'}).end();return;}
  const data=media[req.url.slice(1)];
  if(!data){res.writeHead(404).end();return;}
  if(req.method==='HEAD'){counts.head++;res.writeHead(403,{'Content-Length':'0'}).end();return;}
  counts.get++;
  const range=/^bytes=(\d+)-(\d+)$/.exec(req.headers.range||'');
  const start=range?Number(range[1]):0,end=range?Math.min(Number(range[2]),data.length-1):data.length-1;
  const body=data.subarray(start,end+1);
  res.writeHead(range?206:200,{'Content-Type':req.url==='/video'?'video/mp4':'audio/mp4','Content-Length':String(body.length),...(range?{'Content-Range':`bytes ${start}-${end}/${data.length}`}:{})});
  res.end(body);
});
await new Promise(resolve=>upstream.listen(0,'127.0.0.1',resolve));
const initialPort=env.tunnelPort;
setupTunnelHandler();
while(env.tunnelPort===initialPort)await new Promise(resolve=>setTimeout(resolve,10));
const base=`http://127.0.0.1:${upstream.address().port}`;
const track=name=>createInternalStream(base+'/'+name,{service:'youtube'});
const app=express();
app.get('/redirect',(req,res)=>proxy({urls:base+'/redirect',filename:'track.mp4',service:'youtube'},res));
app.get('/track',(req,res)=>proxy({urls:track('video'),filename:'track.mp4',service:'youtube'},res));
app.get('/clip',(req,res)=>ffmpeg.remux({type:'merge',urls:['video','audio'].map(track),filename:'fixture.mp4',service:'youtube'},res));
const server=await new Promise(resolve=>{const s=app.listen(0,'127.0.0.1',()=>resolve(s));});
const origin=`http://127.0.0.1:${server.address().port}`;
const redirected=await fetch(origin+'/redirect',{signal:AbortSignal.timeout(15000)});
const redirectedBytes=Buffer.from(await redirected.arrayBuffer());
const single=await fetch(origin+'/track',{signal:AbortSignal.timeout(15000)});
const singleBytes=Buffer.from(await single.arrayBuffer());
const response=await fetch(origin+'/clip',{signal:AbortSignal.timeout(15000)});
const result=Buffer.from(await response.arrayBuffer());
writeFileSync('/output/fixture.mp4',result);
console.log(JSON.stringify({http_status:response.status,bytes:result.length,single_track_matches:singleBytes.equals(media.video),redirect_matches:redirectedBytes.equals(media.video),...counts}));
if(process.env.EXPECT_EMPTY==='1')process.exit(result.length===0?0:1);
process.exit(result.length>0 && singleBytes.equals(media.video) && redirectedBytes.equals(media.video)?0:1);
