"""Pure, provenance-aware adapter over the existing native IPC state. No I/O or probes."""
import datetime,re
from zoneinfo import ZoneInfo
UTC=datetime.timezone.utc
ICT=ZoneInfo('Asia/Bangkok')
LAB_TAGS=tuple(f'LAB_PUMP_{i:02}.RUN_S' for i in range(1,6))

def safe_text(value,limit=1000):
 text=str(value or '')[:limit]
 text=re.sub(r'''(?i)(["']?\b(?:secret|token|password|authorization)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|Bearer\s+\S+|\S+)''',lambda m:m[1]+'[redacted]',text)
 text=re.sub(r'\b\d{6,}:[A-Za-z0-9_-]{15,}', '[redacted]',text)
 return text

def parsed(value):
 if not isinstance(value,str):return None
 try:
  d=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
  return d if d.tzinfo else None
 except (ValueError,OverflowError):return None

def seconds(value,now):
 d=parsed(value)
 return (now-d).total_seconds() if d else None

def timestamp(value):
 d=parsed(value)
 try:return d.astimezone(ICT).isoformat(timespec='seconds') if d else 'Not reported'
 except (ValueError,OverflowError):return 'Not reported'

def array(value):return value if isinstance(value,list) else []
def mapping(value):return value if isinstance(value,dict) else {}

def number(value):return value if isinstance(value,(int,float)) and not isinstance(value,bool) and value>=0 else None

def report_state(role,active,now):
 if not active:return 'NOT_CHECKED'
 age=seconds(role.get('lastSeen'),now)
 if age is None:return 'UNKNOWN'
 if role.get('online') is not True:return 'UNREACHABLE'
 return 'REACHABLE' if -30<=age<=3 else 'CACHED'

