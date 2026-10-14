import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';
import {spawn} from 'node:child_process';

function openPort(){return new Promise((resolve,reject)=>{const srv=net.createServer();srv.listen(0,'127.0.0.1',()=>{const p=srv.address().port;srv.close(()=>resolve(p))});srv.on('error',reject)});}
const KEY='test-only-admin-key-with-more-than-24-chars';
test('fresh ingest, dedup, escalation, resolution, RBAC and export', {timeout:15_000},async()=>{
 const root=path.resolve(import.meta.dirname,'..');
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'aqua-test-'));
 for(const file of ['server.mjs','rules.mjs'])fs.copyFileSync(path.join(root,file),path.join(tmp,file));
 fs.cpSync(path.join(root,'public'),path.join(tmp,'public'),{recursive:true});
 fs.mkdirSync(path.join(tmp,'storage'));
 const port=await openPort();
 const env={...process.env,APP_ENV:'production',DEMO_MODE:'false',HOST:'127.0.0.1',PORT:String(port),ADMIN_API_KEY:KEY,TELEGRAM_BOT_TOKEN:'',TELEGRAM_CHAT_ID:''};
 const child=spawn(process.execPath,[path.join(tmp,'server.mjs')],{cwd:tmp,env,stdio:'pipe'});
 const base=`http://127.0.0.1:${port}`;
 async function req(url,body,key=KEY){return fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json',...(key?{'X-API-Key':key}:{})},body:JSON.stringify(body)});}
 try{
   for(let i=0;i<50;i++){if(child.exitCode!==null)throw Error('Server died');try{const r=await fetch(base+'/api/health');if(r.ok)break;}catch{}await new Promise(r=>setTimeout(r,100));}
   let st=await (await fetch(base+'/api/state')).json();
   assert.equal(st.mode,'live-ingest');assert.equal(st.alerts.length,0);assert.equal(st.stations.every(x=>x.status==='unknown'),true);
   const packet={stationId:'CM-01',pressureBar:.6,tankLevelPct:70,flowM3h:1000,turbidityNtu:.4,chlorineMgL:.5,online:true};
   assert.equal((await req('/api/telemetry',packet,null)).status,401);
   assert.equal((await req('/api/telemetry',{...packet,pressureBar:-1})).status,422);
   assert.equal((await req('/api/telemetry',packet)).status,200);
   st=await (await fetch(base+'/api/state')).json();
   assert.equal(st.alerts.filter(a=>a.severity==='critical').length,1);assert.equal(st.metrics.critical,1);
   await req('/api/telemetry',packet);
   st=await (await fetch(base+'/api/state')).json();assert.equal(st.alerts.length,1,'duplicate packet must not create duplicate alerts');
   await req('/api/telemetry',{stationId:'CM-01',pressureBar:1.2});
   st=await (await fetch(base+'/api/state')).json();assert.equal(st.metrics.activeAlertCount,1,'escalation should close previous active record');assert.equal(st.alerts[0].severity,'warning');assert.ok(st.alerts[1].supersededAt);
   await req('/api/telemetry',{stationId:'CM-01',pressureBar:2.5});
   st=await (await fetch(base+'/api/state')).json();assert.equal(st.metrics.activeAlertCount,0);assert.equal(st.alerts[0].severity,'resolved');
   assert.equal((await fetch(base+'/api/export/alerts')).status,401);
   const csv=await fetch(base+'/api/export/alerts',{headers:{'X-API-Key':KEY}});assert.equal(csv.status,200);assert.match(await csv.text(),/AL-/);
   const ack=await req(`/api/alerts/${st.alerts[1].id}/ack`,{});assert.equal(ack.status,200);
   assert.equal((await req('/api/demo/incident',{})).status,403);
   const invalid=await req('/api/telemetry',{stationId:'XXX',pressureBar:1.1});assert.equal(invalid.status,404);
 }finally{child.kill('SIGTERM');await new Promise(resolve=>{if(child.exitCode!==null||child.signalCode)resolve();else child.once('exit',resolve)});fs.rmSync(tmp,{recursive:true,force:true});}
});
