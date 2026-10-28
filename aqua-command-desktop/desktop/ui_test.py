"""Native widget integration test, run on an isolated GTK display; never ships in RPM."""
import argparse,json,pathlib,tempfile,time,sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
p=argparse.ArgumentParser();p.add_argument('--screenshot');p.add_argument('--port',type=int,default=17473);p.add_argument('--installed-root');args=p.parse_args()
if args.installed_root:sys.path.insert(0,str(pathlib.Path(args.installed_root)/'desktop'))
from app import AquaApplication,AquaWindow
ctx=GLib.MainContext.default()
def wait(fn,seconds=15):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  while ctx.pending():ctx.iteration(False)
  if fn():return
  time.sleep(.02)
 raise AssertionError('Native UI integration timeout')
with tempfile.TemporaryDirectory(prefix='aqua-native-ui-') as state:
 app=AquaApplication(state,args.port);app.register(None);w=AquaWindow(app,state,args.port);w.present()
 try:
  wait(lambda:w.status.get('snapshots',0)>=1 and w.status.get('delivered',0)>=1)
  assert w.client and w.client.process.poll() is None
  assert w.status['webUiEnabled'] is False and w.status['readOnly'] is True
  assert 'LAB' in w.mode.get_text();assert len(w.tag_widgets)==5
  w.stop_button.emit('clicked');wait(lambda:w.status['agents'][0]['recording'] is False);assert w.start_button.get_sensitive();assert not w.stop_button.get_sensitive()
  w.start_button.emit('clicked');wait(lambda:w.status['agents'][0]['recording'] is True)
  w.export_button.emit('clicked');wait(lambda:w.last_export is not None);assert w.last_export.read_text().startswith('recorded_at;observed_at;tag_name;')
  print(json.dumps({'nativeWidgets':'GTK4','recordingPauseResume':'PASS','csvExport':'PASS','noUiHttpListener':True,'readOnly':True,'tags':len(w.tag_widgets),'windowWidth':w.get_width(),'windowHeight':w.get_height()}),flush=True)
  if args.screenshot:
   widget=w;paintable=Gtk.WidgetPaintable.new(widget);nodes=[]
   def rendered():
    snapshot=Gtk.Snapshot();paintable.snapshot(snapshot,widget.get_width(),widget.get_height());node=snapshot.to_node()
    if node is not None:nodes.append(node);return True
    return False
   print(json.dumps({'visible':w.get_visible(),'mapped':w.get_mapped(),'childVisible':widget.get_visible(),'childMapped':widget.get_mapped(),'bodyWidth':widget.get_width(),'bodyHeight':widget.get_height()}),flush=True)
   wait(rendered,5);texture=w.get_renderer().render_texture(nodes[0],None);assert texture.save_to_png(args.screenshot);print('Native screenshot saved',flush=True)
 finally:
  process=w.client.process if w.client else None;w.close();wait(lambda:process is None or process.poll() is not None);w.destroy()
