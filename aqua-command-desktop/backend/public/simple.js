const $=id=>document.getElementById(id),text=(id,value)=>$(id).textContent=value??'—',clock=value=>value?new Date(value).toLocaleString('th-TH'):'—';let state=null,busy=false,localError=null;
function render(s){state=s;const a=s.agents?.[0],running=a?.online&&a.recording,stale=!a?.observedAt||Date.now()-Date.parse(a.observedAt)>15000||Date.parse(a.observedAt)>Date.now()+30000;
 text('sourceMode',a?.simulated===false?'อ่านจากไฟล์ Runtime · การเชื่อม WinCC จริงยังไม่ผ่านการตรวจรับ':'ทดสอบบน Linux · ข้อมูล CSV จำลอง · ไม่มีการเชื่อม WinCC/PLC จริง');
 text('recordingState',!a?.online?'ยังติดต่อส่วนเก็บข้อมูลไม่ได้':!running?'หยุดเก็บชั่วคราว':a.lastError?'รอไฟล์ต้นทางที่อ่านได้':!a.observedAt?'รอไฟล์ค่าจากต้นทาง':stale?'ยังไม่มีข้อมูลใหม่จากต้นทาง':'กำลังเก็บข้อมูลทุก 5 วินาที');
 $('start').disabled=busy||!a?.online||running;$('stop').disabled=busy||!a?.online||!running;
 text('snapshots',s.snapshots);text('pending',s.scadaQueueCount);text('acked',s.acked);text('delivered',s.delivered);text('observed',clock(a?.observedAt));
 const ready=a?.gatewayAuthenticated&&s.gatewayConnected&&['VERIFIED','SIMULATED_AVAILABLE'].includes(s.internetStatus); text('networkState',ready?'เครื่องรับพร้อม · ส่งข้อมูลอัตโนมัติ':'รอเครื่องที่พร้อมส่งต่อ');
 text('networkDetail',s.internetStatus==='SIMULATED_AVAILABLE'?'ใช้ปลายทางทดสอบในเครื่อง · Internet เป็นเงื่อนไขจำลอง':s.internetStatus==='VERIFIED'?'เครื่อง Gateway ตรวจทางออก Internet ของตัวเองแล้ว':'ไฟล์และคิวยังเก็บอยู่ในเครื่อง แม้ไม่มี Internet');
 text('notifications',`Telegram: ${s.notificationMode==='dry-run'?'DRY-RUN (ไม่ส่งออก Internet)':s.notificationMode} · แจ้งเตือนแล้ว ${s.notificationSent??0} รายการ`);
 text('verification',s.verificationLevel==='TESTED ON ONE HOST'?'ทดสอบส่งจริงระหว่างโปรเซสบนเครื่องเดียว · READ ONLY':s.verificationLevel);
 const error=localError||a?.lastError;$('error').hidden=!error;text('error',error?'ยังเก็บข้อมูลใหม่ไม่ได้: '+error:'');
 const body=$('tags');body.replaceChildren();for(const [tag,o] of Object.entries(a?.observations||{})){const tr=document.createElement('tr'),value=a.pumps?.[tag];for(const valueText of [tag,o.raw_value??'—',stale?'ข้อมูลเก่า / ไม่ทราบ':value===true?'ON':value===false?'OFF':'ไม่ทราบ',o.quality+' · '+(o.quality_code??'—')]){const td=document.createElement('td');td.textContent=String(valueText);tr.append(td)}body.append(tr)}
 text('logs',(s.events||[]).slice(0,8).map(e=>`${clock(e.time)} · ${e.kind} · ${e.message}`).join('\n'));
}
async function recording(running){busy=true;if(state)render(state);try{const r=await fetch('/api/action',{method:'POST',headers:{'content-type':'application/json','x-aqua-control':document.querySelector('meta[name="aqua-control-token"]').content},body:JSON.stringify({action:'recording',running})});if(!r.ok)throw Error('เปลี่ยนสถานะการเก็บไม่ได้');localError=null;render(await r.json())}catch(e){localError=e.message}finally{busy=false;if(state)render(state)}}
$('start').addEventListener('click',()=>recording(true));$('stop').addEventListener('click',()=>recording(false));
fetch('/api/status').then(r=>r.json()).then(render).catch(()=>text('recordingState','ยังเชื่อมต่อ AQUA ไม่ได้'));
const stream=new EventSource('/api/events');stream.onmessage=e=>render(JSON.parse(e.data));stream.onerror=()=>{text('recordingState','การเชื่อมต่อขาด กำลังเชื่อมใหม่');$('start').disabled=true;$('stop').disabled=true};
