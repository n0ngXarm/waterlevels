"""Native seven-page G2 console. Presentation only: no network, DB or connector access."""
import copy,math
import gi
gi.require_version('Gtk','4.0');gi.require_version('Pango','1.0');gi.require_version('PangoCairo','1.0')
from gi.repository import Gtk,Gdk,Pango,PangoCairo
from presentation import console_state
PAGES=[('overview','ภาพรวม','Operations Overview'),('network','Network Topology','Network Topology / Configured Endpoints'),('sources','SCADA Sources','SCADA Sources & Read-Only Inventory'),('items','Monitored Items','Monitored Items / Configured Names'),('values','Live Monitoring','Selected Signals / Live Monitoring'),('delivery','Gateway & Delivery','Gateway & Delivery Queue'),('logs','Alerts & Audit','Alerts, Notifications & Activity')]
def label(text='',css=None):
 w=Gtk.Label(label=text,xalign=0);w.set_wrap(True)
 if css:w.add_css_class(css)
 return w
def box(vertical=True,spacing=8,css=None):
 w=Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
 if css:w.add_css_class(css)
 return w
def scroll(child):
 s=Gtk.ScrolledWindow();s.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);s.set_child(child);s.set_hexpand(True);s.set_vexpand(True);return s
def panel(title):
 p=box(css='console-panel');p.append(label(title,'panel-title'));return p
def unavailable(title,reason):
 p=box();b=Gtk.Button(label=title);b.set_sensitive(False);b.set_tooltip_text(reason);p.append(b);p.append(label(reason,'caption'));return p
def val(value):return '—' if value is None else str(value)

class DataTable:
 def __init__(self,headers,activate=None,monos=()):
  self.grid=Gtk.Grid(column_spacing=16,row_spacing=0);self.grid.add_css_class('data-table');self.widgets={};self.headers=headers;self.activate=activate;self.monos=monos;self.keys=[]
  self.widget=scroll(self.grid);self.update([])
 def update(self,rows):
  keys=[r[0] for r in rows]
  if keys!=self.keys or not self.grid.get_first_child():
   self.keys=keys;self.widgets={}
   while self.grid.get_first_child():self.grid.remove(self.grid.get_first_child())
   for col,name in enumerate(self.headers):self.grid.attach(label(name,'table-head'),col,0,1,1)
   if not rows:self.grid.attach(label('ยังไม่มีข้อมูลที่รายงาน — ไม่แสดงเป็นศูนย์','empty-state'),0,1,len(self.headers),1)
   for n,(key,cells) in enumerate(rows,1):
    ws=[]
    for col,value in enumerate(cells):
     if col==0 and self.activate:
      w=Gtk.Button(label=str(value));w.add_css_class('table-link');w.connect('clicked',lambda _,k=key:self.activate(k))
     else:
      w=label(str(value),'table-cell');w.set_selectable(True)
      if col in self.monos:w.add_css_class('mono');w.set_wrap(False)
      else:w.set_ellipsize(Pango.EllipsizeMode.END);w.set_max_width_chars(32)
     w.set_hexpand(True);self.grid.attach(w,col,n,1,1);ws.append(w)
    self.widgets[key]=ws
  for key,cells in rows:
   for w,value in zip(self.widgets[key],cells):
    text=str(value);w.set_tooltip_text(text)
    if isinstance(w,Gtk.Button):
     if w.get_label()!=text:w.set_label(text)
    elif w.get_text()!=text:w.set_text(text)

