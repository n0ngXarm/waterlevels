import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import http from 'node:http';import net from 'node:net';import {EventEmitter} from 'node:events';import {spawn} from 'node:child_process';
import {requestJSON} from '../src/lan/protocol.js';import {TelegramTransport} from '../src/lan/telegram.js';import {Store} from '../src/lan/store.js';import {enrollment} from '../src/lan/config.js';import {startSingle} from '../src/lan/supervisor.js';import {DatabaseSync} from 'node:sqlite';
const temp=()=>fs.mkdtempSync(path.join(os.tmpdir(),'aqua-g5-'));const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function wait(fn,ms=12000){const end=Date.now()+ms;while(Date.now()<end){try{const value=await fn();if(value)return value}catch{}await delay(80)}throw Error('G5 evidence timeout')}
async function basePort(){for(let n=0;n<100;n++){const ss=[];try{const a=net.createServer();ss.push(a);await new Promise((r,j)=>{a.once('error',j);a.listen(0,'127.0.0.1',r)});const p=a.address().port;if(p>65400)continue;for(const k of [1,2,8,9,10]){const s=net.createServer();ss.push(s);await new Promise((r,j)=>{s.once('error',j);s.listen(p+k,'127.0.0.1',r)})}return p}catch{}finally{await Promise.all(ss.map(s=>new Promise(r=>s.close(r))))}}throw Error('No free LAB ports')}
const browserRequest=(port,method,url,body,token)=>new Promise((resolve,reject)=>{const raw=body?JSON.stringify(body):null;const req=http.request({hostname:'127.0.0.1',port,path:url,method,headers:{...(raw?{'content-type':'application/json'}:{}),...(token?{'x-aqua-control':token}:{})}},res=>{let text='';res.on('data',p=>text+=p);res.on('end',()=>{try{text=JSON.parse(text)}catch{}resolve({status:res.statusCode,body:text})})});req.on('error',reject);req.end(raw)});
test('G5 interrupted HTTP and Telegram responses reject promptly instead of freezing retry loops',async t=>{
 const server=http.createServer((req,res)=>{req.resume();res.writeHead(200,{'content-length':100});res.flushHeaders();res.write('x');setTimeout(()=>res.destroy(),25)});await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));
 const result=await Promise.race([requestJSON(`http://127.0.0.1:${server.address().port}`,'/v1/status',{id:'PC-01',secret:'a'.repeat(64)},{},{timeoutMs:150}).then(()=> 'resolved',()=> 'rejected'),delay(600).then(()=> 'pending')]);assert.equal(result,'rejected');
 const fake=(options,callback)=>{const req=new EventEmitter();req.destroy=()=>{};req.end=()=>{const res=new EventEmitter();res.statusCode=200;callback(res);queueMicrotask(()=>{res.emit('data',Buffer.from('{'));res.emit('aborted')})};return req};
 const transport=new TelegramTransport({env:{TELEGRAM_ENABLED:'true',TELEGRAM_BOT_TOKEN:'123:FAKE_LAB_ONLY',TELEGRAM_CHAT_ID:'456',TELEGRAM_APPROVED_ENDPOINT:'https://api.telegram.org'},request:fake});
 const telegramResult=await Promise.race([transport.send('[AQUA LAB / SIMULATED] test').then(()=> 'resolved',()=> 'rejected'),delay(600).then(()=> 'pending')]);assert.equal(telegramResult,'rejected');
});
test('G5 owner identity distinguishes a reused live PID from the same active service instance',()=>{
 const dir=temp(),store=new Store(dir);try{store.set('serviceOwner',{pid:process.pid,id:'PC-01',instance:'old-boot:old-start',startedAt:'2000-01-01T00:00:00Z'});assert.doesNotThrow(()=>store.acquireOwner('PC-01'));assert.notEqual(store.get('serviceOwner').instance,'old-boot:old-start');assert.equal(typeof store.get('serviceOwner').instance,'string');assert.throws(()=>store.acquireOwner('PC-01'),/already owned/)}finally{store.close();fs.rmSync(dir,{recursive:true,force:true})}
});
test('G5 read-only startup override applies without discarding data and old enrollment stays immutable',()=>{
 const dir=temp();try{const first=enrollment(dir,{port:43073}),oldFiles=Object.fromEntries(Object.entries(first.files).map(([id,file])=>[id,{file,raw:fs.readFileSync(file,'utf8')}]))
  const ro=enrollment(dir,{readOnly:true});for(const id of ['PC-01','PC-02','PC-03','gateway','dashboard'])assert.equal(ro.configs[id].readOnly,true);assert.equal(ro.configs['PC-01'].dataDir,first.configs['PC-01'].dataDir);
  const next=enrollment(dir,{newSession:true});assert.notEqual(next.generation,first.generation);for(const old of Object.values(oldFiles))assert.equal(fs.readFileSync(old.file,'utf8'),old.raw);
 }finally{fs.rmSync(dir,{recursive:true,force:true})}
});
test('G5 explicit LAN role CLI starts only the requested enrolled service over loopback',async t=>{
 const dir=temp(),port=await basePort(),e=enrollment(dir,{port});const root=path.resolve(import.meta.dirname,'..');
 const child=spawn(process.execPath,['bin/aqua-lab.js','lan','--role','gateway','--config',e.files.gateway,'--data-dir',dir,'--port',String(port)],{cwd:root,stdio:['ignore','pipe','pipe']});child.stdout.resume();child.stderr.resume();
 t.after(async()=>{if(child.exitCode===null&&child.signalCode===null){const done=new Promise(r=>child.once('exit',r));child.kill('SIGTERM');await done}fs.rmSync(dir,{recursive:true,force:true})});
 const status=await wait(async()=>{const value=await requestJSON(`http://127.0.0.1:${port+1}`,'/v1/status',{id:'DASHBOARD',secret:e.configs.gateway.keys.DASHBOARD},{});return value.role==='gateway'?value:false},5000);
 assert.equal(status.pid,child.pid);assert.equal(fs.existsSync(e.configs['PC-01'].dataDir),false);assert.equal(fs.existsSync(e.configs.dashboard.dataDir),false);
});
test('G5 default 5s cadence, supervised recovery and reset archive survive full pipeline operation',async t=>{
 const dir=temp(),port=await basePort(),lab=await startSingle(dir,{port,quiet:true});t.after(async()=>{await lab.stop();fs.rmSync(dir,{recursive:true,force:true})});
 const state=async()=>(await browserRequest(port,'GET','/api/status')).body,token=lab.enrollment.configs.dashboard.controlToken;
 const initial=await wait(async()=>{const s=await state();return s.agents?.every(a=>a.snapshots>=3)?s:false},14000);assert.equal(initial.exportIntervalSeconds,5);
 const dbPath=path.join(lab.enrollment.configs['PC-01'].dataDir,'aqua.sqlite3'),db=new DatabaseSync(dbPath,{readOnly:true});const stamps=db.prepare("SELECT at FROM records WHERE kind='SNAPSHOT' ORDER BY seq LIMIT 3").all().map(r=>Date.parse(r.at));db.close();for(let n=1;n<stamps.length;n++)assert.ok(stamps[n]-stamps[n-1]>=4800&&stamps[n]-stamps[n-1]<=5750,'Default snapshot cadence must be approximately5s');
 await browserRequest(port,'POST','/api/action',{action:'pump',id:'PUMP-03',on:true},token);await browserRequest(port,'POST','/api/action',{action:'gateway',connected:true},token);await browserRequest(port,'POST','/api/action',{action:'internet',online:true},token);
 const active=await wait(async()=>{const s=await state();return s.notificationSent===1&&s.delivered>=initial.snapshots?s:false});const oldPid=active.agents[0].pid;process.kill(oldPid,'SIGKILL');
 await wait(async()=>{const s=await state();return s.agents[0].online&&s.agents[0].pid!==oldPid&&s.pumps['PUMP-03']===true?s:false});assert.equal((await state()).notificationSent,1);
 const generation=lab.enrollment.generation,sessionsBefore=fs.readdirSync(path.join(dir,'sessions')).length;
 const resets=await Promise.all([browserRequest(port,'POST','/api/action',{action:'reset'},token),browserRequest(port,'POST','/api/action',{action:'reset'},token)]);assert.ok(resets.every(r=>r.status===200));
 await wait(async()=>{const s=await state();return s.generation!==generation&&s.agents.every(a=>a.online)?s:false});assert.equal(fs.readdirSync(path.join(dir,'sessions')).length,sessionsBefore+1);assert.equal(fs.existsSync(dbPath),true);
 await lab.control({action:'reset'});await lab.stop();await delay(250);assert.equal(lab.children.size,0,'Stopping must cancel pending reset, never resurrect roles');
 t.diagnostic(JSON.stringify({defaultSnapshotIntervalsMs:stamps.slice(1).map((x,i)=>x-stamps[i]),originalSourcePid:oldPid,resetArchivedDatabase:true,verification:'TESTED ON ONE HOST'}));
});
test('G5 shutdown during an active reset cannot resurrect owned service processes',async t=>{
 const dir=temp(),port=await basePort(),lab=await startSingle(dir,{port,quiet:true});t.after(async()=>{await lab.stop();fs.rmSync(dir,{recursive:true,force:true})});
 const child=lab.children.get('PC-01'),kill=child.kill.bind(child);let delayed=false;
 child.kill=signal=>{if(signal==='SIGTERM'&&!delayed){delayed=true;setTimeout(()=>kill(signal),500);return true}return kill(signal)};
 await lab.control({action:'reset'});await wait(()=>lab.stopping&&lab.resetTimer===null,3000);
 await lab.stop();await delay(700);assert.equal(lab.children.size,0,'A reset already in shutdown must never boot after permanent stop');assert.equal(lab.stopping,true);
});
