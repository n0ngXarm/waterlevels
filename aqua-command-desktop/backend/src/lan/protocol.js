import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import {isIP} from 'node:net';
import {createHash,createHmac,randomBytes,timingSafeEqual} from 'node:crypto';

export const digest=value=>createHash('sha256').update(value).digest('hex');
export const encode=value=>JSON.stringify(value);
const mac=(secret,value)=>createHmac('sha256',secret).update(value).digest('hex');
const equal=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===b.length&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
export const loopback=host=>['127.0.0.1','localhost','::1','[::1]'].includes(host);
const privateIp=host=>isIP(host)===4&&(/^10\./.test(host)||/^192\.168\./.test(host)||(/^172\./.test(host)&&+host.split('.')[1]>=16&&+host.split('.')[1]<=31));
export function endpoint(value,options={}){
 const u=new URL(value);
 if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash||u.pathname!=='/'||(!loopback(u.hostname)&&!(options.allowLan&&privateIp(u.hostname))))throw Error('Only explicit loopback or approved private LAB endpoints are allowed');
 if(!loopback(u.hostname)&&u.protocol==='http:'&&!options.allowInsecureLabHttp)throw Error('HTTP LAN endpoint requires isolated trusted LAB acknowledgement');
 return u;
}
export function requestHeaders(id,secret,path,raw,{time=Date.now(),nonce=randomBytes(20).toString('hex')}={}){
 const stamp=String(time);return {'x-aqua-id':id,'x-aqua-time':stamp,'x-aqua-nonce':nonce,'x-aqua-mac':mac(secret,`POST\n${path}\n${stamp}\n${nonce}\n${digest(raw)}`)};
}
export function authenticate(req,raw,keys,store){
 const id=req.headers['x-aqua-id'],secret=keys[id],stamp=req.headers['x-aqua-time'],nonce=req.headers['x-aqua-nonce'];
 if(typeof secret!=='string'||!Number.isFinite(+stamp)||Math.abs(Date.now()-Number(stamp))>30000||typeof nonce!=='string'||!/^[a-f0-9]{40}$/.test(nonce)||!equal(req.headers['x-aqua-mac'],mac(secret,`${req.method}\n${req.url}\n${stamp}\n${nonce}\n${digest(raw)}`)))throw Object.assign(Error('Authorization failed'),{status:401});
 if(!store.claimNonce(id,nonce))throw Object.assign(Error('Replay rejected'),{status:401});
 return {id,secret,nonce};
}
export function answer(res,status,value,auth=null){
 const raw=encode(value),headers={'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'};
 if(auth)headers['x-aqua-response']=mac(auth.secret,`RESPONSE\n${status}\n${auth.nonce}\n${digest(raw)}`);
 res.writeHead(status,headers);res.end(raw);
}
export function requestJSON(base,path,identity,value,options={}){
 const u=endpoint(base,options),raw=encode(value),headers=requestHeaders(identity.id,identity.secret,path,raw);
 return new Promise((resolve,reject)=>{
  let settled=false,req;const timeoutMs=Math.min(10000,Math.max(100,options.timeoutMs??1500));
  const done=(error,value)=>{if(settled)return;settled=true;clearTimeout(deadline);error?reject(error):resolve(value)};
  const deadline=setTimeout(()=>{done(Error('LAB request deadline exceeded'));req?.destroy()},timeoutMs);
  req=(u.protocol==='https:'?https:http).request({hostname:u.hostname,port:u.port,method:'POST',path,rejectUnauthorized:true,headers:{...headers,'content-type':'application/json','content-length':Buffer.byteLength(raw)},timeout:timeoutMs,...(options.caFile?{ca:fs.readFileSync(options.caFile)}:{})},res=>{
   let bytes=0;const parts=[];
   const interrupted=()=>done(Object.assign(Error('LAB response interrupted'),{transportConnected:true}));
   res.once('aborted',interrupted);res.once('error',interrupted);res.once('close',()=>{if(!res.complete)interrupted()});
   res.on('data',p=>{bytes+=p.length;if(bytes>512*1024){done(Error('Response limit'));req.destroy();return}parts.push(p)});
   res.on('end',()=>{try{
    const body=Buffer.concat(parts).toString('utf8');
    if(!equal(res.headers['x-aqua-response'],mac(identity.secret,`RESPONSE\n${res.statusCode}\n${headers['x-aqua-nonce']}\n${digest(body)}`)))throw Object.assign(Error('Unauthenticated response'),{transportConnected:true,authenticationFailed:true,status:res.statusCode});
    const result=JSON.parse(body);if(res.statusCode!==200)throw Object.assign(Error(result.error||'Service rejected request'),{status:res.statusCode,transportConnected:true,authenticatedPeer:true});done(null,result);
   }catch(e){done(e)}});
  });
  req.on('timeout',()=>{done(Error('LAB request timeout'));req.destroy()});req.on('error',e=>done(e));req.end(raw);
 });
}
export async function readBody(req){
 let size=0;const parts=[];for await(const p of req){size+=p.length;if(size>512*1024)throw Object.assign(Error('Body limit'),{status:413});parts.push(p)}return Buffer.concat(parts).toString('utf8');
}
