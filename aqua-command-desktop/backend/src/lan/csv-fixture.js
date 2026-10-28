import {assertOwnedStorage} from './storage-boundary.js';
import fs from 'node:fs';import path from 'node:path';import {Store} from './store.js';import {CSV_HEADER} from './csv-source.js';
/** LAB input producer, never instantiated for a user-supplied WinCC source directory. */
export function createCsvFixture(config){
 if(!config.fixtureRoot||config.fixtureOwned!==true||!Array.isArray(config.tags)||!config.tags.length)throw Error('Explicit owned LAB fixture required');
 assertOwnedStorage(config.fixtureRoot);const root=fs.realpathSync(config.fixtureRoot),output=path.resolve(config.outputDirectory);if(!output.startsWith(path.resolve(config.fixtureRoot)+path.sep))throw Error('Fixture output must stay inside owned LAB root');fs.mkdirSync(output,{recursive:true});if(!fs.realpathSync(output).startsWith(root+path.sep))throw Error('Fixture output alias outside owned LAB root');
 const app={config,store:new Store(config.dataDir),stopped:false};
 app.write=()=>{const now=new Date(),local=now.toISOString().slice(0,19),day=local.slice(0,10).replaceAll('-',''),file=path.join(config.outputDirectory,`runtime_${day}.csv`),n=app.store.get('samples',0),value=Math.floor(n/6)%2;
  if(fs.existsSync(file)&&(!fs.lstatSync(file).isFile()||fs.lstatSync(file).isSymbolicLink()||fs.statSync(file).size>8388608))throw Error('LAB fixture quota reached');
  const fresh=!fs.existsSync(file),fd=fs.openSync(file,fs.constants.O_WRONLY|fs.constants.O_APPEND|fs.constants.O_CREAT|(fs.constants.O_NOFOLLOW||0),0o600);try{fs.writeFileSync(fd,(fresh?CSV_HEADER+'\r\n':'')+config.tags.map((tag,i)=>`${local};${tag};${i===0?value:i%2};128;0\r\n`).join(''));fs.fsyncSync(fd)}finally{fs.closeSync(fd)}app.store.set('samples',n+1);
 };
 app.start=async()=>{app.write();app.timer=setInterval(()=>{try{app.write()}catch{console.error('LAB input fixture could not append; inspect local storage')}},config.intervalMs||5000);return app};
 app.close=async()=>{app.stopped=true;clearInterval(app.timer);app.store.close()};return app;
}
