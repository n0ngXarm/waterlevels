import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

const PUMP_IDS = ['PUMP-01', 'PUMP-02', 'PUMP-03', 'PUMP-04', 'PUMP-05', 'PUMP-06', 'PUMP-07', 'PUMP-08'];
const DEFAULT_PUMPS = Object.fromEntries(PUMP_IDS.map((id,i) => [id, i === 0 || i === 1 || i === 3 || i === 5 || i === 6]));
const SYSTEM_AGENTS = [
  { id: 'PC-01', label: 'SCADA / Pump Station A', ip: '10.20.0.11' },
  { id: 'PC-02', label: 'SCADA / Pump Station B', ip: '10.20.0.12' },
  { id: 'PC-03', label: 'SCADA / Valve Station', ip: '10.20.0.13' }
];
export class DemoSimulator {
  constructor({ dataDir = path.resolve('./data'), now = () => Date.now(), telegramSink = null } = {}) {
    this.dataDir = dataDir;
    this.now = now;
    this.telegramSink = telegramSink;
    fs.mkdirSync(this.dataDir, { recursive: true });
    this.dbPath = path.join(dataDir, 'simulation-state.json');
    this.state = this.load();
    this.log('AQUA DEMO initialized. No physical PLC/WinCC connections.', 'SYSTEM');
  }
  load() {
    const defaultState = {
      pumps: { ...DEFAULT_PUMPS }, gatewayConnected: false, internetOnline: true,
      tick: 0, snapshots: 0, delivered: 0, queue: [], deliveries: [], events: [],
      lastExport: null, lastDelivery: null, notifiedIds: [], flow: 20.3,
    };
    try {
      const stored = JSON.parse(fs.readFileSync(this.dbPath, 'utf8'));
      return { ...defaultState, ...stored, pumps: { ...DEFAULT_PUMPS, ...stored.pumps }, queue: stored.queue || [] };
    } catch { return defaultState; }
  }
  persist() {
    const temp = `${this.dbPath}.${process.pid}.tmp`;
    fs.writeFileSync(temp, JSON.stringify(this.state, null, 2));
    fs.renameSync(temp, this.dbPath);
  }
  log(message, kind = 'INFO') {
    const event = { time: new Date(this.now()).toISOString(), kind, message, id: randomUUID() };
    this.state.events.unshift(event);
    this.state.events = this.state.events.slice(0, 100);
    this.persist();
    return event;
  }
  exportTick() {
    const at = new Date(this.now()).toISOString();
    this.state.tick++;
    SYSTEM_AGENTS.forEach((agent,i) => {
      const tags = i === 0 ? ['PUMP-01','PUMP-02','PUMP-03'] : i === 1 ? ['PUMP-04','PUMP-05','PUMP-06'] : ['PUMP-07','PUMP-08'];
      const snapshot = {
        id: randomUUID(), schema: 'aqua.runtime-snapshot.v1', simulated: true,
        seq: this.state.tick, agent: agent.id, at,
        values: Object.fromEntries(tags.map(id=>[id,this.state.pumps[id] ? 1 : 0])),
      };
      fs.appendFileSync(path.join(this.dataDir, `${agent.id.toLowerCase()}.jsonl`), JSON.stringify(snapshot)+'\n');
      this.state.queue.push(snapshot);
      this.state.snapshots++;
    });
    this.state.lastExport = at;
    if(this.state.tick % 2 === 1) this.log('Runtime snapshot exported • 3 SCADA agents', 'EXPORT');
    this.flush();
    this.persist();
    return this.state;
  }
  setPump(id, status) {
    if(!PUMP_IDS.includes(id)) throw new Error('Unknown simulated pump');
    const before=this.state.pumps[id];
    if(before===!!status) return false;
    this.state.pumps[id] = !!status;
    const ev = this.log(`${id} ${before?'ON':'OFF'} → ${status?'ON':'OFF'}`, 'PUMP');
    this.state.deliveries.unshift({ id: ev.id, time: ev.time, message: ev.message, delivered: false });
    this.flush(); this.persist();
    return true;
  }
  setGateway(connected) {
    const changed=this.state.gatewayConnected!==!!connected;
    this.state.gatewayConnected=!!connected;
    if (changed) this.log(`PC-04 gateway ${connected?'connected to approved LAB LAN':'disconnected from LAB LAN'}`,connected?'NETWORK':'WARNING');
    this.flush();this.persist();
  }
  setInternet(online) {
    const changed=this.state.internetOnline!==!!online;
    this.state.internetOnline=!!online;
    if(changed)this.log(`PC-04 internet egress ${online?'available':'unavailable'}`,online?'NETWORK':'WARNING');
    this.flush();this.persist();
  }
  flush() {
    if(!this.state.gatewayConnected)return;
    // Simulated authenticated LAN transfer: local snapshots move to PC4 queue only on join.
    // No IP probing or real network scan is performed by this demo.
    if(this.state.queue.length){
      this.state.gatewayQueue = [...(this.state.gatewayQueue||[]), ...this.state.queue];
      this.state.queue=[];
    }
    if(!this.state.internetOnline){this.persist();return;}
    const pending=this.state.gatewayQueue||[];
    if(pending.length){
      this.state.delivered += pending.length;
      this.state.lastDelivery = new Date(this.now()).toISOString();
      this.state.gatewayQueue=[];
      this.log(`Gateway ACK received • ${pending.length} snapshots delivered to local Central mock`, 'DELIVERY');
      fs.appendFileSync(path.join(this.dataDir, 'central-delivered.jsonl'), pending.map(p=>JSON.stringify(p)).join('\n')+'\n');
    }
    for(const evt of this.state.deliveries) {
      if(!evt.delivered){
        evt.delivered=true;
        evt.deliveryType='DRY-RUN TELEGRAM';
        fs.appendFileSync(path.join(this.dataDir, 'telegram-dryrun.jsonl'), JSON.stringify(evt)+'\n');
        if(this.telegramSink) try {this.telegramSink(evt);} catch {}
      }
    }
    this.persist();
  }
  reset(){
    this.state={pumps:{...DEFAULT_PUMPS},gatewayConnected:false,internetOnline:true,tick:0,snapshots:0,delivered:0,queue:[],gatewayQueue:[],deliveries:[],events:[],lastExport:null,lastDelivery:null,notifiedIds:[],flow:20.3};
    this.log('Simulation reset to default scenario', 'SYSTEM');
  }
  publicState(){
    return {
      ...this.state,
      agents: SYSTEM_AGENTS,
      queueCount:this.state.queue.length+(this.state.gatewayQueue||[]).length,
      scadaQueueCount:this.state.queue.length,
      gatewayQueueCount:(this.state.gatewayQueue||[]).length,
      gatewayStatus:this.state.gatewayConnected?'CONNECTED':'DISCONNECTED',
      internetStatus:this.state.internetOnline?'AVAILABLE':'UNAVAILABLE',
      simulation:true,
      time:new Date(this.now()).toISOString(),
      exportIntervalSeconds:5,
    };
  }
}
