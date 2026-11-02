const {chromium}=require('playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const ids=JSON.parse(fs.readFileSync('evidence/q01/ids.json','utf8'));
 const password=fs.readFileSync(require('node:path').join(process.env.LMS_SECRET_DIR, 'db_password'),'utf8');
 const browser=await chromium.launch({headless:true,executablePath:chromium.executablePath()});
 const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage();
 const errors=[];page.on('pageerror',e=>{errors.push(e.message);console.log('PAGEERROR',e.message)});page.on('console',m=>{if(m.type()==='error')console.log('CONSOLE',m.text())});
 const base='http://127.0.0.1:18269';
 await page.goto(base+'/web/login');await page.locator('[name=login]').fill('q01_learner');await page.locator('[name=password]').fill(password);
 await Promise.all([page.waitForURL(u=>!u.pathname.endsWith('/web/login')),page.locator('button[type=submit]').click()]);
 await page.goto(base+`/my/trainings/${ids.enrollment}/exams/${ids.activity}`);
 await page.locator('form button.btn-primary').click();
 await page.locator('.tm_enriched_select').first().waitFor();
 assert(!(await page.content()).includes('Explication finale privée Q01'),'Early correction leak');
 assert.equal(await page.locator('[data-correct], [data-is-correct]').count(),0);
 const first=page.locator('.tm_question').nth(0),second=page.locator('.tm_question').nth(1);
 await second.waitFor({state:'hidden'});
 const save=async()=>{try {await page.locator('.tm_save_status').filter({hasText:'Saved on the server.'}).waitFor();} catch(e) {console.log('STATUS',await page.locator('.tm_save_status').innerText());await page.screenshot({path:'evidence/q01/save-diagnostic.png',fullPage:true});throw e;}};
 await first.locator('select').nth(0).selectOption(String(ids.questions[0].correct[0]));await save();
 await page.reload();await first.locator('select').nth(0).waitFor();
 assert.equal(await first.locator('select').nth(0).inputValue(),String(ids.questions[0].correct[0]));
 // Duplicate item moves to the new row, then survives reload as a partial answer.
 const optionKey=await first.locator('select').nth(0).locator('option:checked').getAttribute('data-option');
 const duplicate=await first.locator('select').nth(1).locator(`option[data-option="${optionKey}"]`).getAttribute('value');
 await first.locator('select').nth(1).selectOption(duplicate);await save();
 assert.equal(await first.locator('select').nth(0).inputValue(),'');
 await first.locator('.tm_clear').click();await save();
 assert.equal(await first.locator('select').nth(1).inputValue(),'');
 for(let i=0;i<3;i++){await first.locator('select').nth(i).selectOption(String(ids.questions[0].correct[i]));await save();}
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'390px overflow');
 await first.locator('select').first().focus();await page.keyboard.press('Tab');
 assert.equal(await page.evaluate(()=>document.activeElement.tagName),'SELECT');
 await page.screenshot({path:'evidence/q01/matching-390.png',fullPage:true});
 await page.locator('.tm_next').click();
 for(let i=0;i<3;i++){await second.locator('select').nth(i).selectOption(String(ids.questions[1].correct[i]));await save();}
 await page.setViewportSize({width:320,height:740});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'320px overflow');
 await page.screenshot({path:'evidence/q01/ordering-320.png',fullPage:true});
 await page.locator('.tm_summary').click();await page.locator('.tm_submit').click();
 await page.getByRole('heading',{name:'Result and final correction',exact:true}).waitFor();
 assert((await page.locator('body').innerText()).includes('100.0 %'));
 assert((await page.locator('body').innerText()).includes('Explication finale privée Q01'));
 await page.screenshot({path:'evidence/q01/result-320.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('PASS: matching, ordering, partial resume, duplicate move, clear, exact native score, final-only correction, 390/320px and keyboard.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
