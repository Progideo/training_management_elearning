/* Runs exclusively on the isolated content origin. Client results are formative. */
(async () => {
    const cfg=JSON.parse(document.getElementById('config').textContent);
    const base=location.pathname.replace(/\/launch$/,'');
    const notify=(type,values={})=>parent.postMessage({type,nonce:cfg.nonce,...values},cfg.portal);
    const report=data=>notify('report',{key:crypto.randomUUID(),data});
    let previous=JSON.stringify(cfg.state);
    if(cfg.kind==='h5p') {
        await new H5PStandalone.H5P(document.getElementById('player'),{
            id:cfg.version,h5pJsonPath:base+'/file',frameJs:base+'/vendor/h5p/frame.bundle.js',
            frameCss:base+'/vendor/h5p/styles/h5p.css',saveFreq:5,
            contentUserData:{0:{state:JSON.stringify(cfg.state)}}
        });
        H5P.externalDispatcher.on('xAPI',event=>{
            const s=event.data.statement, result=s.result;
            // Initial allow-list is a single TrueFalse question, never composite content.
            if(s.verb?.id==='http://adlnet.gov/expapi/verbs/answered' && result?.completion===true
                && result.score?.max===1 && [0,1].includes(result.score.raw)) {
                report({result:{score:result.score.raw,maximum:1,completed:true}});
            }
        });
        setInterval(()=>{
            const frames=[window,...Array.from(document.querySelectorAll('iframe')).map(f=>f.contentWindow)];
            for(const w of frames) {
                try {
                    const instance=w.H5P?.instances?.find(i=>typeof i.getCurrentState==='function');
                    if(!instance) continue;
                    const state=instance.getCurrentState(), encoded=JSON.stringify(state);
                    if(state && encoded!==previous) {previous=encoded;report({state});}
                    break;
                } catch(e) {notify('error',{message:'État du contenu indisponible.'});}
            }
        },3000);
    } else {
        window.API=new Scorm12API({autocommit:false,logLevel:5});
        if(Object.keys(cfg.state).length) {window.API.loadFromJSON(cfg.state);window.API.cmi.core.entry='resume';}
        const commit=()=>{
            const core=window.API.cmi.core;
            report({state:window.API.renderCMIToJSONObject(),result:{
                score:Number(core.score.raw)||0,maximum:Number(core.score.max)||100,
                completed:['passed','completed'].includes(core.lesson_status)}});
        };
        window.API.on('LMSCommit',commit);window.API.on('LMSFinish',commit);
        const iframe=document.createElement('iframe');iframe.title='Activité SCORM 1.2';
        iframe.style='width:100%;height:90vh;border:0';iframe.src=base+'/file/'+cfg.entrypoint;
        document.getElementById('player').appendChild(iframe);
    }
    notify('ready');
})().catch(error=>{
    document.getElementById('player').textContent='Le contenu n’a pas pu être chargé.';
    const cfg=JSON.parse(document.getElementById('config').textContent);
    parent.postMessage({type:'error',nonce:cfg.nonce,message:'Échec de chargement du lecteur.'},cfg.portal);
});
