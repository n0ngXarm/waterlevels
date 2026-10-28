import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
const root=path.resolve(import.meta.dirname,'..');
async function modules(){assert.ok(fs.existsSync(path.join(root,'src/lan/services.js')),'G1 independent services are not implemented');return {...await import('../src/lan/services.js'),...await import('../src/lan/protocol.js')}}
async function freePort(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p}
async function waitFor(fn,ms=8000){const end=Date.now()+ms;let last;while(Date.now()<end){try{last=await fn();if(last)return last}catch{}await new Promise(r=>setTimeout(r,80))}throw Error('timeout waiting for service evidence: '+JSON.stringify(last))}
function secret(){return randomBytes(32).toString('hex')}
test('G1 validates explicit LAB endpoints and never accepts default public/wildcard destinations',async()=>{
 const {endpoint}=await modules();assert.equal(endpoint('http://127.0.0.1:4174').hostname,'127.0.0.1');
 for(const url of ['http://example.com:80','http://0.0.0.0:4174','http://192.168.50.4:4174','http://user:pass@127.0.0.1:4174'])assert.throws(()=>endpoint(url),/LAB|endpoint|loopback/);
 assert.equal(endpoint('http://192.168.50.4:4174',{allowLan:true,allowInsecureLabHttp:true}).hostname,'192.168.50.4');
});
test('G1 authenticates handshake and rejects unknown members or incorrect keys',async t=>{
 const {createGateway,requestJSON}=await modules();const dir=fs.mkdtempSync(path.join(os.tmpdir(),'aqua-g1-'));
 const key=secret(),admin=secret();const gw=createGateway({role:'gateway',id:'PC-04',dataDir:dir,listen:{host:'127.0.0.1',port:0},keys:{'PC-01':key,DASHBOARD:admin}});await gw.start();t.after(async()=>{await gw.close();fs.rmSync(dir,{recursive:true,force:true})});
 const url=`http://127.0.0.1:${gw.port}`;
 const hello=await requestJSON(url,'/v1/handshake',{id:'PC-01',secret:key},{clientNonce:'client-nonce-0123456789'});
 assert.equal(hello.gatewayId,'PC-04');assert.equal(hello.clientNonce,'client-nonce-0123456789');assert.ok(hello.session);
 await assert.rejects(()=>requestJSON(url,'/v1/handshake',{id:'PC-99',secret:key},{clientNonce:'client-nonce-0123456789'}));
 await assert.rejects(()=>requestJSON(url,'/v1/handshake',{id:'PC-01',secret:secret()},{clientNonce:'client-nonce-0123456789'}));
});
test('G1 three independent agent OS processes spool while Gateway is absent then transfer over HTTP',async t=>{
 const {createGateway,requestJSON}=await modules();const dir=fs.mkdtempSync(path.join(os.tmpdir(),'aqua-g1-process-'));
 const gwPort=await freePort(),admin=secret(),keys={DASHBOARD:admin};const children=[],cfgs=[];
 let gw;
 t.after(async()=>{for(const child of children)if(child.exitCode===null)child.kill('SIGTERM');await Promise.all(children.map(child=>new Promise(r=>{if(child.exitCode!==null)return r();child.once('exit',r)})));if(gw)await gw.close();fs.rmSync(dir,{recursive:true,force:true})});
 for(let i=1;i<=3;i++){
  const id=`PC-0${i}`,key=secret(),port=await freePort();keys[id]=key;
  const cfg={role:'agent',id,secret:key,listen:{host:'127.0.0.1',port},gatewayUrl:`http://127.0.0.1:${gwPort}`,dataDir:path.join(dir,id),intervalMs:180};cfgs.push(cfg);
  const file=path.join(dir,id+'.json');fs.writeFileSync(file,JSON.stringify(cfg),{mode:0o600});
  const child=spawn(process.execPath,['bin/aqua-service.js','--config',file],{cwd:root,stdio:['ignore','pipe','pipe']});children.push(child);
 }
 const statuses=await waitFor(async()=>{const s=await Promise.all(cfgs.map(c=>requestJSON(`http://127.0.0.1:${c.listen.port}`,'/v1/status',{id:c.id,secret:c.secret},{})));return s.every(x=>x.pending>=2)?s:false});
 assert.equal(new Set(statuses.map(x=>x.pid)).size,3);assert.ok(statuses.every(x=>x.pid!==process.pid&&x.lanState==='DISCONNECTED'&&x.pending>=2));
 gw=createGateway({role:'gateway',id:'PC-04',dataDir:path.join(dir,'PC-04'),listen:{host:'127.0.0.1',port:gwPort},keys});await gw.start();
 const proof=await waitFor(async()=>{const s=await requestJSON(`http://127.0.0.1:${gwPort}`,'/v1/status',{id:'DASHBOARD',secret:admin},{});return s.received>=6?s:false});
 assert.ok(proof.received>=6);
 const acked=await waitFor(async()=>{const s=await Promise.all(cfgs.map(c=>requestJSON(`http://127.0.0.1:${c.listen.port}`,'/v1/status',{id:c.id,secret:c.secret},{})));return s.every(x=>x.acked>=2&&x.gatewayAuthenticated)?s:false});
 assert.ok(acked.every(x=>x.lastAckAt));
 t.diagnostic(JSON.stringify({verification:'TESTED ON ONE HOST',agentPids:acked.map(x=>x.pid),gatewayPid:process.pid,gatewayPort:gwPort,received:proof.received,acked:acked.map(x=>x.acked),lastAckAt:acked.map(x=>x.lastAckAt)}));
});
