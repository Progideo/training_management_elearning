const {request}=require('playwright');
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const base='http://127.0.0.1:18269';
const percentile=(values,p)=>[...values].sort((a,b)=>a-b)[Math.ceil(values.length*p)-1];
(async()=>{
 const users=JSON.parse(fs.readFileSync('evidence/e06/users.json'));
 const password=fs.readFileSync(require('node:path').join(process.env.LMS_SECRET_DIR, 'db_password'),'utf8');
 const clients=[];
 for(let offset=0;offset<users.length;offset+=5){await Promise.all(users.slice(offset,offset+5).map(async user=>{
  const context=await request.newContext({timeout:60000});
  const login=await context.get(base+'/web/login');const html=await login.text();
  const csrf=html.match(/name="csrf_token"[^>]*value="([^"]+)"/)[1];
  const authenticated=await context.post(base+'/web/login',{form:{csrf_token:csrf,login:user.login,password}});
  assert(!authenticated.url().includes('/web/login'),user.login+' authentication failed');
  clients.push({user,context});
 }));}
 const launches=[],reads=[],saves=[];const evidence=[];
 await Promise.all(clients.map(async({user,context})=>{
  const started=Date.now();const path=base+'/training/interactive/'+user.enrollment+'/'+user.usage;
  const entry=await context.get(path);assert.equal(entry.status(),200);
  const html=await entry.text();const csrf=html.match(/name="csrf_token"[^>]*value="([^"]+)"/)[1];
  const launched=await context.post(path+'/start',{form:{csrf_token:csrf,request_key:crypto.randomUUID()}});
  assert.equal(launched.status(),200);
  const page=await launched.text();const cfg=JSON.parse(page.match(/<script id="config" type="application\/json">(.*?)<\/script>/s)[1]);
  const source=page.match(/id="content"[^>]*src="([^"]+)"/)[1].replace(/&amp;/g,'&');
  launches.push(Date.now()-started);
  const readStart=Date.now();
  for(const suffix of ['/launch','/runner.js','/vendor/scorm12.min.js','/file/index.html']){
   const response=await context.get(source.replace(/\/launch$/,'')+suffix);assert.equal(response.status(),200,'Private resource '+suffix);
  }
  reads.push(Date.now()-readStart);
  const saveStart=Date.now();
  const key=crypto.randomUUID();const payload={key,revision:1,data:{state:{load_test:true},result:{score:100,maximum:100,completed:true}}};
  const response=await context.post(base+'/training/interactive/attempt/'+cfg.attempt+'/save',{form:{csrf_token:cfg.csrf,payload:JSON.stringify(payload)}});
  assert.equal(response.status(),200);const receipt=await response.json();assert.equal(receipt.revision,1);
  saves.push(Date.now()-saveStart);evidence.push({login:user.login,attempt:cfg.attempt,revision:receipt.revision});
  const replay=await context.post(base+'/training/interactive/attempt/'+cfg.attempt+'/save',{form:{csrf_token:cfg.csrf,payload:JSON.stringify(payload)}});
  assert.deepEqual(await replay.json(),receipt);
 }));
 const summary={concurrent_participants:50,successful_saves:evidence.length,
  launch_ms:{p95:percentile(launches,.95),max:Math.max(...launches)},
  private_resources_ms:{p95:percentile(reads,.95),max:Math.max(...reads)},
  save_ms:{p95:percentile(saves,.95),max:Math.max(...saves)},target_save_p95_ms:5000};
 fs.writeFileSync('evidence/e06/load-results.json',JSON.stringify({summary,evidence},null,2));console.log(JSON.stringify(summary));
 assert.equal(evidence.length,50);assert(summary.save_ms.p95<5000,'Save latency target missed');
 await Promise.all(clients.map(c=>c.context.dispose()));
})().catch(e=>{console.error(e);process.exit(1)});