def console_state(status,source_mode,settings,port,session_active=False,now=None):
 now=now or datetime.datetime.now(UTC);status=status if isinstance(status,dict) else {};settings=settings if isinstance(settings,dict) else {}
 agents=[a for a in array(status.get('agents')) if isinstance(a,dict)] if session_active else []
 gateway=status.get('gateway') if session_active and isinstance(status.get('gateway'),dict) else {}
 central=status.get('central') if session_active and isinstance(status.get('central'),dict) else {}
 mode={'runtime':'UNAVAILABLE','csv':'FILE','lab':'SIMULATED'}.get(source_mode,'UNKNOWN')
 tags=list(settings.get('tags',[])) if source_mode=='csv' and isinstance(settings.get('tags'),list) else list(LAB_TAGS) if source_mode=='lab' else []
 tags=[t for t in tags if isinstance(t,str)]
 known_ids=[a.get('id') for a in agents if isinstance(a.get('id'),str)] or ['PC-01']
 devices=[]
 for id in known_ids+['PC-04','CENTRAL-LAB']:
  role=next((a for a in agents if a.get('id')==id),{}) if id not in ('PC-04','CENTRAL-LAB') else gateway if id=='PC-04' else central
  endpoint={'PC-01':f'127.0.0.1:{port+8}','PC-04':f'127.0.0.1:{port+1}','CENTRAL-LAB':f'127.0.0.1:{port+2}'}.get(id)
  devices.append({'id':safe_text(id,80),'role':'Gateway' if id=='PC-04' else 'Central LAB' if id=='CENTRAL-LAB' else 'Agent','endpoint':endpoint,'hostname':None,'observed_ips':[],'internet':None,'reachability':report_state(role,session_active,now),'last_seen':timestamp(role.get('lastSeen')),'checked_age':seconds(role.get('lastSeen'),now),'method':'AQUA HMAC status' if role.get('lastSeen') else 'Not checked','source_mode':mode if id not in ('PC-04','CENTRAL-LAB') else 'LOCAL LAB'})
 def sum_metric(key):
  rows=[a for a in agents if parsed(a.get('lastSeen')) and number(a.get(key)) is not None]
  return {'value':sum(a[key] for a in rows) if rows else None,'coverage':f'{len(rows)}/{len(known_ids)}','partial':len(rows)<len(known_ids),'cached':any(report_state(a,True,now)!='REACHABLE' for a in rows),'as_of':max((timestamp(a.get('lastSeen')) for a in rows),default='Not reported')}
 def gateway_metric(key):
  value=number(gateway.get(key)) if parsed(gateway.get('lastSeen')) else None
  return {'value':value,'coverage':'1/1' if value is not None else '0/1','partial':value is None,'cached':bool(value is not None and report_state(gateway,True,now)!='REACHABLE'),'as_of':timestamp(gateway.get('lastSeen'))}
 metrics={'snapshots':sum_metric('snapshots'),'local':sum_metric('pending'),'gateway':gateway_metric('pending'),'central':gateway_metric('upstreamDelivered')}
 e=gateway.get('egress') if isinstance(gateway.get('egress'),dict) else {};ea=seconds(e.get('checkedAt'),now)
 e_current=report_state(gateway,session_active,now)=='REACHABLE' and ea is not None and -30<=ea<=15
 egress={'status':safe_text(e.get('status') or 'NOT_MEASURED',40),'mode':safe_text(e.get('mode') or gateway.get('internetMode') or 'UNKNOWN',30),'available':bool(e_current and e.get('status') in ('VERIFIED','SIMULATED_AVAILABLE')),'freshness':'CURRENT' if e_current else 'CACHED' if ea is not None else 'UNKNOWN','checked_at':timestamp(e.get('checkedAt')),'method':'Gateway self-check to configured sink; not Agent Internet'}
 signals=[];source_rows=[]
 for a in agents if mode!='UNAVAILABLE' else []:
  observed=a.get('observedAt');age=seconds(observed,now);report=report_state(a,True,now)
  fresh='NEVER_READ' if age is None else 'CLOCK_SKEW' if age< -30 else 'STALE' if age>15 else 'CURRENT'
  if report!='REACHABLE' and age is not None:fresh='CACHED' if fresh=='CURRENT' else fresh
  observations=a.get('observations') if isinstance(a.get('observations'),dict) else {};values=a.get('pumps') if isinstance(a.get('pumps'),dict) else {}
  names=list(observations) or tags
  for tag in names:
   o=observations.get(tag) if isinstance(observations.get(tag),dict) else {};quality=safe_text(o.get('quality') or 'UNKNOWN',40);v=values.get(tag);good=fresh=='CURRENT' and quality=='GOOD' and isinstance(v,bool)
   state='ON' if good and v else 'OFF' if good else 'UNKNOWN'
   reason='Fresh confirmed mapping' if good else 'Source timestamp missing' if age is None else fresh if fresh!='CURRENT' else quality
   signals.append({'key':str(a.get('id',''))+':'+tag,'tag':safe_text(tag,100),'source_id':safe_text(a.get('id'),80),'mode':('SIMULATED' if a.get('simulated') is True else 'FILE' if a.get('simulated') is False and a.get('sourceAdapter')=='wincc-csv' else 'UNKNOWN') if observations else 'NOT_READ','raw':o.get('raw_value'),'state':state,'quality':quality,'quality_code':o.get('quality_code'),'read_error':o.get('read_error'),'freshness':fresh,'age':max(0,int(age)) if age is not None else None,'observed':timestamp(observed),'recorded':timestamp(a.get('lastExport')),'status_received':timestamp(a.get('lastSeen')),'last_good':None,'sample_received':None,'receipt':None,'reason':safe_text(reason,120)})
  source_rows.append({'id':safe_text(a.get('id'),80),'mode':mode,'last_export':timestamp(a.get('lastExport')),'observed':timestamp(observed),'source_error':safe_text(a.get('sourceError')),'transfer_error':safe_text(a.get('transferError')),'pending':number(a.get('pending')) if parsed(a.get('lastSeen')) else None,'acked':number(a.get('acked')) if parsed(a.get('lastSeen')) else None,'last_ack':timestamp(a.get('lastAckAt')),'retry_count':number(a.get('retryCount')),'next_retry':datetime.datetime.fromtimestamp(a['nextRetryAt']/1000,UTC).astimezone(ICT).isoformat(timespec='seconds') if isinstance(a.get('nextRetryAt'),(int,float)) and 0<a['nextRetryAt']<4102444800000 else 'Not reported','reported_at':timestamp(a.get('lastSeen')),'cached':report!='REACHABLE','disk':{k:number(mapping(a.get('disk')).get(k)) for k in ('bytes','maxDatabaseBytes','maxPending','maxHistory','maxRecords')}})
 if not signals and mode!='UNAVAILABLE':
  signals=[{'key':'PC-01:'+tag,'tag':safe_text(tag,100),'source_id':'PC-01','mode':'NOT_READ','raw':None,'state':'UNKNOWN','quality':'UNKNOWN','quality_code':None,'read_error':None,'freshness':'NEVER_READ','age':None,'observed':'Not reported','recorded':'Not reported','status_received':'Not reported','last_good':None,'sample_received':None,'receipt':None,'reason':'Not read in this session'} for tag in tags]
 logs=[{'id':safe_text(e.get('id'),100),'time':timestamp(e.get('time') or e.get('at')),'kind':safe_text(e.get('kind'),40),'message':safe_text(e.get('message'),400)} for e in array(status.get('events'))[:100] if isinstance(e,dict)] if session_active else []
 messages=[{'id':safe_text(m.get('event_id'),100),'source':safe_text(m.get('source_id'),80),'mode':safe_text(m.get('mode') or 'UNKNOWN',30),'message_id':m.get('message_id') if isinstance(m.get('message_id'),(int,str)) else None,'time':timestamp(m.get('delivered_at')),'text':safe_text(m.get('text'),1000)} for m in array(gateway.get('messages'))[:50] if isinstance(m,dict)]
 return {'source_mode':mode,'reading_modes':sorted({r['mode'] for r in signals}) or ['NOT_READ'],'source_available':mode in ('FILE','SIMULATED'),'source_path':safe_text(settings.get('sourceDirectory') if mode=='FILE' else 'Explicit local LAB fixture' if mode=='SIMULATED' else 'No approved Runtime connector'),'configured_tags':tags,'configured_count':len(tags) if mode!='UNAVAILABLE' else None,'scada_auth':'NOT_AVAILABLE','session_active':bool(session_active),'capture_allowed':status.get('captureAllowed') is True and session_active,'transfer_allowed':status.get('transferAllowed') is True and session_active,'devices':devices,'metrics':metrics,'gateway_acked':sum_metric('acked')['value'],'ack_metric':sum_metric('acked'),'egress':egress,'signals':signals,'sources':source_rows,'notification':{'count':gateway_metric('notificationSent')['value'],'pending':gateway_metric('notificationPending')['value'],'count_metric':gateway_metric('notificationSent'),'pending_metric':gateway_metric('notificationPending'),'mode':safe_text(gateway.get('notificationMode') or 'NOT_REPORTED',30),'messages':messages},'events':logs,'dataset':safe_text(status.get('generation') or 'Not reported',100),'updated':now.astimezone(ICT).isoformat(timespec='seconds'),'capabilities':{'browse':False,'wincc_read':False,'item_rules':False,'hot_reload':False,'queue_rows':False,'audit_export':False}}
