import fs from 'node:fs';import {execFileSync} from 'node:child_process';
/** Stable process creation identity, never environment/credentials or a PID alone. */
export function processIdentity(pid){
 if(!Number.isSafeInteger(pid)||pid<=0)return null;
 try{
  if(process.platform==='linux'){
   const boot=fs.readFileSync('/proc/sys/kernel/random/boot_id','utf8').trim(),stat=fs.readFileSync(`/proc/${pid}/stat`,'utf8');
   const start=stat.slice(stat.lastIndexOf(')')+2).trim().split(/\s+/)[19];if(!/^[0-9]+$/.test(start))return null;return `linux:${boot}:${start}`;
  }
  if(process.platform==='win32'){
   const ticks=execFileSync('powershell.exe',['-NoProfile','-NonInteractive','-Command',`(Get-Process -Id ${pid} -ErrorAction Stop).StartTime.ToUniversalTime().Ticks`],{encoding:'utf8',timeout:2000,windowsHide:true,stdio:['ignore','pipe','ignore']}).trim();
   return /^[0-9]+$/.test(ticks)?`windows:${ticks}`:null;
  }
 }catch{}
 return null;
}
