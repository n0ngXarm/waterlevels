#!/usr/bin/python3
"""Native GTK4 AQUA frontend. No HTML, webview, browser or HTTP UI listener."""
import argparse,json,pathlib,sys,threading
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Pango
from client import BackendClient
from model import present_status,prepare_profile,read_tag_names,atomic_json,owned_directory
ROOT=pathlib.Path(__file__).resolve().parents[1]
def label(text='',css=None,x=0):
 w=Gtk.Label(label=text,xalign=x);w.set_wrap(True)
 if css:w.add_css_class(css)
 return w
def box(vertical=False,spacing=0,css=None):
 w=Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
 if css:w.add_css_class(css)
 return w
class AquaWindow(Gtk.ApplicationWindow):
 def __init__(self,app,state_root,port):
  super().__init__(application=app,title='AQUA COMMAND');self.set_default_size(1160,730);self.set_size_request(950,640);self.state_root=pathlib.Path(state_root);self.port=port;self.client=None;self.status={};self.pending={};self.tag_widgets={};self.last_export=None;self.closing=False;self.switching=False;self.generation=0
  self.settings={}
  try:
   pref=self.state_root/'preferences.json'
   if pref.exists():self.settings=json.loads(pref.read_text(encoding='utf-8'))
  except (ValueError,OSError):pass
  css=Gtk.CssProvider();css.load_from_path(str(ROOT/'desktop/style.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
  header=Gtk.HeaderBar();title=box(spacing=10);title.append(Gtk.Image.new_from_icon_name('folder-download-symbolic'));title.append(label('AQUA COMMAND','brand'));header.set_title_widget(title);header.pack_end(label('  READ ONLY  ','readonly'));self.set_titlebar(header)
  root=box(True,12,'body');self.set_child(root)
  top=box(spacing=16);intro=box(True,4);intro.set_hexpand(True);intro.append(label('เก็บข้อมูลในเครื่อง ส่งต่อเมื่อเครื่องพร้อม','page-title'));intro.append(label('Desktop · อ่านค่าเท่านั้น ไม่สั่งงานWinCCหรือPLC','muted'));top.append(intro);source=Gtk.Button(label='ตั้งค่าแหล่งข้อมูล');source.connect('clicked',self.source_dialog);top.append(source);root.append(top)
  self.mode=label('กำลังเปิดส่วนเก็บข้อมูล…','mode');root.append(self.mode)
  cards=box(spacing=18);root.append(cards)
  capture=box(True,12,'card');capture.set_hexpand(True);capture.append(label('01   เก็บข้อมูลทุก5วินาที','card-title'));self.record_state=label('กำลังเชื่อมต่อ…','state');capture.append(self.record_state)
  actions=box(spacing=10);self.start_button=Gtk.Button(label='เริ่มเก็บ');self.start_button.add_css_class('primary');self.start_button.connect('clicked',lambda _:self.send('recording',running=True));self.stop_button=Gtk.Button(label='หยุดเก็บ');self.stop_button.connect('clicked',lambda _:self.send('recording',running=False));actions.append(self.start_button);actions.append(self.stop_button);capture.append(actions);self.observed=label('ข้อมูลต้นทางล่าสุด —','muted');capture.append(self.observed);capture.append(label('ปุ่มนี้ควบคุมเฉพาะการเก็บข้อมูลของAQUA','caption'));cards.append(capture)
  forward=box(True,12,'card');forward.set_hexpand(True);forward.append(label('02   ส่งผ่านGatewayที่ลงทะเบียน','card-title'));self.network=label('กำลังตรวจเครื่องพร้อมรับ…','state');forward.append(self.network);self.egress=label('เก็บรอได้เมื่อยังส่งต่อไม่ได้','muted');forward.append(self.egress);self.telegram=label('Telegram · DRY-RUN','caption');forward.append(self.telegram);forward.append(label('ไม่มีการสแกนเครื่องอื่นในวงแลน','caption'));cards.append(forward)
  metrics=box(spacing=14);self.metrics={}
  for key,name in [('snapshots','เก็บแล้ว'),('pending','รอส่งจากเครื่องนี้'),('gateway_pending','รอส่งที่Gateway'),('delivered','ถึงปลายทางแล้ว')]:
   tile=box(True,3,'metric');tile.set_hexpand(True);tile.append(label(name,'caption'));value=label('—','metric-value');tile.append(value);metrics.append(tile);self.metrics[key]=value
  root.append(metrics)
  self.stack=Gtk.Stack();self.stack.set_vexpand(True);self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE);switcher=Gtk.StackSwitcher(stack=self.stack);root.append(switcher)
  scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);self.grid=Gtk.Grid(column_spacing=24,row_spacing=8);self.grid.add_css_class('tag-grid');scroll.set_child(self.grid);self.stack.add_titled(scroll,'values','ค่าที่อ่าน · อ่านอย่างเดียว')
  logs=Gtk.ScrolledWindow();self.log_view=Gtk.TextView(editable=False,cursor_visible=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR);logs.set_child(self.log_view);self.stack.add_titled(logs,'logs','บันทึกการทำงาน');root.append(self.stack)
  footer=box(spacing=12);self.message=label('ทดสอบบนLinux · ยังไม่ตรวจรับกับWinCC/Windowsจริง','caption');self.message.set_hexpand(True);footer.append(self.message);self.export_button=Gtk.Button(label='บันทึกไฟล์ CSV');self.export_button.connect('clicked',lambda _:self.send('export_csv'));footer.append(self.export_button);self.folder_button=Gtk.Button(label='เปิดโฟลเดอร์');self.folder_button.set_sensitive(False);self.folder_button.connect('clicked',self.open_exports);footer.append(self.folder_button);root.append(footer)
  self.start_button.set_sensitive(False);self.stop_button.set_sensitive(False);self.export_button.set_sensitive(False);self.connect('close-request',self.on_close);GLib.idle_add(self.start_backend)
 def start_backend(self):
  if self.closing:return False
  try:
   self.profile=prepare_profile(self.state_root,self.settings);self.generation+=1;generation=self.generation;self.client=BackendClient(ROOT,self.profile,lambda m:GLib.idle_add(self.on_backend,m,generation),self.port)
  except (ValueError,OSError,RuntimeError) as e:self.show_error(str(e))
  return False
 def on_backend(self,m,generation=None):
  if self.closing or self.switching or generation is not None and generation!=self.generation:return False
  if m.get('type') in ('ready','status'):self.render(m.get('data',{}))
  elif m.get('type')=='error':self.show_error(m.get('message','ส่วนเก็บข้อมูลหยุดทำงาน'))
  elif 'id' in m:
   command=self.pending.pop(m['id'],None)
   if m.get('ok'):
    result=m.get('result',{})
    if 'agents' in result:self.render(result)
    elif command=='export_csv':
     file=pathlib.Path(result['path']).resolve();allowed=(self.profile['data']/'exports').resolve()
     if file.parent!=allowed:self.show_error('ตำแหน่งไฟล์ไม่อยู่ในที่เก็บAQUA');return False
     self.last_export=file;self.folder_button.set_sensitive(True);self.message.set_text(f"บันทึกCSVล่าสุด · {result.get('rows',0)}แถว"+(' · ไฟล์นี้มีข้อมูลเพียงบางส่วนของคิว' if result.get('truncated') else ''))
   else:self.show_error(m.get('error',{}).get('message','ทำรายการไม่ได้ กรุณาตรวจสิทธิ์ไฟล์และคิว'))
  return False
 def send(self,command,**values):
  if not self.client:return
  try:
   key=self.client.request(command,**values);self.pending[key]=command
   if command=='recording':self.start_button.set_sensitive(False);self.stop_button.set_sensitive(False)
  except (OSError,RuntimeError) as e:self.show_error(str(e))
 def render(self,status):
  self.status=status;v=present_status(status);self.mode.set_text(v['mode']);self.record_state.set_text(v['recording']);self.start_button.set_sensitive(v['online'] and not v['running']);self.stop_button.set_sensitive(v['online'] and v['running']);self.export_button.set_sensitive(v['online'] and (v['snapshots'] or 0)>0);self.observed.set_text('ข้อมูลต้นทางล่าสุด '+v['observed']);self.network.set_text(v['network']);self.egress.set_text(v['egress']);self.telegram.set_text(f"Telegram · {'DRY-RUN' if v['notification_mode']=='dry-run' else v['notification_mode']} · แจ้งเตือนแล้ว {v['notifications'] or 0}รายการ")
  for k,w in self.metrics.items():w.set_text(str(v[k]) if v[k] is not None else '—')
  tags=[r['tag'] for r in v['rows']]
  if list(self.tag_widgets)!=tags:
   self.tag_widgets={}
   while self.grid.get_first_child():self.grid.remove(self.grid.get_first_child())
   for i,name in enumerate(['TAG','ค่าดิบ','สถานะ','QUALITY']):self.grid.attach(label(name,'table-head'),i,0,1,1)
   for row,n in zip(v['rows'],range(1,len(v['rows'])+1)):
    widgets=[]
    for i,text in enumerate([row['tag'],'','','']):
     w=label(text,'tag-cell');w.set_selectable(True)
     if i==0:w.set_hexpand(True);w.set_ellipsize(Pango.EllipsizeMode.MIDDLE);w.set_max_width_chars(36);w.set_tooltip_text(row['tag'])
     self.grid.attach(w,i,n,1,1);widgets.append(w)
    self.tag_widgets[row['tag']]=widgets
  for row in v['rows']:
   ws=self.tag_widgets[row['tag']];ws[1].set_text('—' if row['raw'] is None else str(row['raw']));ws[2].set_text(row['state']);ws[3].set_text(f"{row['quality']} · {row['quality_code'] if row['quality_code'] is not None else '—'}")
  self.log_view.get_buffer().set_text(v['logs'])
  if v['error']:self.message.set_text('รอข้อมูลที่อ่านได้ · '+v['error'])
 def show_error(self,message):
  self.message.set_text(message[:350]);self.record_state.set_text('ยังไม่พร้อมเก็บข้อมูล');self.start_button.set_sensitive(False);self.stop_button.set_sensitive(False);self.export_button.set_sensitive(False)
 def open_exports(self,_):
  if self.last_export:
   try:Gio.AppInfo.launch_default_for_uri(self.last_export.parent.as_uri(),None)
   except GLib.Error:self.message.set_text(str(self.last_export.parent))
 def source_dialog(self,_):
  if self.closing or self.switching:return
  dialog=Gtk.Window(title='แหล่งข้อมูล · อ่านอย่างเดียว',transient_for=self,modal=True);dialog.set_default_size(640,490);body=box(True,14,'body');dialog.set_child(body)
  body.append(label('เลือกไฟล์ที่อนุญาตให้AQUAอ่าน','card-title'));external=Gtk.CheckButton(label='อ่านไฟล์RuntimeCSVที่ส่งออกแล้ว');external.set_active(bool(self.settings.get('sourceDirectory')));body.append(external)
  path_label=label(self.settings.get('sourceDirectory') or 'ยังไม่ได้เลือกโฟลเดอร์','muted');path_label.set_selectable(True);body.append(path_label);folder=Gtk.Button(label='เลือกโฟลเดอร์ CSV');body.append(folder)
  chosen={'directory':self.settings.get('sourceDirectory'),'tags':self.settings.get('tags',[])};tags_label=label(f"มีรายชื่อTag {len(chosen['tags'])}รายการ",'muted');tags_button=Gtk.Button(label='เลือกไฟล์รายชื่อTag / Export all.txt');body.append(tags_button);body.append(tags_label)
  timezone=Gtk.DropDown.new_from_strings(['+07:00','+00:00']);timezone.set_selected(1 if self.settings.get('timezoneOffset')=='+00:00' else 0);row=box(spacing=12);row.append(label('เขตเวลาของไฟล์'));row.append(timezone);body.append(row)
  confirmed=Gtk.CheckButton(label='ยืนยันความหมาย0/1และQualityกับLABแล้ว');confirmed.set_active(self.settings.get('mappingConfirmed') is True);body.append(confirmed);body.append(label('ไม่เลือกโหมดไฟล์ = ข้อมูลตัวอย่างบนLinux\nการเปลี่ยนแหล่งข้อมูลเก็บโปรไฟล์และคิวเดิมไว้ ไม่ลบไฟล์ต้นทาง','caption'))
  error=label('','error');body.append(error)
  def picked_folder(picker,result):
   try:chosen['directory']=picker.select_folder_finish(result).get_path();path_label.set_text(chosen['directory'])
   except GLib.Error:pass
  def picked_tags(picker,result):
   try:chosen['tags']=read_tag_names(picker.open_finish(result).get_path());tags_label.set_text(f"พบTagสถานะ {len(chosen['tags'])}รายการ");error.set_text('')
   except GLib.Error:pass
   except (OSError,ValueError,UnicodeError) as e:error.set_text(str(e))
  folder.connect('clicked',lambda _:Gtk.FileDialog(title='เลือกโฟลเดอร์RuntimeCSV').select_folder(dialog,None,picked_folder));tags_button.connect('clicked',lambda _:Gtk.FileDialog(title='เลือกไฟล์รายชื่อTag').open(dialog,None,picked_tags))
  save=Gtk.Button(label='บันทึกและเริ่มอ่าน');save.add_css_class('primary');body.append(save)
  def apply(_):
   if external.get_active() and not chosen['directory']:error.set_text('กรุณาเลือกโฟลเดอร์RuntimeCSVก่อน');return
   settings={'sourceDirectory':chosen['directory'],'tags':chosen['tags'],'timezoneOffset':['+07:00','+00:00'][timezone.get_selected()],'mappingConfirmed':confirmed.get_active()} if external.get_active() else {}
   try:prepare_profile(self.state_root,settings);atomic_json(self.state_root/'preferences.json',settings)
   except (ValueError,OSError,TypeError) as e:error.set_text(str(e));return
   self.switching=True;self.settings=settings;self.record_state.set_text('กำลังเปลี่ยนแหล่งข้อมูล…');old=self.client;self.client=None;self.pending.clear();self.generation+=1;self.last_export=None;self.folder_button.set_sensitive(False);self.render({});self.record_state.set_text('กำลังเปลี่ยนแหล่งข้อมูล…');dialog.destroy()
   def replace():
    if old:old.close()
    def restart():self.switching=False;self.start_backend();return False
    GLib.idle_add(restart)
   threading.Thread(target=replace,daemon=True).start()
  save.connect('clicked',apply);dialog.present()
 def on_close(self,_):
  if self.closing:return True
  self.closing=True;self.record_state.set_text('กำลังปิดและเก็บคิว…');client=self.client
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
 parser=argparse.ArgumentParser(description='AQUA native read-only desktop');parser.add_argument('--version',action='version',version='AQUA COMMAND Desktop 0.6.0');parser.add_argument('--state-dir',default=str(pathlib.Path(GLib.get_user_state_dir())/'aqua-command'));parser.add_argument('--port',type=int,default=4173);args=parser.parse_args()
 GLib.set_application_name('AQUA COMMAND');app=AquaApplication(args.state_dir,args.port);return app.run([sys.argv[0]])
if __name__=='__main__':raise SystemExit(main())
