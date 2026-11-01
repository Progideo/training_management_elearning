/* Portal-side broker: current user authorization and CSRF stay outside package origin. */
(() => {
    const cfg=JSON.parse(document.getElementById('config').textContent);
    const frame=document.getElementById('content'),status=document.getElementById('status');
    const retry=document.createElement('button');retry.textContent='Réessayer la sauvegarde';retry.hidden=true;
    status.after(retry);
    let revision=cfg.revision, queue=[], busy=false, failed=false;
    const seen=new Set();
    async function flush() {
        if(busy||failed||!queue.length) return;
        busy=true;
        const item=queue[0];
        if(!item.revision) item.revision=revision+1;
        try {
            const form=new URLSearchParams({csrf_token:cfg.csrf,payload:JSON.stringify({key:item.key,revision:item.revision,data:item.data})});
            const response=await fetch('/training/interactive/attempt/'+cfg.attempt+'/save',{method:'POST',body:form,credentials:'same-origin'});
            if(!response.ok||response.redirected) throw new Error('Sauvegarde refusée ('+response.status+').');
            const receipt=await response.json();
            if(!receipt.ok) throw new Error('Sauvegarde non confirmée.');
            revision=receipt.revision;queue.shift();
            status.textContent='Sauvegarde confirmée — révision '+revision+'.';
            frame.contentWindow.postMessage({type:'saved',nonce:cfg.nonce,revision},cfg.origin);
        } catch(error) {
            failed=true;retry.hidden=false;
            status.textContent=error.message+' Les données en attente restent dans cet onglet. En cas de conflit, rechargez le lecteur.';
        } finally {busy=false;if(!failed) flush();}
    }
    retry.onclick=()=>{failed=false;retry.hidden=true;flush();};
    window.addEventListener('message',event=>{
        if(event.origin!==cfg.origin||event.source!==frame.contentWindow) return;
        const message=event.data;
        if(!message||typeof message!=='object'||message.nonce!==cfg.nonce) return;
        let size;try{size=JSON.stringify(message).length;}catch(e){return;}
        if(size>131072) return;
        if(message.type==='ready') status.textContent='Contenu chargé dans son espace isolé.';
        if(message.type==='error') status.textContent='Le lecteur signale une erreur. Rechargez ou contactez la coordination.';
        if(message.type==='report'&&cfg.attempt&&typeof message.key==='string'&&message.key.length<=80
                &&message.data&&typeof message.data==='object'&&!seen.has(message.key)) {
            if(queue.length>=100){status.textContent='Trop de sauvegardes en attente. Attendez leur confirmation.';return;}
            seen.add(message.key);queue.push({key:message.key,data:message.data});flush();
        }
    });
    if(cfg.attempt) setInterval(async()=>{
        try {
            const response=await fetch('/training/interactive/attempt/'+cfg.attempt+'/renew',{
                method:'POST',credentials:'same-origin',body:new URLSearchParams({csrf_token:cfg.csrf,lease:String(cfg.lease)})});
            if(!response.ok||response.redirected) throw new Error();
        } catch(e) {status.textContent='Autorisation indisponible. Rechargez le lecteur pour reprendre.';frame.remove();}
    },120000);
    window.addEventListener('beforeunload',event=>{if(queue.length){event.preventDefault();event.returnValue='';}});
})();
