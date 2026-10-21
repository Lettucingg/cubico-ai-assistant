const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8'),{url:'https://bot.cubico.com.pa/admin',runScripts:'outside-only'}),w=dom.window,d=w.document;
w.HTMLElement.prototype.scrollIntoView=()=>{};w.showView=id=>{d.body.dataset.view=id};w.URL.createObjectURL=()=> 'blob:test';w.URL.revokeObjectURL=()=>{};
let records=[],connections=[],calls=[],pending=null;const now='2026-10-21T15:00:00Z';
async function request(path,options){const url=new URL(path,'https://bot.cubico.com.pa'),method=options.method,body=options.body?JSON.parse(options.body):null;calls.push({path:url.pathname,method,body});let result={};
 if(url.pathname==='/panel/incidencias'&&method==='POST'){result={...body,id:1,codigo:'INC-0001',creador:'alexander',responsable:null,estado:'pendiente',revision:1,historial:[{usuario:'alexander',fecha:now,accion:'Creada'}],creado_en:now,actualizado_en:now};records=[result]}
 else if(url.pathname==='/panel/incidencias'){if(pending)return await pending;result={incidencias:records,usuarios:['alexander','luis']}}
 else if(url.pathname==='/panel/incidencias/1'&&method==='PATCH'){result={...records[0],...body,revision:2};records=[result]}
 else if(url.pathname==='/panel/incidencias/1')result=records[0];
 else if(url.pathname==='/panel/conexiones-ia'&&method==='POST'){result={id:'abc',nombre:body.nombre,token:'fixture-secret',permisos:body.permisos,vence_en:now};connections=[result]}
 else if(url.pathname==='/panel/conexiones-ia')result={conexiones:connections};
 else if(method==='DELETE'){connections=[];result={ok:true}}
 return {ok:true,json:async()=>result};
}
w.eval(fs.readFileSync('app/static/team-tools.js','utf8'));const tools=w.CubicoTeamTools;tools.init(request,()=>({view:'chats',context:'Chat 5071234567 · iPhone · 1.5.0'}));
const tick=()=>new Promise(setImmediate),submit=id=>d.getElementById(id).dispatchEvent(new w.Event('submit',{cancelable:true}));
(async()=>{
 d.body.dataset.view='chats';d.getElementById('message-input').value='Respuesta sin enviar';d.getElementById('tt-quick-report').click();assert.equal(d.body.dataset.view,'chats');assert.equal(d.getElementById('tt-inc-section').value,'chats');assert.match(d.getElementById('tt-inc-context').value,/iPhone/);
 d.getElementById('tt-inc-title').value='<img src=x onerror=1> Botón';d.getElementById('tt-inc-description').value='No funciona';
 d.getElementById('tt-inc-minimize').click();assert.equal(d.getElementById('tt-inc-new').hidden,true);assert.equal(d.getElementById('tt-report-resume').hidden,false);d.body.dataset.view='costs';d.getElementById('tt-report-resume').click();assert.equal(d.getElementById('tt-inc-section').value,'chats');assert.equal(d.getElementById('tt-inc-description').value,'No funciona');assert.equal(d.getElementById('message-input').value,'Respuesta sin enviar');
 d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(d.getElementById('tt-inc-new').hidden,true);d.getElementById('tt-quick-report').click();assert.equal(d.getElementById('tt-inc-description').value,'No funciona');submit('tt-inc-form');submit('tt-inc-form');await tick();await tick();assert.equal(calls.filter(c=>c.method==='POST').length,1);assert.equal(d.body.dataset.view,'costs');assert.equal(d.getElementById('tt-inc-new').hidden,true);assert.equal(d.getElementById('tt-report-resume').hidden,true);d.body.dataset.view='incidents';await tools.load();d.querySelector('[data-ticket]').click();await tick();assert.equal(d.querySelector('#tt-inc-detail img'),null);assert.equal(d.getElementById('tt-inc-detail').hidden,false);assert.match(d.getElementById('tt-inc-list').textContent,/Botón/);
 d.getElementById('tt-edit-state').value='en_revision';d.getElementById('tt-edit-owner').value='luis';d.getElementById('tt-edit-note').value='Revisando';submit('tt-edit-form');await tick();await tick();assert.equal(records[0].estado,'en_revision');assert.equal(records[0].responsable,'luis');
 d.getElementById('tt-ai-name').value='Mi Claude';submit('tt-ai-form');await tick();await tick();assert.equal(d.getElementById('tt-ai-token').textContent,'Bearer fixture-secret');assert.equal(w.localStorage.length,0);d.getElementById('tt-ai-hide').click();assert.equal(d.getElementById('tt-ai-secret').textContent,'');
 d.querySelector('[data-revoke]').click();await tick();await tick();assert.equal(connections.length,0);assert.match(d.getElementById('tt-ai-status').textContent,/revocado/);
 let finish;pending=new Promise(r=>finish=r);const late=tools.load();tools.reset();finish({ok:true,json:async()=>({incidencias:records,usuarios:[]})});await late;assert.equal(d.getElementById('tt-inc-list').textContent,'');assert.equal(d.getElementById('tt-inc-detail').textContent,'');
 tools.newReport();d.getElementById('tt-inc-title').value='Descartar este';d.getElementById('tt-inc-discard').click();assert.equal(d.getElementById('tt-report-resume').hidden,true);tools.newReport();assert.equal(d.getElementById('tt-inc-title').value,'');tools.reset();assert.equal(d.getElementById('tt-inc-new').hidden,true);assert.equal(d.getElementById('tt-report-resume').hidden,true);
 assert.equal(calls.some(c=>/enviar|control|responder/.test(c.path)),false);
 console.log('Incident context, duplicate-click guard, escaped content, status/owner updates, token concealment, revocation and logout race passed');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
