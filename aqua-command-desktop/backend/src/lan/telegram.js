import https from 'node:https';
export class DeliveryError extends Error{constructor(message='Telegram transport failed',retryAfterMs=0){super(message);this.retryAfterMs=retryAfterMs}}
export class TelegramTransport{
 constructor({env=process.env,request=https.request}={}){
  this.mode=env.TELEGRAM_ENABLED==='true'?'telegram':'dry-run';this.request=request;
  this.token=this.mode==='telegram'?(env.TELEGRAM_BOT_TOKEN||''):'';this.chat=this.mode==='telegram'?(env.TELEGRAM_CHAT_ID||''):'';
  this.configured=this.mode==='telegram'&&env.TELEGRAM_APPROVED_ENDPOINT==='https://api.telegram.org'&&/^[0-9]+:[A-Za-z0-9_-]+$/.test(this.token)&&/^-?[0-9]+$/.test(this.chat);
 }
 call(method,value){
  if(!this.configured||!['getMe','sendMessage'].includes(method))return Promise.reject(new DeliveryError('Telegram test configuration is not approved/complete'));
  const raw=JSON.stringify(value);
  return new Promise((resolve,reject)=>{
   let settled=false,req;const done=(error,value)=>{if(settled)return;settled=true;clearTimeout(deadline);error?reject(error):resolve(value)};
   const deadline=setTimeout(()=>{done(new DeliveryError('Telegram request deadline exceeded; response ambiguous'));req?.destroy()},4000);
   req=this.request({hostname:'api.telegram.org',port:443,path:`/bot${this.token}/${method}`,method:'POST',rejectUnauthorized:true,timeout:4000,headers:{'content-type':'application/json','content-length':Buffer.byteLength(raw)}},res=>{
    const parts=[];let size=0;
    const interrupted=()=>done(new DeliveryError('Telegram response interrupted; delivery may be ambiguous'));
    res.once('aborted',interrupted);res.once('error',interrupted);res.once('close',()=>{if(!res.complete)interrupted()});
    res.on('data',p=>{size+=p.length;if(size>256*1024){done(new DeliveryError());req.destroy();return}parts.push(p)});
    res.on('end',()=>{try{const body=JSON.parse(Buffer.concat(parts).toString('utf8'));
     if(res.statusCode!==200||body.ok!==true){const seconds=body.parameters?.retry_after;throw new DeliveryError('Telegram API rejected request',Number.isFinite(seconds)?Math.min(3600,Math.max(1,seconds))*1000:res.statusCode===429?5000:0)}
     done(null,body.result);
    }catch(e){done(e instanceof DeliveryError?e:new DeliveryError('Telegram response invalid or ambiguous'))}});
   });
   req.on('timeout',()=>{done(new DeliveryError('Telegram request timed out; delivery may be ambiguous'));req.destroy()});req.on('error',()=>done(new DeliveryError('Telegram connection failed')));req.end(raw);
  });
 }
 async probe(){if(this.mode==='dry-run'||!this.configured)return false;const result=await this.call('getMe',{});if(!result?.is_bot)throw new DeliveryError('Telegram identity check failed');return true}
 async send(text){if(!text.startsWith('[AQUA LAB / SIMULATED]')||text.length>3000)throw new DeliveryError('Only labelled LAB notifications allowed');const result=await this.call('sendMessage',{chat_id:this.chat,text});if(!Number.isSafeInteger(result?.message_id))throw new DeliveryError('Telegram delivery response ambiguous');return result.message_id}
}
