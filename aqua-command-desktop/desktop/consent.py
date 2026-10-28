"""Remember review choices for an exact scope; never authorize startup automatically."""
import hashlib,json,pathlib
from model import owned_directory,atomic_json

def scope_key(scope):
 return hashlib.sha256(json.dumps(scope,sort_keys=True,ensure_ascii=True).encode()).hexdigest()

class ConsentBook:
 def __init__(self,root,source=None):
  self.root=pathlib.Path(root);self.source=source;self.grants={}
  try:
   with (self.root/'permissions.json').open('rb') as f:raw=f.read(32769)
   value=json.loads(raw) if len(raw)<=32768 else {}
   if value.get('version')==1 and isinstance(value.get('grants'),dict):
    self.grants={k:v for k,v in value['grants'].items() if k in ('capture','transfer') and isinstance(v,str) and len(v)==64}
  except (OSError,ValueError,AttributeError):pass
 def approved(self,action,scope):return self.grants.get(action)==scope
 def remember(self,action,scope):
  if action not in ('capture','transfer'):raise ValueError('Unsupported permission')
  self.grants[action]=scope;self.save()
 def clear(self):self.grants={};self.save()
 def save(self):
  root=owned_directory(self.root,self.source);root.mkdir(parents=True,exist_ok=True,mode=0o700)
  atomic_json(root/'permissions.json',{'version':1,'grants':self.grants})
