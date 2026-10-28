import {assertStorageOutsideInput} from './csv-source.js';
import {fork} from 'node:child_process';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {enrollment} from './config.js';import {loopback,endpoint} from './protocol.js';
const service=fileURLToPath(new URL('../../bin/aqua-service.js',import.meta.url));
const running=c=>c&&c.exitCode===null&&c.signalCode===null;
export async function startSingle(dataRoot,options={}){
 if(options.sourceDirectory)assertStorageOutsideInput(options.sourceDirectory,dataRoot);
 const lab={enrollment:enrollment(dataRoot,options),children:new Map(),stopping:false,wantedGateway:options.profile==='readonly',restarts:new Set(),resetTimer:null,resetting:false};let operation=Promise.resolve(),shutdownRequested=false,shutdownTask=null,resetTask=null;
 for(const cfg of Object.values(lab.enrollment.configs))if(!loopback(cfg.listen.host)||!path.resolve(cfg.dataDir).startsWith(lab.enrollment.root+path.sep))throw Error('Single mode accepts only local LAB listeners/storage');
 for(const cfg of Object.values(lab.enrollment.configs))for(const url of [cfg.gatewayUrl,...(cfg.gatewayUrls||[]),cfg.upstream?.url,cfg.notificationSink?.url,cfg.gateway?.url,cfg.central?.url,...(cfg.agents||[]).map(a=>a.url)].filter(Boolean))endpoint(url);
 const log=text=>{if(!options.quiet)console.log(text)};
 async function stopOne(id){const c=lab.children.get(id);lab.children.delete(id);if(!running(c))return;await new Promise(resolve=>{const timer=setTimeout(()=>c.kill('SIGKILL'),5000);c.once('exit',()=>{clearTimeout(timer);resolve()});c.kill('SIGTERM')})}
 async function launch(id){
  if(shutdownRequested||lab.stopping)return;
  if(running(lab.children.get(id)))return lab.children.get(id);
  const env={...process.env};if(id!=='gateway')for(const name of ['TELEGRAM_ENABLED','TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','TELEGRAM_APPROVED_ENDPOINT'])delete env[name];
  const child=fork(service,['--config',lab.enrollment.files[id]],{env,stdio:['ignore','pipe','pipe','ipc']});lab.children.set(id,child);
  if(!options.quiet){child.stdout.on('data',p=>process.stdout.write(p));child.stderr.on('data',p=>process.stderr.write(p))}else{child.stdout.resume();child.stderr.resume()}
  child.on('message',message=>{if(id==='dashboard'&&message?.type==='control')lab.control(message.body).then(result=>{if(child.connected)child.send({type:'control-result',id:message.id,result})},()=>{if(child.connected)child.send({type:'control-result',id:message.id,error:'LAB operation failed'})})});
  child.once('exit',()=>{if(lab.children.get(id)===child&&!lab.stopping&&(id!=='gateway'||lab.wantedGateway)){lab.children.delete(id);log(`${id} stopped unexpectedly; restoring durable LAB role`);const timer=setTimeout(()=>{lab.restarts.delete(timer);if(!lab.stopping)launch(id).catch(()=>log(`${id} restart failed; inspect LAB port/data permissions`))},500);lab.restarts.add(timer)}});
  await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('LAB role readiness timeout')),7000);const onExit=()=>{clearTimeout(timeout);reject(Error('LAB role failed to start'))};child.once('exit',onExit);child.on('message',m=>{if(m?.type==='ready'){clearTimeout(timeout);child.off('exit',onExit);resolve()}})});return child;
 }
 async function boot(){await Promise.all(Object.keys(lab.enrollment.configs).filter(id=>id.startsWith('PC-0')||id==='central'||id==='fixture').map(launch));if(shutdownRequested||lab.stopping)return;if(lab.wantedGateway)await launch('gateway');if(shutdownRequested||lab.stopping)return;if(!options.desktop)await launch('dashboard')}
 const stopRoles=async()=>{lab.stopping=true;if(lab.resetTimer){clearTimeout(lab.resetTimer);lab.resetTimer=null}for(const timer of lab.restarts)clearTimeout(timer);lab.restarts.clear();await Promise.all([...lab.children.keys()].map(stopOne))};
 lab.stop=()=>{shutdownRequested=true;return shutdownTask??=(async()=>{await stopRoles();if(resetTask)await resetTask;await stopRoles()})()};
 lab.control=body=>{const next=operation.then(async()=>{
  if(shutdownRequested)throw Error('LAB is shutting down');
  if(lab.resetting&&body.action!=='reset')throw Error('LAB reset in progress');
  if(body.action==='gateway'){lab.wantedGateway=body.connected;if(body.connected)await launch('gateway');else await stopOne('gateway');return {ok:true}}
  if(body.action==='reset'){if(lab.resetting)return {resetting:true};lab.resetting=true;lab.resetTimer=setTimeout(()=>{lab.resetTimer=null;resetTask=(async()=>{await stopRoles();if(shutdownRequested)return;lab.enrollment=enrollment(dataRoot,{...options,newSession:true});if(shutdownRequested)return;lab.stopping=false;lab.wantedGateway=options.profile==='readonly';await boot()})().catch(async()=>{await stopRoles();log('Reset startup failed; original session data remains preserved')}).finally(()=>{lab.resetting=false})},150);return {resetting:true}}
  throw Error('Unknown supervisor control');
 });operation=next.catch(()=>{});return next};
 try{await boot();return lab}catch(e){await lab.stop();throw e}
}
