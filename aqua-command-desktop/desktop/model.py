"""Desktop presentation and private local settings. No WinCC/PLC client or writer."""
import csv,datetime,hashlib,json,os,pathlib,re,uuid
TAG=re.compile(r'[-A-Za-z0-9_.]{1,100}\Z')
def valid_tags(tags):
 if not isinstance(tags,list) or not 1<=len(tags)<=100 or any(not isinstance(t,str) or not TAG.fullmatch(t) or t in ('__proto__','constructor','prototype') for t in tags) or len(set(tags))!=len(tags):raise ValueError('ชื่อ Tag ไม่ถูกต้อง หรือเกิน100รายการ')
 return tags

def read_tag_names(file):
 with pathlib.Path(file).open('rb') as f:raw=f.read(2_000_001)
 if len(raw)>2_000_000:raise ValueError('ไฟล์รายชื่อใหญ่เกินกำหนด')
 text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')
 if text.startswith('DmTag\t'):
  rows=list(csv.reader(text.splitlines(),delimiter='\t'))
  if len(rows)<3 or not rows[1][0].startswith('[NAME]'):raise ValueError('ไม่ใช่ไฟล์ตั้งค่าTagที่รองรับ')
  tags=[r[0] for r in rows[3:] if len(r)>=3 and r[2]=='Binary Tag' and r[0].endswith('.RUN_S')]
 else:tags=[s.strip() for s in text.splitlines() if s.strip()]
 return valid_tags(tags)

def owned_directory(root,source=None):
 root=pathlib.Path(root).absolute()
 if source:
  src=pathlib.Path(source).resolve();target=root.resolve()
  if target==src or src in target.parents:raise ValueError('ที่เก็บAQUAต้องอยู่นอกโฟลเดอร์ต้นทาง')
 for part in [root,*root.parents]:
  if part.is_symlink():raise ValueError('ไม่ใช้ลิงก์เป็นที่เก็บข้อมูลAQUA')
 if root.exists():
  todo=[root];count=0
  while todo:
   p=todo.pop();count+=1
   if count>10000:raise ValueError('ที่เก็บข้อมูลมีรายการมากเกินกำหนด')
   if p.is_symlink() or p.is_file() and p.stat().st_nlink>1:raise ValueError('ไม่ใช้ลิงก์เป็นที่เก็บข้อมูลAQUA')
   if p.is_dir():todo.extend(p.iterdir())
 return root

def atomic_json(file,value):
 file=pathlib.Path(file);tmp=file.with_name(file.name+'.'+uuid.uuid4().hex+'.tmp')
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.replace(tmp,file)
 finally:
  if tmp.exists():tmp.unlink()

def prepare_profile(state_root,settings):
 if not isinstance(settings,dict):raise ValueError('การตั้งค่าไม่ถูกต้อง')
 settings=dict(settings)
 if set(settings)-{'sourceDirectory','tags','timezoneOffset','mappingConfirmed'}:raise ValueError('การตั้งค่าไม่รองรับ')
 if settings.get('sourceDirectory'):
  source=pathlib.Path(settings['sourceDirectory']).resolve()
  if not source.is_dir():raise ValueError('ไม่พบโฟลเดอร์CSVต้นทาง')
  settings['sourceDirectory']=str(source);valid_tags(settings.get('tags'))
  if not re.fullmatch(r'[+-](?:0\d|1[0-3]):[0-5]\d|[+-]14:00',settings.get('timezoneOffset','+07:00')):raise ValueError('เขตเวลาไม่ถูกต้อง')
  settings['timezoneOffset']=settings.get('timezoneOffset','+07:00');settings['mappingConfirmed']=settings.get('mappingConfirmed') is True
 else:settings={}
 root=owned_directory(state_root,settings.get('sourceDirectory'));fingerprint=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()[:20] if settings else 'lab'
 root.mkdir(parents=True,exist_ok=True,mode=0o700);config=root/('source-'+fingerprint+'.json');atomic_json(config,settings)
 return {'config':config,'data':root/'profiles'/fingerprint,'settings':settings}

def present_status(status,now=None):
 a=(status.get('agents') or [{}])[0];now=now or datetime.datetime.now(datetime.timezone.utc)
 try:observed=datetime.datetime.fromisoformat((a.get('observedAt') or '').replace('Z','+00:00'));age=(now-observed).total_seconds();stale=age>15 or age< -30
 except (KeyError,TypeError,ValueError):observed=None;stale=True
 online=a.get('online') is True;running=online and a.get('recording') is True
 if not online:recording='กำลังเชื่อมต่อส่วนเก็บข้อมูล'
 elif not running:recording='หยุดเก็บชั่วคราว'
 elif a.get('sourceError'):recording='รอไฟล์ต้นทางที่อ่านได้'
 elif not observed:recording='รอไฟล์ค่าจากต้นทาง'
 elif stale:recording='ยังไม่มีข้อมูลใหม่จากต้นทาง'
 else:recording='กำลังเก็บข้อมูลทุก5วินาที'
 ready=a.get('gatewayAuthenticated') is True and status.get('gatewayConnected') is True and status.get('internetStatus') in ('VERIFIED','SIMULATED_AVAILABLE')
 rows=[]
 for tag,o in (a.get('observations') or {}).items():
  value=(a.get('pumps') or {}).get(tag);state='ไม่ทราบ' if stale or not online or o.get('quality')!='GOOD' else 'ON' if value is True else 'OFF' if value is False else 'ไม่ทราบ'
  rows.append({'tag':tag,'raw':o.get('raw_value'),'state':state,'quality':o.get('quality','UNKNOWN'),'quality_code':o.get('quality_code')})
 return {'mode':'ไฟล์ต้นทาง · WinCC ยังไม่ผ่านการตรวจรับ' if a.get('simulated') is False else 'LAB · ข้อมูลตัวอย่าง ไม่เชื่อมWinCC/PLC','recording':recording,'online':online,'running':running,'gateway_ready':ready,'network':'เครื่องรับพร้อม · ส่งต่ออัตโนมัติ' if ready else 'เก็บรอในเครื่อง · ยังไม่มีเครื่องรับพร้อม','egress':'Internetจำลอง · ปลายทางทดสอบในเครื่อง' if status.get('internetStatus')=='SIMULATED_AVAILABLE' else 'GatewayตรวจทางออกInternetของตัวเองแล้ว' if status.get('internetStatus')=='VERIFIED' else 'ยังไม่ยืนยันทางออกInternet','snapshots':status.get('snapshots'),'pending':status.get('scadaQueueCount'),'gateway_pending':status.get('gatewayQueueCount'),'delivered':status.get('delivered'),'notifications':status.get('notificationSent'),'observed':observed.astimezone().strftime('%d/%m/%Y %H:%M:%S %Z') if observed else '—','rows':rows,'error':a.get('lastError'),'logs':'\n'.join(f"{e.get('time','')}  {e.get('kind','')}  {e.get('message','')}" for e in status.get('events',[])[:16]),'notification_mode':status.get('notificationMode','dry-run')}
