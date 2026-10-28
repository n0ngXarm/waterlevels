"""Actual native-widget geometry/screenshots on an isolated Wayland compositor. Test only."""
import argparse,json,pathlib,tempfile,time,sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--installed-root');p.add_argument('--scale',type=float,default=1);args=p.parse_args()
if args.installed_root:sys.path.insert(0,str(pathlib.Path(args.installed_root)/'desktop'))
from app import AquaApplication,AquaWindow
from console import PAGES
ctx=GLib.MainContext.default();out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True);results=[]
def spin(t=.1):
 end=time.monotonic()+t
 while time.monotonic()<end:
  while ctx.pending():ctx.iteration(False)
  time.sleep(.01)
def wait(fn,t=15):
 end=time.monotonic()+t
 while time.monotonic()<end:
  spin(.03)
  if fn():return
 raise AssertionError('Layout integration timeout')
def snap(w,file):
 paintable=Gtk.WidgetPaintable.new(w);nodes=[]
 def frame():
  s=Gtk.Snapshot();paintable.snapshot(s,w.get_width(),w.get_height());n=s.to_node()
  if n is not None:nodes.append(n);return True
  return False
 wait(frame,5);assert w.get_renderer().render_texture(nodes[-1],None).save_to_png(str(file))
def rect(w,ancestor):
 ok,bounds=w.compute_bounds(ancestor)
 assert ok
 return [round(bounds.get_x(),1),round(bounds.get_y(),1),round(bounds.get_width(),1),round(bounds.get_height(),1)]
settings=Gtk.Settings.get_default()
if args.scale!=1:settings.set_property('gtk-xft-dpi',int(96*1024*args.scale))
app=AquaApplication(str(out/'unused-app-state'),22473);app.register(None)
for index,(width,height) in enumerate(((1366,768),(1440,900),(1600,900),(1920,1080))):
 with tempfile.TemporaryDirectory(prefix='aqua-g2-layout-') as state:
  w=AquaWindow(app,state,22473+index*100);w.set_default_size(width,height);w.set_size_request(width,height);w.present()
  try:
   wait(lambda:w.get_mapped());assert (w.get_width(),w.get_height())==(width,height),('Actual allocation mismatch',width,height,w.get_width(),w.get_height());assert w.client is None;assert list(pathlib.Path(state).iterdir())==[]
   w.source_dialog(None);w.source_editor.mode.set_selected(2);w.source_editor.save_button.emit('clicked');w.start_button.emit('clicked');w.consent_dialog.approve_button.emit('clicked');wait(lambda:w.status.get('snapshots',0)>=1)
   w.send_button.emit('clicked');w.consent_dialog.approve_button.emit('clicked');wait(lambda:w.status.get('delivered',0)>=1)
   for key,_,_ in PAGES:
    w.pages.set_visible_child_name(key);spin(.15);page=w.pages.get_visible_child();assert page.get_width()>0 and page.get_height()>0
    for component in (w.page_title,w.mode,w.pages,w.start_button,w.source_button,w.export_button):
     x,y,ww,hh=rect(component,w);assert x>=-1 and y>=-1 and x+ww<=width+1 and y+hh<=height+1,('Outside window',key,component.get_name(),[x,y,ww,hh],width,height)
    snap(w,out/f'{width}x{height}-{key}.png');results.append({'requested':[width,height],'actual':[w.get_width(),w.get_height()],'page':key,'scale':args.scale,'titlePixelHeight':w.page_title.get_layout().get_pixel_size()[1],'visiblePageSize':[page.get_width(),page.get_height()],'result':'PASS'})
   # Existing dialog remains native and fits within the smallest target monitor.
   if width==1366:
    w.source_dialog(None);wait(lambda:w.source_editor is not None);spin(.2);assert w.source_editor.get_width()<=width and w.source_editor.get_height()<=height;snap(w.source_editor,out/'source-dialog.png');w.source_editor.close()
  finally:
   proc=w.client.process if w.client else None;w.close();wait(lambda:proc is None or proc.poll() is not None);spin(.1)
(out/'layout-results.json').write_text(json.dumps(results,indent=2));print(json.dumps({'actualNativePages':len(results),'resolutions':4,'fontScale':args.scale,'result':'PASS'}),flush=True)
