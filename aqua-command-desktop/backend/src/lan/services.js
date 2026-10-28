import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import {randomBytes} from 'node:crypto';
import {endpoint,authenticate,answer,readBody,requestJSON,digest,encode,loopback} from './protocol.js';
import {Store,GROUPS} from './store.js';
import {TelegramTransport} from './telegram.js';
import {runtimeAdapter} from './adapters.js';

// A bounded, recent retained-history view; callers must disclose truncation.
export function retainedExport(store){
 const totalRecords=Number(store.db.prepare('SELECT count(*) n FROM records').get().n),rows=store.db.prepare('SELECT payload FROM records ORDER BY seq DESC LIMIT 2000').all(),records=[];let bytes=0;
 for(const r of rows){const size=Buffer.byteLength(r.payload);if(bytes+size>250000)break;bytes+=size;records.push(JSON.parse(r.payload))}
 return {records:records.reverse(),totalRecords,truncated:records.length<totalRecords,bytes};
}

function serverFor(config,store,keys,handle){
 const scheme=config.tls?'https':'http';endpoint(`${scheme}://${config.listen.host}:${config.listen.port}`,config);
 const handler=async(req,res)=>{
  let auth=null;
  try{
   if(req.method==='GET'&&req.url==='/health')return answer(res,200,{id:config.id,role:config.role,protocol:1,simulated:true});
   if(req.method!=='POST')return answer(res,405,{error:'POST required'});
   const raw=await readBody(req);auth=authenticate(req,raw,keys,store);const body=JSON.parse(raw);
   const result=await handle(req.url,body,auth.id);answer(res,200,result,auth);
  }catch(e){if(e.dropAck){req.socket.destroy();return}answer(res,e.status||400,{error:e.status?e.message:'LAB service/storage operation failed'},auth)}
 };
 const server=config.tls?https.createServer({key:fs.readFileSync(config.tls.keyFile),cert:fs.readFileSync(config.tls.certFile)},handler):http.createServer(handler);
 server.requestTimeout=5000;server.headersTimeout=5000;
 return server;
}
async function open(app){await new Promise((resolve,reject)=>{app.server.once('error',reject);app.server.listen(app.config.listen.port,app.config.listen.host,resolve)});app.port=app.server.address().port;return app}
async function close(app){app.stopped=true;clearInterval(app.timer);clearInterval(app.exportTimer);if(app.busy)await app.busy.catch(()=>{});await new Promise(r=>app.server.close(r));app.store.close()}

