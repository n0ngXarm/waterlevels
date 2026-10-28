import http from 'node:http';import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {timingSafeEqual} from 'node:crypto';
import {answer,readBody,requestJSON,loopback} from './protocol.js';import {GROUPS} from './store.js';
const publicDir=path.resolve(fileURLToPath(new URL('../../public/',import.meta.url)));
const tokenEqual=(a,b)=>typeof a==='string'&&typeof b==='string'&&Buffer.byteLength(a)===Buffer.byteLength(b)&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
export function createDashboard(config,{onControl=null,headless=false}={}){
 if(!loopback(config.listen.host))throw Error('Dashboard stays loopback-only; use an approved local viewer per LAB host');
 if(!/^[A-Za-z0-9_-]{16,128}$/.test(config.controlToken))throw Error('Invalid local control token');
 const app={config,port:null,clients:new Set(),cache:new Map(),history:[],lastPoint:null,polling:null,stopped:false};
 app.status=()=>{
  const agents=config.agents.map(c=>app.cache.get(c.id)||{id:c.id,pumps:null,online:false,lastSeen:null,pending:null,snapshots:null,acked:null,lastError:'Awaiting enrolled service'});
  const gateway=app.cache.get('PC-04')||{id:'PC-04',online:false,pending:null,received:null,upstreamDelivered:0,internetOnline:false,messages:[]},central=app.cache.get('CENTRAL-LAB')||{id:'CENTRAL-LAB',online:false};
  const pumps={},pumpQuality={};for(const a of agents)for(const id of GROUPS[a.id]){pumps[id]=typeof a.pumps?.[id]==='boolean'?a.pumps[id]:null;pumpQuality[id]=pumps[id]===null?'UNKNOWN':a.online?'GOOD':'STALE'}
  const sum=field=>agents.some(a=>typeof a[field]==='number')?agents.reduce((n,a)=>n+(a[field]??0),0):null;
  const full=agents.every(a=>a.online)&&Object.keys(pumps).length===8&&Object.values(pumps).every(v=>typeof v==='boolean'),run=Object.values(pumps).filter(x=>x===true).length,lastExport=agents.map(a=>a.lastExport).filter(Boolean).sort().at(-1)||null;
  const flow=full?+(run*4.06).toFixed(2):null,pressure=full?+(run*.084).toFixed(3):null,temp=full?24.6:null;
  const events=[...agents,gateway].flatMap(a=>(a.logs||[]).map(e=>({...e,id:a.id+':'+e.id,message:a.id+' · '+e.message}))).sort((a,b)=>b.time.localeCompare(a.time)).slice(0,100);
  const source=sum('pending');
  return {profile:config.profile||'legacy',simulation:agents.every(a=>a.simulated!==false),transport:'real-tcp',verificationLevel:config.controlMode==='single'?'TESTED ON ONE HOST':'LAN CONFIGURED / TWO HOSTS NOT VERIFIED',gatewayEndpoint:loopback(new URL(config.gateway.url).hostname)?config.gateway.url:'ENROLLED LAB ENDPOINT (REDACTED)',actionsAllowed:config.controlMode==='single'&&!config.readOnly&&!!onControl,readOnly:!!config.readOnly,dashboardPid:process.pid,time:new Date().toISOString(),generation:config.generation,agents,gateway,central,pumps,pumpQuality,dataQuality:full?'GOOD':'STALE / UNKNOWN',runPercent:full?Math.round(run/8*100):null,flow,pressure,temperature:temp,history:app.history,events,snapshots:sum('snapshots'),tick:Math.max(0,...agents.map(a=>a.sequence||0)),scadaQueueCount:source,gatewayQueueCount:gateway.pending,queueCount:source===null?null:source+(gateway.pending||0),queueIsPartial:!full||!gateway.online,acked:sum('acked'),delivered:gateway.upstreamDelivered??null,notificationSent:gateway.notificationSent??null,notificationPending:gateway.notificationPending??null,notificationMode:gateway.notificationMode||'dry-run',lastExport,lastDelivery:gateway.lastDelivery||null,gatewayConnected:gateway.online===true,gatewayStatus:gateway.online?'GATEWAY_AUTHENTICATED':'UNAVAILABLE',internetOnline:gateway.online&&['VERIFIED','SIMULATED_AVAILABLE'].includes(gateway.egress?.status),internetStatus:gateway.egress?.status||'UNKNOWN',internetMode:gateway.internetMode||'simulated',exportIntervalSeconds:(config.intervalMs||5000)/1000};
 };
 app.poll=async()=>{
  await Promise.all([...config.agents.map(c=>({...c,identity:c.id})),{...config.gateway,id:'PC-04',identity:'DASHBOARD'},...(config.central?[{...config.central,id:'CENTRAL-LAB',identity:'DASHBOARD'}]:[])].map(async c=>{
   try{const status=await requestJSON(c.url,'/v1/status',{id:c.identity,secret:c.secret},{},{...config,timeoutMs:700});app.cache.set(c.id,{...status,online:true,lastSeen:new Date().toISOString()})}
   catch{const old=app.cache.get(c.id);app.cache.set(c.id,{...old,id:c.id,online:false,lastError:'Enrolled service unavailable; values may be stale'})}
  }));
  const state=app.status();if(state.lastExport&&state.lastExport!==app.lastPoint&&state.dataQuality==='GOOD'){app.history.push({at:state.lastExport,flow:state.flow,pressure:state.pressure});app.history=app.history.slice(-60);app.lastPoint=state.lastExport}
  const frame=`data: ${JSON.stringify(app.status())}\n\n`;for(const client of app.clients)if(!client.write(frame))client.end();
 };
 app.action=async body=>{
  if(config.profile==='readonly'&&body?.action==='recording'){if(typeof body.running!=='boolean'||Object.keys(body).some(k=>!['action','running'].includes(k)))throw Error('Only local recording boolean allowed');await Promise.all(config.agents.map(a=>requestJSON(a.url,'/v1/recording',{id:a.id,secret:a.secret},{running:body.running},config)));await app.poll();return app.status()}
  if(config.readOnly||config.controlMode!=='single'||!onControl)throw Object.assign(Error('Read-only / non-simulation controls are disabled'),{status:403});
  if(!body||typeof body.action!=='string')throw Error('Invalid LAB action');
  if(body.action==='gateway'){if(typeof body.connected!=='boolean')throw Error('Boolean required');await onControl(body)}
  else if(body.action==='reset'){await onControl(body);return {...app.status(),resetting:true}}
  else if(body.action==='pump'){
   if(typeof body.on!=='boolean')throw Error('Boolean required');const id=Object.keys(GROUPS).find(id=>GROUPS[id].includes(body.id));if(!id)throw Error('Unknown simulated pump');const a=config.agents.find(a=>a.id===id);await requestJSON(a.url,'/v1/sim/pump',{id:a.id,secret:a.secret},{id:body.id,on:body.on},config);
  }else if(body.action==='internet'){if(typeof body.online!=='boolean')throw Error('Boolean required');await requestJSON(config.gateway.url,'/v1/sim/internet',{id:'DASHBOARD',secret:config.gateway.secret},{online:body.online},config)}
  else if(body.action==='export')await Promise.all(config.agents.map(a=>requestJSON(a.url,'/v1/sim/export',{id:a.id,secret:a.secret},{},config)));
  else if(body.action==='fault')await requestJSON(config.gateway.url,'/v1/sim/fault',{id:'DASHBOARD',secret:config.gateway.secret},{dropNextAck:true},config);
  else throw Error('Unknown LAB action');
  await app.poll();return app.status();
 };
 app.server=headless?null:http.createServer(async(req,res)=>{
  const valid=[`127.0.0.1:${app.port}`,`localhost:${app.port}`];if(!valid.includes(req.headers.host))return answer(res,403,{error:'Local Host required'});
  try{
   const url=new URL(req.url,'http://localhost');
   if(req.method==='GET'&&url.pathname==='/api/status')return answer(res,200,app.status());
   if(req.method==='GET'&&/^\/api\/download\/PC-0[123]\.(jsonl|csv)$/.test(url.pathname)){
    const id=url.pathname.split('/').at(-1).split('.')[0],a=config.agents.find(a=>a.id===id);if(!a)return answer(res,404,{error:'Unknown enrolled source'});
    const result=await requestJSON(a.url,'/v1/exports',{id:a.id,secret:a.secret},{},config);
    if(url.pathname.endsWith('.csv')){const lines=['recorded_at;observed_at;tag_name;raw_value;quality_code;read_error;quality'];for(const event of result.records.filter(e=>e.schema_version===2&&e.kind==='SNAPSHOT'))for(const [tag,o] of Object.entries(event.observations))lines.push([event.at,event.observed_at,tag,o.raw_value??'',o.quality_code??'',o.read_error,o.quality].join(';'));res.writeHead(200,{'content-type':'text/csv; charset=utf-8','content-disposition':`attachment; filename="AQUA-${id}.csv"`,'cache-control':'no-store','x-content-type-options':'nosniff'});return res.end(lines.join('\r\n')+'\r\n')}
    res.writeHead(200,{'content-type':'application/x-ndjson','content-disposition':`attachment; filename="AQUA-${id}.jsonl"`,'cache-control':'no-store','x-content-type-options':'nosniff'});return res.end(result.records.map(r=>JSON.stringify(r)).join('\n')+'\n');
   }
   if(req.method==='GET'&&url.pathname==='/api/events'){if(app.clients.size>=20)return answer(res,503,{error:'Viewer limit'});res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});app.clients.add(res);req.once('close',()=>app.clients.delete(res));res.write(`data: ${JSON.stringify(app.status())}\n\n`);return}
   if(req.method==='POST'&&url.pathname==='/api/action'){
    if(!tokenEqual(req.headers['x-aqua-control'],config.controlToken)||(req.headers.origin&&req.headers.origin!==`http://${req.headers.host}`))return answer(res,403,{error:'Local control authorization required'});
    return answer(res,200,await app.action(JSON.parse(await readBody(req))));
   }
   if(req.method!=='GET')return answer(res,405,{error:'GET required'});
   const resource=url.pathname==='/'?(config.profile==='readonly'?'simple.html':'index.html'):url.pathname==='/advanced'?'index.html':decodeURIComponent(url.pathname).slice(1),file=path.resolve(publicDir,resource);
   if(!file.startsWith(publicDir+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile())return answer(res,404,{error:'Not found'});
   let content=fs.readFileSync(file);if(['index.html','simple.html'].includes(resource))content=Buffer.from(content.toString().replace('</head>',`<meta name="aqua-control-token" content="${config.controlToken}"></head>`));
   const type={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}[path.extname(file)]||'application/octet-stream';
   res.writeHead(200,{'content-type':type,'cache-control':'no-store','x-content-type-options':'nosniff','content-security-policy':"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"});res.end(content);
  }catch(e){answer(res,e.status||400,{error:e.status===403?e.message:'LAB request failed; check enrolled service status'})}
 });
 app.start=async()=>{if(!headless){await new Promise((r,j)=>{app.server.once('error',j);app.server.listen(config.listen.port,config.listen.host,r)});app.port=app.server.address().port;}await app.poll();app.timer=setInterval(()=>{if(!app.polling){app.polling=app.poll().catch(()=>{}).finally(()=>app.polling=null)}},500);return app};
 app.close=async()=>{app.stopped=true;clearInterval(app.timer);if(app.polling)await app.polling;for(const res of app.clients)res.end();app.clients.clear();if(app.server?.listening)await new Promise(r=>app.server.close(r))};return app;
}
