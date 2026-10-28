#!/usr/bin/python3
"""Native, operator-started read-only workstation. Opening it starts no workers."""
import argparse,json,pathlib,sys,threading
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Pango
from client import BackendClient
from model import present_status,prepare_profile,read_tag_names,atomic_json,owned_directory,valid_tags
from consent import ConsentBook,scope_key
ROOT=pathlib.Path(__file__).resolve().parents[1]
VERSION='0.7.0'
def label(text='',css=None,x=0):
 w=Gtk.Label(label=text,xalign=x);w.set_wrap(True)
 if css:w.add_css_class(css)
 return w
def box(vertical=False,spacing=0,css=None):
 w=Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
 if css:w.add_css_class(css)
 return w
def button(text,callback,css=None):
 w=Gtk.Button(label=text);w.connect('clicked',callback)
 if css:w.add_css_class(css)
 return w
class ConsentDialog(Gtk.Window):
 def __init__(self,owner,action,details,accept):
  title='อนุญาตให้อ่านและเก็บข้อมูล' if action=='capture' else 'อนุญาตให้ส่งข้อมูล'
  super().__init__(title=title,transient_for=owner,modal=True);self.set_default_size(700,660)
  body=box(True,16,'dialog-body');self.set_child(body);body.append(label('ตรวจรายละเอียดก่อนเริ่ม','eyebrow'));body.append(label(title,'page-title'));review=Gtk.ScrolledWindow();review.set_min_content_height(280);review.set_max_content_height(300);review.set_propagate_natural_height(True);review.set_child(label(details,'review-details'));body.append(review)
  body.append(label('สิทธิ์นี้ใช้ต่อเนื่องจนกว่าจะหยุดหรือปิดโปรแกรม ไม่ถามซ้ำทุก 5 วินาที','muted'))
  self.remember_check=Gtk.CheckButton(label='ไม่ถามซ้ำสำหรับแหล่งข้อมูล / ปลายทางชุดนี้');body.append(self.remember_check);body.append(label('ยังต้องกดเริ่มเองทุกครั้งที่เปิดโปรแกรม เปลี่ยนแหล่งข้อมูลหรือเครื่องรับจะถามใหม่ ถอนสิทธิ์ได้จากเมนูสิทธิ์ใช้งาน','caption'))
  row=box(spacing=12);self.cancel_button=button('ยกเลิก',lambda _:self.close());self.approve_button=button('อนุญาตและเริ่ม',lambda _:self.approve(accept),'primary');row.append(self.cancel_button);row.append(self.approve_button);body.append(row)
  self.connect('close-request',lambda _:self.released(owner));self.owner=owner
 def released(self,owner):owner.consent_dialog=None;return False
 def approve(self,accept):
  remember=self.remember_check.get_active();self.owner.consent_dialog=None;self.destroy();accept(remember)
