const sharedAddons = process.env.TM_ADDONS_DIR;
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const callbacks={},timers=new Map(),bodies=[];
 let timerId=0,calls=0;
 const status={textContent:'',after(){}},retry={hidden:true},frame={contentWindow:{postMessage(){}},remove(){}};
 const cfg={origin:'https://content.test',nonce:'nonce',csrf:'fictitious',attempt:1,revision:0,lease:1,save:'/training/interactive/attempt/1/save'};
 const document={getElementById:id=>({config:{textContent:JSON.stringify(cfg)},status,content:frame})[id],createElement:()=>retry};
 const context={document,window:{addEventListener:(key,callback)=>callbacks[key]=callback},URLSearchParams,AbortController,
  setTimeout:(callback,ms)=>{timers.set(++timerId,{callback,ms});return timerId},clearTimeout:id=>timers.delete(id),setInterval:()=>0,
  fetch:async(url,options)=>{
   bodies.push(options.body.toString());calls++;
   if(calls===1)return new Promise((resolve,reject)=>options.signal?.addEventListener('abort',()=>reject(new Error('timeout'))));
   return {ok:true,redirected:false,json:async()=>({ok:true,attempt:1,revision:1})};
  }};
 vm.runInNewContext(fs.readFileSync(sharedAddons+'/training_interactive/static/src/parent.js','utf8'),context);
 const message=data=>callbacks.message({origin:cfg.origin,source:frame.contentWindow,data:{nonce:cfg.nonce,...data}});
 // A foreign origin, frame or nonce must never trigger a save.
 for (const invalid of [
  {origin:'https://foreign.test',source:frame.contentWindow,data:{nonce:cfg.nonce,type:'report',key:'bad',data:{}}},
  {origin:cfg.origin,source:{},data:{nonce:cfg.nonce,type:'report',key:'bad',data:{}}},
  {origin:cfg.origin,source:frame.contentWindow,data:{nonce:'forged',type:'report',key:'bad',data:{}}},
 ]) callbacks.message(invalid);
 assert.equal(calls,0,'Cross-context messages must not save');
 message({type:'report',key:'stable-key',data:{state:{step:2}}});
 const timeout=[...timers.values()].find(t=>t.ms===15000);
 assert(timeout,'A stalled save must have a bounded timeout');timeout.callback();
 await new Promise(setImmediate);
 assert.equal(retry.hidden,false,'Failed save exposes retry');
 const failure=status.textContent;message({type:'ready'});
 assert.equal(status.textContent,failure,'Late ready must not hide an unsaved answer');
 retry.onclick();await new Promise(setImmediate);
 assert.equal(calls,2);assert.equal(bodies[0],bodies[1],'Retry preserves idempotence key and revision');
 assert.match(status.textContent,/Sauvegarde confirmée/);
 let warned=false;callbacks.beforeunload({preventDefault(){warned=true}});assert.equal(warned,false);
 console.log('PASS: timeout, visible failure, stable exact replay, ready cannot mask failure, queue drained.');
})().catch(e=>{console.error(e);process.exitCode=1});
