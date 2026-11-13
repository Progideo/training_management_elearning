import json
from pathlib import Path
from odoo.tests import new_test_user
from odoo.addons.training_management_interactive.tests.test_content_security import package
assert env.cr.dbname == 'e01'
author=new_test_user(env, login='e01_browser_author', password=Path('/run/secrets/db_password').read_text(), groups='training_management_interactive.group_elearning_author')
peer=new_test_user(env, login='e01_browser_peer', password=Path('/run/secrets/db_password').read_text(), groups='base.group_portal')
params=env['ir.config_parameter']
params.set_str('training_elearning.portal_origin','http://127.0.0.1:18269')
params.set_str('training_elearning.content_origin','http://localhost:18270')
resource=env['training.elearning.resource'].with_user(author).create({'name':'E01 paquet hostile fictif', 'format':'scorm12'})
malicious=b'''<!doctype html><html><meta charset="utf-8"><h1>Paquet hostile fictif</h1><pre id="result"></pre><script>
(async()=>{
 const result={};
 try {result.parentDOM=top.document.body.innerText;} catch(e){result.parentDOM='BLOCKED';}
 try {result.portalCookie=top.document.cookie;} catch(e){result.portalCookie='BLOCKED';}
 try {result.portalData=await(await fetch('http://127.0.0.1:18269/web/session/get_session_info',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:'{"jsonrpc":"2.0","params":{}}'})).text();} catch(e){result.portalData='BLOCKED';}
 result.contentCookies=document.cookie;
 document.querySelector('#result').textContent=JSON.stringify(result);
 top.postMessage({type:'ready',nonce:'FORGED'},'http://127.0.0.1:18269');
})();</script></html>'''
version=env['training.elearning.version'].with_user(author)._import(resource,'hostile-1',package({'index.html':malicious,'private.txt':b'Fictional private subfile'}),'Fictional test','Security test only')
files=env['training.elearning.file'].sudo().search([('version_id','=',version.id)])
env.cr.commit()
print('E01_IDS='+json.dumps({'version':version.id,'author':author.id,'file':files[0].id}))