export function createAgent(config){
 if(!GROUPS[config.id]||!/^([a-f0-9]{64})$/.test(config.secret)||!Number.isFinite(config.intervalMs??5000)||(config.intervalMs??5000)<50)throw Error('Invalid enrolled agent configuration');
 endpoint(config.gatewayUrl,config);
 const candidates=config.gatewayUrls||[config.gatewayUrl];if(!Array.isArray(candidates)||!candidates.length||candidates.length>8||new Set(candidates).size!==candidates.length)throw Error('At most8 explicit enrolled Gateway endpoints required');for(const u of candidates)endpoint(u,config);
 const checkedSource=config.sourceAdapter==='wincc-csv'?runtimeAdapter('wincc-csv',null,config.id,config):null;
 const app={config,store:new Store(config.dataDir,config.storage),port:null,stopped:false,lastError:null,spoolError:null,errorCount:0,lanState:'DISCONNECTED',gatewayAuthenticated:false,session:null,sessionExpires:0,nextRetry:0,retryCount:0,nextExport:Date.now(),busy:null};
 app.selectedGatewayUrl=config.gatewayUrl;app.nextRetry=app.store.get('retryAt',0);app.retryCount=app.store.get('consecutiveFailures',0);app.errorCount=app.store.get('errorCount',0);
 try{app.source=checkedSource||runtimeAdapter(config.sourceAdapter||'simulated-runtime',app.store,config.id,config);if(checkedSource)checkedSource.store=app.store}catch(e){app.store.close();throw e}if(!app.source.available){app.store.close();throw Error('WinCC source unavailable until separately approved')}
 app.sample=()=>app.source.kind==='wincc-csv'?app.source.capture():app.store.append(config.id,'SNAPSHOT',app.source.read());
 app.setPump=(id,on)=>{
  if(app.source.readOnly)throw Object.assign(Error('Runtime source is read-only; commands forbidden'),{status:403});
  const pumps=app.store.pumps(config.id);if(!Object.hasOwn(pumps,id)||typeof on!=='boolean')throw Error('Invalid simulated pump command');
  const before=pumps[id];if(before===on)return {changed:false};pumps[id]=on;
  return {changed:true,event:app.store.append(config.id,'STATE_CHANGE',pumps,{tag_name:id,before,value:on})};
 };
 app.status=()=>({id:config.id,role:'agent',pid:process.pid,simulated:app.source.simulated,readOnly:app.source.readOnly===true||config.readOnly===true,sourceAdapter:app.source.kind,recording:!app.store.get('recordingPaused',false),observedAt:app.store.get('runtimeObservedAt'),observations:app.store.get('runtimeObservations',{}),...app.store.stats(),pumps:app.source.readOnly?app.store.get('pumps',Object.fromEntries(config.csv.tags.map(tag=>[tag,null]))):app.store.pumps(config.id),nextExport:new Date(app.nextExport).toISOString(),errorCount:app.errorCount,retryCount:app.store.get('retryCount',0),inFlight:app.store.get('inFlight',0),nextRetryAt:app.store.get('retryAt',0),lanState:app.lanState,gatewayAuthenticated:app.gatewayAuthenticated,gatewayAddress:new URL(app.selectedGatewayUrl).host,lastError:app.spoolError||app.lastError,disk:app.store.disk(),logs:app.store.logs()});
 app.server=serverFor(config,app.store,{[config.id]:config.secret},async(route,body)=>{
  if(route==='/v1/status')return app.status();
  if(route==='/v1/sim/pump'){if(config.readOnly||app.source.readOnly)throw Object.assign(Error('Read-only source; commands forbidden'),{status:403});return app.setPump(body.id,body.on)}
  if(route==='/v1/recording'){if(!app.source.readOnly||typeof body.running!=='boolean')throw Object.assign(Error('Local recording boolean required'),{status:400});app.store.set('recordingPaused',!body.running);return {ok:true,recording:body.running}}
  if(route==='/v1/exports')return retainedExport(app.store);
  if(route==='/v1/sim/export'){if(config.readOnly||app.source.readOnly)throw Object.assign(Error('Read-only LAB'),{status:403});return app.sample()}
  throw Object.assign(Error('Unknown route'),{status:404});
 });
 app.exportDue=()=>{
  if(app.source.readOnly&&app.store.get('recordingPaused',false))return;
  if(Date.now()>=app.nextExport){try{app.sample();app.spoolError=null;app.nextExport=Date.now()+(config.intervalMs??5000)}catch(e){app.spoolError=app.source.readOnly?'Read-only input/storage error: '+e.message:'Local spool/storage quota failure; unACKed data retained';app.errorCount++;try{app.store.set('errorCount',app.errorCount)}catch{}app.nextExport=Date.now()+1000}}
 };
 app.step=async({sample=true}={})=>{
  if(app.stopped)return;if(sample)app.exportDue();
  const rows=app.store.pending();if(!rows.length||Date.now()<app.nextRetry)return;
  try{
   const identity={id:config.id,secret:config.secret};
   if(!app.session||app.sessionExpires<=Date.now()){
    let hello,lastFailure;
    for(const base of candidates){try{
     const clientNonce=randomBytes(20).toString('hex'),response=await requestJSON(base,'/v1/handshake',identity,{clientNonce},config);
     if(response.clientNonce!==clientNonce||response.gatewayId!=='PC-04'||typeof response.session!=='string'||!Number.isFinite(response.expiresAt))throw Error('Handshake mismatch');
     if(app.source.readOnly&&response.ready!==true){lastFailure=Object.assign(Error('Approved Gateway egress not ready'),{transportConnected:true,authenticatedPeer:true});continue}
     hello=response;app.selectedGatewayUrl=base;break;
    }catch(e){lastFailure=e}}
    if(!hello)throw lastFailure||Error('No approved Gateway available');
    app.session=hello.session;app.sessionExpires=hello.expiresAt;app.lanState='LAN_CONNECTED';if(!app.gatewayAuthenticated)app.store.log('LAN_CONNECT','Enrolled Gateway handshake authenticated');app.gatewayAuthenticated=true;
   }
   app.store.set('inFlight',rows.length);
   const response=await requestJSON(app.selectedGatewayUrl,'/v1/events',identity,{session:app.session,events:rows.map(r=>JSON.parse(r.payload))},config);
   const want=new Map(rows.map(r=>[r.id,r.digest]));
   if(!Array.isArray(response.acks)||response.acks.length!==want.size||new Set(response.acks.map(a=>a.event_id)).size!==want.size||response.acks.some(a=>want.get(a.event_id)!==a.sha256))throw Object.assign(Error('ACK digest/set mismatch'),{transportConnected:true,authenticatedPeer:true});
   app.store.acknowledge(response.acks);app.lastError=null;app.retryCount=0;app.nextRetry=Date.now()+150;app.store.set('consecutiveFailures',0);app.store.set('retryAt',app.nextRetry);
  }catch(e){const wasAuthenticated=app.gatewayAuthenticated;app.lanState=e.transportConnected?'LAN_CONNECTED':'DISCONNECTED';app.gatewayAuthenticated=e.authenticatedPeer===true;app.session=null;app.lastError=e.authenticationFailed?'Gateway authentication failed; local data retained':'Gateway unavailable / request not ACKed';if(wasAuthenticated&&!e.transportConnected)try{app.store.log('LAN_DISCONNECT','Enrolled Gateway transport no longer available')}catch{}app.retryCount++;app.nextRetry=Date.now()+Math.min(5000,200*2**Math.min(app.retryCount-1,5))*(.8+Math.random()*.4);try{app.store.set('retryCount',app.store.get('retryCount',0)+1);app.store.set('consecutiveFailures',app.retryCount);app.store.set('retryAt',app.nextRetry);app.store.log('RETRY','Gateway upload retained locally')}catch{app.spoolError='Spool metadata write failure; events retained'}}
  finally{try{app.store.set('inFlight',0)}catch{app.spoolError='Spool metadata write failure; events retained'}}
 };
 app.start=async()=>{await open(app);app.store.set('inFlight',0);app.exportTimer=setInterval(()=>{if(!app.stopped)app.exportDue()},50);app.timer=setInterval(()=>{if(!app.busy){app.busy=app.step({sample:false}).catch(()=>{app.lastError='Local service/storage failure';app.errorCount++}).finally(()=>app.busy=null)}},50);return app};app.close=()=>close(app);return app;
}
export function createGateway(config,options={}){
 if(config.upstream)endpoint(config.upstream.url,config);if(config.notificationSink)endpoint(config.notificationSink.url,config);
 const app={config,store:new Store(config.dataDir,{...config.storage,notifications:true}),port:null,stopped:false,lastError:null,busy:null};
 app.telegram=options.telegram||new TelegramTransport({env:config.internetMode==='real'?(options.env??process.env):{}});
 if(app.store.get('internetOnline')===null)app.store.set('internetOnline',config.internetOnline??config.internetMode==='real');
 app.setInternet=online=>{if(config.readOnly)throw Object.assign(Error('Read-only LAB'),{status:403});if(typeof online!=='boolean')throw Error('Internet gate must be boolean');app.store.set('internetOnline',online);app.store.log('EGRESS_CHANGE',`Gateway outbound simulation gate ${online?'UP':'DOWN'}`)};
 app.status=()=>({id:config.id,role:'gateway',pid:process.pid,simulated:true,...app.store.stats(),...app.store.notificationStats(),internetMode:config.internetMode||'simulated',internetOnline:app.store.get('internetOnline',false),egress:app.store.get('egress',{status:'BLOCKED',mode:config.internetMode||'simulated',checkedAt:null}),upstreamConfigured:!!config.upstream,upstreamDelivered:app.store.get('upstreamDelivered',0),lastDelivery:app.store.get('lastDelivery'),notificationMode:config.notificationSink?'mock-http':app.telegram.mode,telegramCooldownUntil:app.store.get('telegramNotBefore',0),lastError:app.lastError,messages:app.store.messages(),disk:app.store.disk(),logs:app.store.logs()});
 app.server=serverFor(config,app.store,config.keys,async(route,body,id)=>{
  if(route==='/v1/status'){if(id!=='DASHBOARD')throw Object.assign(Error('Admin identity required'),{status:403});return app.status()}
  if(route==='/v1/sim/internet'){if(id!=='DASHBOARD')throw Object.assign(Error('Admin identity required'),{status:403});app.setInternet(body.online);return {ok:true}}
  if(route==='/v1/sim/fault'){
   if(id!=='DASHBOARD'||config.readOnly)throw Object.assign(Error('Simulation admin required'),{status:403});
   if(!body||!Object.keys(body).length||Object.keys(body).some(k=>!['beforeCommit','dropNextAck'].includes(k)||typeof body[k]!=='boolean'))throw Object.assign(Error('Invalid fault controls'),{status:400});
   if(Object.hasOwn(body,'beforeCommit'))app.store.set('beforeCommit',body.beforeCommit);
   if(Object.hasOwn(body,'dropNextAck'))app.store.set('dropNextAck',body.dropNextAck);return {ok:true};
  }
  if(!GROUPS[id])throw Object.assign(Error('Exporter enrollment required'),{status:403});
  if(route==='/v1/handshake'){
   if(typeof body.clientNonce!=='string'||body.clientNonce.length<16||body.clientNonce.length>128)throw Error('Invalid handshake');
   return {...app.store.session(id),clientNonce:body.clientNonce,gatewayId:'PC-04',ready:app.store.get('internetOnline',false)&&((config.internetMode||'simulated')==='simulated'||app.store.get('egress',{}).status==='VERIFIED')};
  }
  if(route==='/v1/events'){
   if(!app.store.validSession(id,body.session))throw Object.assign(Error('Session expired'),{status:409});
   if(app.store.get('beforeCommit',false)){app.store.set('beforeCommit',false);throw Object.assign(Error('LAB fault before commit; no ACK'),{status:503})}
   const acks=app.store.ingest(id,body.events);
   if(app.store.get('dropNextAck',false)){app.store.set('dropNextAck',false);app.store.log('RETRY','LAB ACK dropped AFTER durable commit');throw Object.assign(Error('LAB ACK dropped'),{dropAck:true})}
   return {acks};
  }
  throw Object.assign(Error('Unknown route'),{status:404});
 });
 app.deliver=async()=>{
  const mode=config.internetMode||'simulated';
  if(!app.store.get('internetOnline',false)){app.store.set('egress',{status:'BLOCKED',mode,checkedAt:null});return}
  if(app.telegram.mode==='telegram'){
   if(mode!=='real'||!app.telegram.configured){app.store.set('egress',{status:'UNCONFIGURED',mode,checkedAt:null});return}
   if(app.store.get('telegramNotBefore',0)>Date.now())return;
   if(app.store.get('probeAfter',0)<=Date.now()){
    try{if(!await app.telegram.probe())throw Error('Egress probe failed');app.store.set('egress',{status:'VERIFIED',mode,checkedAt:new Date().toISOString()});app.store.set('probeAfter',Date.now()+10000)}
    catch(e){const delay=e.retryAfterMs||5000;app.store.set('telegramNotBefore',Date.now()+delay);app.store.set('egress',{status:'UNREACHABLE',mode,checkedAt:new Date().toISOString()});app.lastError='Gateway egress verification failed';return}
   }
  }else if(mode==='real'){app.store.set('egress',{status:'UNCONFIGURED',mode,checkedAt:null});return}
  else app.store.set('egress',{status:'SIMULATED_AVAILABLE',mode,checkedAt:new Date().toISOString()});
  if(config.upstream&&app.store.get('upstreamRetryAt',0)<=Date.now()){
   const first=app.store.pending(1)[0];
   if(first){const rows=app.store.db.prepare("SELECT * FROM records WHERE state!='acked' AND source=? ORDER BY seq LIMIT 32").all(first.source);
    try{const response=await requestJSON(config.upstream.url,'/v1/events',{id:'PC-04',secret:config.upstream.secret},{source:first.source,events:rows.map(r=>JSON.parse(r.payload))},config);const want=new Map(rows.map(r=>[r.id,r.digest]));if(!Array.isArray(response.acks)||response.acks.length!==want.size||new Set(response.acks.map(a=>a.event_id)).size!==want.size||response.acks.some(a=>want.get(a.event_id)!==a.sha256))throw Error('Upstream ACK mismatch');app.store.markForwarded(response.acks);app.store.set('upstreamFailures',0);app.lastError=null}
    catch{const n=app.store.get('upstreamFailures',0)+1;app.store.set('upstreamFailures',n);app.store.set('upstreamRetryAt',Date.now()+Math.min(5000,200*2**Math.min(n-1,5)));app.store.log('RETRY','Upstream ACK unavailable; durable outbound retained');app.lastError='Upstream request not ACKed'}
   }
  }
  const row=app.store.nextNotification();if(!row)return;
  try{
   if(config.notificationSink){const response=await requestJSON(config.notificationSink.url,'/v1/notification',{id:'PC-04',secret:config.notificationSink.secret},{event:JSON.parse(row.payload)},config);if(response.event_id!==row.id||response.sha256!==digest(row.payload))throw Error('Notification ACK mismatch');app.store.markNotification(row.id,'mock-http')}
   else if(app.telegram.mode==='dry-run')app.store.markNotification(row.id,'dry-run');
   else{app.store.set('telegramNotBefore',Date.now()+1100);const messageId=await app.telegram.send(row.text);app.store.markNotification(row.id,'telegram',messageId)}
  }catch(e){const delay=e.retryAfterMs||Math.min(60000,500*2**Math.min(row.attempts,7));app.store.failNotification(row.id,delay);if(app.telegram.mode==='telegram')app.store.set('telegramNotBefore',Date.now()+delay);app.lastError='Notification retained; response failed or ambiguous'}
 };
 app.start=async()=>{await open(app);app.timer=setInterval(()=>{if(!app.busy){app.busy=app.deliver().catch(()=>{app.lastError='Gateway outbound/storage failure'}).finally(()=>app.busy=null)}},150);return app};app.close=()=>close(app);return app;
}
export function createCentral(config){
 const app={config,store:new Store(config.dataDir,{...config.storage,allowReorderedRuntime:true}),stopped:false,port:null};
 app.status=()=>({id:config.id,role:'central',pid:process.pid,simulated:true,...app.store.stats(),...app.store.notificationStats()});
 app.server=serverFor(config,app.store,config.keys,async(route,body,id)=>{
  if(route==='/v1/status'&&id==='DASHBOARD')return app.status();
  if(id!=='PC-04')throw Object.assign(Error('Gateway enrollment required'),{status:403});
  if(route==='/v1/events'){
   const acks=app.store.ingest(body.source,body.events);
   if(app.store.get('dropNextAck',false)){app.store.set('dropNextAck',false);throw Object.assign(Error('LAB upstream ACK lost after commit'),{dropAck:true})}
   return {acks};
  }
  if(route==='/v1/notification'){
   const ack=app.store.receiveNotification(body.event);
   if(app.store.get('dropNotificationAck',false)){app.store.set('dropNotificationAck',false);throw Object.assign(Error('LAB notification ACK lost after commit'),{dropAck:true})}
   return ack;
  }
  throw Object.assign(Error('Unknown route'),{status:404});
 });app.start=()=>open(app);app.close=()=>close(app);return app;
}
