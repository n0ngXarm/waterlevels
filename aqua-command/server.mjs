import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { RULES, severityOf, evaluateTelemetry, alertMessage } from './rules.mjs';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
for (const line of (fs.existsSync(path.join(ROOT,'.env')) ? fs.readFileSync(path.join(ROOT,'.env'),'utf8') : '').split(/\r?\n/)) {
  const m = line.match(/^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$/);
  if (m && !Object.hasOwn(process.env,m[1])) process.env[m[1]] = m[2].replace(/^(['"])(.*)\1$/,'$2');
}
const HOST = process.env.HOST || '127.0.0.1';
const PORT = Number(process.env.PORT) || 8787;
const DEMO = process.env.DEMO_MODE !== 'false';
const SEND_DEMO = process.env.SEND_DEMO_ALERTS === 'true';
const BOT = process.env.TELEGRAM_BOT_TOKEN || '';
const CHAT = process.env.TELEGRAM_CHAT_ID || '';
const TELEGRAM_BASE = (process.env.TELEGRAM_API_BASE || 'https://api.telegram.org').replace(/\/+$/, '');
const SECRET = process.env.ADMIN_API_KEY || '';
const VIEWER_KEY = process.env.VIEWER_API_KEY || '';
const GATEWAY_KEY = process.env.GATEWAY_INGEST_KEY || '';
const REQUIRE_AUTH_FOR_READ = process.env.REQUIRE_AUTH_FOR_READ === 'true';
const REMINDER_MS = Math.max(5, Number(process.env.REMINDER_MINUTES)||30)*60_000;
const SEND_GAP = Math.max(1000, Number(process.env.TELEGRAM_MIN_GAP_MS)||1400);
const STALE_AFTER_MS = Math.max(30,Number(process.env.STALE_AFTER_SECONDS)||120)*1000;
const DATA_PATH = path.join(ROOT,'storage','state.json');
const PUBLIC = path.join(ROOT,'public');
fs.mkdirSync(path.dirname(DATA_PATH), {recursive:true});
const now = () => new Date().toISOString();
const num = (n,d=1) => Math.round(n*10**d)/10**d;
const safeId = v => typeof v === 'string' && /^[\w-]{2,64}$/.test(v);

let stations = [
  {id:'CM-01',name:'สถานีผลิตน้ำป่าตัน',district:'เมืองเชียงใหม่',region:'อำเภอเมืองเชียงใหม่',zone:'โซนเมือง',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',pwaBranchCode:'1004',scopeStatus:'AUTHORIZED_PILOT',lat:18.824,lon:98.995,px:371.0,py:248.8,x:60.5,y:45.7,pressureBar:2.84,tankLevelPct:78,flowM3h:2860,turbidityNtu:0.48,chlorineMgL:0.54,online:true},
  {id:'CM-02',name:'สถานีผลิตน้ำอุโมงค์',district:'เมืองเชียงใหม่',region:'อำเภอเมืองเชียงใหม่',zone:'โซนเมือง',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',pwaBranchCode:'1004',scopeStatus:'AUTHORIZED_PILOT',lat:18.790,lon:98.955,px:355.6,py:254.7,x:57.9,y:46.9,pressureBar:2.65,tankLevelPct:82,flowM3h:1950,turbidityNtu:0.38,chlorineMgL:0.51,online:true},
  {id:'CM-03',name:'สถานีผลิตน้ำแม่กวง',district:'สันทราย',region:'อำเภอสันทราย',zone:'โซนตะวันออก',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',pwaBranchCode:'1004',scopeStatus:'AUTHORIZED_PILOT',lat:18.855,lon:99.045,px:390.2,py:243.5,x:63.8,y:44.7,pressureBar:2.72,tankLevelPct:74,flowM3h:1820,turbidityNtu:0.42,chlorineMgL:0.48,online:true},
  {id:'CM-04',name:'สถานีผลิตน้ำแม่แฝก',district:'สันทราย',region:'อำเภอสันทราย',zone:'โซนเหนือ',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',pwaBranchCode:'1004',scopeStatus:'AUTHORIZED_PILOT',lat:19.005,lon:99.020,px:380.6,py:217.7,x:62.2,y:39.5,pressureBar:2.45,tankLevelPct:69,flowM3h:940,turbidityNtu:0.35,chlorineMgL:0.49,online:true},
  {id:'CM-05',name:'สถานีจ่ายน้ำแม่ริม',district:'แม่ริม',region:'อำเภอแม่ริม',zone:'โซนเหนือ',pwaBranch:'กปภ.สาขาแม่ริม',pwaBranchCode:'1005',scopeStatus:'OUT_OF_PILOT_SCOPE',lat:18.915,lon:98.945,px:351.8,py:233.2,x:57.2,y:42.6,pressureBar:2.58,tankLevelPct:71,flowM3h:1420,turbidityNtu:0.44,chlorineMgL:0.46,online:true},
  {id:'CM-06',name:'สถานีผลิตน้ำสันกำแพง',district:'สันกำแพง',region:'อำเภอสันกำแพง',zone:'โซนตะวันออก',pwaBranch:'กปภ.สาขาสันกำแพง',pwaBranchCode:'1006',scopeStatus:'OUT_OF_PILOT_SCOPE',lat:18.745,lon:99.120,px:419.1,py:262.4,x:68.8,y:48.5,pressureBar:2.35,tankLevelPct:65,flowM3h:1150,turbidityNtu:0.51,chlorineMgL:0.44,online:true},
  {id:'CM-07',name:'สถานีจ่ายน้ำหางดง',district:'หางดง',region:'อำเภอหางดง',zone:'โซนใต้',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',pwaBranchCode:'1004',scopeStatus:'AUTHORIZED_PILOT',lat:18.685,lon:98.915,px:340.2,py:272.8,x:55.2,y:50.5,pressureBar:2.48,tankLevelPct:68,flowM3h:1280,turbidityNtu:0.39,chlorineMgL:0.52,online:true},
  {id:'CM-08',name:'สถานีจ่ายน้ำสารภี',district:'สารภี',region:'อำเภอสารภี',zone:'โซนใต้',pwaBranch:'กปภ.สาขาเชียงใหม่ (พ)',pwaBranchCode:'1004',scopeStatus:'AUTHORIZED_PILOT',lat:18.710,lon:99.035,px:386.4,py:268.5,x:63.2,y:49.7,pressureBar:2.61,tankLevelPct:77,flowM3h:1360,turbidityNtu:0.41,chlorineMgL:0.50,online:true},
  {id:'CM-09',name:'สถานีผลิตน้ำแม่แตง',district:'แม่แตง',region:'อำเภอแม่แตง',zone:'โซนเหนือ',pwaBranch:'กปภ.สาขาแม่แตง',pwaBranchCode:'1007',scopeStatus:'OUT_OF_PILOT_SCOPE',lat:19.125,lon:98.940,px:349.8,py:197.0,x:56.9,y:35.4,pressureBar:2.38,tankLevelPct:64,flowM3h:880,turbidityNtu:0.45,chlorineMgL:0.47,online:true},
  {id:'CM-10',name:'สถานีผลิตน้ำจอมทอง',district:'จอมทอง',region:'อำเภอจอมทอง',zone:'โซนใต้',pwaBranch:'กปภ.สาขาจอมทอง',pwaBranchCode:'1008',scopeStatus:'OUT_OF_PILOT_SCOPE',lat:18.420,lon:98.680,px:249.8,py:318.4,x:39.6,y:59.7,pressureBar:2.52,tankLevelPct:73,flowM3h:1020,turbidityNtu:0.40,chlorineMgL:0.45,online:true},
  {id:'CM-11',name:'สถานีผลิตน้ำฝาง',district:'ฝาง',region:'อำเภอฝาง',zone:'โซนเหนือสุด',pwaBranch:'กปภ.สาขาฝาง',pwaBranchCode:'1009',scopeStatus:'OUT_OF_PILOT_SCOPE',lat:19.915,lon:99.210,px:453.7,py:61.0,x:74.8,y:8.2,pressureBar:2.42,tankLevelPct:66,flowM3h:950,turbidityNtu:0.43,chlorineMgL:0.43,online:true},
  {id:'CM-12',name:'สถานีผลิตน้ำฮอด',district:'ฮอด',region:'อำเภอฮอด',zone:'โซนใต้สุด',pwaBranch:'กปภ.สาขาฮอด',pwaBranchCode:'1030',scopeStatus:'OUT_OF_PILOT_SCOPE',lat:18.190,lon:98.610,px:222.8,py:358.0,x:35.0,y:67.6,pressureBar:2.30,tankLevelPct:61,flowM3h:760,turbidityNtu:0.46,chlorineMgL:0.42,online:true}
];

let reservoirs = [
  {id:'RES-01',name:'เขื่อนแม่งัดสมบูรณ์ชล',nameEn:'Mae Ngat Somboon Chon Dam',district:'แม่แตง',capacityMcm:265.0,storageMcm:212.5,storagePct:80.2,inflowM3s:14.2,outflowM3s:8.5,status:'normal',statusText:'ปกติ (80.2%)',dataClassification:'PUBLIC_EXTERNAL'},
  {id:'RES-02',name:'เขื่อนแม่กวงอุดมธารา',nameEn:'Mae Kuang Udom Thara Dam',district:'ดอยสะเก็ด',capacityMcm:263.0,storageMcm:189.4,storagePct:72.0,inflowM3s:11.8,outflowM3s:6.2,status:'normal',statusText:'ปกติ (72.0%)',dataClassification:'PUBLIC_EXTERNAL'},
  {id:'RES-03',name:'จุดสูบน้ำดิบแม่น้ำปิง (ป่าตัน)',nameEn:'Ping River Raw Water Intake',district:'เมืองเชียงใหม่',capacityMcm:null,waterLevelM:3.45,thresholdM:3.70,storagePct:93.2,status:'normal',statusText:'ระดับน้ำปกติ (3.45 ม.รทก.)',dataClassification:'PUBLIC_EXTERNAL'}
];

// Load Station Registry from config if available (Priority 1 Data Integrity)
const REGISTRY_PATH = path.resolve(ROOT, '..', 'config', 'station_registry.json');
if (fs.existsSync(REGISTRY_PATH)) {
  try {
    const reg = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
    if (Array.isArray(reg.stations) && reg.stations.length > 0) {
      stations = reg.stations.map(st => {
        const existing = stations.find(x => x.id === st.id) || {};
        return {
          ...existing,
          id: st.id,
          name: st.name,
          district: st.district,
          region: 'อำเภอ' + st.district,
          pwaBranch: st.pwa_branch_name,
          pwaBranchCode: st.pwa_branch_code,
          scopeStatus: st.scope_status,
          rtuPlantId: st.rtu_plant_id,
          lat: st.lat,
          lon: st.lon,
          px: st.px,
          py: st.py,
          x: st.x,
          y: st.y
        };
      });
    }
  } catch (err) {
    console.error('Warning: could not parse station_registry.json:', err.message);
  }
}
for (const s of stations) {
  s.hasTelemetry=DEMO;
  s.lastSeen=DEMO?now():null;
  if (!DEMO) for(const field of ['pressureBar','tankLevelPct','flowM3h','turbidityNtu','chlorineMgL']) s[field]=null;
  if (!DEMO) s.online=false;
}
const history = Array.from({length:96},(_,i)=>({
  time: new Date(Date.now()-(95-i)*15*60_000).toISOString(),
  pressure: num(2.62+Math.sin(i*.24)*.24+Math.sin(i*.07)*.12+Math.random()*.08,2),
  flow: Math.round(22.5+Math.sin(i*.16)*2.6+Math.cos(i*.39)*1.2+Math.random()*.7),
  tank: num(72+Math.sin(i*.11)*6+Math.random()*1.8,1)
}));
if (!DEMO) history.length=0;
let store = {alerts:[], queue:[], active:{}, updatedAt:now()};
try { const previous=JSON.parse(fs.readFileSync(DATA_PATH,'utf8')); store={...store, alerts:previous.alerts||[],queue:previous.queue||[],active:previous.active||{}}; }
catch (e) {if (e.code!=='ENOENT') console.error('Could not read state:',e.message);}
let saveTimer;
function saveSoon() {clearTimeout(saveTimer); saveTimer=setTimeout(saveNow,400);}
function saveNow() {try {let temp=DATA_PATH+'.tmp';fs.writeFileSync(temp,JSON.stringify(store));fs.renameSync(temp,DATA_PATH);}catch(e){console.error('State persistence error:',e.message);}}
function statusOf(s) {if (!s.hasTelemetry) return 'unknown';const a=evaluateTelemetry(s);return a.some(x=>x.severity==='critical')?'critical':a.some(x=>x.severity==='warning')?'warning':'normal';}
function snapshot() {
  const details=stations.map(s=>({
    ...s,
    status:statusOf(s),
    dataClassification: s.hasTelemetry ? (s.dataClassification || (DEMO ? 'DEMO' : 'AUTHORIZED_FIELD_TELEMETRY')) : (DEMO ? 'DEMO' : 'NO_DATA'),
    scopeStatus: s.scopeStatus || (s.pwaBranchCode === '1004' ? 'AUTHORIZED_PILOT' : 'OUT_OF_PILOT_SCOPE')
  }));
  const valid=details.filter(s=>s.hasTelemetry);
  const mean=field=>{const values=valid.map(s=>s[field]).filter(v=>typeof v==='number');return values.length?values.reduce((a,b)=>a+b,0)/values.length:0;};
  const alertCounts={critical:store.alerts.filter(a=>a.severity==='critical'&&!a.resolvedAt&&!a.supersededAt).length,warning:store.alerts.filter(a=>a.severity==='warning'&&!a.resolvedAt&&!a.supersededAt).length};
  const activeStationAlerts=details.filter(s=>s.status!=='normal').length;
  const resAvg=Math.round(reservoirs.reduce((a,r)=>a+(r.storagePct||0),0)/reservoirs.length*10)/10;
  return {
    province:'เชียงใหม่',
    serverTime:now(),
    mode:DEMO?'demo':'live-ingest',
    stations:details,
    reservoirs,
    history,
    alerts:store.alerts.slice(0,100),
    queueStats:{
      pending:store.queue.filter(x=>x.status==='pending').length,
      failed:store.queue.filter(x=>x.status==='failed').length,
      sent:store.queue.filter(x=>x.status==='sent').length
    },
    queueRecent:store.queue.slice(-8).reverse().map(j=>({id:j.id,alertId:j.alertId,status:j.status,attempt:j.attempt,createdAt:j.createdAt,sentAt:j.sentAt||null,lastError:j.lastError||null})),
    metrics:{
      total:details.length,
      online:details.filter(x=>x.online).length,
      normal:details.filter(x=>x.status==='normal').length,
      warning:details.filter(x=>x.status==='warning').length,
      critical:details.filter(x=>x.status==='critical').length,
      activeStations:activeStationAlerts,
      pressure:num(mean('pressureBar'),2),
      tank:num(mean('tankLevelPct'),1),
      flow:Math.round(valid.reduce((a,s)=>a+(s.flowM3h||0),0)),
      turbidity:num(mean('turbidityNtu'),2),
      chlorine:num(mean('chlorineMgL'),2),
      reservoirAvgPct:resAvg,
      activeAlertCount:alertCounts.critical+alertCounts.warning
    },
    telegram:{configured:Boolean(BOT&&CHAT),demoForwarding:SEND_DEMO,reminderMinutes:REMINDER_MS/60},
    rules:RULES.map(({id,title,warning,critical,unit,direction})=>({id,title,warning,critical,unit,direction}))
  };
}
const clients = new Set();
function broadcast() {const message=`data: ${JSON.stringify(snapshot())}\n\n`;for(const c of clients) try{c.write(message);}catch{clients.delete(c);}}
const uid=()=>crypto.randomUUID().slice(0,8).toUpperCase();
function createAlert(station,rule,severity,value,{resolved=false,demo=DEMO}={}) {
  const message=resolved?`${rule.title} กลับสู่เกณฑ์ที่กำหนด (${value}${rule.unit})` :
    `${rule.title}: ${value}${rule.unit} / เกณฑ์เตือน ${rule.warning}${rule.unit}, วิกฤต ${rule.critical}${rule.unit}`;
  const alert={id:`AL-${uid()}`,stationId:station.id,stationName:station.name,region:station.region,title:resolved?`${rule.title} — กลับสู่ปกติ`:rule.title,severity:resolved?'resolved':severity,message,value,ruleId:rule.id,createdAt:now(),resolvedAt:resolved?now():null,acknowledgedAt:null,demo};
  store.alerts.unshift(alert);store.alerts=store.alerts.slice(0,400);
  if(BOT&&CHAT&&(!demo||SEND_DEMO)) store.queue.push({id:uid(),alertId:alert.id,status:'pending',attempt:0,nextAt:Date.now(),createdAt:now(),lastError:null});
  saveSoon();broadcast();return alert;
}
function processRules(station,{demo=DEMO,initial=false}={}) {
  for(const rule of RULES) {
    const current=severityOf(rule,station[rule.field]);const key=station.id+':'+rule.id;
    const prev=store.active[key]||null;
    if(current===prev?.severity) {
      if(current && !initial && Date.now()-(prev.lastNotice||0)>REMINDER_MS) {for(const a of store.alerts)if(a.stationId===station.id&&a.ruleId===rule.id&&!a.resolvedAt&&!a.supersededAt)a.supersededAt=now();createAlert(station,rule,current,station[rule.field],{demo});store.active[key]={severity:current,lastNotice:Date.now()};}
      continue;
    }
    if (current) {
      if(prev)for(const a of store.alerts)if(a.stationId===station.id&&a.ruleId===rule.id&&!a.resolvedAt&&!a.supersededAt)a.supersededAt=now();
      if(!initial)createAlert(station,rule,current,station[rule.field],{demo});
      store.active[key]={severity:current,lastNotice:Date.now()};
    } else {
      if(prev && !initial)createAlert(station,rule,'resolved',station[rule.field],{resolved:true,demo});
      delete store.active[key];
    }
    if(prev && current===null) {
      for(const a of store.alerts) if(a.stationId===station.id && a.ruleId===rule.id && !a.resolvedAt && a.severity!=='resolved') a.resolvedAt=now();
    }
  }
  saveSoon();
}
function seedAlerts(){
  if (!DEMO || store.alerts.length) return;
  for(const s of stations)for(const {rule,severity,value} of evaluateTelemetry(s)){
    createAlert(s,rule,severity,value,{demo:true});store.active[s.id+':'+rule.id]={severity,lastNotice:Date.now()};
  }
  saveNow();
}
seedAlerts();
let lastTelegramSend=0,sending=false;
async function processQueue() {
  if(sending||!BOT||!CHAT)return;
  const job=store.queue.find(x=>x.status==='pending' && x.nextAt<=Date.now());if(!job)return;
  const gap=Date.now()-lastTelegramSend;if(gap<SEND_GAP)return;
  const alert=store.alerts.find(x=>x.id===job.alertId);if(!alert){job.status='failed';job.lastError='Missing alert';saveSoon();return;}
  sending=true;lastTelegramSend=Date.now();job.attempt++;
  try {
    const response=await fetch(`${TELEGRAM_BASE}/bot${BOT}/sendMessage`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({chat_id:CHAT,text:alertMessage(alert),disable_web_page_preview:true}),signal:AbortSignal.timeout(8000)});
    const answer=await response.json();
    if(!response.ok||!answer.ok) throw new Error(`Telegram HTTP ${response.status}: ${answer.description||'Unknown'}`);
    job.status='sent';job.sentAt=now();job.messageId=answer.result?.message_id;
  }catch(err){job.lastError=String(err.message).slice(0,180);if(job.attempt>=6){job.status='failed';}else{job.nextAt=Date.now()+Math.min(300_000,3000*2**(job.attempt-1));}}
  finally{sending=false;store.queue=store.queue.slice(-500);saveSoon();broadcast();}
}
setInterval(processQueue,950).unref();
// A silent station cannot send online=false itself. Detect stale telemetry centrally.
if(!DEMO) setInterval(()=>{for(const s of stations)if(s.hasTelemetry && s.online && Date.now()-new Date(s.lastSeen).getTime()>STALE_AFTER_MS){s.online=false;processRules(s,{demo:false});broadcast();}},10_000).unref();
if(DEMO) setInterval(()=>{
  const i=Math.floor(Math.random()*stations.length),s=stations[i];
  s.pressureBar=num(Math.max(0,Math.min(6,s.pressureBar+(Math.random()-.5)*.065)),2);
  s.tankLevelPct=num(Math.max(0,Math.min(100,s.tankLevelPct+(Math.random()-.5)*.45)),1);
  s.flowM3h=Math.round(Math.max(0,s.flowM3h+(Math.random()-.5)*35));
  processRules(s,{demo:true});
  history.push({time:now(),pressure:num(stations.reduce((a,b)=>a+b.pressureBar,0)/stations.length,2),flow:num(stations.reduce((a,b)=>a+b.flowM3h,0)/1000,2),tank:num(stations.reduce((a,b)=>a+b.tankLevelPct,0)/stations.length,1)});history.shift();broadcast();
},7500).unref();
const contentTypes={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.json':'application/json; charset=utf-8','.ico':'image/x-icon'};
function reply(res,code,payload){res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(payload));}
function extractToken(req, url) {
  const h = req.headers['x-api-key'] || req.headers['authorization'];
  if (h) {
    if (h.startsWith('Bearer ')) return h.slice(7).trim();
    return h.trim();
  }
  if (url && url.searchParams && url.searchParams.has('token')) {
    return url.searchParams.get('token');
  }
  return null;
}
function checkKey(req){
  if(!SECRET||SECRET.length<24)return false;
  const token = extractToken(req);
  return typeof token==='string' && token.length===SECRET.length && crypto.timingSafeEqual(Buffer.from(token),Buffer.from(SECRET));
}
function checkGatewayKey(req){
  const token = req.headers['x-gateway-token'] || extractToken(req);
  if(!token) return false;
  const validKeys = [GATEWAY_KEY, SECRET].filter(k => k && k.length >= 24);
  for(const k of validKeys){
    if(token.length === k.length && crypto.timingSafeEqual(Buffer.from(token), Buffer.from(k))){
      return true;
    }
  }
  return false;
}
function checkReadKey(req, url){
  if(!REQUIRE_AUTH_FOR_READ) return true;
  if(DEMO && isLoopback(req)) return true;
  const token = extractToken(req, url);
  if(!token) return false;
  const validKeys = [SECRET, VIEWER_KEY, GATEWAY_KEY].filter(k => k && k.length >= 24);
  for(const k of validKeys){
    if(token.length === k.length && crypto.timingSafeEqual(Buffer.from(token), Buffer.from(k))){
      return true;
    }
  }
  return false;
}
function isLoopback(req){const remote=req.socket.remoteAddress||'';return remote==='127.0.0.1'||remote==='::1'||remote==='::ffff:127.0.0.1';}
async function body(req){let length=0,chunks=[];for await(const c of req){length+=c.length;if(length>16_384)throw Object.assign(new Error('Body too large'),{status:413});chunks.push(c);}let parsed=JSON.parse(Buffer.concat(chunks).toString('utf8'));if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw Error('Expected JSON object');return parsed;}
async function handler(req,res){
  const url=new URL(req.url,`http://${req.headers.host||'localhost'}`);const p=url.pathname;
  if(req.method==='GET'&&p==='/api/health')return reply(res,200,{ok:true,mode:DEMO?'demo':'live-ingest',telegramConfigured:Boolean(BOT&&CHAT),authEnforced:REQUIRE_AUTH_FOR_READ,uptimeSeconds:Math.round(process.uptime())});
  if(req.method==='GET'&&p==='/api/state'){
    if(!checkReadKey(req,url)) return reply(res,401,{error:'Authentication required to access state'});
    return reply(res,200,snapshot());
  }
  if(req.method==='GET'&&p==='/api/stream'){
    if(!checkReadKey(req,url)) return reply(res,401,{error:'Authentication required to access stream'});
    res.writeHead(200,{'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-cache, no-transform','Connection':'keep-alive','X-Accel-Buffering':'no','X-Content-Type-Options':'nosniff'});
    clients.add(res);res.write(`retry: 3000\ndata: ${JSON.stringify(snapshot())}\n\n`);const interval=setInterval(()=>res.write(': ping\n\n'),20000);req.on('close',()=>{clearInterval(interval);clients.delete(res);});return;
  }
  if(req.method==='GET'&&p==='/api/export/alerts'){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    const cols=['id','createdAt','stationId','stationName','region','title','severity','message','resolvedAt','acknowledgedAt','demo'];
    const csv=[cols.join(','),...store.alerts.map(a=>cols.map(k=>'"'+String(a[k]??'').replaceAll('"','""')+'"').join(','))].join('\r\n');
    res.writeHead(200,{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':'attachment; filename="aqua-alerts.csv"','Cache-Control':'no-store'});return res.end('\ufeff'+csv);
  }
  if(req.method==='POST'&&p==='/api/v1/ingest/telemetry'){
    if(!checkGatewayKey(req)) return reply(res,401,{error:'Invalid or missing Gateway token'});
    let b=await body(req);
    if(!b.stationId||!safeId(b.stationId)) return reply(res,422,{error:'Valid stationId is required'});
    if(!b.collectorId||typeof b.collectorId!=='string') return reply(res,422,{error:'Valid collectorId is required'});
    if(!b.sourceTimestamp||isNaN(Date.parse(b.sourceTimestamp))) return reply(res,422,{error:'Valid ISO-8601 sourceTimestamp required'});
    if(!b.points||typeof b.points!=='object'||Array.isArray(b.points)) return reply(res,422,{error:'Points dictionary is required'});

    const s=stations.find(x=>x.id===b.stationId);
    if(!s) return reply(res,404,{error:`Unknown station ID: ${b.stationId}`});

    const fieldKeywords={
      PT:'pressureBar',pressure:'pressureBar',
      LT:'tankLevelPct',tank:'tankLevelPct',
      FT:'flowM3h',flow:'flowM3h',
      AT_01:'turbidityNtu',turbidity:'turbidityNtu',
      AT_02:'chlorineMgL',chlorine:'chlorineMgL'
    };
    const bounds={
      pressureBar:[0,15],tankLevelPct:[0,100],flowM3h:[0,100000],
      turbidityNtu:[0,1000],chlorineMgL:[0,20]
    };

    let updatedAny=false,overallQuality='GOOD';
    for(const [pointId,pt] of Object.entries(b.points)){
      if(!pt||typeof pt!=='object') continue;
      const val=pt.value;
      const qual=pt.quality||'GOOD';
      if(qual!=='GOOD') overallQuality=qual;
      if(typeof val!=='number'||!Number.isFinite(val)){
        return reply(res,422,{error:`Invalid numeric value for point ${pointId}`});
      }
      let targetField=null;
      for(const [kw,fld] of Object.entries(fieldKeywords)){
        if(pointId.includes(kw)){targetField=fld;break;}
      }
      if(!targetField) continue;
      const [lo,hi]=bounds[targetField];
      if(val<lo||val>hi){
        return reply(res,422,{error:`Point ${pointId} value ${val} out of engineering bounds [${lo}, ${hi}]`});
      }
      s[targetField]=val;
      updatedAny=true;
    }
    if(!updatedAny) return reply(res,422,{error:'No recognizable telemetry points provided'});

    const incomingTime=new Date(b.sourceTimestamp).getTime();
    const lastSeenTime=s.lastSeen ? new Date(s.lastSeen).getTime() : 0;
    const isHistoricalReplay=incomingTime < (lastSeenTime - 15000);

    s.dataClassification='AUTHORIZED_FIELD_TELEMETRY';
    s.collectorId=b.collectorId;
    s.sequenceNumber=b.sequenceNumber||s.sequenceNumber||0;
    s.sourceTimestamp=b.sourceTimestamp;
    s.quality=overallQuality;
    s.online=overallQuality==='GOOD';
    s.hasTelemetry=true;

    if(!isHistoricalReplay){
      s.lastSeen=now();
      processRules(s,{demo:false});
      const avg=field=>{const a=stations.map(x=>x[field]).filter(v=>typeof v==='number');return a.length?a.reduce((x,y)=>x+y,0)/a.length:0;};
      history.push({time:b.sourceTimestamp,pressure:num(avg('pressureBar'),2),flow:num(stations.reduce((a,x)=>a+(x.flowM3h||0),0)/1000,2),tank:num(avg('tankLevelPct'),1)});
      if(history.length>96) history.shift();
    }
    broadcast();
    return reply(res,200,{
      ok:true,
      stationId:s.id,
      status:statusOf(s),
      dataClassification:s.dataClassification,
      isHistoricalReplay,
      sequenceNumber:b.sequenceNumber
    });
  }
  if(req.method==='POST'&&p==='/api/telemetry'){
    if(!checkKey(req))return reply(res,401,{error:'Invalid admin API key'});
    let b=await body(req);const s=stations.find(x=>x.id===b.stationId);if(!s)return reply(res,404,{error:'Unknown station ID'});
    const fields={pressureBar:[0,12],tankLevelPct:[0,100],flowM3h:[0,100_000],turbidityNtu:[0,1000],chlorineMgL:[0,20]};
    if(!Object.keys(fields).some(k=>Object.hasOwn(b,k))&&!Object.hasOwn(b,'online'))return reply(res,422,{error:'At least one telemetry field is required'});
    for(const [k,[lo,hi]]of Object.entries(fields))if(Object.hasOwn(b,k)){
      if(typeof b[k]!=='number'||!Number.isFinite(b[k])||b[k]<lo||b[k]>hi)return reply(res,422,{error:`Invalid ${k}`});
    }
    if(Object.hasOwn(b,'online')&&typeof b.online!=='boolean')return reply(res,422,{error:'Invalid online'});
    for(const k of [...Object.keys(fields),'online'])if(Object.hasOwn(b,k))s[k]=b[k];
    if(!Object.hasOwn(b,'online'))s.online=true;
    s.hasTelemetry=true;s.lastSeen=now();
    processRules(s,{demo:false});
    const avg=field=>{const a=stations.map(s=>s[field]).filter(v=>typeof v==='number');return a.length?a.reduce((x,y)=>x+y,0)/a.length:0;};
    history.push({time:now(),pressure:num(avg('pressureBar'),2),flow:num(stations.reduce((a,s)=>a+(s.flowM3h||0),0)/1000,2),tank:num(avg('tankLevelPct'),1)});if(history.length>96)history.shift();
    broadcast();return reply(res,200,{ok:true,stationId:s.id,status:statusOf(s)});
  }
  if(req.method==='POST'&&p==='/api/incidents'){
    if(!checkKey(req))return reply(res,401,{error:'Invalid admin API key'});
    let b=await body(req);
    const alert={
      id: b.id || `PWA-${uid()}`,
      stationId: b.stationId || 'PWA',
      stationName: b.stationName || 'กปภ.',
      region: b.region || 'ส่วนภูมิภาค',
      title: b.title || 'ประกาศหยุดจ่ายน้ำ',
      severity: b.severity || 'warning',
      message: b.message || '',
      value: b.value !== undefined ? b.value : '-',
      ruleId: b.ruleId || 'pwa-outage',
      createdAt: b.createdAt || now(),
      resolvedAt: b.resolvedAt || null,
      acknowledgedAt: null,
      demo: Boolean(b.demo)
    };
    store.alerts.unshift(alert);
    store.alerts = store.alerts.slice(0, 400);
    saveSoon();
    broadcast();
    return reply(res, 200, {ok: true, alertId: alert.id});
  }
  if(req.method==='POST'&&p==='/api/demo/incident'){
    if(!DEMO)return reply(res,403,{error:'Simulation disabled'});
    if(!isLoopback(req)&&!checkKey(req))return reply(res,401,{error:'Admin key required for remote demo actions'});
    const b=await body(req);const s=stations.find(x=>x.id===b.stationId)||stations.find(x=>x.id==='CM-01');
    const types={'pressure-low':{field:'pressureBar',value:0.64},'tank-low':{field:'tankLevelPct',value:12},'turbidity-high':{field:'turbidityNtu',value:5.8},'station-offline':{field:'online',value:false}};
    const preset=types[b.type]||types['pressure-low'];s[preset.field]=preset.value;processRules(s,{demo:true});broadcast();return reply(res,200,{ok:true,stationId:s.id,status:statusOf(s)});
  }
  if(req.method==='POST'&&p==='/api/demo/reset'){
    if(!DEMO)return reply(res,403,{error:'Simulation disabled'});
    if(!isLoopback(req)&&!checkKey(req))return reply(res,401,{error:'Admin key required'});
    for(const s of stations){s.pressureBar=2.65;s.tankLevelPct=75;s.turbidityNtu=.45;s.chlorineMgL=.52;s.online=true;processRules(s,{demo:true});}
    broadcast();return reply(res,200,{ok:true});
  }
  if(req.method==='POST'&&p==='/api/queue/retry-failed'){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    if(!BOT||!CHAT)return reply(res,422,{error:'Telegram not configured'});
    let count=0;for(const j of store.queue)if(j.status==='failed'){j.status='pending';j.attempt=0;j.nextAt=Date.now();j.lastError=null;count++;}
    saveSoon();broadcast();return reply(res,200,{ok:true,retried:count});
  }
  if(req.method==='POST'&&p==='/api/test-telegram'){
    if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});
    if(!BOT||!CHAT)return reply(res,422,{error:'Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env'});
    const a={id:`TEST-${uid()}`,title:'ทดสอบการเชื่อมต่อ Telegram',severity:'info',stationName:'ศูนย์ควบคุม',region:'ทุกพื้นที่',message:'ข้อความทดสอบจาก AQUA COMMAND สำเร็จเมื่อ Telegram ยอมรับการส่ง',createdAt:now(),demo:true};
    store.alerts.unshift(a);store.queue.push({id:uid(),alertId:a.id,status:'pending',attempt:0,nextAt:Date.now(),createdAt:now(),lastError:null});saveSoon();broadcast();return reply(res,202,{ok:true,queued:true,id:a.id});
  }
  const ack=p.match(/^\/api\/alerts\/([A-Za-z0-9-]+)\/ack$/);
  if(req.method==='POST'&&ack){if(!checkKey(req))return reply(res,401,{error:'Admin API key required'});const a=store.alerts.find(x=>x.id===ack[1]);if(!a)return reply(res,404,{error:'Alert not found'});a.acknowledgedAt=now();saveSoon();broadcast();return reply(res,200,{ok:true});}
  if(p.startsWith('/api/'))return reply(res,404,{error:'API not found'});
  if(req.method!=='GET'&&req.method!=='HEAD')return reply(res,405,{error:'Method not allowed'});
  const safePath=path.resolve(PUBLIC,'.'+decodeURIComponent(p==='/'?'/index.html':p));
  if(!safePath.startsWith(PUBLIC+path.sep))return reply(res,403,{error:'Forbidden'});
  try{const stat=fs.statSync(safePath);if(!stat.isFile())throw Error('Not a file');res.writeHead(200,{'Content-Type':contentTypes[path.extname(safePath)]||'application/octet-stream','X-Content-Type-Options':'nosniff','Cache-Control':'public, max-age=300','Content-Security-Policy':"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",'Referrer-Policy':'no-referrer'});fs.createReadStream(safePath).pipe(res);}catch{return reply(res,404,{error:'Not found'});}
}
const server=http.createServer((req,res)=>handler(req,res).catch(e=>reply(res,e.status||400,{error:e.message||'Bad request'})));
server.listen(PORT,HOST,()=>console.log(`AQUA COMMAND [${DEMO?'DEMO':'LIVE INGEST'}] http://${HOST}:${PORT} Telegram: ${BOT&&CHAT?'configured':'not configured'}`));
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{saveNow();server.close();setTimeout(()=>process.exit(0),1000).unref();});
