const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8'),{url:'https://panel.test',runScripts:'outside-only'}),w=dom.window,d=w.document;
const drawer=d.getElementById('general-bruno-drawer');drawer.showModal=()=>{drawer.open=true};drawer.close=()=>{drawer.open=false};
w.eval(fs.readFileSync('app/static/general-assistant.js','utf8'));
let queue=[];const tick=()=>new Promise(setImmediate),$=id=>d.getElementById(id);
w.CubicoGeneralBruno.init(body=>new Promise(resolve=>queue.push({body,resolve})));
const response=(data={})=>({ok:true,json:async()=>({telefono:null,privado:true,alcance:'general',consultado_en:'2026-10-29T20:00:00Z',respuesta:'Texto <img src=x>',borrador:'Borrador',...data})});
(async()=>{
 $('general-bruno-open').click();assert.equal(drawer.open,true);$('general-bruno-question').value='Pagos';$('general-bruno-prepare').click();$('general-bruno-prepare').click();assert.equal(queue.length,1);assert.equal(queue[0].body.modo,'borrador');
 $('general-bruno-close').click();assert.equal(drawer.open,false);queue.shift().resolve(response());await tick();$('general-bruno-open').click();assert.equal($('general-bruno-output').hidden,false);assert.equal(d.querySelector('#general-bruno-answer img'),null);assert.equal($('message-input').value,'');
 $('general-bruno-ask').click();w.CubicoGeneralBruno.reset();queue.shift().resolve(response());await tick();assert.equal($('general-bruno-output').hidden,true);assert.equal($('general-bruno-draft').value,'');assert.equal($('general-bruno-ask').disabled,false);
 $('general-bruno-question').value='Reintento';$('general-bruno-ask').click();queue.shift().resolve({ok:false,json:async()=>({detail:'Fuente no disponible'})});await tick();assert.match($('general-bruno-status').textContent,/Fuente no disponible/);assert.equal($('general-bruno-question').value,'Reintento');assert.equal($('general-bruno-ask').disabled,false);
 $('general-bruno-ask').click();queue.shift().resolve(response({telefono:'50712345678'}));await tick();assert.equal($('general-bruno-output').hidden,true);assert.match($('general-bruno-status').textContent,/no corresponde/);
 console.log('General assistant: close/reopen, duplicate click, safe text, no send/editor writes, auth reset, failure recovery and wrong-context rejection passed');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
