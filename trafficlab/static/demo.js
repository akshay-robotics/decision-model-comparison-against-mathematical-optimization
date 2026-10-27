"use strict";
const canvas=document.getElementById('demo'),ctx=canvas.getContext('2d');
const status=document.getElementById('status'),play=document.getElementById('play'),record=document.getElementById('record');
const names={gurobi:'Gurobi',microsoft:'Microsoft',jev:'Jev 1.13',luna:'Luna', 'sol-medium':'Sol · medium'};
const colors={bg:'#f5f3ed',ink:'#18332e',muted:'#60756b',green:'#34735b',blue:'#5b98c7',orange:'#db9262'};
let data=[],resultImage=new Image(),start=0,playing=false,recorder=null,chunks=[];
function text(value,x,y,size=24,color=colors.ink,weight='400'){ctx.fillStyle=color;ctx.font=`${weight} ${size}px system-ui`;ctx.fillText(value,x,y);}
function round(x,y,w,h,color,r=18){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=color;ctx.fill();}
function metrics(episode,t){let n=0,done=0,total=0;for(const car of episode.demand){if(car.depart>t)continue;n++;if(car.arrival!==null&&car.arrival<=t)done++;total+=Math.max(0,Math.min(t,car.arrival===null?Infinity:car.arrival)-car.depart);}return {done,remaining:78-done,mean:n?total/n:0};}
function frameAt(episode,t){let index=Math.max(0,Math.min(episode.frames.length-1,Math.floor((t-.1)/.5)));return episode.frames[index];}
function road(frame,x,y){
 const size=252,cx=x+size/2,cy=y+size/2,s=1.15;
 round(x,y,size,size,'#eaf0e9',14);ctx.fillStyle='#c5d1c6';ctx.fillRect(cx-12,y,24,size);ctx.fillRect(x,cy-12,size,24);
 ctx.strokeStyle='#f8faf4';ctx.lineWidth=2;ctx.setLineDash([9,7]);ctx.beginPath();ctx.moveTo(cx,y);ctx.lineTo(cx,y+size);ctx.moveTo(x,cy);ctx.lineTo(x+size,cy);ctx.stroke();ctx.setLineDash([]);
 ctx.save();ctx.beginPath();ctx.rect(x,y,size,size);ctx.clip();for(const v of frame.vehicles){ctx.beginPath();ctx.arc(cx+(v.x-100)*s,cy-(v.y-100)*s,4,0,Math.PI*2);ctx.fillStyle=v.kind==='CAV'?colors.orange:colors.blue;ctx.fill();}ctx.restore();
 let phase=frame.signal;ctx.strokeStyle=phase==='YELLOW'?'#d8a63f':phase==='ALL_RED'?'#cc674b':colors.green;ctx.lineWidth=6;ctx.beginPath();if(phase==='NS'){ctx.moveTo(cx,cy-19);ctx.lineTo(cx,cy+19);}else{ctx.moveTo(cx-19,cy);ctx.lineTo(cx+19,cy);}ctx.stroke();
}
function panel(episode,t,index){
 const x=48+(index%3)*620,y=192+Math.floor(index/3)*390;
 round(x,y,584,368,'white');text(names[episode.controller],x+24,y+42,28,colors.ink,'700');
 const frame=frameAt(episode,t),m=metrics(episode,t);road(frame,x+24,y+82);
 const tx=x+306;for(const [label,value,offset] of [['COMPLETED / TOTAL',`${m.done} / 78`,0],['CARS REMAINING',`${m.remaining}`,86],['MEAN SYSTEM TIME',`${m.mean.toFixed(1)} s`,172]]){text(label,tx,y+94+offset,15,colors.muted,'600');text(value,tx,y+139+offset,40,colors.ink,'700');}
}
function replay(t){
 ctx.fillStyle=colors.bg;ctx.fillRect(0,0,1920,1080);
 text('TRAFFIC DECISION LAB / EARLY EXPERIMENT',48,44,18,colors.green,'700');text('Same traffic. Different decisions.',48,104,44,colors.ink,'700');
 text('Revised objective · 15 s planning · 78 cars · seed 7',48,150,24,colors.muted);
 text(`${t.toFixed(1)} / 120 s`,1500,105,40,colors.ink,'700');
 data.forEach((e,i)=>panel(e,t,i));
 const x=1288,y=582;round(x,y,584,368,'#e5ecdf');text('ONE SHARED OBJECTIVE',x+25,y+43,22,colors.green,'700');
 text('Accumulated queues',x+25,y+100,29);text('+ 0.5 × switches',x+25,y+145,29);text('+ 10 × final queue',x+25,y+190,29,colors.green,'700');
 text('Saved SUMO positions · playback 4×',x+25,y+245,20,colors.muted);text('System time: cars scheduled so far.',x+25,y+281,18,colors.muted);text('Remaining includes future scheduled cars.',x+25,y+312,18,colors.muted);
 text('One seed, one episode/model. Traffic outcomes ≠ a general optimization guarantee.',48,1020,22,colors.muted);
 text('Simulations paused during model computation; playback does not represent decision latency.',48,1055,18,colors.muted);
}
function intro(){ctx.fillStyle=colors.bg;ctx.fillRect(0,0,1920,1080);text('EARLY EXPERIMENT / TRAFFIC SIGNAL CONTROL',100,220,24,colors.green,'700');text('Can decision models control',100,370,72,colors.ink,'700');text('traffic lights as well as an optimizer?',100,465,72,colors.ink,'700');text('Microsoft · Jev · Luna · Sol compared with Gurobi in SUMO',100,580,34,colors.muted);text('Same demand. Same timing rules. A revised planning objective.',100,650,34,colors.muted);text('Watch all five saved runs on one simulation clock.',100,810,30,colors.green,'600');text('An early pilot, not evidence of general long-horizon optimization.',100,945,24,colors.muted);}
function draw(seconds){if(seconds<4)intro();else if(seconds<34)replay(Math.min(120,(seconds-4)*4));else ctx.drawImage(resultImage,0,0,1920,1080);}
function finish(){playing=false;draw(42);play.disabled=false;record.disabled=false;if(recorder&&recorder.state==='recording'){recorder.stop();}else status.textContent='Preview complete.';}
function tick(now){if(!playing)return;const elapsed=(now-start)/1000;draw(Math.min(elapsed,42));if(elapsed>=42){finish();return;}requestAnimationFrame(tick);}
function begin(capture){if(playing)return;play.disabled=record.disabled=true;chunks=[];if(capture){
 const types=['video/mp4;codecs="avc1.42E01E"','video/mp4','video/webm;codecs=vp9','video/webm'];const mime=types.find(t=>MediaRecorder.isTypeSupported(t));
 recorder=new MediaRecorder(canvas.captureStream(24),{mimeType:mime,videoBitsPerSecond:1600000});
 recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};recorder.onstop=()=>{const blob=new Blob(chunks,{type:recorder.mimeType}),url=URL.createObjectURL(blob),link=document.getElementById('download');link.href=url;link.download=recorder.mimeType.includes('mp4')?'traffic-demo-recording.mp4':'traffic-demo-recording.webm';link.style.display='inline';const video=document.getElementById('recording');video.src=url;video.hidden=false;status.textContent=`Recording ready · ${(blob.size/1048576).toFixed(1)} MiB · 42 seconds`;recorder.stream.getTracks().forEach(track=>track.stop());};recorder.start(1000);
 }status.textContent=capture?'Recording the browser canvas…':'Playing synchronized saved replays…';start=performance.now();playing=true;requestAnimationFrame(tick);}
play.addEventListener('click',()=>begin(false));record.addEventListener('click',()=>begin(true));
Promise.all([fetch('/demo-data.json').then(r=>{if(!r.ok)throw Error('Published replay data missing');return r.json();}),new Promise((resolve,reject)=>{resultImage.onload=resolve;resultImage.onerror=reject;resultImage.src='/demo-results.png';})]).then(([value])=>{data=value.episodes;window.demoMetricsForValidation=t=>data.map(e=>({controller:e.controller,...metrics(e,t)}));intro();play.disabled=false;record.disabled=typeof MediaRecorder==='undefined'||!canvas.captureStream;status.textContent='Ready · saved results only';}).catch(e=>status.textContent=`Unable to load demo: ${e.message}`);
