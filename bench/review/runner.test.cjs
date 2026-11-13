const sharedAddons = process.env.TM_ADDONS_DIR;
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const callbacks={},sent=[];
 const H5P={externalDispatcher:{on:(name,cb)=>callbacks[name]=cb},instances:[{getCurrentState:()=>({answer:true})}]};
 const cfg={kind:'h5p',version:1,state:{},nonce:'n',portal:'https://portal.test'};
 const window={H5P};
 const context={window,H5P,H5PStandalone:{H5P:function(){return Promise.resolve()}},
  location:{pathname:'/tm-content/fictitious/launch'},crypto:{randomUUID:()=>String(sent.length)},setInterval:()=>0,
  document:{getElementById:id=>id==='config'?{textContent:JSON.stringify(cfg)}:{},querySelectorAll:()=>[]},
  parent:{postMessage:message=>sent.push(message)}};
 vm.runInNewContext(fs.readFileSync(sharedAddons+'/training_interactive/static/src/runner.js','utf8'),context);
 await new Promise(setImmediate);
 callbacks.xAPI({data:{statement:{verb:{id:'http://adlnet.gov/expapi/verbs/answered'},result:{completion:true,score:{max:1,raw:1}}}}});
 const report=sent.find(m=>m.type==='report');
 assert.equal(report.data.state?.answer,true,'Answer and result must persist together, without waiting for polling');
 assert.equal(report.data.result.score,1);
 console.log('PASS: H5P confirmed answer state is saved atomically with its formative result.');
})().catch(e=>{console.error(e);process.exitCode=1});
