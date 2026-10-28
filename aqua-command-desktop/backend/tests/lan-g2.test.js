import {test} from 'node:test';import assert from 'node:assert/strict';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import http from 'node:http';import {randomBytes} from 'node:crypto';
import net from 'node:net';import {spawn} from 'node:child_process';
import {Store} from '../src/lan/store.js';import {createAgent,createGateway} from '../src/lan/services.js';import {requestJSON,requestHeaders,answer,digest} from '../src/lan/protocol.js';
const key=()=>randomBytes(32).toString('hex');
const temp=()=>fs.mkdtempSync(path.join(os.tmpdir(),'aqua-g2-'));
async function port(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const n=s.address().port;await new Promise(r=>s.close(r));return n}
const exited=c=>c.exitCode!==null||c.signalCode!==null;
async function wait(fn,timeout=8000){const until=Date.now()+timeout;while(Date.now()<until){try{const v=await fn();if(v)return v}catch{}await new Promise(r=>setTimeout(r,60))}throw Error('Recovery evidence timeout')}
test('G2 pending quota never purges unACKed records and ACKed retention preserves sequence',()=>{
 const dir=temp();let s=new Store(dir,{maxPending:3,maxHistory:2});
 try{
  const values=s.pumps('PC-01'),events=Array.from({length:3},()=>s.append('PC-01','SNAPSHOT',values));
  assert.throws(()=>s.append('PC-01','SNAPSHOT',values),/quota/i);assert.equal(s.stats().pending,3);
  s.acknowledge(s.pending().map(r=>({event_id:r.id,sha256:r.digest})));assert.equal(s.db.prepare('SELECT count(*) n FROM records').get().n,2);
  s.close();s=new Store(dir,{maxPending:3,maxHistory:2});const next=s.append('PC-01','SNAPSHOT',values);assert.equal(next.sequence,4);assert.notEqual(next.event_id,events[0].event_id);
 }finally{s.close();fs.rmSync(dir,{recursive:true,force:true})}
});
test('G2 failed storage commits do not advance sequence or silently reset data',()=>{
 const dir=temp();let s=new Store(dir);
 try{
  s.append('PC-01','SNAPSHOT',s.pumps('PC-01'));s.db.exec('PRAGMA query_only=ON');
  assert.throws(()=>s.append('PC-01','SNAPSHOT',s.pumps('PC-01')));assert.equal(s.stats().sequence,1);s.close();
  s=new Store(dir);assert.equal(s.stats().pending,1);assert.equal(s.db.prepare('PRAGMA integrity_check').get().integrity_check,'ok');
 }finally{s.close();fs.rmSync(dir,{recursive:true,force:true})}
});
test('G2 interruption before commit and lost ACK after commit retain/retry same event without duplicates',async t=>{
 const dir=temp(),secret=key(),admin=key();let agent;
 const gw=createGateway({role:'gateway',id:'PC-04',dataDir:path.join(dir,'gateway'),listen:{host:'127.0.0.1',port:0},keys:{'PC-01':secret,DASHBOARD:admin}});await gw.start();
 t.after(async()=>{if(agent)await agent.close();await gw.close();fs.rmSync(dir,{recursive:true,force:true})});
 const url=`http://127.0.0.1:${gw.port}`,identity={id:'DASHBOARD',secret:admin};
 agent=createAgent({role:'agent',id:'PC-01',secret,dataDir:path.join(dir,'agent'),listen:{host:'127.0.0.1',port:0},gatewayUrl:url,intervalMs:5000});
 agent.sample();agent.nextExport=Date.now()+60000;
 await requestJSON(url,'/v1/sim/fault',identity,{beforeCommit:true});await agent.step();assert.equal(gw.store.stats().received,0);assert.equal(agent.store.stats().pending,1);
 await requestJSON(url,'/v1/sim/fault',identity,{dropNextAck:true});agent.nextRetry=0;await agent.step();assert.equal(gw.store.stats().received,1);assert.equal(agent.store.stats().pending,1);
 agent.nextRetry=0;await agent.step();assert.equal(gw.store.stats().received,1);assert.equal(gw.store.stats().duplicates,1);assert.equal(agent.store.stats().pending,0);assert.equal(agent.store.stats().acked,1);
 const persisted=agent.store.get('retryCount');assert.ok(persisted>=2);
});
test('G2 actual HTTP rejects replay/nonfinite time and client retains data on a signed mismatched ACK',async t=>{
 const dir=temp(),secret=key();let mode='badack';let agent;
 const fake=http.createServer(async(req,res)=>{
  let raw='';for await(const p of req)raw+=p;const body=JSON.parse(raw),auth={secret,nonce:req.headers['x-aqua-nonce']};
  answer(res,200,req.url==='/v1/handshake'?{gatewayId:'PC-04',clientNonce:body.clientNonce,session:'test-session',expiresAt:Date.now()+60000}:{acks:body.events.map(e=>({event_id:e.event_id,sha256:'0'.repeat(64)}))},auth);
 });await new Promise(r=>fake.listen(0,'127.0.0.1',r));
 t.after(async()=>{if(agent)await agent.close();await new Promise(r=>fake.close(r));fs.rmSync(dir,{recursive:true,force:true})});
 agent=createAgent({role:'agent',id:'PC-01',secret,dataDir:dir,listen:{host:'127.0.0.1',port:0},gatewayUrl:`http://127.0.0.1:${fake.address().port}`,intervalMs:5000});
 agent.sample();agent.nextExport=Date.now()+60000;await agent.step();assert.equal(agent.store.stats().pending,1);assert.equal(agent.store.stats().acked,0);
 const gd=temp(),gw=createGateway({role:'gateway',id:'PC-04',dataDir:gd,listen:{host:'127.0.0.1',port:0},keys:{'PC-01':secret}});await gw.start();t.after(async()=>{await gw.close();fs.rmSync(gd,{recursive:true,force:true})});
 const route='/v1/handshake',raw=JSON.stringify({clientNonce:'client-nonce-1234567890'}),headers=requestHeaders('PC-01',secret,route,raw);
 const rawRequest=h=>new Promise((resolve,reject)=>{const req=http.request({hostname:'127.0.0.1',port:gw.port,path:route,method:'POST',headers:h},res=>{res.resume();res.on('end',()=>resolve(res.statusCode))});req.on('error',reject);req.end(raw)});
 assert.equal(await rawRequest(headers),200);assert.equal(await rawRequest(headers),401);
 assert.equal(await rawRequest(requestHeaders('PC-01',secret,route,raw,{time:Infinity})),401);
});
test('G2 data ownership guard and SIGKILL recovery preserve immutable source and Gateway records',async t=>{
 const dir=temp(),secret=key(),admin=key(),gp=await port(),ap=await port(),children=[];
 const root=path.resolve(import.meta.dirname,'..');
 const ac={role:'agent',id:'PC-01',secret,dataDir:path.join(dir,'agent'),listen:{host:'127.0.0.1',port:ap},gatewayUrl:`http://127.0.0.1:${gp}`,intervalMs:200};
 const gc={role:'gateway',id:'PC-04',dataDir:path.join(dir,'gateway'),listen:{host:'127.0.0.1',port:gp},keys:{'PC-01':secret,DASHBOARD:admin}};
 const start=(cfg,name)=>{const file=path.join(dir,name+'.json');fs.writeFileSync(file,JSON.stringify(cfg),{mode:0o600});const c=spawn(process.execPath,['bin/aqua-service.js','--config',file],{cwd:root,stdio:['ignore','pipe','pipe']});children.push(c);return c};
 const kill=async c=>{if(exited(c))return;const done=new Promise(r=>c.once('exit',r));c.kill('SIGKILL');await done};
 t.after(async()=>{await Promise.all(children.map(kill));fs.rmSync(dir,{recursive:true,force:true})});
 let agent=start(ac,'agent');const status=()=>requestJSON(`http://127.0.0.1:${ap}`,'/v1/status',{id:'PC-01',secret},{});
 const offline=await wait(async()=>{const s=await status();return s.pending>=2?s:false});
 const duplicate=start({...ac,listen:{host:'127.0.0.1',port:await port()}},'duplicate');
 await wait(()=>exited(duplicate),4000).catch(()=>{});assert.ok(exited(duplicate),'Second service must fail closed before exporting from the same source database');assert.notEqual(duplicate.exitCode,0);
 let gateway=start(gc,'gateway');await wait(async()=>{const s=await status();return s.acked>=offline.pending?s:false});
 await kill(gateway);const pending=await wait(async()=>{const s=await status();return s.pending>=2?s:false});await kill(agent);
 let store=new Store(ac.dataDir);const retained=store.pending().map(r=>({id:r.id,digest:r.digest}));store.close();
 gateway=start(gc,'gateway-restarted');agent=start(ac,'agent-restarted');
 await wait(async()=>{const s=await status();return s.acked>=pending.acked+retained.length?s:false});
 await kill(agent);await kill(gateway);
 store=new Store(ac.dataDir);for(const row of retained)assert.equal(store.db.prepare('SELECT state FROM records WHERE id=? AND digest=?').get(row.id,row.digest).state,'acked');assert.ok(store.stats().sequence>pending.sequence);store.close();
 const destination=new Store(gc.dataDir);assert.ok(destination.stats().received>=offline.pending+retained.length);assert.equal(destination.db.prepare('PRAGMA integrity_check').get().integrity_check,'ok');destination.close();
 t.diagnostic(JSON.stringify({verification:'TESTED ON ONE HOST',initialAgentPid:offline.pid,restartedAgentPid:agent.pid,restartedGatewayPid:gateway.pid,recoveredEventIds:retained.map(x=>x.id)}));
});
test('G2 snapshot producer continues while authenticated network handshake is stalled',async t=>{
 const dir=temp(),secret=key();const stalled=http.createServer(()=>{});await new Promise(r=>stalled.listen(0,'127.0.0.1',r));
 const agent=createAgent({role:'agent',id:'PC-01',secret,dataDir:dir,listen:{host:'127.0.0.1',port:0},gatewayUrl:`http://127.0.0.1:${stalled.address().port}`,intervalMs:180});await agent.start();
 t.after(async()=>{await agent.close();stalled.closeAllConnections();await new Promise(r=>stalled.close(r));fs.rmSync(dir,{recursive:true,force:true})});
 await new Promise(r=>setTimeout(r,750));assert.ok(agent.store.stats().snapshots>=3,'Snapshot timer must run independently of network awaits');assert.equal(agent.store.stats().acked,0);
});