class Topology(Gtk.DrawingArea):
 def __init__(self):
  super().__init__();self.set_hexpand(True);self.set_vexpand(True);self.set_content_width(480);self.set_content_height(170);self.nodes=[];self.egress={};self.set_draw_func(self.draw)
 def update(self,nodes,egress):self.nodes=nodes;self.egress=egress;self.queue_draw()
 def draw(self,area,c,w,h):
  palette={'bg':(0.10,.18,.26),'line':(.17,.26,.34),'text':(.93,.96,.98),'muted':(.65,.72,.78),'accent':(.25,.78,.86),'warn':(.91,.70,.36)}
  def txt(x,y,s,size,width,color='text',mono=False):
   layout=PangoCairo.create_layout(c);fd=Pango.FontDescription();fd.set_family('DejaVu Sans Mono' if mono else 'Noto Sans Thai');dpi=Gtk.Settings.get_default().get_property('gtk-xft-dpi');scale=dpi/(96*1024) if dpi and dpi>0 else 1;fd.set_absolute_size(size*scale*Pango.SCALE);layout.set_font_description(fd);layout.set_text(s,-1);layout.set_width(int(width*Pango.SCALE));layout.set_ellipsize(Pango.EllipsizeMode.END);c.set_source_rgb(*palette[color]);c.move_to(x,y);PangoCairo.show_layout(c,layout)
  count=max(1,len(self.nodes));gap=20;nw=(w-gap*(count-1))/count;nh=109;y=6
  for i,d in enumerate(self.nodes):
   x=i*(nw+gap);c.set_source_rgb(*palette['bg']);c.rectangle(x,y,nw,nh);c.fill_preserve();c.set_source_rgb(*palette['line']);c.set_line_width(1);c.stroke()
   txt(x+10,y+7,d['id'],14,nw-20);txt(x+10,y+29,d['endpoint'] or 'Not reported',13,nw-20,'accent',True);txt(x+10,y+52,d['role']+' · local service',11,nw-20,'muted');txt(x+10,y+70,d['reachability'],11,nw-20,'muted');txt(x+10,y+88,'Hostname: not reported',10,nw-20,'muted')
   if i<count-1:
    c.set_source_rgb(*palette['line']);c.set_dash([4,4]);c.move_to(x+nw,y+55);c.line_to(x+nw+gap,y+55);c.stroke();c.set_dash([])
  txt(0,124,'เส้นประ = configured application flow · ไม่ใช่สาย LAN / NIC / VLAN ที่ตรวจพบ',11,w,'muted')
  es=self.egress;txt(0,145,'Gateway egress: '+es.get('mode','UNKNOWN')+' / '+es.get('status','NOT_MEASURED')+' / '+es.get('freshness','UNKNOWN'),11,w,'warn')

