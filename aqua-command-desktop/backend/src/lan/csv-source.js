import fs from 'node:fs';import path from 'node:path';import {digest} from './protocol.js';
const canonical=p=>{p=path.resolve(p);const tail=[];while(!fs.existsSync(p)){tail.unshift(path.basename(p));const parent=path.dirname(p);if(parent===p)break;p=parent}return path.join(fs.realpathSync(p),...tail)};
export function assertStorageOutsideInput(input,output){const source=canonical(input),target=canonical(output);if(target===source||target.startsWith(source+path.sep))throw Error('AQUA storage must be outside the read-only input directory')}
export const CSV_HEADER='timestamp_local;tag_name;raw_value;quality_code;read_error';
/** Reads only files already produced by WinCC. No OT client, command or write API. */
export class CsvReadonlySource{
 constructor(config,store,sourceId){
  const c=config.csv||{};
  if(!Array.isArray(c.tags)||!c.tags.length||c.tags.length>100||new Set(c.tags).size!==c.tags.length||c.tags.some(x=>typeof x!=='string'||(!/^[-A-Za-z0-9_.]{1,100}$/.test(x)||Object.hasOwn(Object.prototype,x)))||!/^[-+](0\d|1[0-4]):[0-5]\d$/.test(c.timezoneOffset||''))throw Error('Explicit CSV tags and timezone offset required');
  this.kind='wincc-csv';this.available=true;this.readOnly=true;this.simulated=c.fixture===true;this.store=store;this.sourceId=sourceId;this.config=c;
  this.directory=path.resolve(c.directory||'');const data=canonical(config.dataDir),input=canonical(this.directory);
  if(!c.directory)throw Error('Read-only input folder required');assertStorageOutsideInput(this.directory,config.dataDir);
  if(c.goodQualityCodes!==undefined&&(!Array.isArray(c.goodQualityCodes)||!c.goodQualityCodes.length||c.goodQualityCodes.some(q=>!Number.isSafeInteger(q)||q<0||q>4294967295)))throw Error('Invalid approved quality codes');
  this.good=c.goodQualityCodes||[128];
 }
 capture(){
  const root=fs.realpathSync(this.directory),names=fs.readdirSync(root).filter(n=>/^runtime_\d{8}\.csv$/.test(n)).sort();if(names.length>366)throw Error('Input file limit reached; archive stopped inputs outside this folder');
  let imported=0;
  for(const name of names){
   const file=path.join(root,name),before=fs.lstatSync(file);if(!before.isFile()||before.isSymbolicLink())throw Error('Input must be a regular local CSV file');
   const fd=fs.openSync(file,'r');let bytes;
   try{const stat=fs.fstatSync(fd);if(!stat.isFile()||stat.ino!==before.ino||stat.dev!==before.dev||stat.size>8388608)throw Error('Input replaced or file quota exceeded');bytes=Buffer.alloc(stat.size);let n=0;while(n<bytes.length){const got=fs.readSync(fd,bytes,n,bytes.length-n,n);if(!got)throw Error('Input changed during read');n+=got}}finally{fs.closeSync(fd)}
   const cursor=this.store.get('csv:'+name,{offset:0,hash:digest(Buffer.alloc(0))});if(bytes.length<cursor.offset||digest(bytes.subarray(0,cursor.offset))!==cursor.hash)throw Error('Committed input changed/replaced/truncated; retained queue is safe');
   let offset=cursor.offset;
   if(!offset){const end=bytes.indexOf(10);if(end<0)break;const header=bytes.subarray(0,end).toString('utf8').replace(/^\uFEFF/,'').replace(/\r$/,'');if(header!==CSV_HEADER)throw Error('Not a runtime CSV: Tag configuration exports are not live readings');offset=end+1}
   let frame=null;
   while(offset<bytes.length&&imported<32){
    const end=bytes.indexOf(10,offset);if(end<0)break;
    const line=bytes.subarray(offset,end).toString('utf8').replace(/\r$/,'');const f=line.split(';');
    if(f.length!==5||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(f[0])||!this.config.tags.includes(f[1])||!/^(-?\d+)?$/.test(f[3])||! /^-?\d+$/.test(f[4]))throw Error('Invalid runtime CSV row; cursor retained');
    const at=new Date(f[0]+this.config.timezoneOffset);if(!Number.isFinite(+at)||new Date(f[0]+'Z').toISOString().slice(0,19)!==f[0])throw Error('Invalid source timestamp');
    if(frame&&frame.observed_at!==at.toISOString())throw Error('Incomplete runtime frame before next timestamp; cursor retained');
    frame??={observed_at:at.toISOString(),observations:{},values:{},simulated:this.simulated};
    if(Object.hasOwn(frame.values,f[1]))throw Error('Duplicate tag in runtime frame');
    const raw=f[2]===''?null:Number(f[2]),qualityCode=f[3]===''?null:Number(f[3]),readError=Number(f[4]);
    if((raw!==null&&(!/^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(f[2])||!Number.isFinite(raw)))||(qualityCode!==null&&(!Number.isSafeInteger(qualityCode)||qualityCode<0||qualityCode>4294967295))||!Number.isSafeInteger(readError))throw Error('Invalid runtime numeric data');
    const good=readError===0&&this.good.includes(qualityCode)&&raw!==null,confirmed=this.config.mappingConfirmed===true;
    const state=good&&confirmed&&(raw===0||raw===1)?raw===1:null;
    frame.values[f[1]]=state;frame.observations[f[1]]={raw_value:raw,quality_code:qualityCode,read_error:readError,quality:!good?'BAD':!confirmed?'UNVERIFIED_MAPPING':state===null?'UNSUPPORTED_VALUE':'GOOD'};
    offset=end+1;
    if(Object.keys(frame.values).length===this.config.tags.length){const previous=this.store.get('runtimeObservedAt');if(previous&&frame.observed_at<previous)throw Error('Source timestamp moved backwards; cursor retained');this.store.appendRuntime(this.sourceId,frame,{key:'csv:'+name,value:{offset,hash:digest(bytes.subarray(0,offset))}});imported++;frame=null}
   }
   if(frame||offset<bytes.length)break; // never skip a partial batch to process newer files
   if(imported>=32)break;
  }
  return imported;
 }
}
