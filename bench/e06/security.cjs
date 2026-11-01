const {request}=require('/Users/jbcrouigneau/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
(async()=>{
 const base='http://127.0.0.1:18269',ids=JSON.parse(fs.readFileSync('evidence/e05/ids.json'));
 const password=fs.readFileSync('/private/tmp/tm-e01-20261101-secrets/db_password','utf8');
 async function login(name){const c=await request.newContext();const r=await c.get(base+'/web/login');const csrf=(await r.text()).match(/name="csrf_token"[^>]*value="([^"]+)"/)[1];await c.post(base+'/web/login',{form:{csrf_token:csrf,login:name,password}});return c;}
 const learner=await login('e05_learner'),peer=await login('e05_peer');
 const path=base+'/training/interactive/'+ids.enrollments.X_e05_learner+'/'+ids.usages.X_scorm12;
 const entry=await learner.get(path);const csrf=(await entry.text()).match(/name="csrf_token"[^>]*value="([^"]+)"/)[1];
 const launch=await learner.post(path+'/start',{form:{csrf_token:csrf,request_key:crypto.randomUUID()}});
 const html=await launch.text(),cfg=JSON.parse(html.match(/<script id="config" type="application\/json">(.*?)<\/script>/s)[1]);
 const url=html.match(/id="content"[^>]*src="([^"]+)"/)[1].replace(/&amp;/g,'&');
 assert([403,404].includes((await peer.get(launch.url())).status()));
 assert([403,404].includes((await peer.get(path)).status()));
 assert([403,404].includes((await learner.get(base+'/training/interactive/preview/'+ids.versions.scorm12)).status()));
 assert([400,403].includes((await learner.post(launch.url()+'/save',{form:{payload:'{}'}})).status()));
 const raw=await learner.get(url);assert.equal(raw.status(),200);
 assert(!raw.headers()['set-cookie']);assert.equal(raw.headers()['cache-control'],'no-store');
 assert(raw.headers()['content-security-policy'].includes('sandbox allow-scripts allow-same-origin'));
 const revision=cfg.revision+1;
 const responses=await Promise.all(['a','b'].map(label=>learner.post(launch.url()+'/save',{
  form:{csrf_token:cfg.csrf,payload:JSON.stringify({key:'concurrent-'+label+'-'+crypto.randomUUID(),revision,data:{state:{concurrent:label}}})}})));
 const statuses=responses.map(r=>r.status()).sort();assert.deepEqual(statuses,[200,409]);
 fs.writeFileSync('/private/tmp/tm-e01-20261101-secrets/participant-file-url',url.replace(/\/launch$/,'/file/index.html'));
 console.log(JSON.stringify({checks:['cross-user page and attempt denied','participant preview denied','CSRF required','no content cookie','sandbox CSP','simultaneous revisions resolved explicitly'],concurrent_statuses:statuses,attempt:cfg.attempt,expected_revision:revision}));
 await learner.dispose();await peer.dispose();
})().catch(e=>{console.error(e);process.exit(1)});
