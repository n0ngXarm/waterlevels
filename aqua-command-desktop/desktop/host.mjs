import fs from 'node:fs';import path from 'node:path';import {randomUUID} from 'node:crypto';import {fileURLToPath} from 'node:url';
import {startSingle} from '../backend/src/lan/supervisor.js';import {createDashboard} from '../backend/src/lan/dashboard.js';import {CsvReadonlySource,assertStorageOutsideInput} from '../backend/src/lan/csv-source.js';import {assertOwnedStorage} from '../backend/src/lan/storage-boundary.js';import {requestJSON} from '../backend/src/lan/protocol.js';
export async function startDesktopHost({dataRoot,port=4173,sourceSettings={},emit=()=>{}}){
 if(!dataRoot)throw Error('A separate owned AQUA data directory is required');dataRoot=path.resolve(dataRoot);
 const settings=sourceSettings;if(!settings||Array.isArray(settings)||Object.keys(settings).some(k=>!['sourceDirectory','tags','timezoneOffset','mappingConfirmed','internetMode'].includes(k)))throw Error('Unsupported source settings');
 if(settings.sourceDirectory){if(!fs.statSync(settings.sourceDirectory).isDirectory())throw Error('CSV source folder unavailable');new CsvReadonlySource({dataDir:dataRoot,csv:{directory:settings.sourceDirectory,tags:settings.tags,timezoneOffset:settings.timezoneOffset||'+07:00',mappingConfirmed:settings.mappingConfirmed===true}},null,'PC-01')}
 const lab=await startSingle(dataRoot,{port,profile:'readonly',readOnly:true,desktop:true,requireConsent:true,quiet:true,sourceDirectory:settings.sourceDirectory,csvTags:settings.tags,csvTimezone:settings.timezoneOffset,mappingConfirmed:settings.mappingConfirmed===true,internetMode:settings.internetMode||'simulated'});
 const model=createDashboard(lab.enrollment.configs.dashboard,{headless:true});try{await model.start()}catch(e){await lab.stop();throw e}
 let captureAllowed=false,transferAllowed=false;
 const status=()=>({...model.status(),captureAllowed:captureAllowed&&model.status().agents?.[0]?.captureAllowed===true,transferAllowed:transferAllowed&&model.status().agents?.[0]?.transferAllowed===true,webUiEnabled:false,frontend:'native-gtk4',readOnly:true});
 const setTransfer=async running=>{const c=lab.enrollment.configs.dashboard,a=c.agents[0];await Promise.all([requestJSON(a.url,'/v1/transfer',{id:a.id,secret:a.secret},{running},{}),requestJSON(c.gateway.url,'/v1/transfer',{id:'DASHBOARD',secret:c.gateway.secret},{running},{})]);transferAllowed=running};
 const commands={status:async()=>status(),recording:async m=>{if(typeof m.running!=='boolean')throw Error('Local recording boolean required');if(m.running)await lab.control({action:'fixture',running:true});await model.action({action:'recording',running:m.running});captureAllowed=m.running;if(!m.running)await lab.control({action:'fixture',running:false});return status()},transfer:async m=>{if(typeof m.running!=='boolean')throw Error('Transfer boolean required');try{await setTransfer(m.running)}catch(e){await setTransfer(false).catch(()=>{});transferAllowed=false;throw e}return status()},export_csv:async()=>{
  const a=lab.enrollment.configs.dashboard.agents[0],result=await requestJSON(a.url,'/v1/exports',{id:a.id,secret:a.secret},{},{}),lines=['recorded_at;observed_at;tag_name;raw_value;quality_code;read_error;quality'];
  for(const event of result.records.filter(e=>e.schema_version===2&&e.kind==='SNAPSHOT'))for(const [tag,o] of Object.entries(event.observations))lines.push([event.at,event.observed_at,tag,o.raw_value??'',o.quality_code??'',o.read_error,o.quality].join(';'));
  const directory=path.join(dataRoot,'exports');if(settings.sourceDirectory)assertStorageOutsideInput(settings.sourceDirectory,directory);assertOwnedStorage(dataRoot);fs.mkdirSync(directory,{recursive:true,mode:0o700});
  const file=path.join(directory,`AQUA-${new Date().toISOString().replaceAll(':','-')}-${randomUUID().slice(0,8)}.csv`),fd=fs.openSync(file,'wx',0o600);try{fs.writeFileSync(fd,lines.join('\r\n')+'\r\n');fs.fsyncSync(fd)}finally{fs.closeSync(fd)}return {path:file,rows:lines.length-1,truncated:result.truncated===true,totalRecords:result.totalRecords};
 }};
 let stopped=false;const timer=setInterval(()=>emit({type:'status',data:status()}),1000);
 return {lab,model,status,async request(m){
  if(!m||typeof m.id!=='string'||!m.id.length||m.id.length>80)return {id:null,ok:false,error:{code:'INVALID_REQUEST'}};
  if(stopped)return {id:m.id,ok:false,error:{code:'CLOSING'}};
  if(!Object.hasOwn(commands,m.command)||Object.keys(m).some(k=>!['id','command',...(['recording','transfer'].includes(m.command)?['running','approved']:[])].includes(k)))return {id:m.id,ok:false,error:{code:'READ_ONLY',message:'Only local recording, saved-data export and status are allowed'}};
  if(['recording','transfer'].includes(m.command)&&m.running===true&&m.approved!==true)return {id:m.id,ok:false,error:{code:'CONSENT_REQUIRED',message:'Explicit approval is required before starting'}};
  try{return {id:m.id,ok:true,result:await commands[m.command](m)}}catch{return {id:m.id,ok:false,error:{code:'LOCAL_OPERATION_FAILED',message:'Check local source and AQUA storage permissions'}}}
 },async close(){if(stopped)return;stopped=true;clearInterval(timer);await Promise.all([model.close(),lab.stop()])}};
}
async function main(){const args=process.argv.slice(2),value=k=>args.includes(k)?args[args.indexOf(k)+1]:undefined;const dataRoot=value('--data-dir');let settings={};if(value('--config')){const raw=fs.readFileSync(value('--config'));if(raw.length>32768)throw Error('Configuration size limit');settings=JSON.parse(raw)}
 const emit=m=>{if(!process.stdout.destroyed&&!process.stdout.writableNeedDrain)process.stdout.write(JSON.stringify(m)+'\n')};const host=await startDesktopHost({dataRoot,port:Number(value('--port')||4173),sourceSettings:settings,emit});
 let closing=false,buffer='',operation=Promise.resolve(),queued=0;
 const stop=async()=>{if(closing)return;closing=true;await operation.catch(()=>{});await host.close();process.exit(0)};
 process.on('SIGTERM',stop);process.on('SIGINT',stop);process.stdin.on('end',stop);
 process.stdin.on('data',chunk=>{buffer+=chunk.toString('utf8');if(Buffer.byteLength(buffer)>32768){buffer='';emit({id:null,ok:false,error:{code:'INPUT_LIMIT'}});return}while(buffer.includes('\n')){const i=buffer.indexOf('\n'),line=buffer.slice(0,i);buffer=buffer.slice(i+1);if(!line.trim())continue;let m;try{m=JSON.parse(line)}catch{emit({id:null,ok:false,error:{code:'INVALID_JSON'}});continue}if(queued>=16){emit({id:m?.id??null,ok:false,error:{code:'BUSY'}});continue}queued++;operation=operation.then(async()=>{if(!closing)emit(await host.request(m))}).finally(()=>queued--)}});
 emit({type:'ready',data:host.status()});
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(()=>{console.error('AQUA desktop backend could not start. Check Node22.13+, local ports, source/config and owned data permissions.');process.exitCode=1});
