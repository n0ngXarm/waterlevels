import {assertOwnedStorage} from './storage-boundary.js';
import fs from 'node:fs';
import path from 'node:path';
import {DatabaseSync} from 'node:sqlite';
import {randomUUID,randomBytes} from 'node:crypto';
import {digest,encode} from './protocol.js';
import {processIdentity} from './process-identity.js';

export const GROUPS={'PC-01':['PUMP-01','PUMP-02','PUMP-03'],'PC-02':['PUMP-04','PUMP-05','PUMP-06'],'PC-03':['PUMP-07','PUMP-08']};
export const INITIAL=Object.fromEntries(Object.values(GROUPS).flat().map(id=>[id,['PUMP-01','PUMP-02','PUMP-04','PUMP-06','PUMP-07'].includes(id)]));
export class Store{
 constructor(dir,options={}){
  this.maxPending=options.maxPending??10000;this.maxHistory=options.maxHistory??2000;this.maxRecords=options.maxRecords??50000;
  this.notifications=options.notifications===true;this.allowReorderedRuntime=options.allowReorderedRuntime===true;
  for(const n of [this.maxPending,this.maxHistory,this.maxRecords])if(!Number.isSafeInteger(n)||n<1||n>1000000)throw Error('Invalid LAB storage quota');
  assertOwnedStorage(dir);fs.mkdirSync(dir,{recursive:true,mode:0o700});this.dir=dir;this.db=new DatabaseSync(path.join(dir,'aqua.sqlite3'));
  this.db.exec('PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=3000;');
  this.db.exec('PRAGMA max_page_count=16384; PRAGMA wal_autocheckpoint=256; PRAGMA journal_size_limit=4194304;');
  this.db.exec(`CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY,value TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,source TEXT NOT NULL,seq INTEGER NOT NULL,kind TEXT NOT NULL,at TEXT NOT NULL,payload TEXT NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL DEFAULT 0,acked_at TEXT,UNIQUE(source,seq));
   CREATE TABLE IF NOT EXISTS nonces(source TEXT,nonce TEXT,at REAL,PRIMARY KEY(source,nonce));
   CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,source TEXT,expires REAL);
   CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY,at TEXT,kind TEXT,message TEXT);
   CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,source TEXT,payload TEXT,text TEXT,state TEXT NOT NULL DEFAULT 'pending',mode TEXT,attempts INTEGER NOT NULL DEFAULT 0,next_at REAL NOT NULL DEFAULT 0,delivered_at TEXT,message_id TEXT);
   CREATE TABLE IF NOT EXISTS notification_receipts(id TEXT PRIMARY KEY,digest TEXT,text TEXT,at TEXT);`);
 }
 get(key,fallback=null){const row=this.db.prepare('SELECT value FROM kv WHERE key=?').get(key);return row?JSON.parse(row.value):fallback}
 set(key,value){this.db.prepare('INSERT OR REPLACE INTO kv VALUES(?,?)').run(key,encode(value))}
 acquireOwner(id){return this.tx(()=>{
  const owner=this.get('serviceOwner');
  if(owner){
   if(owner.id!==id||!Number.isSafeInteger(owner.pid)||owner.pid<=0)throw Object.assign(Error('LAB role/data identity mismatch'),{code:'LAB_ROLE_DATA_MISMATCH'});
   let alive=true;try{process.kill(owner.pid,0)}catch(e){if(e.code==='ESRCH')alive=false}
   const liveInstance=alive?processIdentity(owner.pid):null;
   if(alive&&(!owner.instance||!liveInstance||owner.instance===liveInstance))throw Object.assign(Error('LAB data directory is already owned by a running service'),{code:'LAB_DATA_IN_USE'});
  }
  const instance=processIdentity(process.pid);if(!instance)throw Object.assign(Error('Cannot establish stable LAB process ownership'),{code:'LAB_PROCESS_IDENTITY_UNAVAILABLE'});
  this.set('serviceOwner',{id,pid:process.pid,instance,startedAt:new Date().toISOString()});
 })}
 tx(fn){this.db.exec('BEGIN IMMEDIATE');try{const value=fn();this.db.exec('COMMIT');return value}catch(e){this.db.exec('ROLLBACK');throw e}}
 claimNonce(source,nonce){
  this.db.prepare('DELETE FROM nonces WHERE at<?').run(Date.now()-60000);
  try{this.db.prepare('INSERT INTO nonces VALUES(?,?,?)').run(source,nonce,Date.now());return true}catch(e){if((e.errcode&255)===19)return false;throw e}
 }
 log(kind,message){this.db.prepare('INSERT INTO logs(at,kind,message) VALUES(?,?,?)').run(new Date().toISOString(),kind,String(message).slice(0,300));this.db.exec('DELETE FROM logs WHERE id<(SELECT MAX(id)-999 FROM logs)')}
 logs(){return this.db.prepare('SELECT * FROM logs ORDER BY id DESC LIMIT 100').all().map(r=>({...r,time:r.at}))}
 pumps(source){return this.get('pumps',Object.fromEntries((GROUPS[source]||[]).map(id=>[id,INITIAL[id]])))}
 append(source,kind,values,extra={}){
  return this.tx(()=>{
   if(this.db.prepare("SELECT count(*) n FROM records WHERE state!='acked'").get().n>=this.maxPending)throw Object.assign(Error('Local pending quota reached; retained records are not deleted'),{status:507});
   const seq=this.get('sequence',0)+1;
   const event={event_id:`${source}:${randomUUID()}`,schema:'aqua.runtime.v1',schema_version:1,source_id:source,sequence:seq,kind,at:new Date().toISOString(),simulated:true,values,...extra};
   const payload=encode(event),hash=digest(payload);
   this.db.prepare('INSERT INTO records(id,source,seq,kind,at,payload,digest) VALUES(?,?,?,?,?,?,?)').run(event.event_id,source,seq,kind,event.at,payload,hash);
   this.set('sequence',seq);this.set('pumps',values);this.set(kind==='SNAPSHOT'?'snapshots':'transitions',this.get(kind==='SNAPSHOT'?'snapshots':'transitions',0)+1);
   if(kind==='SNAPSHOT')this.set('lastExport',event.at);
   this.log(kind,`${source} #${seq}${extra.tag_name?' '+extra.tag_name:''}`);return event;
  });
 }
 appendRuntime(source,frame,cursor){return this.tx(()=>{
  const previous=this.get('runtimePrevious',{}),changes=[];
  for(const [tag,value] of Object.entries(frame.values)){
   if(typeof value==='boolean'&&typeof previous[tag]==='boolean'&&value!==previous[tag])changes.push({tag_name:tag,before:previous[tag],value});
  }
  if(this.stats().pending+1+changes.length>this.maxPending)throw Error('Local pending quota reached; cursor and committed data retained');
  const at=new Date().toISOString();
  for(const [kind,extra] of [['SNAPSHOT',{}],...changes.map(c=>['STATE_CHANGE',c])]){
   const seq=this.get('sequence',0)+1,event={event_id:`${source}:${randomUUID()}`,schema:'aqua.runtime.v2',schema_version:2,source_id:source,sequence:seq,kind,at,simulated:frame.simulated,observed_at:frame.observed_at,values:frame.values,observations:frame.observations,...extra};
   this.validate(source,event);const payload=encode(event);
   this.db.prepare('INSERT INTO records(id,source,seq,kind,at,payload,digest) VALUES(?,?,?,?,?,?,?)').run(event.event_id,source,seq,kind,at,payload,digest(payload));this.set('sequence',seq);
   const key=kind==='SNAPSHOT'?'snapshots':'transitions';this.set(key,this.get(key,0)+1);this.log(kind,`${source} read-only runtime #${seq}`);
  }
  this.set('runtimePrevious',frame.values);this.set('pumps',frame.values);this.set('runtimeObservedAt',frame.observed_at);this.set('runtimeObservations',frame.observations);this.set('lastExport',at);this.set(cursor.key,cursor.value);
 })}
 pending(limit=32){return this.db.prepare("SELECT * FROM records WHERE state!='acked' ORDER BY seq LIMIT ?").all(limit)}
 acknowledge(acks){return this.tx(()=>{
  let count=0;for(const ack of acks){const r=this.db.prepare("UPDATE records SET state='acked',acked_at=? WHERE id=? AND digest=? AND state!='acked'").run(new Date().toISOString(),ack.event_id,ack.sha256);count+=Number(r.changes)}
  if(count){this.set('acked',this.get('acked',0)+count);this.set('lastAckAt',new Date().toISOString());this.log('DELIVERY',`${count} records Gateway ACKed`);this.db.prepare("DELETE FROM records WHERE state='acked' AND id NOT IN (SELECT id FROM records WHERE state='acked' ORDER BY seq DESC LIMIT ?)").run(this.maxHistory)}return count;
 })}
 session(source){const token=randomBytes(32).toString('hex'),expiresAt=Date.now()+30000;this.db.prepare('DELETE FROM sessions WHERE expires<?').run(Date.now());this.db.prepare('INSERT INTO sessions VALUES(?,?,?)').run(digest(token),source,expiresAt);return {session:token,expiresAt}}
 validSession(source,token){return typeof token==='string'&&!!this.db.prepare('SELECT token FROM sessions WHERE token=? AND source=? AND expires>?').get(digest(token),source,Date.now())}
 validate(source,event){
  if(event?.schema==='aqua.runtime.v2'){
   const fail=()=>{throw Object.assign(Error('Invalid read-only runtime schema'),{status:400})};
   if(!GROUPS[source]||event.source_id!==source||event.schema_version!==2||typeof event.simulated!=='boolean'||!['SNAPSHOT','STATE_CHANGE'].includes(event.kind)||!Number.isSafeInteger(event.sequence)||event.sequence<1||typeof event.event_id!=='string'||!event.event_id.startsWith(source+':')||event.event_id.length>100||!Number.isFinite(Date.parse(event.at))||!Number.isFinite(Date.parse(event.observed_at))||!event.values||!event.observations)fail();
   const tags=Object.keys(event.values);if(!tags.length||tags.length>100||Object.keys(event.observations).length!==tags.length)fail();
   for(const tag of tags){const v=event.values[tag],o=event.observations[tag];if(!/^[-A-Za-z0-9_.]{1,100}$/.test(tag)||(v!==null&&typeof v!=='boolean')||!o||Object.keys(o).some(k=>!['raw_value','quality_code','read_error','quality'].includes(k))||(o.raw_value!==null&&!Number.isFinite(o.raw_value))||(o.quality_code!==null&&(!Number.isSafeInteger(o.quality_code)||o.quality_code<0||o.quality_code>4294967295))||!Number.isSafeInteger(o.read_error)||!['GOOD','BAD','UNVERIFIED_MAPPING','UNSUPPORTED_VALUE'].includes(o.quality)||(o.quality!=='GOOD'&&v!==null)||(o.quality==='GOOD'&&(o.read_error!==0||![0,1].includes(o.raw_value)||v!==(o.raw_value===1))))fail()}
   const allowed=['event_id','schema','schema_version','source_id','sequence','kind','at','simulated','observed_at','values','observations',...(event.kind==='STATE_CHANGE'?['tag_name','before','value']:[])];if(Object.keys(event).some(k=>!allowed.includes(k)))fail();
   if(event.kind==='STATE_CHANGE'&&(!tags.includes(event.tag_name)||typeof event.before!=='boolean'||typeof event.value!=='boolean'||event.before===event.value||event.values[event.tag_name]!==event.value))fail();return;
  }
  const ids=GROUPS[source];
  if(!ids||!event||event.schema!=='aqua.runtime.v1'||event.schema_version!==1||event.source_id!==source||event.simulated!==true||!['SNAPSHOT','STATE_CHANGE'].includes(event.kind)||!Number.isSafeInteger(event.sequence)||event.sequence<1||typeof event.event_id!=='string'||!event.event_id.startsWith(source+':')||event.event_id.length>100||typeof event.at!=='string'||!Number.isFinite(Date.parse(event.at))||!event.values||Object.keys(event.values).length!==ids.length||!ids.every(id=>typeof event.values[id]==='boolean'))throw Object.assign(Error('Invalid simulated runtime schema'),{status:400});
  const allowed=['event_id','schema','schema_version','source_id','sequence','kind','at','simulated','values',...(event.kind==='STATE_CHANGE'?['tag_name','before','value']:[])];
  if(Object.keys(event).some(k=>!allowed.includes(k)))throw Object.assign(Error('Unexpected runtime field'),{status:400});
  if(event.kind==='STATE_CHANGE'&&(!ids.includes(event.tag_name)||typeof event.before!=='boolean'||typeof event.value!=='boolean'||event.before===event.value||event.values[event.tag_name]!==event.value))throw Object.assign(Error('Invalid state transition'),{status:400});
 }
 ingest(source,events){
  if(!Array.isArray(events)||!events.length||events.length>32)throw Object.assign(Error('Invalid batch'),{status:400});
  events.forEach(e=>this.validate(source,e));
  if(events.some((e,i)=>i>0&&e.sequence<=events[i-1].sequence))throw Object.assign(Error('Batch order rejected'),{status:409});
  return this.tx(()=>{
   let last=this.get('last:'+source,0),duplicates=0;const acks=[];
   for(const event of events){
    const payload=encode(event),hash=digest(payload),old=this.db.prepare('SELECT digest FROM records WHERE id=?').get(event.event_id);
    if(old){if(old.digest!==hash)throw Object.assign(Error('Event ID collision'),{status:409});duplicates++}
    else{
     if(this.db.prepare('SELECT count(*) n FROM records').get().n>=this.maxRecords)throw Object.assign(Error('Gateway ledger quota reached; source must retain backlog'),{status:507});
     if(event.sequence!==last+1&&!(event.schema_version===2&&(event.sequence>last||this.allowReorderedRuntime)))throw Object.assign(Error('Source sequence gap/collision'),{status:409});
     this.db.prepare('INSERT INTO records(id,source,seq,kind,at,payload,digest) VALUES(?,?,?,?,?,?,?)').run(event.event_id,source,event.sequence,event.kind,event.at,payload,hash);
     last=Math.max(last,event.sequence);this.set('received',this.get('received',0)+1);
     if(this.notifications&&event.kind==='STATE_CHANGE')this.db.prepare('INSERT INTO notifications(id,source,payload,text) VALUES(?,?,?,?)').run(event.event_id,source,payload,this.notificationText(event));
    }
    acks.push({event_id:event.event_id,sha256:hash});
   }
   this.set('last:'+source,last);this.set('duplicates',this.get('duplicates',0)+duplicates);this.log('DELIVERY',`${source}: ${events.length} durably received`);return acks;
  });
 }
 stats(){return {snapshots:this.get('snapshots',0),transitions:this.get('transitions',0),pending:Number(this.db.prepare("SELECT count(*) n FROM records WHERE state!='acked'").get().n),acked:this.get('acked',0),received:this.get('received',0),duplicates:this.get('duplicates',0),lastExport:this.get('lastExport'),lastAckAt:this.get('lastAckAt'),sequence:this.get('sequence',0),latest:this.db.prepare("SELECT payload FROM records WHERE kind='SNAPSHOT' ORDER BY seq DESC LIMIT 1").get()?.payload??null}}
 disk(){return {bytes:['aqua.sqlite3','aqua.sqlite3-wal','aqua.sqlite3-shm'].reduce((sum,name)=>{try{return sum+fs.statSync(path.join(this.dir,name)).size}catch{return sum}},0),maxDatabaseBytes:64*1024*1024,maxPending:this.maxPending,maxHistory:this.maxHistory,maxRecords:this.maxRecords}}
 notificationText(e){return `[${e.simulated?'AQUA LAB / SIMULATED':'AQUA READ-ONLY FILE / WINCC CONNECTION UNVERIFIED'}]\n${e.source_id} ${e.tag_name}: ${e.before?'ON':'OFF'} -> ${e.value?'ON':'OFF'}\n${e.observed_at||e.at}\nevent_id: ${e.event_id}`}
 notificationStats(){return {notificationPending:Number(this.db.prepare("SELECT count(*) n FROM notifications WHERE state='pending'").get().n),notificationSent:Number(this.db.prepare("SELECT count(*) n FROM notifications WHERE state='delivered'").get().n),notificationEffects:Number(this.db.prepare('SELECT count(*) n FROM notification_receipts').get().n)}}
 messages(){return this.db.prepare("SELECT id event_id,source source_id,text,mode,delivered_at,message_id FROM notifications WHERE state='delivered' ORDER BY delivered_at DESC LIMIT 50").all()}
 nextNotification(){return this.db.prepare("SELECT * FROM notifications WHERE state='pending' AND next_at<=? ORDER BY rowid LIMIT 1").get(Date.now())}
 markNotification(id,mode,messageId=null){return this.tx(()=>{this.db.prepare("UPDATE notifications SET state='delivered',mode=?,delivered_at=?,message_id=? WHERE id=? AND state='pending'").run(mode,new Date().toISOString(),messageId===null?null:String(messageId),id);this.log('DELIVERY',`${mode} transition notification committed`)})}
 failNotification(id,delay){this.db.prepare('UPDATE notifications SET attempts=attempts+1,next_at=? WHERE id=?').run(Date.now()+delay,id);this.log('RETRY','Transition notification remains queued')}
 receiveNotification(event){
  this.validate(event.source_id,event);if(event.kind!=='STATE_CHANGE')throw Object.assign(Error('Only state transitions can notify'),{status:400});
  return this.tx(()=>{const hash=digest(encode(event)),old=this.db.prepare('SELECT digest FROM notification_receipts WHERE id=?').get(event.event_id);
   if(old&&old.digest!==hash)throw Object.assign(Error('Notification ID collision'),{status:409});
   if(!old){if(this.db.prepare('SELECT count(*) n FROM notification_receipts').get().n>=this.maxRecords)throw Object.assign(Error('Notification receipt quota reached'),{status:507});this.db.prepare('INSERT INTO notification_receipts VALUES(?,?,?,?)').run(event.event_id,hash,this.notificationText(event),new Date().toISOString())}
   return {event_id:event.event_id,sha256:hash};
  });
 }
 markForwarded(acks){return this.tx(()=>{let changed=0;for(const ack of acks)changed+=Number(this.db.prepare("UPDATE records SET state='acked',acked_at=? WHERE id=? AND digest=? AND state!='acked'").run(new Date().toISOString(),ack.event_id,ack.sha256).changes);this.set('upstreamDelivered',this.get('upstreamDelivered',0)+changed);if(changed){this.set('lastDelivery',new Date().toISOString());this.log('DELIVERY',`${changed} records upstream ACKed`)}return changed})}
 close(){this.db.close()}
}