class ConsoleView:
 def __init__(self,owner):
  self.owner=owner;self.pages=Gtk.Stack();self.pages.set_hexpand(True);self.pages.set_vexpand(True);self.pages.set_transition_type(Gtk.StackTransitionType.NONE);self.last_model={};self.latest={};self.context=None;self.focus_device='PC-01';self.focus_signal=None;self.frozen=False
  self.freeze_button=Gtk.ToggleButton(label='พักการแสดงผล');self.freeze_button.connect('toggled',self.toggle_freeze)
  self.overview_topology=Topology();self.network_topology=Topology();self.metric_labels={};self.metric_scopes={};self.pipeline_labels={};self.nav_callback=None
  self.build_overview();self.build_network();self.build_sources();self.build_items();self.build_monitoring();self.build_delivery();self.build_logs()
 def add_page(self,key,child):self.pages.add_named(scroll(child),key)
 def build_overview(self):
  body=box(spacing=12);metrics=box(False,10)
  for key,title in [('snapshots','Snapshots ที่เก็บแล้ว'),('local','Local pending events'),('gateway','Gateway pending events'),('central','Central accepted events')]:
   tile=box(css='metric');tile.set_hexpand(True);tile.append(label(title,'caption'));v=label('—','metric-value');scope=label('Not reported','micro');tile.append(v);tile.append(scope);metrics.append(tile);self.metric_labels[key]=v;self.metric_scopes[key]=scope
  body.append(metrics);row=box(False,12);graph=panel('Configured endpoint flow · เครื่องเดียว / Local LAB');graph.set_hexpand(True);graph.append(self.overview_topology);row.append(graph)
  inspect=panel('Source & permission');inspect.set_size_request(255,-1);self.inspector=label('','detail-copy');inspect.append(self.inspector);row.append(inspect);body.append(row)
  pipeline=box(False,8)
  for key,title in [('collect','COLLECT 5s'),('local','LOCAL SPOOL'),('ack','GATEWAY ACK'),('central','CENTRAL ACK'),('notification','NOTIFICATION')]:
   tile=box(css='pipeline-stage');tile.set_hexpand(True);tile.append(label(title,'eyebrow'));value=label('—','stage-value');tile.append(value);pipeline.append(tile);self.pipeline_labels[key]=value
  body.append(pipeline);body.append(label('Central ACK และ Notification เป็นหลักฐานคนละเส้นทางจาก Gateway · ไม่ใช่ Telegram read receipt','caption'));self.overview_note=label('','notice');body.append(self.overview_note);self.add_page('overview',body)
 def build_network(self):
  body=box(spacing=12);body.append(label('แสดง configured service endpoints เท่านั้น ยังไม่มี observed NIC IP, Hostname หรือ Physical LAN inventory','notice'));p=panel('Application flow / ไม่สแกนเครือข่าย');p.append(self.network_topology);body.append(p)
  self.device_table=DataTable(['Role / Agent ID','Configured endpoint','Reachability','Status received (+07)','OS hostname'],self.select_device,monos=(1,));self.device_table.widget.set_min_content_height(150);body.append(self.device_table.widget)
  row=box(False,12);self.device_detail=label('','detail-copy');self.device_detail.set_hexpand(True);row.append(self.device_detail);copy=Gtk.Button(label='Copy endpoint');copy.connect('clicked',self.copy_endpoint);row.append(copy);body.append(row)
  body.append(unavailable('Refresh / discover devices','ไม่มี observe-only command หรือ NIC inventory ใน Backend ปัจจุบัน เปลี่ยนหน้าไม่ทำ probe; ใช้สถานะเดิมใน session ที่อนุญาตเท่านั้น'));self.add_page('network',body)
 def build_sources(self):
  body=box(spacing=12);self.source_summary=label('','notice');body.append(self.source_summary);self.source_table=DataTable(['Source','Capability','Scope / count','Status']);body.append(self.source_table.widget)
  p=panel('Read-only capability / แยกสิทธิ์ของ AQUA จาก SCADA');self.capability_text=label('','detail-copy');p.append(self.capability_text);body.append(p)
  row=box(False,12);row.append(unavailable('Browse OPC / register connector','ไม่มี OPC / WinCC Runtime connector ที่อนุมัติ ไม่เปิดบริการหรืออ่าน credentials เอง'));row.append(unavailable('Test one selected item','ยังไม่มี bounded read contract; ไม่ใช้ full capture หรือ LAB มาทดแทน'));body.append(row);self.add_page('sources',body)
 def build_items(self):
  body=box(spacing=12);self.item_summary=label('','notice');body.append(self.item_summary);self.item_table=DataTable(['Exact configured Tag','Source','Sampling','Rules / enable state']);body.append(self.item_table.widget)
  p=panel('Selected monitoring configuration');p.append(label('รายการนี้มาจากชื่อที่กำหนดในโปรไฟล์ปัจจุบัน ไม่ใช่จำนวน Tag ทั้งหมดของ WinCC การแก้ Source/รายชื่อด้วยหน้าตั้งค่าเดิมจะหยุด session และใช้โปรไฟล์แยก คิวเก่ายังอยู่','detail-copy'));body.append(p)
  row=box(False,12);row.append(unavailable('Add / disable item','รอ G4: ยังไม่มี per-item schema, atomic revision หรือ hot reload ที่รักษา cursor/ACK'));row.append(unavailable('Save rule / preview event','รอ backend scope แยก: ON/OFF/stale/bad quality rules ยังไม่รองรับ ไม่สร้าง event จำลอง'));body.append(row);self.add_page('items',body)
 def build_monitoring(self):
  body=box(spacing=12);row=box(False,12);self.signal_search=Gtk.SearchEntry(placeholder_text='ค้นหา Tag / Source — กรองหน้าจอเท่านั้น');self.signal_search.set_hexpand(True);self.signal_search.connect('search-changed',lambda _:self.render_signals());row.append(self.signal_search)
  self.quality_filter=Gtk.DropDown.new_from_strings(['ทุกสถานะ','GOOD / CURRENT','BAD / Unknown / Stale']);self.quality_filter.connect('notify::selected',lambda *_:self.render_signals());row.append(self.quality_filter);body.append(row)
  self.monitor_note=label('','notice');body.append(self.monitor_note);self.signal_table=DataTable(['Tag / ดูรายละเอียด','Source','RAW','STATE','Quality / code','Freshness / age'],self.select_signal);body.append(self.signal_table.widget)
  self.signal_expander=Gtk.Expander(label='รายละเอียดการอ่าน / เหตุผล Unknown — คลิก Tag เพื่อเปิด');p=panel('Observed / recorded / status received — คนละเวลา');self.signal_detail=label('','detail-copy');self.signal_detail.set_selectable(True);p.append(self.signal_detail);self.signal_expander.set_child(p);body.append(self.signal_expander);body.append(label('Isometric: Not available — ยังไม่มี selected-item mapping; เก็บ asset เดิมไว้','caption'));self.add_page('values',body)
 def build_delivery(self):
  body=box(spacing=12);self.delivery_note=label('','notice');body.append(self.delivery_note);self.delivery_table=DataTable(['Stage / scope','Count / evidence','Freshness','Meaning']);body.append(self.delivery_table.widget)
  p=panel('Retry / source storage metadata');self.retry_text=label('','detail-copy');p.append(self.retry_text);body.append(p)
  body.append(unavailable('Per-event queue / receipt lookup','ยังไม่มี bounded queue row contract: oldest pending, per-record attempts, exact receipt และ ACK rate = Not reported ไม่เปิด SQLite โดยตรงจาก UI'));self.add_page('delivery',body)
 def build_logs(self):
  body=box(spacing=12);self.event_search=Gtk.SearchEntry(placeholder_text='ค้นหา recent activity — ไม่ query source เพิ่ม');self.event_search.connect('search-changed',lambda _:self.render_events());body.append(self.event_search)
  body.append(label('Recent activity จำกัดล่าสุด 100 merged role logs; log-row ID ไม่ใช่ process event UUID และไม่ใช่ audit history ทั้งหมด','notice'));self.event_table=DataTable(['ICT (+07)','Role log-row ID','Kind','Redacted detail']);body.append(self.event_table.widget)
  p=panel('Notification receipts — ดู mode ทีละรายการ');self.notification_table=DataTable(['Event ID / Source','Mode','Result','Time (+07)']);p.append(self.notification_table.widget);body.append(p)
  body.append(unavailable('Filtered audit export / config revision','ยังไม่มี actor/config audit ledger หรือ filtered export contract ปุ่มบันทึก CSV เดิมส่งออก recent snapshots ไม่ใช่ audit report'));self.add_page('logs',body)
 def update(self,status,source_mode,settings,port,active):
  fresh=console_state(status,source_mode,settings,port,session_active=active);context=(source_mode,tuple(settings.get('tags') or []),settings.get('sourceDirectory'))
  self.latest=fresh
  if self.context!=context or not active:
   if self.freeze_button.get_active():self.freeze_button.set_active(False)
   self.frozen=False
  self.context=context
  if self.frozen:
   cached=copy.deepcopy(self.last_model);cached['capture_allowed']=fresh['capture_allowed'];cached['transfer_allowed']=fresh['transfer_allowed'];self.last_model=self.cached_display(cached);self.render();return
  self.last_model=fresh;self.render()
 def cached_display(self,m):
  m=copy.deepcopy(m)
  for d in m['devices']:d['reachability']='CACHED'
  for metric in m['metrics'].values():metric['cached']=True
  m['ack_metric']['cached']=True;m['notification']['count_metric']['cached']=True;m['notification']['pending_metric']['cached']=True
  m['egress']['freshness']='CACHED';m['egress']['available']=False
  for r in m['signals']:r['freshness']='DISPLAY_CACHED';r['state']='UNKNOWN';r['reason']='พักการแสดงผล; RAW เป็นภาพที่เก็บไว้'
  return m
 def toggle_freeze(self,b):
  self.frozen=b.get_active();b.set_label('แสดงข้อมูลต่อ' if self.frozen else 'พักการแสดงผล')
  if self.frozen and self.last_model:self.last_model=self.cached_display(self.last_model);self.render()
  elif self.latest:self.last_model=self.latest;self.render()
  self.owner.update_display_status(self.frozen)
 def render(self):
  m=self.last_model
  if not m:return
  for key,item in m['metrics'].items():
   self.metric_labels[key].set_text(val(item['value']));scope=('CACHED · ' if item['cached'] else '')+('partial '+item['coverage'] if item['partial'] else 'reported '+item['coverage']);self.metric_scopes[key].set_text(scope+' · '+('current backlog' if key in ('local','gateway') else 'dataset cumulative'))
  for topo in (self.overview_topology,self.network_topology):topo.update(m['devices'],m['egress'])
  self.inspector.set_text('Source: '+m['source_mode']+'\nConfigured names: '+val(m['configured_count'])+'\nWinCC session: Not available\nNIC IP / OS login: Not reported\nข้อมูลขณะพักหน้าจอ = CACHED')
  self.pipeline_labels['collect'].set_text('5s · '+('allowed' if m['capture_allowed'] else 'waiting'))
  self.pipeline_labels['local'].set_text(val(m['metrics']['local']['value'])+' events');self.pipeline_labels['ack'].set_text(val(m['gateway_acked'])+' events'+(' · CACHED' if m['ack_metric']['cached'] else ' · partial' if m['ack_metric']['partial'] else ''));self.pipeline_labels['central'].set_text(val(m['metrics']['central']['value'])+' events');self.pipeline_labels['notification'].set_text(val(m['notification']['count'])+' records / all modes'+(' · CACHED' if m['notification']['count_metric']['cached'] else ''))
  self.overview_note.set_text('WinCC Runtime ยังไม่พร้อม — ไม่มี connector ที่ได้รับอนุญาต; ไม่ใช้ LAB แทนเอง' if not m['source_available'] else ('SIMULATED LAB — ค่าทดสอบในเครื่องเดียว ไม่ใช่ WinCC / Internet จริง' if m['source_mode']=='SIMULATED' else 'FILE — อ่าน CSV ที่อนุญาต ไม่ได้ยืนยันการเชื่อม WinCC Runtime โดยตรง'))
  self.device_table.update([(d['id'],[d['id']+' / '+d['role'],d['endpoint'] or 'Not reported',d['reachability'],d['last_seen'],'Not reported']) for d in m['devices']]);self.render_device_detail()
  self.source_summary.set_text('Selected source: '+m['source_mode']+' · '+m['source_path'])
  self.source_table.update([('selected',[m['source_mode'],'Configured CSV batch' if m['source_available'] else 'Unavailable',val(m['configured_count'])+' configured names','Read-only / manual consent']),('wincc',['WinCC Runtime / OPC','Not supported','Total tags: Not available','No approved connector']),('mapping',['Imported mapping','Names only','Eligible names, not all tasks','Configuration ≠ runtime'])])
  self.capability_text.set_text('Hostname / NIC inventory: Not reported\nAQUA peer authentication: enrolled role status only\nSCADA / OS session: Not available\nSelective read: complete configured CSV frames only\nOPC browse / total WinCC tasks: Not supported\nLast source read: '+(m['sources'][0]['observed'] if m['sources'] else 'Not reported'))
  self.item_summary.set_text('AQUA configured names: '+val(m['configured_count'])+' · รอบ 5s เมื่ออนุญาต · การกรองตารางไม่เปลี่ยนรายการที่เก็บ')
  self.item_table.update([(t,[t,'PC-01 / '+m['source_mode'],'5s','Per-item rules / enable: unavailable']) for t in m['configured_tags']]);self.render_signals()
  e=m['egress'];self.delivery_note.set_text('Gateway egress: '+e['status']+' / '+e['mode']+' / '+e['freshness']+' · checked: '+e['checked_at']+'\nInternet ของ Agent = NOT_MEASURED; Central ACK ≠ Telegram')
  self.delivery_table.update([(key,[title,val(metric['value']),('CACHED' if metric['cached'] else 'Reported') if metric['value'] is not None else 'Not reported',meaning]) for key,title,metric,meaning in [('local','Local spool',m['metrics']['local'],'UnACKed events, including snapshots/transitions'),('gateway','Gateway outbound',m['metrics']['gateway'],'Waiting upstream ACK'),('central','Central accepted',m['metrics']['central'],'Not Telegram delivery')]]+[('ack',['Gateway accepted',val(m['gateway_acked']),('CACHED' if m['ack_metric']['cached'] else 'Reported')+' / '+m['ack_metric']['coverage'],m['ack_metric']['as_of']]),('notify',['Notifications (all modes)',val(m['notification']['count']),m['notification']['mode']+(' · CACHED' if m['notification']['count_metric']['cached'] else ''),m['notification']['count_metric']['as_of']])])
  self.retry_text.set_text('\n'.join(s['id']+' · retries '+val(s['retry_count'])+' · next '+s['next_retry']+'\nLocal DB bytes '+val(s['disk']['bytes'])+' / quota '+val(s['disk']['maxDatabaseBytes'])+' · Source error: '+(s['source_error'] or '—')+' · Transfer error: '+(s['transfer_error'] or '—') for s in m['sources']) or 'Not reported — session ยังไม่เริ่ม; ไม่เปิดฐานข้อมูลเพื่อเติมตัวเลข')
  self.render_events()
  self.notification_table.update([(str(i),[n['id']+' / '+n['source'],n['mode'],'Dry-run recorded (not sent)' if n['mode']=='dry-run' else 'Mock sink accepted' if n['mode']=='mock-http' else 'Telegram API accepted' if n['mode']=='telegram' and n['message_id'] is not None else 'Not verified',n['time']]) for i,n in enumerate(m['notification']['messages'])])
  self.owner.tag_widgets=self.signal_table.widgets
 def render_signals(self):
  m=self.last_model
  if not m:return
  search=self.signal_search.get_text().casefold();quality=self.quality_filter.get_selected();rows=[]
  for r in m['signals']:
   if search and search not in (r['tag']+' '+r['source_id']).casefold():continue
   good=r['quality']=='GOOD' and r['freshness']=='CURRENT'
   if quality==1 and not good or quality==2 and good:continue
   rows.append((r['key'],[r['tag'],r['source_id']+' / '+r['mode'],val(r['raw']),r['state'],r['quality']+' / '+val(r['quality_code']),r['freshness']+' / '+(str(r['age'])+'s' if r['age'] is not None else '—')]))
  self.signal_table.update(rows);self.owner.tag_widgets=self.signal_table.widgets;self.monitor_note.set_text(m['source_mode']+' config / data '+','.join(m['reading_modes'])+' · '+str(len(rows))+' displayed / '+str(len(m['signals']))+' configured observations · State Unknown มีเหตุผลแยกจาก RAW / Quality')
  self.render_signal_detail()
 def select_signal(self,key):self.focus_signal=key;self.signal_expander.set_expanded(True);self.render_signal_detail()
 def render_signal_detail(self):
  rows=self.last_model.get('signals',[]);r=next((r for r in rows if r['key']==self.focus_signal),rows[0] if rows else None)
  self.signal_detail.set_text('ยังไม่มีค่า — เลือก Source และอนุญาตอ่านก่อน' if not r else r['tag']+' · '+r['reason']+'\nObserved: '+r['observed']+' | Recorded locally: '+r['recorded']+'\nStatus received: '+r['status_received']+'\nRead error: '+val(r['read_error'])+' | Quality code: '+val(r['quality_code'])+'\nLast good / sample received / exact receipt: Not reported (ไม่มี contract)')
 def render_events(self):
  if not self.last_model:return
  query=self.event_search.get_text().casefold();events=[e for e in self.last_model['events'] if not query or query in (' '.join(e.values())).casefold()];self.event_table.update([(e['id'],[e['time'],e['id'],e['kind'],e['message']]) for e in events])
 def select_device(self,key):self.focus_device=key;self.render_device_detail()
 def render_device_detail(self):
  d=next((d for d in self.last_model.get('devices',[]) if d['id']==self.focus_device),None)
  self.device_detail.set_text('Not reported' if not d else d['id']+' · '+d['method']+' · '+d['last_seen']+'\nObserved NIC / interface / subnet: Not reported; PC Internet: NOT_MEASURED')
 def copy_endpoint(self,_):
  d=next((d for d in self.last_model.get('devices',[]) if d['id']==self.focus_device),None)
  if d and d['endpoint']:Gdk.Display.get_default().get_clipboard().set(d['endpoint']);self.owner.message.set_text('คัดลอก configured endpoint แล้ว — ไม่ใช่ observed NIC IP')
