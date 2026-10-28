import {assertOwnedStorage} from './storage-boundary.js';
import {assertStorageOutsideInput} from './csv-source.js';
import fs from 'node:fs';import path from 'node:path';import {randomBytes,randomUUID} from 'node:crypto';
const privateFile=(file,value)=>{const tmp=file+'.'+randomUUID()+'.tmp',fd=fs.openSync(tmp,'wx',0o600);try{fs.writeFileSync(fd,JSON.stringify(value,null,2));fs.fsyncSync(fd)}finally{fs.closeSync(fd)}fs.renameSync(tmp,file);if(process.platform!=='win32'){fs.chmodSync(file,0o600);const d=fs.openSync(path.dirname(file),'r');try{fs.fsyncSync(d)}finally{fs.closeSync(d)}}};
function configSet(dir,configs){const generationDir=path.join(dir,'config-'+randomUUID());fs.mkdirSync(generationDir,{mode:0o700});const files={};for(const [id,config] of Object.entries(configs)){const file=path.join(generationDir,id+'.json');privateFile(file,config);files[id]=file}return files}
export function enrollment(root,options={}){
 root=path.resolve(root);assertOwnedStorage(root);if(options.sourceDirectory)assertStorageOutsideInput(options.sourceDirectory,root);fs.mkdirSync(root,{recursive:true});
 if(fs.existsSync(path.join(root,'simulation-state.json')))throw Error('Legacy v0.3 data detected: select a new LAB data directory');
 const profile=options.profile||'legacy';
 const dir=path.join(root,'enrollment');fs.mkdirSync(dir,{recursive:true,mode:0o700});if(process.platform!=='win32')fs.chmodSync(dir,0o700);
 const manifestPath=path.join(dir,'manifest.json');const old=fs.existsSync(manifestPath)?JSON.parse(fs.readFileSync(manifestPath,'utf8')):null;
 if(options.port!==undefined&&(!Number.isSafeInteger(options.port)||options.port<1024||options.port>65400))throw Error('Invalid LAB base port');
 if(old&&profile!==(old.profile||'legacy'))throw Error('Use a separate data directory for a different collector profile');
 if(old&&!options.newSession){
  if(options.sourceDirectory&&path.resolve(options.sourceDirectory)!==old.sourceDirectory)throw Error('Source directory is pinned; select a new data directory');
  if(options.port&&options.port!==old.basePort)throw Error('Enrollment ports are pinned; use a separate LAB data directory');
  const configs={};for(const [id,file] of Object.entries(old.files)){if(!path.resolve(file).startsWith(root+path.sep))throw Error('Enrollment file must remain in LAB directory');configs[id]=JSON.parse(fs.readFileSync(file,'utf8'))}
  if(old.sourceDirectory)assertStorageOutsideInput(old.sourceDirectory,root);
  if(options.csvTags&&JSON.stringify(options.csvTags)!==JSON.stringify(configs['PC-01']?.csv?.tags))throw Error('Tag settings changed: choose a separate data directory');
  const changed=(options.readOnly===true&&!old.readOnly)||(options.internetMode&&options.internetMode!==old.internetMode);
  if(changed){if(options.readOnly===true){for(const c of Object.values(configs))c.readOnly=true;old.readOnly=true}if(options.internetMode){configs.gateway.internetMode=options.internetMode;configs.dashboard.internetMode=options.internetMode;old.internetMode=options.internetMode}old.files=configSet(dir,configs);privateFile(manifestPath,old)}return {...old,configs,root};
 }
 const port=options.port||old?.basePort||4173;if(!Number.isSafeInteger(port)||port<1024||port>65400)throw Error('Invalid LAB base port');
 const idFile=path.join(dir,'identities.json');const identities=fs.existsSync(idFile)?JSON.parse(fs.readFileSync(idFile,'utf8')):Object.fromEntries(['PC-01','PC-02','PC-03','DASHBOARD','UPSTREAM','CONTROL'].map(id=>[id,randomBytes(32).toString('hex')]));if(!Object.values(identities).every(x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x)))throw Error('Invalid persisted LAB identity');if(!fs.existsSync(idFile))privateFile(idFile,identities);
 const generation=randomUUID(),session=path.join(root,'sessions',generation),configs={};fs.mkdirSync(session,{recursive:true});
 const intervalMs=options.intervalMs||old?.intervalMs||5000,readOnly=profile==='readonly'?true:options.readOnly??old?.readOnly??false;
 for(let n=1;n<=(profile==='readonly'?1:3);n++){const id=`PC-0${n}`;configs[id]={role:'agent',id,secret:identities[id],listen:{host:'127.0.0.1',port:port+7+n},gatewayUrl:`http://127.0.0.1:${port+1}`,dataDir:path.join(session,id),intervalMs,readOnly,sourceAdapter:'simulated-runtime'}}
 configs.gateway={role:'gateway',id:'PC-04',listen:{host:'127.0.0.1',port:port+1},keys:Object.fromEntries(['PC-01','PC-02','PC-03','DASHBOARD'].map(id=>[id,identities[id]])),dataDir:path.join(session,'PC-04'),readOnly,internetMode:options.internetMode||old?.internetMode||'simulated',upstream:{url:`http://127.0.0.1:${port+2}`,secret:identities.UPSTREAM}};
 configs.central={role:'central',id:'CENTRAL-LAB',listen:{host:'127.0.0.1',port:port+2},keys:{'PC-04':identities.UPSTREAM,DASHBOARD:identities.DASHBOARD},dataDir:path.join(session,'CENTRAL-LAB')};
 configs.dashboard={role:'dashboard',id:'DASHBOARD',listen:{host:'127.0.0.1',port},dataDir:path.join(session,'DASHBOARD'),controlToken:identities.CONTROL,controlMode:'single',readOnly,intervalMs,generation,agents:Object.keys(configs).filter(id=>id.startsWith('PC-0')).map(id=>({id,url:`http://127.0.0.1:${configs[id].listen.port}`,secret:identities[id]})),gateway:{url:`http://127.0.0.1:${port+1}`,secret:identities.DASHBOARD},central:{url:`http://127.0.0.1:${port+2}`,secret:identities.DASHBOARD}};
 configs.dashboard.internetMode=configs.gateway.internetMode;
 let sourceDirectory=null;
 if(profile==='readonly'){
  sourceDirectory=options.sourceDirectory?path.resolve(options.sourceDirectory):old?.sourceDirectory||null;
  const tags=options.csvTags||['LAB_PUMP_01.RUN_S','LAB_PUMP_02.RUN_S','LAB_PUMP_03.RUN_S','LAB_PUMP_04.RUN_S','LAB_PUMP_05.RUN_S'];
  const input=sourceDirectory||path.join(root,'fixture-input');
  Object.assign(configs['PC-01'],{sourceAdapter:'wincc-csv',csv:{directory:input,tags,timezoneOffset:sourceDirectory?(options.csvTimezone||'+07:00'):'+00:00',mappingConfirmed:sourceDirectory?options.mappingConfirmed===true:true,goodQualityCodes:[128],fixture:!sourceDirectory}});
  configs.gateway.internetOnline=true;configs.dashboard.profile='readonly';
  if(!sourceDirectory)configs.fixture={role:'fixture',id:'LAB-FIXTURE',fixtureOwned:true,fixtureRoot:root,listen:{host:'127.0.0.1',port:0},dataDir:path.join(session,'LAB-FIXTURE'),outputDirectory:input,tags,intervalMs};
 }
 const files=configSet(dir,configs);
 const manifest={version:1,profile,sourceDirectory,basePort:port,generation,intervalMs,readOnly,internetMode:configs.gateway.internetMode,files};privateFile(manifestPath,manifest);return {...manifest,configs,root};
}
