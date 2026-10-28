"""Exercise native consent controls against real private LAB processes; never shipped."""
import argparse,json,pathlib,tempfile,time,sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
p=argparse.ArgumentParser();p.add_argument('--screenshot');p.add_argument('--screenshot-idle');p.add_argument('--screenshot-consent');p.add_argument('--port',type=int,default=17473);p.add_argument('--installed-root');args=p.parse_args()
if args.installed_root:sys.path.insert(0,str(pathlib.Path(args.installed_root)/'desktop'))
from app import AquaApplication,AquaWindow
ctx=GLib.MainContext.default()
def spin(seconds=.3):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  while ctx.pending():ctx.iteration(False)
  time.sleep(.02)
def wait(fn,seconds=15):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  spin(.02)
  if fn():return
 raise AssertionError('Native integration timeout')
def screenshot(w,file):
 if not file:return
 paintable=Gtk.WidgetPaintable.new(w);nodes=[]
 def rendered():
  s=Gtk.Snapshot();paintable.snapshot(s,w.get_width(),w.get_height());n=s.to_node()
  if n is not None:nodes.append(n);return True
  return False
 wait(rendered,5);assert w.get_renderer().render_texture(nodes[0],None).save_to_png(file)
with tempfile.TemporaryDirectory(prefix='aqua-native-consent-') as state:
 app=AquaApplication(state,args.port);app.register(None);w=AquaWindow(app,state,args.port);w.present()
 try:
  spin(.8);assert w.pages.get_pages().get_n_items()==7,'G2 has seven native pages';assert w.client is None,'Opening window must not start a backend';assert list(pathlib.Path(state).iterdir())==[],'Opening must not create spool/config files';assert w.source_mode=='runtime';assert not w.start_button.get_sensitive();screenshot(w,args.screenshot_idle)
  w.source_dialog(None);w.source_editor.mode.set_selected(2);w.source_editor.save_button.emit('clicked');spin();assert w.source_mode=='lab';assert w.client is None
  w.start_button.emit('clicked');assert w.consent_dialog is not None;screenshot(w.consent_dialog,args.screenshot_consent);w.consent_dialog.cancel_button.emit('clicked');spin();assert w.client is None,'Cancel means no worker/source access'
  w.start_button.emit('clicked');w.consent_dialog.remember_check.set_active(True);w.consent_dialog.approve_button.emit('clicked');wait(lambda:w.status.get('snapshots',0)>=1);assert len(w.tag_widgets)==5;assert w.status['webUiEnabled'] is False and w.status['readOnly'] is True
  spin(.6);assert w.status.get('delivered',0)==0;assert w.status.get('scadaQueueCount',0)>=1;assert w.status['transferAllowed'] is False
  w.send_button.emit('clicked');assert w.consent_dialog is not None;w.consent_dialog.approve_button.emit('clicked');wait(lambda:w.status.get('delivered',0)>=1)
  w.console.freeze_button.set_active(True);frozen=w.console.last_model['metrics']['snapshots']['value'];wait(lambda:w.status.get('snapshots',0)>frozen,12);assert w.console.last_model['metrics']['snapshots']['value']==frozen;assert w.status['captureAllowed'] is True;w.console.freeze_button.set_active(False);wait(lambda:w.console.last_model['metrics']['snapshots']['value']>frozen)
  w.console.signal_search.set_text('LAB_PUMP_01');spin();assert len(w.tag_widgets)==1;assert len(w.status['agents'][0]['observations'])==5;w.console.signal_search.set_text('');spin();assert len(w.tag_widgets)==5
  w.stop_button.emit('clicked');wait(lambda:w.status.get('captureAllowed') is False);w.start_button.emit('clicked');assert w.consent_dialog is None,'Remember skips repeated dialog, not the manual start button';wait(lambda:w.status.get('captureAllowed') is True)
  w.export_button.emit('clicked');wait(lambda:w.last_export is not None);assert w.last_export.read_text().startswith('recorded_at;observed_at;tag_name;');screenshot(w,args.screenshot)
  w2=AquaWindow(app,state,args.port);w2.present();spin(.4);assert w2.book.approved('capture',w2.scopes()[0]);assert w2.client is None;w2.close();spin()
  process=w.client.process;w.revoke_permissions(None);wait(lambda:w.client is None and not w.switching and process.poll() is not None);w.start_button.emit('clicked');assert w.consent_dialog is not None,'Revocation clears remembered grant';w.consent_dialog.cancel_button.emit('clicked')
  # Malformed CSV preferences cannot silently select a LAB source.
  bad=pathlib.Path(state)/'invalid-csv';bad.mkdir();(bad/'preferences.json').write_text(json.dumps({'version':2,'mode':'csv','source':{}}));w3=AquaWindow(app,bad,args.port);w3.begin_capture();spin(.3);assert w3.client is None;assert not (bad/'profiles').exists();w3.close();spin()
  lost=pathlib.Path(state)/'host-lost';w4=AquaWindow(app,lost,args.port);w4.present();w4.source_dialog(None);w4.source_editor.mode.set_selected(2);w4.source_editor.save_button.emit('clicked');w4.start_button.emit('clicked');w4.consent_dialog.approve_button.emit('clicked');wait(lambda:w4.status.get('snapshots',0)>=1);w4.client.close();wait(lambda:all(r['state']=='UNKNOWN' for r in w4.console.last_model['signals']) and w4.console.last_model['devices'][0]['reachability']!='REACHABLE',5);assert not w4.start_button.get_sensitive();w4.close();spin()
  print(json.dumps({'nativeWidgets':'GTK4','noAutoStart':True,'cancelStartsNothing':True,'captureAndTransferSeparate':True,'rememberedPermissionStillRequiresClick':True,'revocationStopsOwnedBackend':True,'laterLaunchIdle':True,'csvExport':'PASS','noUiHttpListener':True,'readOnly':True,'sevenPages':True,'displayFreezeKeepsCapture':True,'backendLossShowsCached':True}),flush=True)
 finally:
  process=w.client.process if w.client else None;w.close();wait(lambda:process is None or process.poll() is not None);spin()