class SourceEditor(Gtk.Window):
 def __init__(self,owner):
  super().__init__(title='ตั้งค่าแหล่งข้อมูล',transient_for=owner,modal=True);self.set_default_size(690,620);self.owner=owner
  body=box(True,12,'dialog-body');self.set_child(body);body.append(label('01  เลือกสิ่งที่จะอ่าน','eyebrow'));body.append(label('แหล่งข้อมูลปั๊ม','page-title'))
  self.mode=Gtk.DropDown.new_from_strings(['WinCC Runtime จริง — ยังไม่มีช่องทางอ่านที่อนุญาต','ไฟล์ Runtime CSV ที่ส่งออกไว้แล้ว','ข้อมูล LAB — จำลองเฉพาะในเครื่องนี้']);self.mode.set_selected({'runtime':0,'csv':1,'lab':2}[owner.source_mode]);body.append(self.mode)
  self.description=label('','notice');body.append(self.description)
  self.chosen={'directory':owner.settings.get('sourceDirectory'),'tags':owner.settings.get('tags',[])}
  self.csv_box=box(True,8);body.append(self.csv_box);self.path_label=label(self.chosen['directory'] or 'ยังไม่ได้เลือกโฟลเดอร์','muted');self.path_label.set_selectable(True);self.csv_box.append(self.path_label)
  self.csv_box.append(button('เลือกโฟลเดอร์ Runtime CSV',self.pick_folder));self.csv_box.append(button('นำเข้ารายชื่อ Tag / Export all.txt',self.pick_tags));self.tags_label=label(f"รายชื่อ Tag: {len(self.chosen['tags'])} รายการ",'muted');self.csv_box.append(self.tags_label)
  self.timezone=Gtk.DropDown.new_from_strings(['+07:00','+00:00']);self.timezone.set_selected(1 if owner.settings.get('timezoneOffset')=='+00:00' else 0);row=box(spacing=12);row.append(label('เขตเวลาของไฟล์'));row.append(self.timezone);self.csv_box.append(row)
  self.confirmed=Gtk.CheckButton(label='ตรวจสอบความหมาย 0/1 และ Quality กับผู้ดูแลแล้ว');self.confirmed.set_active(owner.settings.get('mappingConfirmed') is True);self.csv_box.append(self.confirmed)
  self.error=label('','error');body.append(self.error);body.append(label('บันทึกการตั้งค่าอย่างเดียว ยังไม่อ่านค่า ไม่เริ่มส่ง และไม่แก้ WinCC/PLC','caption'))
  row=box(spacing=12);row.append(button('ยกเลิก',lambda _:self.close()));self.save_button=button('บันทึกการตั้งค่า',self.save,'primary');row.append(self.save_button);body.append(row)
  self.mode.connect('notify::selected',lambda *_:self.update());self.update();self.connect('close-request',lambda _:self.released())
 def released(self):self.owner.source_editor=None;return False
 def update(self):
  selected=self.mode.get_selected();self.csv_box.set_visible(selected==1)
  self.description.set_text(['ยังไม่มี OPC UA ที่เปิดใช้งานตามข้อมูลผู้ใช้ โปรแกรมจึงยังอ่าน WinCC Runtime โดยตรงไม่ได้ ต้องตกลงช่องทางอ่านกับผู้ดูแลก่อน AQUA จะไม่เปิดบริการ แก้โครงการ หรือใช้ LAB แทนเอง','อ่านเฉพาะไฟล์ที่มีค่าปัจจุบันส่งออกมาแล้ว รายชื่อ Tag อย่างเดียวไม่ใช่ Runtime','โหมดทดสอบเท่านั้น ใช้ Tag จำลองและเครื่องรับจำลองในเครื่องเดียว ไม่มีการเข้าถึง WinCC หรือ Internet จริง'][selected])
 def pick_folder(self,_):
  def done(picker,result):
   try:self.chosen['directory']=picker.select_folder_finish(result).get_path();self.path_label.set_text(self.chosen['directory'] or 'ต้องเลือกโฟลเดอร์ในเครื่อง')
   except GLib.Error:pass
  Gtk.FileDialog(title='เลือกโฟลเดอร์ Runtime CSV ที่อนุญาตให้อ่าน').select_folder(self,None,done)
 def pick_tags(self,_):
  def done(picker,result):
   try:self.chosen['tags']=read_tag_names(picker.open_finish(result).get_path());self.tags_label.set_text(f"Tag สถานะ: {len(self.chosen['tags'])} รายการ");self.error.set_text('')
   except GLib.Error:pass
   except (OSError,ValueError,UnicodeError,TypeError) as e:self.error.set_text(str(e))
  Gtk.FileDialog(title='เลือกไฟล์รายชื่อ Tag ที่อนุญาตให้อ่าน').open(self,None,done)
 def save(self,_):
  mode=['runtime','csv','lab'][self.mode.get_selected()];settings={}
  try:
   if mode=='csv':
    directory=self.chosen['directory']
    if not directory or not pathlib.Path(directory).is_dir():raise ValueError('กรุณาเลือกโฟลเดอร์ Runtime CSV ในเครื่อง')
    valid_tags(self.chosen['tags']);owned_directory(self.owner.state_root,directory)
    settings={'sourceDirectory':str(pathlib.Path(directory).resolve()),'tags':self.chosen['tags'],'timezoneOffset':['+07:00','+00:00'][self.timezone.get_selected()],'mappingConfirmed':self.confirmed.get_active()}
   root=owned_directory(self.owner.state_root,settings.get('sourceDirectory'));root.mkdir(parents=True,exist_ok=True,mode=0o700);atomic_json(root/'preferences.json',{'version':2,'mode':mode,'source':settings})
  except (OSError,ValueError,TypeError) as e:self.error.set_text(str(e));return
  owner=self.owner;owner.settings=settings;owner.source_mode=mode;owner.book=ConsentBook(owner.state_root,settings.get('sourceDirectory'));owner.last_export=None;owner.source_editor=None;owner.render({});owner.message.set_text('บันทึกการตั้งค่าแล้ว — ยังไม่เริ่มอ่านหรือส่ง');self.destroy()
