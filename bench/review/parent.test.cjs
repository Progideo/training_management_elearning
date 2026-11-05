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
 // A failed lease renewal removes the actual iframe. A later successful save
 // still has to acknowledge the server receipt and drain the retained queue.
 const closedCallbacks={},savedBodies=[];
 let renew,acknowledgements=0;
 const closedStatus={textContent:'',after(){}},closedRetry={hidden:true};
 const closedFrame={contentWindow:{postMessage(){acknowledgements++;}},remove(){this.contentWindow=null;}};
 const closedCfg={...cfg,save:'/closed-frame/save',renew:'/closed-frame/renew'};
 const closedDocument={getElementById:id=>({config:{textContent:JSON.stringify(closedCfg)},status:closedStatus,content:closedFrame})[id],createElement:()=>closedRetry};
 vm.runInNewContext(fs.readFileSync(sharedAddons+'/training_interactive/static/src/parent.js','utf8'),{
  document:closedDocument,window:{addEventListener:(key,callback)=>closedCallbacks[key]=callback},URLSearchParams,AbortController,
  setTimeout:()=>0,clearTimeout(){},setInterval:callback=>{renew=callback;return 1;},
  fetch:async(url,options)=>{
   if(url===closedCfg.renew)throw new Error('offline');
   savedBodies.push(options.body.toString());
   if(savedBodies.length===1)throw new Error('offline');
   return {ok:true,redirected:false,json:async()=>({ok:true,revision:1})};
  },
 });
 closedCallbacks.message({origin:closedCfg.origin,source:closedFrame.contentWindow,data:{nonce:closedCfg.nonce,type:'report',key:'retained-offline-key',data:{state:{step:2}}}});
 await new Promise(setImmediate);
 assert.equal(closedRetry.hidden,false);
 await renew();assert.equal(closedFrame.contentWindow,null,'Renewal failure removes the iframe');
 closedRetry.onclick();await new Promise(setImmediate);
 assert.equal(savedBodies.length,2);assert.equal(savedBodies[0],savedBodies[1]);
 assert.equal(closedRetry.hidden,true,'A confirmed save is not reported as a failure after frame removal');
 assert.match(closedStatus.textContent,/Sauvegarde confirmée/);
 assert.match(closedStatus.textContent,/Rechargez le lecteur/);
 assert.equal(acknowledgements,0);
 let closedWarned=false;closedCallbacks.beforeunload({preventDefault(){closedWarned=true;}});
 assert.equal(closedWarned,false,'The confirmed queue permits resuming the reader');
 closedCallbacks.message({origin:closedCfg.origin,source:null,data:{nonce:closedCfg.nonce,type:'report',key:'forged-detached-frame',data:{state:{step:99}}}});
 await new Promise(setImmediate);
 assert.equal(savedBodies.length,2,'A null source cannot impersonate a removed frame');
 console.log('PASS: timeout, visible failure, stable exact replay, ready cannot mask failure, queue drained.');
 console.log('PASS: offline replay after iframe removal preserves confirmation and rejects null message sources.');
})().catch(e=>{console.error(e);process.exitCode=1});
