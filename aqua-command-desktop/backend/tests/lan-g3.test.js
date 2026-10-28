import {test} from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {randomBytes} from 'node:crypto';
import * as services from '../src/lan/services.js';import {Store} from '../src/lan/store.js';
const key=()=>randomBytes(32).toString('hex'),temp=()=>fs.mkdtempSync(path.join(os.tmpdir(),'aqua-g3-'));
function source(dir,secret){return services.createAgent({role:'agent',id:'PC-01',secret,dataDir:dir,listen:{host:'127.0.0.1',port:0},gatewayUrl:'http://127.0.0.1:1',intervalMs:5000})}
function records(a){return a.store.pending().map(r=>JSON.parse(r.payload))}
function gate(){assert.equal(typeof services.createCentral,'function','G3 upstream/sink is not implemented')}
test('G3 snapshots never notify; one transition notifies once across repeated ingest and restart',async t=>{
 gate();const dir=temp(),secret=key();let gw;let agent=source(path.join(dir,'agent'),secret);
 const cfg={role:'gateway',id:'PC-04',dataDir:path.join(dir,'gateway'),listen:{host:'127.0.0.1',port:0},keys:{'PC-01':secret},internetMode:'simulated'};
 t.after(async()=>{await agent.close();if(gw)await gw.close();fs.rmSync(dir,{recursive:true,force:true})});
 agent.sample();agent.sample();agent.setPump('PUMP-03',true);assert.equal(agent.setPump('PUMP-03',true).changed,false);agent.sample();
 gw=services.createGateway(cfg,{env:{}});gw.store.ingest('PC-01',records(agent));await gw.deliver();assert.equal(gw.status().notificationSent,0);assert.equal(gw.status().notificationPending,1);
 gw.setInternet(true);await gw.deliver();assert.equal(gw.status().notificationSent,1);gw.store.ingest('PC-01',records(agent));await gw.deliver();assert.equal(gw.status().notificationSent,1);
 await gw.close();gw=services.createGateway(cfg,{env:{}});await gw.deliver();assert.equal(gw.status().notificationSent,1);assert.equal(gw.status().messages.length,1);assert.ok(gw.status().messages[0].text.startsWith('[AQUA LAB / SIMULATED]'));
 await agent.close();agent=source(path.join(dir,'agent'),secret);assert.equal(agent.setPump('PUMP-03',true).changed,false);
});
test('G3 real HTTP Central buffers while Internet down and deduplicates after lost upstream ACK',async t=>{
 gate();const dir=temp(),secret=key(),upstreamKey=key(),admin=key();const agent=source(path.join(dir,'agent'),secret);agent.sample();agent.sample();
 const central=services.createCentral({role:'central',id:'CENTRAL-LAB',dataDir:path.join(dir,'central'),listen:{host:'127.0.0.1',port:0},keys:{'PC-04':upstreamKey,DASHBOARD:admin}});await central.start();
 const gw=services.createGateway({role:'gateway',id:'PC-04',dataDir:path.join(dir,'gateway'),listen:{host:'127.0.0.1',port:0},keys:{'PC-01':secret},upstream:{url:`http://127.0.0.1:${central.port}`,secret:upstreamKey},internetMode:'simulated'},{env:{}});
 t.after(async()=>{await gw.close();await central.close();await agent.close();fs.rmSync(dir,{recursive:true,force:true})});
 gw.store.ingest('PC-01',records(agent));await gw.deliver();assert.equal(central.status().received,0);assert.equal(gw.status().pending,2);
 central.store.set('dropNextAck',true);gw.setInternet(true);await gw.deliver();assert.equal(central.status().received,2);assert.equal(gw.status().pending,2);
 gw.store.set('upstreamRetryAt',0);await gw.deliver();assert.equal(central.status().received,2);assert.equal(central.status().duplicates,2);assert.equal(gw.status().pending,0);assert.equal(gw.status().upstreamDelivered,2);
});
test('G3 mock HTTP notification sink creates one effect even if first response is lost',async t=>{
 gate();const dir=temp(),secret=key(),upstreamKey=key();const agent=source(path.join(dir,'agent'),secret);agent.sample();agent.setPump('PUMP-03',true);
 const central=services.createCentral({role:'central',id:'CENTRAL-LAB',dataDir:path.join(dir,'sink'),listen:{host:'127.0.0.1',port:0},keys:{'PC-04':upstreamKey}});await central.start();
 const gw=services.createGateway({role:'gateway',id:'PC-04',dataDir:path.join(dir,'gw'),listen:{host:'127.0.0.1',port:0},keys:{'PC-01':secret},notificationSink:{url:`http://127.0.0.1:${central.port}`,secret:upstreamKey},internetMode:'simulated'},{env:{}});
 t.after(async()=>{await gw.close();await central.close();await agent.close();fs.rmSync(dir,{recursive:true,force:true})});
 gw.store.ingest('PC-01',records(agent));central.store.set('dropNotificationAck',true);gw.setInternet(true);await gw.deliver();assert.equal(central.status().notificationEffects,1);assert.equal(gw.status().notificationSent,0);
 gw.store.db.exec('UPDATE notifications SET next_at=0');await gw.deliver();assert.equal(central.status().notificationEffects,1);assert.equal(gw.status().notificationSent,1);
});
test('G3 Telegram defaults off and fixed HTTPS transport handles 429 without leaking tokens',async()=>{
 gate();const {TelegramTransport}=await import('../src/lan/telegram.js');let calls=[];
 const transport=new TelegramTransport({env:{TELEGRAM_BOT_TOKEN:'123:test',TELEGRAM_CHAT_ID:'456'},request(){throw Error('Default mode made external request')}});
 assert.equal(transport.mode,'dry-run');assert.equal(await transport.probe(),false);
 const {EventEmitter}=await import('node:events');
 const fake=(options,callback)=>{calls.push(options);const req=new EventEmitter();req.end=()=>{const res=new EventEmitter();res.statusCode=429;callback(res);queueMicrotask(()=>{res.emit('data',Buffer.from('{"ok":false,"parameters":{"retry_after":60}}'));res.emit('end')})};req.destroy=()=>{};return req};
 const enabled=new TelegramTransport({env:{TELEGRAM_ENABLED:'true',TELEGRAM_BOT_TOKEN:'123:FAKE_TEST_ONLY',TELEGRAM_CHAT_ID:'456',TELEGRAM_APPROVED_ENDPOINT:'https://api.telegram.org'},request:fake});
 await assert.rejects(()=>enabled.send('[AQUA LAB / SIMULATED] test'),e=>e.retryAfterMs===60000&&!e.message.includes('FAKE_TEST_ONLY'));
 assert.equal(calls.length,1);assert.equal(calls[0].hostname,'api.telegram.org');assert.equal(calls[0].port,443);assert.equal(calls[0].rejectUnauthorized,true);
});
test('G3 Telegram cooldown blocks whole queue and probes across Gateway restart',async t=>{
 gate();const dir=temp(),secret=key();const agent=source(path.join(dir,'agent'),secret);agent.sample();agent.setPump('PUMP-03',true);agent.setPump('PUMP-03',false);
 let sends=0,probes=0;const telegram={mode:'telegram',configured:true,probe:async()=>{probes++;return true},send:async()=>{sends++;throw Object.assign(Error('rate limited'),{retryAfterMs:60000})}};
 const cfg={role:'gateway',id:'PC-04',dataDir:path.join(dir,'gw'),listen:{host:'127.0.0.1',port:0},keys:{'PC-01':secret},internetMode:'real'};let gw=services.createGateway(cfg,{telegram});
 t.after(async()=>{await gw.close();await agent.close();fs.rmSync(dir,{recursive:true,force:true})});
 gw.store.ingest('PC-01',records(agent));gw.setInternet(true);await gw.deliver();await gw.deliver();assert.equal(sends,1);assert.equal(gw.status().notificationPending,2);
 await gw.close();gw=services.createGateway(cfg,{telegram});await gw.deliver();assert.equal(sends,1);assert.equal(probes,1);
});
test('G3 WinCC adapter remains an unavailable read-only interface without any driver access',async()=>{
 assert.ok(fs.existsSync(path.resolve(import.meta.dirname,'../src/lan/adapters.js')),'Adapter boundary is missing');
 const {WinCCReadonlyAdapter}=await import('../src/lan/adapters.js');const source=new WinCCReadonlyAdapter();assert.equal(source.available,false);assert.throws(()=>source.read(),/authorization|approved|unavailable/i);
});
