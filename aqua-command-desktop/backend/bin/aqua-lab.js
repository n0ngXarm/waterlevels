#!/usr/bin/env node
import path from 'node:path';import fs from 'node:fs';import {fileURLToPath} from 'node:url';import {startSingle} from '../src/lan/supervisor.js';import {enrollment} from '../src/lan/config.js';import {runRole} from './aqua-service.js';
export async function main(args=process.argv.slice(2)){
 const value=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
 const command=args[0]&&!args[0].startsWith('--')?args[0]:'readonly';
 if(args.includes('--help')){console.log('AQUA COMMAND read-only\n readonly [--source-dir DIR] [--data-dir DIR] [--port 4173]\n single [--data-dir DIR] [--port 4173] [--read-only] [--internet simulated|real]\n init [--data-dir DIR] [--port 4173]\n lan --role agent|gateway|central|dashboard --config ROLE.json [--allow-lan]\nLAN uses the exact enrolled config; no scans or host networking changes. Default single is loopback, simulated runtime and Telegram dry-run.');return}
 if(command==='lan')return runRole(args,{lanMode:true});
 if(!['single','init','readonly'].includes(command))throw Object.assign(Error('Unknown LAB command'),{code:'LAB_COMMAND_INVALID'});
 const dataRoot=path.resolve(value('--data-dir')||process.env.AQUA_DATA_DIR||(command==='readonly'?'./aqua-data':'./lab-data-v04'));
 const port=value('--port')||process.env.PORT;const options={port:port===undefined?undefined:Number(port),readOnly:true,internetMode:value('--internet')||undefined};
 if(command==='readonly'||value('--source-dir')){options.profile='readonly';if(value('--source-dir')){options.sourceDirectory=path.resolve(value('--source-dir'));if(!fs.statSync(options.sourceDirectory).isDirectory()||dataRoot===options.sourceDirectory||dataRoot.startsWith(options.sourceDirectory+path.sep))throw Error('Read-only input must be an existing folder outside AQUA data')}}
 if(options.internetMode&&!['simulated','real'].includes(options.internetMode))throw Error('Invalid Internet mode');
 if(command==='init'){const e=enrollment(dataRoot,options);console.log('Private enrolled role files (never publish contents):');for(const [id,file] of Object.entries(e.files))console.log(`${id}: ${file}`);return e}
 const lab=await startSingle(dataRoot,options);console.log(`AQUA COMMAND read-only: http://127.0.0.1:${lab.enrollment.basePort} | source: ${options.sourceDirectory?'READ-ONLY CSV (WinCC not verified)':'SIMULATED LAB CSV'} / real TCP on ONE HOST`);
 let stopping=false;const stop=async()=>{if(stopping)return;stopping=true;await lab.stop();process.exit(0)};process.once('SIGINT',stop);process.once('SIGTERM',stop);return lab;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().catch(e=>{console.error('AQUA LAB start failed:',e.code||'CHECK_LAB_PORTS_OR_DATA');process.exitCode=1});
