const $ = (id) => document.getElementById(id);
const ns='http://www.w3.org/2000/svg';
const controlToken=document.querySelector('meta[name="aqua-control-token"]')?.content||'';
let lastReceive=0,sceneKey='',rowsKey='';
const state = { actionsAllowed:false,pumpQuality:{},agents:[],history:[],pumps: {}, gatewayConnected:false, internetOnline:true, events:[], snapshots:0, delivered:0, queueCount:0, lastExport:null, tick:0 };
const coordinates={
 'PUMP-01':[239,225], 'PUMP-02':[333,268], 'PUMP-03':[427,311],
 'PUMP-04':[614,326], 'PUMP-05':[712,379],
 'PUMP-06':[887,368], 'PUMP-07':[980,413], 'PUMP-08':[1072,458],
};
const int = (x) => x===null||x===undefined?'—':Math.round(Number(x)||0).toLocaleString('en-US');
const clock = (date) => date ? new Date(date).toLocaleTimeString('th-TH',{hour12:false}) : '--:--:--';
function safe(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
let toastTimer;function toast(msg){$('toast').textContent=msg;$('toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('show'),2400)}
async function action(body){if(!state.actionsAllowed||Date.now()-lastReceive>4000)return toast('Controls disabled: read-only or stale viewer');try{const r=await fetch('/api/action',{method:'POST',headers:{'content-type':'application/json','X-Aqua-Control':controlToken},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'Action failed');update(data);if(body.action==='reset')toast('New LAB session requested; previous files stay archived')}catch(e){toast('ERROR: '+e.message)}}

const PIPES=[
  [[70,315],[128,285],[213,315],[304,271],[392,306],[492,266],[589,305],[683,257],[764,289],[837,254],[925,288],[1057,230],[1180,264]],
  [[151,359],[231,321],[309,354],[392,319],[480,359],[567,314],[659,354],[740,316],[856,363],[949,320],[1062,369],[1176,312]],
  [[242,198],[316,161],[443,208],[518,167],[625,214],[709,173],[840,222]],
  [[408,315],[475,341],[528,312],[597,350],[679,313],[772,356],[863,323],[945,363],[1042,330]],
  [[552,94],[568,123],[528,143],[551,159],[620,187],[682,154],[741,181]],
  [[648,118],[692,94],[778,126],[827,98],[907,133],[951,114]],
  [[780,194],[823,214],[889,180],[974,215]],
  [[752,430],[846,389],[937,438],[1045,397],[1159,446]],
  [[883,488],[952,458],[1063,509],[1178,454]],
  [[1085,210],[1085,270],[1000,305],[1055,333]],
];
function pts(a){return a.map(x=>x.join(',')).join(' ')}
function pipeSvg(coords){let p=pts(coords);return `<polyline class="pipe-glow" points="${p}"/><polyline points="${p}" stroke="#04516e" stroke-width="8" fill="none" stroke-linejoin="round" stroke-linecap="round"/><polyline class="pipe-core" points="${p}"/><polyline class="pipe-flow" points="${p}"/>`}
function isoPad(x,y,w=148){return `<g transform="translate(${x} ${y})"><path d="M ${-w*.53} 18 L ${w*.16} -17 L ${w*.56} 8 L ${-w*.15} 46 Z" fill="#071724" opacity=".75" transform="translate(9 13)"/><path d="M ${-w*.53} 15 L ${w*.16} -20 L ${w*.56} 6 L ${-w*.15} 40 Z" fill="url(#baseMetal)" stroke="#42829b" stroke-opacity=".7" stroke-width="1.7"/><path d="M ${-w*.15} 40 L ${w*.56} 6 L ${w*.56} 14 L ${-w*.15} 49 Z" fill="#0a2639" stroke="#11475e"/><path d="M ${-w*.53} 15 L ${-w*.15} 40 L ${-w*.15} 49 L ${-w*.53} 23 Z" fill="#15445c"/></g>`}
function pump(x,y,id,i){let known=typeof state.pumps[id]==='boolean'&&state.pumpQuality[id]==='GOOD';let on=state.pumps[id]===true;let led=!known?'#8795a5':on?'#1cf6b3':'#ff6575';let status=!known?(state.pumpQuality[id]||'UNKNOWN'):on?'RUNNING':'STOPPED';return `<g class="pump-object ${on?'active-pump':'idle-pump'}" data-pump="${id}" tabindex="0" role="button" aria-label="Toggle ${id}, currently ${status}" transform="translate(${x} ${y})"><title>${id} · ${status} · Click to toggle</title>
 <g transform="translate(0 13)"><path d="M-81 12 L-1 -27 L93 11 L9 55 Z" fill="#00131f" opacity=".8" transform="translate(5,13)"/><path d="M-77 10 L3 -29 L92 8 L8 50 Z" fill="url(#baseMetal)" stroke="#3982a1" stroke-width="1.2"/><path d="M8 50 L92 8 L92 19 L8 61 Z" fill="#09273a"/><path d="M-77 10 L8 50 L8 61 L-77 22 Z" fill="#20536a"/>
 <g transform="translate(-3 0) rotate(-27)" filter="url(#motorShadow)">
 <path d="M-50 5 L72 5" stroke="#193f53" stroke-width="16"/><rect x="-63" y="-25" width="21" height="42" rx="3" fill="#2e6982" stroke="#6aa5b3" stroke-width="1.5"/><rect x="-41" y="-19" width="77" height="36" rx="12" fill="url(#bodyMetal)" stroke="#5b8e9c" stroke-width="1"/>
 <g opacity=".8">${[-23,-13,-3,7,17].map(n=>`<path d="M${n} -15V13" stroke="#93c3ca" stroke-width="3.1" opacity=".32"/>`).join('')}</g>
 <ellipse cx="-42" cy="-1" rx="10" ry="21" fill="#36697d" stroke="#77a8b4" stroke-width="2"/><ellipse cx="36" cy="-1" rx="9" ry="18" fill="#1b536b" stroke="#619cb5" stroke-width="2"/><rect x="41" y="-12" width="28" height="24" rx="7" fill="url(#metalShade)" stroke="#4c8798"/><ellipse cx="69" cy="0" rx="9" ry="13" fill="#2c718a" stroke="#78bbca" stroke-width="1.2"/>
 <rect x="-10" y="-31" width="31" height="11" rx="2" fill="#345469" stroke="#6eaec0"/><path d="M1 -31 L9 -40 L15 -31" stroke="#709fb4" stroke-width="3" fill="none"/>
 </g>
 </g>
 <ellipse cx="42" cy="-32" rx="24" ry="12" fill="url(#aura)"/><path d="M42 -16 V-29" stroke="${led}" stroke-width="1.8" opacity=".76"/><ellipse cx="42" cy="-29" rx="11" ry="5.3" fill="#174455" stroke="${led}" stroke-width="3.4" filter="url(#motorShadow)"/><ellipse cx="42" cy="-29" rx="4" ry="2.5" fill="${led}"/>
 <text x="-80" y="69" fill="#6aa9be" font-size="10" letter-spacing="1.2" font-family="Arial">${id}</text>
 </g>`}
function valve(x,y,on=true){let c=on?'#22ddbb':'#e26478';return `<g transform="translate(${x} ${y})"><path d="M0 -17 V-4" stroke="#467b90" stroke-width="3"/><ellipse cy="-18" rx="12" ry="5" fill="#0a3e50" stroke="${c}" stroke-width="3"/><path d="M-7 -18H7" stroke="${c}" stroke-width="1.3"/><circle cx="0" cy="-18" r="2.1" fill="${c}"/></g>`}
function tank(x,y,i){return `<g transform="translate(${x} ${y})" filter="url(#motorShadow)"><path d="M-30 13 L-26 54 Q0 70 28 54 L32 13" fill="url(#water)" stroke="#3984a1" stroke-width="1.6"/><ellipse cx="0" cy="13" rx="31" ry="14" fill="url(#metalShade)" stroke="#62adbb" stroke-width="1.5"/><ellipse cx="0" cy="2" rx="26" ry="10" fill="#19475d" stroke="#73a7b8" stroke-width="2"/><ellipse cx="0" cy="1" rx="13" ry="5.3" fill="#0b3446" stroke="${i===3?'#ff6779':'#13c99d'}" stroke-width="4"/><path d="M-19 49 Q0 60 17 49" stroke="#8cecff" stroke-opacity=".3" fill="none" stroke-width="2"/><path d="M-25 34 L-29 52 M25 34 L29 52" stroke="#081b2b" stroke-width="4"/><text x="-27" y="82" fill="#5d99b3" font-size="10" font-family="Arial">TANK-0${i+1}</text></g>`}
function platform(x,y){return `<g transform="translate(${x},${y})"><path d="M-73 12 L38 -38 L140 12 L25 74Z" fill="#0a2638" stroke="#256584" stroke-width="2"/><path d="M-73 12 L25 74 L25 83 L-73 20 Z" fill="#092033"/><path d="M25 74 L140 12 L140 21 L25 83Z" fill="#123a50"/><path d="M-40 8 L35 -23 L104 11 L26 54Z" fill="#12364e" stroke="#2a607e" stroke-dasharray="4 7" stroke-opacity=".55"/></g>`}
function leader(x,y,label,color='#4bbdd8'){let w=label.length*7+30;return `<g transform="translate(${x},${y})"><path d="M0 0 L21 -19 L45 -19" stroke="${color}" stroke-width="1.4" stroke-opacity=".85" fill="none"/><circle cy="0" r="4.5" fill="#092839" stroke="${color}" stroke-width="1.8"/><rect x="45" y="-34" width="${w}" height="31" rx="2" fill="#12506d" fill-opacity=".92" stroke="#1d7f9e" stroke-opacity=".7"/><circle cx="60" cy="-18" r="5" fill="${color}"/><text x="73" y="-14" fill="#c4f0f7" font-size="12" font-weight="bold" font-family="Arial">${label}</text></g>`}
function renderScene(){
 $('pipeWork').innerHTML = PIPES.map(pipeSvg).join('') + platform(502,223)+platform(927,383)+[valve(390,246,true),valve(507,204,true),valve(742,273,true),valve(1017,330,false),valve(1154,289,true),valve(874,195,true)].join('');
 $('tankLayer').innerHTML = [[541,95],[658,127],[760,165],[869,186]].map(([x,y],i)=>tank(x,y,i)).join('') + leader(1008,199,'FILTRATION ZONE');
 $('pumpLayer').innerHTML = Object.entries(coordinates).map(([id,xy],i)=>pump(xy[0],xy[1],id,i)).join('');
 $('stationLabels').innerHTML=leader(675,303,'MAIN PUMP STATION')+leader(998,487,'BOOSTER STATION');
 document.querySelectorAll('.pump-object').forEach(el=>{const click=()=>{if(!state.actionsAllowed||state.pumpQuality[el.dataset.pump]!=='GOOD')return toast('No fresh simulated runtime / read-only');action({action:'pump',id:el.dataset.pump,on:!state.pumps[el.dataset.pump]})};el.setAttribute('aria-disabled',String(!state.actionsAllowed||state.pumpQuality[el.dataset.pump]!=='GOOD'));el.addEventListener('click',click);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();click()}})});
}
function update(data){
 Object.assign(state,data);lastReceive=Date.now();$('runPercent').textContent=int(state.runPercent);$('sidebarQueue').textContent=int(state.queueCount);$('queueCount').textContent=(state.queueIsPartial?'≥ ':'')+int(state.queueCount);$('totalSnapshots').textContent=int(state.snapshots);$('deliveredCount').textContent=int(state.delivered);$('lastExport').textContent=clock(state.lastExport);$('gatewayBadge').textContent=state.gatewayStatus||'UNKNOWN';$('gatewayBadge').className=state.gatewayConnected?'status-good':'status-bad';$('internetBadge').textContent=state.internetStatus||'UNKNOWN';$('internetBadge').className=state.internetOnline?'status-good':'status-bad';
 $('gatewayToggle').querySelector('span:last-child').textContent=state.gatewayConnected?'DISCONNECT GATEWAY':'CONNECT GATEWAY';$('internetToggle').querySelector('span:last-child').textContent=(state.internetMode==='real'?'EGRESS GATE: ':'SIM NET: ')+(state.gateway?.internetOnline?'UP':'DOWN');
 $('simFlow').textContent=state.flow===null?'—':state.flow+' m³/h';$('simPressure').textContent=state.pressure===null?'—':state.pressure+' MPa';$('simTemp').textContent=state.temperature===null?'—':state.temperature+'°C';$('dataQuality').textContent=state.dataQuality==='GOOD'?'MOCK runtime · real TCP':state.dataQuality||'UNKNOWN';$('modeBadge').textContent=state.readOnly?'READ-ONLY LAB':'SIMULATED RUNTIME';$('telegramMode').textContent=(state.notificationMode||'dry-run').toUpperCase()+' · '+int(state.notificationSent);$('networkQueues').textContent=int(state.scadaQueueCount)+' / '+int(state.gatewayQueueCount);
 for(const agent of state.agents||[]){const life=$(agent.id+'-life');if(!life)continue;life.textContent=agent.online?'ONLINE':'STALE';life.className='pill '+(agent.online?'positive':'stale');$(agent.id+'-detail').textContent='E '+clock(agent.lastExport)+'  Q '+int(agent.pending)+'\nN '+clock(agent.nextExport)+'  ERR '+int(agent.errorCount)}
 for(const id of ['gatewayToggle','internetToggle','exportNow','resetAll','faultAck'])$(id).disabled=!state.actionsAllowed||((id==='internetToggle'||id==='faultAck')&&!state.gatewayConnected);
 const key=JSON.stringify([state.pumps,state.pumpQuality,state.actionsAllowed]);if(key!==rowsKey){rowsKey=key;$('pumpRows').innerHTML=Object.entries(state.pumps).map(([id,on])=>{const q=state.pumpQuality[id]||'UNKNOWN',good=q==='GOOD';return `<button class="pump-row ${!good?'unknown':on?'':'stopped'}" data-id="${safe(id)}" ${!state.actionsAllowed||!good?'disabled':''} title="Simulated runtime only · ${safe(q)}"><span class="disc">${!good?'?':on?'✓':'×'}</span><div><b>${safe(id)}</b><small>${!good?safe(q):on?'RUNNING':'STOPPED'}</small></div></button>`}).join('');document.querySelectorAll('.pump-row').forEach(x=>x.addEventListener('click',()=>action({action:'pump',id:x.dataset.id,on:!state.pumps[x.dataset.id]})))}
 $('events').innerHTML=(state.events||[]).slice(0,30).map(ev=>`<div class="event"><span class="event-time">${clock(ev.time)}</span><span class="event-kind ${safe(ev.kind)}">${safe(ev.kind)}</span><span class="event-text">${safe(ev.message)}</span></div>`).join('');
 if(key!==sceneKey){sceneKey=key;renderScene()}drawChart();renderDiagnostics();
}
function drawChart(){const svg=$('chart'),points=state.history||[];let o='';for(let i=0;i<=5;i++){const y=14+i*35;o+=`<line x1="48" y1="${y}" x2="920" y2="${y}" stroke="#14425b" stroke-width="1" opacity=".65"/><text x="11" y="${y+4}" fill="#547e91" font-size="10">${(1-i*.2).toFixed(1)}</text>`}
 if(!points.length){svg.innerHTML=o+'<text x="60" y="110" fill="#7399ad" font-size="13">Waiting for fresh Agent runtime — no fabricated samples</text>';return}
 for(const [field,max,color] of [['flow',40,'#10e1d5'],['pressure',.6,'#ff9d62']]){const line=points.map((p,i)=>`${i?'L':'M'}${(48+i*870/Math.max(1,points.length-1)).toFixed(1)},${(189-Math.min(1,p[field]/max)*175).toFixed(1)}`).join(' ');o+=`<path d="${line}" fill="none" stroke="${color}" stroke-width="2.2"/>`}
 for(let i=0;i<Math.min(9,points.length);i++){const index=Math.round(i*(points.length-1)/Math.max(1,Math.min(8,points.length-1)));o+=`<text x="${48+i*870/Math.max(1,Math.min(8,points.length-1))}" y="207" fill="#4d8197" font-size="9" text-anchor="middle">${clock(points[index].at)}</text>`}svg.innerHTML=o;
}
function renderDiagnostics(){
 const expanded=[...$('diagnosticsBody').querySelectorAll('details')].map(x=>x.open);
 $('verificationProof').textContent=(state.verificationLevel||'NOT VERIFIED')+' · '+state.transport+' · '+(state.gatewayEndpoint||'ENROLLED ENDPOINT')+' · SIMULATED RUNTIME · no PLC/WinCC access';
 $('diagnosticsBody').innerHTML=`<table class="diagnostic-table"><thead><tr><th>Agent / PID</th><th>Last seen</th><th>Export / Next</th><th>Queue / In-flight / ACKed</th><th>Retry / Errors</th><th>LAN / Auth</th><th>Last ACK</th><th>Disk</th></tr></thead><tbody>${(state.agents||[]).map(a=>`<tr><td>${safe(a.id)} / ${int(a.pid)} ${a.online?'ONLINE':'STALE'}</td><td>${clock(a.lastSeen)}</td><td>${clock(a.lastExport)} / ${clock(a.nextExport)}</td><td>${int(a.pending)} / ${int(a.inFlight)} / ${int(a.acked)}</td><td>${int(a.retryCount)} / ${int(a.errorCount)}</td><td>${safe(a.lanState||'UNKNOWN')} / ${a.gatewayAuthenticated?'LAST AUTH OK':'NOT AUTHENTICATED'}</td><td>${clock(a.lastAckAt)}</td><td>${a.disk?int(a.disk.bytes/1024)+' KiB':'—'}</td></tr>`).join('')}</tbody></table><p>GW RECEIVED ${int(state.gateway?.received)} · DUPLICATES ${int(state.gateway?.duplicates)}</p><p>SOURCE QUEUE ${int(state.scadaQueueCount)} · GATEWAY QUEUE ${int(state.gatewayQueueCount)} · UPSTREAM DELIVERED ${int(state.delivered)} · NOTIFICATION ${int(state.notificationSent)} (${safe(state.notificationMode)})</p><p>Gateway egress: ${safe(state.internetStatus)} / ${safe(state.internetMode)} · Intake and outbound are independent. Last-known pump values are never converted to OFF when stale.</p><details><summary>Latest Runtime snapshots / schema evidence</summary><pre>${safe(JSON.stringify((state.agents||[]).map(a=>({id:a.id,latest:a.latest?JSON.parse(a.latest):null,error:a.lastError})),null,2))}</pre></details><details><summary>Actual notification records</summary><pre>${safe(JSON.stringify(state.gateway?.messages||[],null,2))}</pre></details>`;
 $('diagnosticsBody').querySelectorAll('details').forEach((x,i)=>x.open=expanded[i]===true);
}
$('gatewayToggle').onclick=()=>action({action:'gateway',connected:!state.gatewayConnected});
$('internetToggle').onclick=()=>action({action:'internet',online:!state.gateway?.internetOnline});
$('exportNow').onclick=()=>action({action:'export'});
$('resetAll').onclick=()=>{if(confirm('Start a new LAB session? Current queues and files remain archived; no original data is deleted'))action({action:'reset'})};
$('diagnostics').onclick=()=>$('diagnosticsDialog').showModal();$('closeDiagnostics').onclick=()=>$('diagnosticsDialog').close();$('faultAck').onclick=()=>action({action:'fault'});
$('help').onclick=()=>$('aboutDialog').showModal();$('closeDialog').onclick=()=>$('aboutDialog').close();
let view={scale:1,x:0,y:0},drag=null;const world=$('world');function setView(){world.style.transform=`translate(${view.x}px,${view.y}px) scale(${view.scale})`}
const svg=$('plantSvg');svg.addEventListener('pointerdown',e=>{if(e.target.closest('.pump-object'))return;drag={x:e.clientX,y:e.clientY,startX:view.x,startY:view.y};svg.setPointerCapture(e.pointerId)});
svg.addEventListener('pointermove',e=>{if(!drag)return;const r=svg.getBoundingClientRect();view.x=drag.startX+(e.clientX-drag.x)*1260/r.width;view.y=drag.startY+(e.clientY-drag.y)*620/r.height;setView()});
svg.addEventListener('pointerup',()=>drag=null);svg.addEventListener('pointercancel',()=>drag=null);
svg.addEventListener('wheel',e=>{e.preventDefault();view.scale=Math.max(.65,Math.min(2,view.scale+(e.deltaY<0?.08:-.08)));setView()},{passive:false});
$('resetCam').onclick=()=>{view={scale:1,x:0,y:0};setView()};
function tickClock(){$('clock').textContent=new Date().toLocaleTimeString('th-TH',{hour12:false});$('footerDate').textContent=new Date().toLocaleDateString('en-GB');}
tickClock();setInterval(()=>{tickClock();if(lastReceive&&Date.now()-lastReceive>4000){$('modeBadge').textContent='VIEW STALE · LAST VALUES';for(const id of ['gatewayToggle','internetToggle','exportNow','resetAll','faultAck'])$(id).disabled=true}},1000);
fetch('/api/status').then(r=>r.json()).then(update).catch(()=>toast('Failed to reach local simulator'));
const stream=new EventSource('/api/events');stream.onmessage=e=>{try{update(JSON.parse(e.data))}catch{}};
stream.onerror=()=>toast('Reconnecting to local simulator...');
