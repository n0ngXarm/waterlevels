import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import http from 'node:http';import net from 'node:net';
async function mods(){assert.ok(fs.existsSync(path.resolve(import.meta.dirname,'../src/lan/dashboard.js')),'G4 API bridge is missing');return {...await import('../src/lan/dashboard.js'),...await import('../src/lan/supervisor.js')}}
const temp=()=>fs.mkdtempSync(path.join(os.tmpdir(),'aqua-g4-'));
async function basePort(){for(let n=0;n<100;n++){const servers=[];try{const first=net.createServer();await new Promise((r,j)=>{first.once('error',j);first.listen(0,'127.0.0.1',r)});servers.push(first);const p=first.address().port;if(p>65400)continue;for(const offset of [1,2,8,9,10]){const s=net.createServer();servers.push(s);await new Promise((r,j)=>{s.once('error',j);s.listen(p+offset,'127.0.0.1',r)})}return p}catch{}finally{await Promise.all(servers.map(s=>new Promise(r=>s.close(r))))}}throw Error('No LAB port range')}
const req=(port,method,url,body,token,extra={})=>new Promise((resolve,reject)=>{const raw=body?JSON.stringify(body):null;const r=http.request({hostname:'127.0.0.1',port,path:url,method,headers:{...(raw?{'content-type':'application/json','content-length':Buffer.byteLength(raw)}:{}),...(token?{'x-aqua-control':token}:{}),...extra}},res=>{let b='';res.on('data',p=>b+=p);res.on('end',()=>{try{b=JSON.parse(b)}catch{}resolve({status:res.statusCode,body:b})})});r.on('error',reject);r.end(raw)});
async function wait(fn,timeout=10000){const end=Date.now()+timeout;while(Date.now()<end){try{const value=await fn();if(value)return value}catch{}await new Promise(r=>setTimeout(r,100))}throw Error('G4 actual service evidence timeout')}
test('G4 offline/read-only bridge reports unknown pumps and rejects all simulation controls',async t=>{
 const {createDashboard}=await mods();const dir=temp();
 const cfg={role:'dashboard',id:'DASHBOARD',dataDir:dir,listen:{host:'127.0.0.1',port:0},controlToken:'unit-control-token',readOnly:true,controlMode:'readonly',agents:['PC-01','PC-02','PC-03'].map(id=>({id,url:'http://127.0.0.1:1',secret:'a'.repeat(64)})),gateway:{url:'http://127.0.0.1:1',secret:'b'.repeat(64)},intervalMs:5000};
 const app=createDashboard(cfg);await app.start();t.after(async()=>{await app.close();fs.rmSync(dir,{recursive:true,force:true})});
 const s=await req(app.port,'GET','/api/status');assert.equal(s.status,200);assert.ok(Object.values(s.body.pumps).every(v=>v===null));assert.equal(s.body.actionsAllowed,false);
 for(const action of [{action:'pump',id:'PUMP-03',on:true},{action:'gateway',connected:true},{action:'internet',online:true},{action:'reset'}])assert.equal((await req(app.port,'POST','/api/action',action,cfg.controlToken)).status,403);
});
test('G4 existing API/UI actions operate actual separate services with enrollment and no snapshot spam',async t=>{
 const {startSingle}=await mods();const dir=temp(),port=await basePort();const lab=await startSingle(dir,{port,intervalMs:180,quiet:true});t.after(async()=>{await lab.stop();fs.rmSync(dir,{recursive:true,force:true})});
 const state=async()=>(await req(port,'GET','/api/status')).body,token=lab.enrollment.configs.dashboard.controlToken;
 const before=await wait(async()=>{const s=await state();return s.agents?.every(a=>a.online&&a.snapshots>=2)?s:false});assert.equal(new Set(before.agents.map(a=>a.pid)).size,3);assert.equal(before.gatewayConnected,false);assert.ok(before.scadaQueueCount>=6);
 assert.equal((await req(port,'POST','/api/action',{action:'pump',id:'PUMP-03',on:true})).status,403);
 assert.equal((await req(port,'POST','/api/action',{action:'pump',id:'PUMP-03',on:true},token,{'Origin':'https://untrusted.invalid'})).status,403);
 assert.equal((await req(port,'POST','/api/action',{action:'pump',id:'PUMP-03',on:'true'},token)).status,400);
 assert.equal((await req(port,'POST','/api/action',{action:'pump',id:'PUMP-03',on:true},token)).status,200);
 await req(port,'POST','/api/action',{action:'gateway',connected:true},token);
 const joined=await wait(async()=>{const s=await state();return s.gatewayConnected&&s.gatewayQueueCount>=6?s:false});assert.equal(joined.delivered,0);assert.equal(joined.internetOnline,false);
 await req(port,'POST','/api/action',{action:'internet',online:true},token);
 const delivered=await wait(async()=>{const s=await state();return s.delivered>=joined.gatewayQueueCount&&s.notificationSent===1?s:false});assert.equal(delivered.transport,'real-tcp');assert.equal(delivered.verificationLevel,'TESTED ON ONE HOST');
 await req(port,'POST','/api/action',{action:'pump',id:'PUMP-03',on:true},token);await new Promise(r=>setTimeout(r,500));assert.equal((await state()).notificationSent,1);
 assert.ok((await req(port,'GET','/')).body.includes('aqua-control-token'));assert.equal((await req(port,'GET','/aqua-isometric-pump-scene.svg')).status,200);
 t.diagnostic(JSON.stringify({verification:delivered.verificationLevel,agentPids:delivered.agents.map(a=>a.pid),gatewayPid:delivered.gateway.pid,centralPid:delivered.central.pid,dashboardPid:delivered.dashboardPid,received:delivered.gateway.received,upstreamDelivered:delivered.delivered,notificationSent:delivered.notificationSent}));
});
test('G4 reachable TCP with rejected authentication is not reported as a disconnected LAN',async t=>{
 const {createAgent,createGateway}=await import('../src/lan/services.js');const {randomBytes}=await import('node:crypto');const dir=temp(),key=randomBytes(32).toString('hex');
 const gw=createGateway({role:'gateway',id:'PC-04',listen:{host:'127.0.0.1',port:0},dataDir:path.join(dir,'gw'),keys:{'PC-01':key}});await gw.start();
 const a=createAgent({role:'agent',id:'PC-01',secret:randomBytes(32).toString('hex'),listen:{host:'127.0.0.1',port:0},dataDir:path.join(dir,'a'),gatewayUrl:`http://127.0.0.1:${gw.port}`,intervalMs:5000});
 t.after(async()=>{await a.close();await gw.close();fs.rmSync(dir,{recursive:true,force:true})});
 a.sample();a.nextExport=Date.now()+60000;await a.step();assert.equal(a.status().lanState,'LAN_CONNECTED');assert.equal(a.status().gatewayAuthenticated,false);assert.equal(a.status().pending,1);
});
