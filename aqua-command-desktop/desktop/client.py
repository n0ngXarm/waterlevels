"""Own one private Node child; communicate through bounded JSON lines, never a browser."""
import json,pathlib,subprocess,threading,uuid
class BackendClient:
 def __init__(self,root,profile,on_message,port=4173):
  self.on_message=on_message;self.lock=threading.Lock();self.closed=False;self.errors=[]
  self.process=subprocess.Popen(['node',str(pathlib.Path(root)/'desktop/host.mjs'),'--data-dir',str(profile['data']),'--config',str(profile['config']),'--port',str(port)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
  threading.Thread(target=self._read,daemon=True).start();threading.Thread(target=self._errors,daemon=True).start()
 def _read(self):
  while True:
   line=self.process.stdout.readline(2_000_001)
   if not line:break
   if len(line)>2_000_000:self.on_message({'type':'error','message':'ข้อความสถานะใหญ่เกินกำหนด'});break
   try:self.on_message(json.loads(line))
   except (ValueError,TypeError):self.on_message({'type':'error','message':'อ่านสถานะจากส่วนเก็บข้อมูลไม่ได้'})
  if not self.closed:self.on_message({'type':'error','message':'ส่วนเก็บข้อมูลหยุดทำงาน ตรวจพอร์ต/สิทธิ์ไฟล์ หรือโปรแกรมAQUAอีกหน้าต่าง'})
 def _errors(self):
  for line in self.process.stderr:self.errors=(self.errors+[line[:512]])[-4:]
 def request(self,command,**values):
  with self.lock:
   if self.closed or self.process.poll() is not None:raise RuntimeError('ส่วนเก็บข้อมูลไม่ได้ทำงาน')
   request={'id':uuid.uuid4().hex,'command':command,**values};self.process.stdin.write(json.dumps(request)+'\n');self.process.stdin.flush();return request['id']
 def close(self):
  with self.lock:
   if self.closed:return
   self.closed=True
   try:self.process.stdin.close()
   except (BrokenPipeError,OSError):pass
  try:self.process.wait(timeout=10)
  except subprocess.TimeoutExpired:
   self.process.terminate()
   try:self.process.wait(timeout=5)
   except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
