#!/usr/bin/env node
import {main} from './aqua-lab.js';
main().catch(e=>{console.error('AQUA LAB start failed:',e.code||'CHECK_LAB_PORTS_OR_DATA');process.exitCode=1});
