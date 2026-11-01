const {chromium}=require('/Users/jbcrouigneau/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const ids=JSON.parse(fs.readFileSync('evidence/e05/ids.json'));
 const browser=await chromium.launch({headless:true,executablePath:chromium.executablePath()});
 const context=await browser.newContext();const page=await context.newPage();const base='http://127.0.0.1:18269';
 await page.goto(base+'/web/login');await page.locator('[name=login]').fill('e05_learner');await page.locator('[name=password]').fill(fs.readFileSync('/private/tmp/tm-e01-20261101-secrets/db_password','utf8'));
 await Promise.all([page.waitForURL(u=>!u.pathname.endsWith('/web/login')),page.locator('button[type=submit]').click()]);
 const path='/training/interactive/'+ids.enrollments.Y_e05_learner+'/'+ids.usages.Y_scorm12;
 await page.goto(base+path);await page.getByRole('button',{name:/^(Commencer|Reprendre la tentative)$/}).click();
 await page.frameLocator('#content').frameLocator('iframe').getByRole('button',{name:'Terminer avec 80/100'}).click();
 await page.locator('#status').filter({hasText:'Sauvegarde confirmée'}).waitFor();
 await page.getByRole('link',{name:'Revenir à ma formation'}).click();
 await page.screenshot({path:'evidence/e05/y-threshold-not-met.png',fullPage:true});
 await page.goto(base+path);await page.getByText('Activité à terminer dans votre formation.',{exact:false}).waitFor();
 console.log('PASS: same SCORM completed at 80/100 in Y with threshold 90 remains incomplete');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