class AquaWindow(Gtk.ApplicationWindow):
 def __init__(self,app,state_root,port):
  super().__init__(application=app,title='AQUA COMMAND');self.set_default_size(1320,820);self.set_size_request(1050,650)
  self.state_root=pathlib.Path(state_root);self.port=port;self.client=None;self.status={};self.pending={};self.tag_widgets={};self.last_export=None;self.closing=False;self.switching=False;self.generation=0;self.consent_dialog=None;self.source_editor=None;self.capture_requested=False;self.source_mode='runtime';self.settings={}
  try:
   with (self.state_root/'preferences.json').open('rb') as f:raw=f.read(32769)
   p=json.loads(raw) if len(raw)<=32768 else {}
   if p.get('version')==2 and p.get('mode') in ('runtime','csv','lab') and isinstance(p.get('source'),dict):self.source_mode=p['mode'];self.settings=p['source']
   elif p.get('sourceDirectory'):self.source_mode='csv';self.settings=p
  except (ValueError,OSError,AttributeError):pass
  self.book=ConsentBook(self.state_root,self.settings.get('sourceDirectory'))
  css=Gtk.CssProvider();css.load_from_path(str(ROOT/'desktop/style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
  header=Gtk.HeaderBar();brand=label('AQUA COMMAND','brand');brand.set_wrap(False);header.set_title_widget(brand);header.pack_start(label('  DESKTOP  ','eyebrow'));header.pack_end(label('อ่านอย่างเดียว','readonly'));self.set_titlebar(header)
  shell=box();self.set_child(shell);side=box(True,10,'sidebar');side.set_size_request(185,-1);side.append(label('สถานีของคุณ','eyebrow'));side.append(label('เก็บค่าปั๊ม\nส่งต่ออย่างมีสิทธิ์','side-title'));shell.append(side)
  self.pages=Gtk.Stack();self.pages.set_hexpand(True);self.pages.set_vexpand(True);self.pages.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
  for key,name in [('overview','ภาพรวมการทำงาน'),('values','ค่าปั๊มที่อ่านได้'),('logs','ประวัติการทำงาน'),('permissions','สิทธิ์และการเชื่อมต่อ')]:side.append(button(name,lambda _,k=key:self.pages.set_visible_child_name(k),'nav'))
  spacer=box();spacer.set_vexpand(True);side.append(spacer);side.append(label('ไม่สั่งเปิด / ปิดปั๊ม\nไม่แก้ WinCC / PLC','caption'));side.append(label('Linux LAB · '+VERSION,'caption'))
  main=box(True,12,'body');main.set_hexpand(True);shell.append(main)
  title_row=box(spacing=12);title_box=box(True,4);title_box.set_hexpand(True);title_box.append(label('เก็บข้อมูลปั๊มจากต้นทาง','page-title'));title_box.append(label('เลือกแหล่งข้อมูล อนุญาตอ่าน แล้วค่อยอนุญาตส่ง','muted'));title_row.append(title_box);title_row.append(button('ตั้งค่าแหล่งข้อมูล',self.source_dialog));main.append(title_row)
  self.mode=label('','mode');main.append(self.mode);main.append(self.pages)
  overview=box(True,16,'overview');overview_scroll=Gtk.ScrolledWindow();overview_scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);overview_scroll.set_child(overview);self.pages.add_named(overview_scroll,'overview')
  flow=box(spacing=12);overview.append(flow)
  self.source_value,self.source_detail=self.flow_card(flow,'01  แหล่งข้อมูล','')
  self.store_value,self.store_detail=self.flow_card(flow,'02  เก็บไว้ในเครื่อง','ทุก 5 วินาที · คิวถาวร')
  self.dest_value,self.dest_detail=self.flow_card(flow,'03  ส่งไปเครื่องรับ','')
  controls=box(True,12,'card');overview.append(controls);self.record_state=label('','state');controls.append(self.record_state);self.observed=label('','muted');controls.append(self.observed)
  row=box(spacing=10);self.start_button=button('เริ่มอ่านทุก 5 วินาที',lambda _:self.request_capture(),'primary');self.stop_button=button('หยุดอ่าน',lambda _:self.send('recording',running=False));self.end_button=button('หยุดงานทั้งหมด',lambda _:self.end_session());row.append(self.start_button);row.append(self.stop_button);row.append(self.end_button);controls.append(row)
  self.network=label('','state');controls.append(self.network);row=box(spacing=10);self.send_button=button('อนุญาตส่งข้อมูล',lambda _:self.request_transfer());self.stop_send_button=button('หยุดส่ง',lambda _:self.send('transfer',running=False));row.append(self.send_button);row.append(self.stop_send_button);controls.append(row);self.egress=label('','caption');controls.append(self.egress)
  metrics=box(spacing=10);self.metrics={}
  for key,name in [('snapshots','ชุดค่าที่เก็บแล้ว'),('pending','ชุดข้อมูลรอส่ง'),('gateway_pending','ค้างที่เครื่องรับ'),('delivered','ปลายทางยืนยันแล้ว')]:
   tile=box(True,4,'metric');tile.set_hexpand(True);tile.append(label(name,'caption'));v=label('—','metric-value');tile.append(v);self.metrics[key]=v;metrics.append(tile)
  overview.append(metrics);self.telegram=label('','notice');overview.append(self.telegram)
  scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);self.grid=Gtk.Grid(column_spacing=24,row_spacing=8);self.grid.add_css_class('tag-grid');scroll.set_child(self.grid);self.pages.add_named(scroll,'values')
  logs=Gtk.ScrolledWindow();self.log_view=Gtk.TextView(editable=False,cursor_visible=False,wrap_mode=Gtk.WrapMode.WORD_CHAR);logs.set_child(self.log_view);self.pages.add_named(logs,'logs')
  permissions=box(True,16,'card');permissions.append(label('คุณควบคุมการเริ่มงาน','card-title'));self.permission_status=label('','review-details');permissions.append(self.permission_status);permissions.append(label('เปิดโปรแกรม: ไม่อ่าน ไม่สร้างข้อมูล ไม่ตรวจเครือข่าย และไม่ส่งเอง\nเริ่มอ่าน: ยินยอมครั้งเดียวต่อการเริ่มงาน อ่านต่อเนื่องทุก 5 วินาที\nเริ่มส่ง: ต้องอนุญาตแยกจากการอ่าน\nไม่ถามซ้ำ: จำเฉพาะชุดข้อมูลและปลายทางนี้ แต่ยังต้องกดเริ่มเอง\nเปลี่ยนแหล่งข้อมูลหรือปลายทาง: ขออนุญาตใหม่','muted'));permissions.append(button('ถอนสิทธิ์ทั้งหมดและหยุดงาน',self.revoke_permissions,'danger'));self.pages.add_named(permissions,'permissions')
  footer=box(spacing=12);self.message=label('ยังไม่มีงานทำงานอยู่ เลือกแหล่งข้อมูลเพื่อเริ่ม','caption');self.message.set_hexpand(True);footer.append(self.message);self.export_button=button('บันทึก CSV ล่าสุด',lambda _:self.send('export_csv'));self.folder_button=button('เปิดโฟลเดอร์',self.open_exports);footer.append(self.export_button);footer.append(self.folder_button);main.append(footer)
  self.connect('close-request',self.on_close);self.render({})
 def flow_card(self,parent,title,value):
  card=box(True,8,'flow-card');card.set_hexpand(True);card.append(label(title,'eyebrow'));v=label(value,'card-title');v.set_max_width_chars(28);card.append(v);detail=label('','caption');detail.set_max_width_chars(32);detail.set_selectable(True);card.append(detail);parent.append(card);return v,detail
 def scopes(self):
  capture=scope_key({'mode':self.source_mode,'settings':self.settings,'interval':5,'readOnly':True,'state':str(self.state_root.absolute())})
  transfer=scope_key({'capture':capture,'gateway':f'http://127.0.0.1:{self.port+1}','gatewayId':'PC-04','central':f'http://127.0.0.1:{self.port+2}','telegram':'dry-run'})
  return capture,transfer
 def consent(self,action,details,callback):
  if self.consent_dialog or self.closing or self.switching:return
  scope=self.scopes()[0 if action=='capture' else 1]
  def accept(remember):
   if remember:
    try:self.book.remember(action,scope)
    except (OSError,ValueError) as e:self.show_error(str(e));return
   callback()
  if self.book.approved(action,scope):callback();return
  self.consent_dialog=ConsentDialog(self,action,details,accept);self.consent_dialog.present()
 def request_capture(self):
  if self.source_mode=='runtime':self.message.set_text('ยังไม่มีช่องทางอ่าน WinCC Runtime ที่ได้รับอนุญาต กรุณาตกลงกับผู้ดูแลก่อน');return
  source=self.settings.get('sourceDirectory') if self.source_mode=='csv' else 'Tag จำลองในเครื่องนี้ (LAB)'
  tags=self.settings.get('tags',[]) if self.source_mode=='csv' else [f'LAB_PUMP_{i:02}.RUN_S' for i in range(1,6)]
  details=f"ต้นทาง: {source}\nอ่านอย่างเดียวทุก 5 วินาที จนกว่าจะหยุด\nเก็บใน: {self.state_root}\nการส่งข้อมูล: ยังไม่อนุญาต\nTag: {len(tags)} รายการ\n"+'\n'.join(tags)
  self.consent('capture',details,self.begin_capture)
 def begin_capture(self):
  if self.client:self.send('recording',running=True,approved=True);return
  self.capture_requested=True;self.start_backend()
 def request_transfer(self):
  if not self.client:return
  details=f"ต้นทาง: {self.settings.get('sourceDirectory','Tag จำลอง LAB ในเครื่องนี้')}\nข้อมูล: ค่าปั๊ม เวลา และคุณภาพข้อมูลในคิว\nเครื่องรับ: PC-04 ในเครื่องนี้ · 127.0.0.1:{self.port+1}\nปลายทางถัดไป: CENTRAL-LAB · 127.0.0.1:{self.port+2}\nส่งคิวเก่าและข้อมูลใหม่จนกว่าจะหยุด\nTelegram: ทดสอบเท่านั้น ไม่ส่งข้อความจริง\nการทดสอบนี้ยังไม่ใช่การส่งข้ามเครื่อง LAN"
  self.consent('transfer',details,lambda:self.send('transfer',running=True,approved=True))
 def start_backend(self):
  if self.closing or self.switching or self.source_mode=='runtime':return
  try:
   if self.source_mode=='csv':
    if not self.settings.get('sourceDirectory'):raise ValueError('ยังไม่ได้เลือกโฟลเดอร์ Runtime CSV — จะไม่ใช้ข้อมูล LAB แทน')
    valid_tags(self.settings.get('tags'))
   self.profile=prepare_profile(self.state_root,self.settings if self.source_mode=='csv' else {});self.generation+=1;generation=self.generation;self.client=BackendClient(ROOT,self.profile,lambda m:GLib.idle_add(self.on_backend,m,generation),self.port);self.message.set_text('กำลังเริ่มตามสิทธิ์ที่อนุญาต — การส่งยังปิดอยู่');self.start_button.set_sensitive(False)
  except (ValueError,OSError,RuntimeError,TypeError) as e:self.capture_requested=False;self.show_error(str(e))
 def on_backend(self,m,generation):
  if self.closing or self.switching or generation!=self.generation:return False
  if m.get('type') in ('ready','status'):
   self.render(m.get('data',{}))
   if m.get('type')=='ready' and self.capture_requested:self.capture_requested=False;self.send('recording',running=True,approved=True)
  elif m.get('type')=='error':self.show_error(m.get('message','ส่วนเก็บข้อมูลหยุดทำงาน'))
  elif 'id' in m:
   command=self.pending.pop(m['id'],None)
   if not m.get('ok'):self.show_error(m.get('error',{}).get('message','ทำรายการไม่ได้'));return False
   result=m.get('result',{})
   if 'agents' in result:self.render(result)
   elif command=='export_csv':
    file=pathlib.Path(result['path']).resolve()
    if file.parent!=(self.profile['data']/'exports').resolve():self.show_error('ตำแหน่งไฟล์ไม่อยู่ในที่เก็บ AQUA');return False
    self.last_export=file;self.folder_button.set_sensitive(True);self.message.set_text(f"บันทึก CSV ล่าสุด {result.get('rows',0)} แถว"+(' — มีเพียงบางส่วนของคิว' if result.get('truncated') else ''))
  return False
 def send(self,command,**values):
  if not self.client:return
  try:
   key=self.client.request(command,**values);self.pending[key]=command
   if command=='recording':self.start_button.set_sensitive(False);self.stop_button.set_sensitive(False)
   if command=='transfer':self.send_button.set_sensitive(False);self.stop_send_button.set_sensitive(False)
  except (OSError,RuntimeError) as e:self.show_error(str(e))
 def render(self,status):
  self.status=status;v=present_status(status);active=self.client is not None and not self.switching;capturing=status.get('captureAllowed') is True;sending=status.get('transferAllowed') is True
  mode_names={'runtime':'WinCC Runtime จริง','csv':'ไฟล์ Runtime CSV','lab':'LAB · ข้อมูลจำลอง'}
  self.source_value.set_text(mode_names[self.source_mode]);self.source_detail.set_text('ยังไม่มีช่องทางอ่านที่ได้รับอนุญาต' if self.source_mode=='runtime' else self.settings.get('sourceDirectory','ข้อมูลทดสอบในเครื่อง'))
  self.store_value.set_text('ทุก 5 วินาที · อ่านอย่างเดียว');self.store_detail.set_text(str(getattr(self,'profile',{}).get('data',self.state_root/'profiles')))
  self.dest_value.set_text('เครื่องรับ LAB ในเครื่องนี้');self.dest_detail.set_text(f"PC-04 · 127.0.0.1:{self.port+1}\nTelegram: ทดสอบ ไม่ส่งจริง")
  self.mode.set_text('ยังไม่พร้อมอ่าน WinCC Runtime — ไม่มี OPC UA ที่เปิดใช้งานและยังไม่ได้ตกลงช่องทางอื่น' if self.source_mode=='runtime' else 'LAB ที่เลือกเอง · ไม่เชื่อม WinCC / PLC และไม่มี Internet จริง' if self.source_mode=='lab' else 'ไฟล์ CSV ที่เลือกเอง · ไม่ใช่การอ่าน WinCC โดยตรง')
  self.record_state.set_text(v['recording'] if active and capturing else 'รออนุญาต / หยุดอ่านอยู่')
  self.observed.set_text('ข้อมูลต้นทางล่าสุด: '+v['observed'] if active else 'ยังไม่ได้อ่านข้อมูลต้นทางในครั้งนี้')
  self.start_button.set_sensitive(not self.closing and not self.switching and self.source_mode!='runtime' and not capturing and not self.capture_requested)
  self.stop_button.set_sensitive(active and capturing);self.end_button.set_sensitive(active);self.send_button.set_sensitive(active and not sending and (status.get('snapshots') or 0)>0);self.stop_send_button.set_sensitive(active and sending)
  self.network.set_text('การส่ง: อนุญาตแล้ว · '+v['network'] if sending else 'การส่ง: ยังไม่อนุญาต — เก็บคิวไว้ในเครื่อง')
  self.egress.set_text('ส่งเฉพาะเครื่องรับทดสอบที่แสดงด้านบน ไม่มีการสแกน LAN' if sending else 'ยังไม่ตรวจ Internet หรือส่งข้อมูลไปเครื่องรับ')
  self.telegram.set_text('โหมด LAB: ตัวเลข “ปลายทางยืนยันแล้ว” หมายถึงปลายทางจำลองในเครื่องนี้ ไม่ใช่ Telegram หรือ Internet จริง')
  self.permission_status.set_text(f"อ่านข้อมูล: {'กำลังอ่านตามสิทธิ์' if capturing else 'ปิด'}\nส่งข้อมูล: {'อนุญาตแล้ว' if sending else 'ปิด'}\nจำการอนุญาตอ่าน: {'มี เฉพาะชุดนี้' if self.book.approved('capture',self.scopes()[0]) else 'ถามก่อนเริ่ม'}\nจำการอนุญาตส่ง: {'มี เฉพาะชุดนี้' if self.book.approved('transfer',self.scopes()[1]) else 'ถามก่อนเริ่ม'}")
  for k,w in self.metrics.items():w.set_text(str(v[k]) if active and v[k] is not None else '—')
  self.export_button.set_sensitive(active and (status.get('snapshots') or 0)>0);self.folder_button.set_sensitive(self.last_export is not None)
  self.render_tags(v['rows'] if active else []);self.log_view.get_buffer().set_text(self.activities(status))
 def render_tags(self,rows):
  tags=[r['tag'] for r in rows]
  if list(self.tag_widgets)!=tags or not self.grid.get_first_child():
   self.tag_widgets={}
   while self.grid.get_first_child():self.grid.remove(self.grid.get_first_child())
   for i,name in enumerate(['ชื่อ Tag','ค่าที่อ่าน','สถานะปั๊ม','คุณภาพ']):self.grid.attach(label(name,'table-head'),i,0,1,1)
   if not rows:self.grid.attach(label('ยังไม่มีค่า — เลือกแหล่งข้อมูลและอนุญาตอ่านก่อน','muted'),0,1,4,1)
   for n,row in enumerate(rows,1):
    widgets=[]
    for i,text in enumerate([row['tag'],'','','']):
     w=label(text,'tag-cell');w.set_selectable(True)
     if i==0:w.set_hexpand(True);w.set_ellipsize(Pango.EllipsizeMode.MIDDLE);w.set_max_width_chars(36);w.set_tooltip_text(row['tag'])
     self.grid.attach(w,i,n,1,1);widgets.append(w)
    self.tag_widgets[row['tag']]=widgets
  for row in rows:
   ws=self.tag_widgets[row['tag']];ws[1].set_text('—' if row['raw'] is None else str(row['raw']));ws[2].set_text({'ON':'ทำงาน','OFF':'หยุด'}.get(row['state'],'ไม่ทราบ'));ws[3].set_text({'GOOD':'อ่านได้','BAD':'ข้อมูลไม่สมบูรณ์','UNVERIFIED_MAPPING':'ยังไม่ยืนยันความหมาย'}.get(row['quality'],row['quality']))
 def activities(self,status):
  names={'SNAPSHOT':'บันทึกค่าปั๊มลงเครื่องแล้ว','STATE_CHANGE':'พบสถานะปั๊มเปลี่ยน','DELIVERY':'เครื่องรับยืนยันได้รับข้อมูล','LAN_CONNECT':'ยืนยันตัวตนเครื่องรับแล้ว','LAN_DISCONNECT':'เครื่องรับขาดการเชื่อมต่อ','RETRY':'ยังส่งไม่ได้ เก็บข้อมูลไว้เพื่อส่งใหม่'}
  return '\n\n'.join(e.get('time','')+'  '+names.get(e.get('kind'),e.get('kind','กิจกรรม')) for e in status.get('events',[])[:30]) or 'ยังไม่เริ่มงาน จึงยังไม่มีประวัติในครั้งนี้'
 def show_error(self,message):
  self.message.set_text(message[:350]);self.start_button.set_sensitive(False);self.stop_button.set_sensitive(False);self.send_button.set_sensitive(False);self.stop_send_button.set_sensitive(False);self.export_button.set_sensitive(False)
 def open_exports(self,_):
  if self.last_export:
   try:Gio.AppInfo.launch_default_for_uri(self.last_export.parent.as_uri(),None)
   except GLib.Error:self.message.set_text(str(self.last_export.parent))
 def source_dialog(self,_):
  if self.closing or self.switching or self.source_editor or self.consent_dialog:return
  def open_editor():self.source_editor=SourceEditor(self);self.source_editor.present()
  if self.client:self.end_session(open_editor)
  else:open_editor()
 def end_session(self,after=None):
  if self.switching:return
  self.capture_requested=False;self.generation+=1;self.switching=True;old=self.client;self.client=None;self.pending.clear();self.render({});self.message.set_text('กำลังหยุดงาน รอคำขอที่เริ่มไปแล้วจบ…')
  def close():
   if old:old.close()
   def done():
    self.switching=False;self.render({});self.message.set_text('หยุดงานแล้ว ข้อมูลเดิมยังอยู่ในเครื่อง')
    if after and not self.closing:after()
    return False
   GLib.idle_add(done)
  threading.Thread(target=close,daemon=True).start()
 def revoke_permissions(self,_):
  def clear():
   try:self.book.clear();self.message.set_text('ถอนสิทธิ์แล้ว ครั้งหน้าจะถามก่อนเริ่มอ่านและส่ง');self.render({})
   except (OSError,ValueError) as e:self.show_error(str(e))
  self.end_session(clear)
 def on_close(self,_):
  if self.closing:return True
  self.closing=True;client=self.client;self.client=None;self.generation+=1
  if self.consent_dialog:self.consent_dialog.destroy()
  if self.source_editor:self.source_editor.destroy()
  def finish():
   if client:client.close()
   GLib.idle_add(self.destroy)
  threading.Thread(target=finish,daemon=True).start();return True
class AquaApplication(Gtk.Application):
 def __init__(self,state_root,port):super().__init__(application_id='org.aquacommand.Desktop',flags=Gio.ApplicationFlags.NON_UNIQUE);self.state_root=state_root;self.port=port
 def do_activate(self):
  window=self.get_active_window()
  if not window:window=AquaWindow(self,self.state_root,self.port)
  window.present()
def main():
 parser=argparse.ArgumentParser(description='AQUA operator-started read-only desktop');parser.add_argument('--version',action='version',version='AQUA COMMAND Desktop '+VERSION);parser.add_argument('--state-dir',default=str(pathlib.Path(GLib.get_user_state_dir())/'aqua-command'));parser.add_argument('--port',type=int,default=4173);args=parser.parse_args();GLib.set_application_name('AQUA COMMAND');return AquaApplication(args.state_dir,args.port).run([sys.argv[0]])
if __name__=='__main__':raise SystemExit(main())
