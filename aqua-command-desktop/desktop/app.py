#!/usr/bin/python3
"""Native, operator-started read-only workstation. Opening it starts no workers."""
import argparse,json,pathlib,sys,threading,copy
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Pango
from client import BackendClient
from model import present_status,prepare_profile,read_tag_names,atomic_json,owned_directory,valid_tags
from consent import ConsentBook,scope_key
from console import ConsoleView,PAGES
ROOT=pathlib.Path(__file__).resolve().parents[1]
VERSION='0.8.0'
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
  self.state_root=pathlib.Path(state_root);self.port=port;self.client=None;self.status={};self.pending={};self.tag_widgets={};self.last_export=None;self.closing=False;self.switching=False;self.generation=0;self.consent_dialog=None;self.source_editor=None;self.capture_requested=False;self.host_error=False;self.presentation_timer=None;self.source_mode='runtime';self.settings={}
  try:
   with (self.state_root/'preferences.json').open('rb') as f:raw=f.read(32769)
   p=json.loads(raw) if len(raw)<=32768 else {}
   if p.get('version')==2 and p.get('mode') in ('runtime','csv','lab') and isinstance(p.get('source'),dict):self.source_mode=p['mode'];self.settings=p['source']
   elif p.get('sourceDirectory'):self.source_mode='csv';self.settings=p
  except (ValueError,OSError,AttributeError):pass
  self.book=ConsentBook(self.state_root,self.settings.get('sourceDirectory'))
  css=Gtk.CssProvider();css.load_from_path(str(ROOT/'desktop/style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
  header=Gtk.HeaderBar();brand=label('AQUA COMMAND','brand');brand.set_wrap(False);header.set_title_widget(brand);local=label('LOCAL LAB · 1 HOST','eyebrow');local.set_wrap(False);header.pack_start(local);header.pack_end(label('READ ONLY','readonly'));self.set_titlebar(header)
  shell=box();self.set_child(shell);side=box(True,6,'sidebar');side.set_size_request(232,-1);side.append(label('NETWORK + SCADA','eyebrow'));side.append(label('Operations Console','side-title'));shell.append(side)
  self.console=ConsoleView(self);self.pages=self.console.pages;header.pack_end(self.console.freeze_button);self.nav_buttons={};first=None
  for key,name,_ in PAGES:
   nav=Gtk.ToggleButton(label=name);nav.add_css_class('nav')
   if first:nav.set_group(first)
   else:first=nav
   nav.connect('toggled',lambda b,k=key:self.pages.set_visible_child_name(k) if b.get_active() else None);side.append(nav);self.nav_buttons[key]=nav
  first.set_active(True);spacer=box();spacer.set_vexpand(True);side.append(spacer);side.append(label('Configured endpoints เท่านั้น\nไม่มี NIC / Hostname inventory\nWinCC Runtime: unavailable','caption'));side.append(button('สิทธิ์ / การเชื่อมต่อ',self.permissions_dialog));side.append(label('G2 UI preview · '+VERSION,'caption'))
  main=box(True,8,'body');main.set_hexpand(True);shell.append(main);self.page_title=label('Operations Overview','page-title');main.append(self.page_title)
  self.display_status=label('','display-status');main.append(self.display_status);self.mode=label('','mode');main.append(self.mode)
  actions=Gtk.FlowBox();actions.set_selection_mode(Gtk.SelectionMode.NONE);actions.set_max_children_per_line(7);actions.set_min_children_per_line(1);actions.set_column_spacing(6);actions.set_row_spacing(6);main.append(actions)
  self.start_button=button('เริ่มอ่านทุก 5s',lambda _:self.request_capture(),'primary');self.stop_button=button('หยุดอ่าน',lambda _:self.send('recording',running=False));self.send_button=button('อนุญาตส่ง',lambda _:self.request_transfer());self.stop_send_button=button('หยุดส่ง',lambda _:self.send('transfer',running=False));self.end_button=button('หยุดงานทั้งหมด',lambda _:self.end_session());self.source_button=button('ตั้งค่าแหล่งข้อมูล',self.source_dialog)
  for b in (self.start_button,self.stop_button,self.send_button,self.stop_send_button,self.end_button,self.source_button):actions.append(b)
  main.append(self.pages);footer=box(spacing=8);self.message=label('รอผู้ใช้เลือก Source และอนุญาต — ยังไม่มีงานทำงานอยู่','caption');self.message.set_hexpand(True);self.message.set_ellipsize(Pango.EllipsizeMode.END);self.message.set_max_width_chars(80);footer.append(self.message);self.export_button=button('บันทึก CSV ล่าสุด',lambda _:self.send('export_csv'));self.folder_button=button('เปิดโฟลเดอร์',self.open_exports);footer.append(self.export_button);footer.append(self.folder_button);main.append(footer)
  self.pages.connect('notify::visible-child-name',self.page_changed);self.connect('close-request',self.on_close);self.render({});self.presentation_timer=GLib.timeout_add_seconds(1,self.refresh_presentation)
 def page_changed(self,*_):
  key=self.pages.get_visible_child_name();self.page_title.set_text(next(title for k,_,title in PAGES if k==key))
  if not self.nav_buttons[key].get_active():self.nav_buttons[key].set_active(True)
 def update_display_status(self,frozen=False):
  if not hasattr(self,'display_status'):return
  if self.host_error:self.display_status.set_text('BACKEND NOT REPORTING · ข้อมูลค้าง / CACHED · สถานะงานยังไม่ยืนยัน — กดหยุดงานทั้งหมดก่อนเริ่มใหม่')
  elif frozen:self.display_status.set_text('CACHED DISPLAY · พักภาพที่ '+self.console.last_model.get('updated','Not reported')+' · การเก็บ/ส่งยังทำงานตามสิทธิ์เดิม')
  else:self.display_status.set_text('G2 · existing-field bindings · IP แสดงเป็น configured endpoint ไม่ใช่ observed NIC · ไม่มีการสแกน')
 def permissions_dialog(self,_):
  if self.consent_dialog or self.source_editor or self.closing:return
  dialog=Gtk.Window(title='สิทธิ์และการเชื่อมต่อ',transient_for=self,modal=True);dialog.set_default_size(640,500);body=box(True,14,'dialog-body');dialog.set_child(body);body.append(label('คุณควบคุมการเริ่มงาน','page-title'))
  body.append(label('เปิดโปรแกรมใหม่: ไม่อ่าน ไม่สร้างคิว ไม่ probe และไม่ส่งเอง\nอนุญาตอ่าน: ต่อเนื่องทุก5s จนหยุด\nอนุญาตส่ง: แยกจากสิทธิ์อ่าน\nไม่ถามซ้ำ: จำเฉพาะ scope เดิม แต่ต้องกดเริ่มเอง\nถอนสิทธิ์: หยุดงาน คิวเดิมยังอยู่','detail-copy'))
  scope=self.scopes();body.append(label('จำสิทธิ์อ่านชุดนี้: '+('มี' if self.book.approved('capture',scope[0]) else 'ไม่มี')+'\nจำสิทธิ์ส่งชุดนี้: '+('มี' if self.book.approved('transfer',scope[1]) else 'ไม่มี'),'notice'))
  def revoke(_):dialog.destroy();self.revoke_permissions(None)
  body.append(button('ถอนสิทธิ์ทั้งหมดและหยุดงาน',revoke,'danger'));body.append(button('ปิด',lambda _:dialog.close()));dialog.present()
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
   self.host_error=False
   self.profile=prepare_profile(self.state_root,self.settings if self.source_mode=='csv' else {});self.generation+=1;generation=self.generation;self.client=BackendClient(ROOT,self.profile,lambda m:GLib.idle_add(self.on_backend,m,generation),self.port);self.message.set_text('กำลังเริ่มตามสิทธิ์ที่อนุญาต — การส่งยังปิดอยู่');self.start_button.set_sensitive(False)
  except (ValueError,OSError,RuntimeError,TypeError) as e:self.capture_requested=False;self.show_error(str(e))
 def on_backend(self,m,generation):
  if not isinstance(m,dict):self.host_error=True;self.show_error('Host message invalid');return False
  if self.closing or self.switching or generation!=self.generation:return False
  if m.get('type') in ('ready','status'):
   self.host_error=False;self.render(m.get('data',{}))
   if m.get('type')=='ready' and self.capture_requested:self.capture_requested=False;self.send('recording',running=True,approved=True)
  elif m.get('type')=='error':self.host_error=True;self.refresh_presentation();self.show_error(m.get('message','ส่วนเก็บข้อมูลหยุดทำงาน'))
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
 def refresh_presentation(self):
  if self.closing:return False
  if self.client and self.client.process.poll() is not None:self.host_error=True
  self.render(self.status)
  return True
 def render(self,status):
  status=status if isinstance(status,dict) else {};self.status=status;shown=copy.deepcopy(status)
  if self.host_error:
   shown['captureAllowed']=False;shown['transferAllowed']=False
   for role in [*(shown.get('agents') or []),shown.get('gateway'),shown.get('central')]:
    if isinstance(role,dict):role['online']=False
  records=status.get('snapshots');has_records=isinstance(records,(int,float)) and not isinstance(records,bool) and records>0
  active=self.client is not None and not self.switching;capturing=shown.get('captureAllowed') is True and active;sending=shown.get('transferAllowed') is True and active
  self.console.update(shown,self.source_mode,self.settings,self.port,active);self.update_display_status(self.console.frozen)
  mode={'runtime':'UNAVAILABLE — ยังไม่มี WinCC Runtime connector ที่อนุญาต','csv':'FILE — CSV ที่ผู้ใช้เลือก ไม่ใช่การยืนยัน Live WinCC','lab':'SIMULATED — LAB ที่เลือกเอง / ไม่เชื่อม PLC หรือ WinCC'}[self.source_mode]
  self.mode.set_text(mode+' · Data: '+','.join(self.console.latest.get('reading_modes',[]))+(' · สถานะอ่าน/ส่ง: ไม่ทราบ (Backend ไม่รายงาน)' if self.host_error else ' · อ่าน: '+('อนุญาต' if capturing else 'หยุด/รอสิทธิ์')+' · ส่ง: '+('อนุญาต' if sending else 'หยุด/รอสิทธิ์')))
  self.start_button.set_sensitive(not self.closing and not self.switching and self.source_mode!='runtime' and not capturing and not self.capture_requested and not self.host_error);self.stop_button.set_sensitive(capturing);self.end_button.set_sensitive(active);self.send_button.set_sensitive(active and not self.host_error and not sending and has_records);self.stop_send_button.set_sensitive(sending);self.export_button.set_sensitive(active and not self.host_error and has_records);self.folder_button.set_sensitive(self.last_export is not None)
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
    self.switching=False;self.host_error=False;self.render({});self.message.set_text('หยุดงานแล้ว ข้อมูลเดิมยังอยู่ในเครื่อง')
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
  self.closing=True
  if self.presentation_timer:GLib.source_remove(self.presentation_timer);self.presentation_timer=None
  client=self.client;self.client=None;self.generation+=1
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
