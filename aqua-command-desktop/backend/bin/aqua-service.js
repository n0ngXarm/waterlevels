#!/usr/bin/env node
import {createCsvFixture} from '../src/lan/csv-fixture.js';
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';import {randomUUID} from 'node:crypto';
import {createAgent,createGateway,createCentral} from '../src/lan/services.js';import {createDashboard} from '../src/lan/dashboard.js';import {loopback} from '../src/lan/protocol.js';
export async function runRole(args=process.argv.slice(2),{lanMode=false}={}){
 const value=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
 if(args.includes('--help')){console.log('AQUA LAB role: --config <enrolled-role.json>; LAN: --role agent|gateway|central|dashboard [--allow-lan]');return}
 const file=value('--config');if(!file)throw Object.assign(Error('Enrolled config required'),{code:'LAB_CONFIG_REQUIRED'});
 const config=JSON.parse(fs.readFileSync(file,'utf8'));
 if(lanMode){
  if(!['agent','gateway','central','dashboard'].includes(value('--role'))||value('--role')!==config.role)throw Object.assign(Error('Role/config mismatch'),{code:'LAB_ROLE_MISMATCH'});
  const hosts=[config.listen?.host,...[config.gatewayUrl,...(config.gatewayUrls||[]),config.upstream?.url,config.notificationSink?.url,config.gateway?.url,config.central?.url,...(config.agents||[]).map(x=>x.url)].filter(Boolean).map(url=>new URL(url).hostname)];
  if(hosts.some(host=>!loopback(host))&&(!args.includes('--allow-lan')||config.allowLan!==true))throw Object.assign(Error('Explicit LAB LAN permission required'),{code:'LAB_ALLOW_LAN_REQUIRED'});
  if(config.role==='dashboard'){config.controlMode='readonly';config.readOnly=true}
 }
 if(config.role==='agent'&&config.sourceAdapter==='wincc-csv')config.readOnly=true;
 const control=body=>new Promise((resolve,reject)=>{if(!process.send)return reject(Error('Single-host supervisor required'));const id=randomUUID(),timeout=setTimeout(()=>{process.off('message',handler);reject(Error('Supervisor timeout'))},6000);const handler=m=>{if(m?.type==='control-result'&&m.id===id){clearTimeout(timeout);process.off('message',handler);m.error?reject(Error(m.error)):resolve(m.result)}};process.on('message',handler);process.send({type:'control',id,body})});
 let app;try{
  app=config.role==='fixture'?createCsvFixture(config):config.role==='agent'?createAgent(config):config.role==='gateway'?createGateway(config):config.role==='central'?createCentral(config):config.role==='dashboard'?createDashboard(config,{onControl:process.send?control:null}):null;
  if(!app)throw Error('Unknown LAB role');if(app.store)app.store.acquireOwner(config.id);await app.start();console.log(`${config.id} ${config.role}: approved LAB listener ready; PID ${process.pid}`);
  if(process.send)process.send({type:'ready',id:config.id,port:app.port});
  let stopping=false;const stop=async()=>{if(stopping)return;stopping=true;try{await app.close()}finally{process.exit(0)}};process.once('SIGINT',stop);process.once('SIGTERM',stop);process.once('disconnect',stop);return app;
 }catch(e){if(app)try{await app.close()}catch{}throw e}
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))runRole().catch(e=>{console.error('AQUA LAB service failed:',e.code||'INVALID_LAB_CONFIGURATION_OR_STORAGE');process.exitCode=1});
