const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const html=fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8');
const dom=new JSDOM(html,{url:'https://panel.test/admin',runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window,d=w.document;
w.scrollTo=()=>{};w.matchMedia=()=>({matches:false});w.requestAnimationFrame=cb=>cb();w.HTMLElement.prototype.scrollIntoView=()=>{};
const chats=[{telefono:'5071',nombre:'Cliente de prueba',tiene_no_leidos:true,ultimo_mensaje_cliente:{contenido:'Hola',timestamp:'2026-10-19T10:00:00Z'}}];
let fail=false,secondary=0;
w.fetch=async url=>{
 const path=new URL(url).pathname;
 if(path==='/panel/conversaciones')return {ok:!fail,status:fail?503:200,json:async()=>chats};
 secondary++;return new Promise(()=>{}); // An unavailable profile/context service must not hold the inbox.
};
for(const f of ['panel-personalization.js','panel-mobile-layout.js','chat-text-editor.js','app-release.js','operational-context.js','bot-cost-analytics.js','daily-report.js','alert-management.js','internal-assistant.js'])w.eval(fs.readFileSync('app/static/'+f,'utf8'));
// Deliberately omit chat-location.js to reproduce an optional asset download failure.
w.eval(html.match(/<script>\s*([\s\S]*?)<\/script>/)[1]);
(async()=>{
 d.getElementById('login-user').value='alexander';d.getElementById('login-pass').value='test';
 await Promise.race([w.login(),new Promise((_,reject)=>setTimeout(()=>reject(Error('Login waited for secondary data')),500))]);
 assert.equal(d.getElementById('login-overlay').style.display,'none');
 assert.equal(d.querySelectorAll('#chat-items .chat-item').length,1);assert(secondary>0);
 w.showView('chats');assert.match(d.getElementById('chat-items').textContent,/Cliente de prueba/);
 d.getElementById('attach-location').click();assert.match(d.querySelector('.toast').textContent,/seguir usando los chats/);
 fail=true;await w.recargarConversaciones();assert.equal(d.getElementById('chat-load-status').hidden,false);
 assert.match(d.getElementById('chat-load-message').textContent,/última lista/);assert.equal(d.querySelectorAll('#chat-items .chat-item').length,1);
 fail=false;d.getElementById('chat-load-retry').click();await new Promise(setImmediate);
 assert.equal(d.getElementById('chat-load-status').hidden,true);assert.equal(d.querySelectorAll('#chat-items .chat-item').length,1);
 console.log('Chats render with hung secondary services and missing location asset; failed refresh preserves list and Retry recovers');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
