const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8'),{url:'https://panel.test',runScripts:'outside-only'}),w=dom.window,d=w.document;
w.eval(fs.readFileSync('app/static/chat-rewrite.js','utf8'));
let phone='5071',session='a',calls=0,resolve,notices=[];const input=d.getElementById('message-input');input.disabled=false;input.value='Coordina con Teresa';
w.CubicoRewrite.init({getPhone:()=>phone,getSession:()=>session,getInput:()=>input,notify:t=>notices.push(t),onUse:text=>{input.value=text},request:async(p,body)=>{calls++;assert.equal(body.mensaje,input.value);return await new Promise(r=>resolve=r)}});
const click=()=>d.getElementById('rewrite-text').onclick();
const answer=()=>resolve({ok:true,json:async()=>({telefono:'5071',enviado:false,borrador:'Puedes coordinar el retiro con Teresa.'})});
(async()=>{
 let pending=click();click();assert.equal(calls,1);answer();await pending;
 assert.equal(input.value,'Coordina con Teresa');assert.equal(d.getElementById('rewrite-preview').hidden,false);
 d.getElementById('rewrite-use').click();assert.equal(input.value,'Puedes coordinar el retiro con Teresa.');assert(w.CubicoRewrite.isAssisted('5071'));
 pending=click();input.value='Nuevo texto que debo conservar';answer();await pending;d.getElementById('rewrite-use').click();assert.equal(input.value,'Nuevo texto que debo conservar');
 pending=click();phone='5072';w.CubicoRewrite.reset();answer();await pending;assert.equal(d.getElementById('rewrite-preview').hidden,true);
 phone='5071';pending=click();session='other';answer();await pending;assert.equal(d.getElementById('rewrite-preview').hidden,true);
 w.CubicoRewrite.clear();assert(!w.CubicoRewrite.isAssisted('5071'));
 console.log('Rewrite: explicit draft/use, no automatic send, duplicate guard, edited text and stale chat/session preservation passed');w.close();
})().catch(e=>{console.error(e);w.close();process.exitCode=1});
