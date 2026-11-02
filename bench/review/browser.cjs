// Reuse the delivered browser recipes, retaining their original evidence untouched.
const fs=require('node:fs'),assert=require('node:assert/strict');
const recipe=process.argv[2];
assert(['e01/browser','e05/browser','q01/browser','e06/load','e06/security'].includes(recipe));
let source=fs.readFileSync('bench/'+recipe+'.cjs','utf8')
 .replaceAll('evidence/e01','evidence/review/e01').replaceAll('evidence/e05','evidence/review/e05')
 .replaceAll('evidence/q01','evidence/review/q01').replaceAll('evidence/e06','evidence/review/e06')
 .replaceAll('tm-e01-20261101-secrets','tm-review-20261102-secrets');
if(recipe==='e05/browser') {
 const after="await page.locator('#status').filter({hasText:'Sauvegarde confirmée'}).waitFor();";
 source=source.replace(after,after+`
 await page.reload();
 await hframe.locator('[role=radio][aria-checked=true]').filter({hasText:'Yes'}).waitFor();
 console.log('PASS: H5P answer restored immediately after its confirmed result.');
 `);
}
if(recipe==='e06/security') {
 source=source.replace('const revision=cfg.revision+1;', `
 const revision=cfg.revision+1;
 const deep='['.repeat(2000)+'0'+']'.repeat(2000);
 assert.equal((await learner.post(launch.url()+'/save',{form:{csrf_token:cfg.csrf,payload:deep}})).status(),409);
 const huge='{"key":"huge","revision":'+revision+',"data":{"result":{"score":'+('1'+'0'.repeat(400))+',"maximum":'+('1'+'0'.repeat(401))+',"completed":true}}}';
 assert.equal((await learner.post(launch.url()+'/save',{form:{csrf_token:cfg.csrf,payload:huge}})).status(),409);
 console.log('PASS: deeply nested JSON and oversized numeric score refused without HTTP 500 or revision consumption.');
 `);
}
(async()=>{
 for(let count=0;count<30;count++) {
  try {
   const response=await fetch('http://127.0.0.1:18269/web/login',{signal:AbortSignal.timeout(2000)});
   if(response.ok&&(await response.text()).includes('name="csrf_token"')) {
    new Function('require',source)(require);return;
   }
  } catch(error) { /* Gateway and application may still be starting. */ }
  await new Promise(resolve=>setTimeout(resolve,1000));
 }
 throw new Error('Local portal did not become ready');
})().catch(error=>{console.error(error);process.exitCode=1});
