/* NODE_PATH=/path/to/node_modules node test_panel_design.cjs (jsdom is a test dependency). */
const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const html=fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8');
const dom=new JSDOM(html,{url:'https://panel.test/admin',runScripts:'outside-only'}),w=dom.window,d=w.document;
w.scrollTo=()=>{};w.matchMedia=()=>({matches:false});w.HTMLElement.prototype.scrollIntoView=()=>{};
w.URL.createObjectURL=()=> 'blob:test';w.URL.revokeObjectURL=()=>{};w.requestAnimationFrame=cb=>cb();
const fixtures={
 conversaciones:[{telefono:'5071',nombre:'Lissete',tiene_no_leidos:true,necesita_atencion_humana:false,ultimo_mensaje_cliente:{id:1,contenido:'Hola',timestamp:new Date().toISOString()},ultimo_mensaje:{contenido:'Hola'}},{telefono:'5072',nombre:'Cliente',tiene_no_leidos:false,necesita_atencion_humana:true,motivo_escalamiento:'Revisar caso',ultimo_mensaje_cliente:{id:2,contenido:'Consulta',timestamp:new Date().toISOString()}}],
 solicitudes:[{telefono:'5071',nombre:'Lissete',tipo:'retiro',pago_reportado:true,pago_confirmado:false,requiere_verificacion:true,requiere_factura:true,actualizado_en:new Date().toISOString(),monto_reportado:2.4},{telefono:'5072',nombre:'Cliente',tipo:'domicilio',direccion:'Calle de prueba',actualizado_en:new Date().toISOString()}],
 oportunidades:[{id:1,empresa:'Arthur',estado:'nueva',telefono:'5071',resumen:'Envíos de libros',actualizada_en:new Date().toISOString()},{id:2,empresa:'Otra empresa',estado:'en_revision',telefono:'5072',resumen:'Cotización'}],
 resumen:{conversaciones_hoy:2,atencion_humana:1,retiros:1,domicilios:1,pagos_pendientes:1,listos:0,oportunidades_activas:2,tokens_totales:10,costo_usd:0.01},
 uso:{conversaciones:2,costo_usd:.03,tokens_totales:30,input_tokens:20,output_tokens:10,chats:[],dias:[{fecha:'2026-10-04',costo_usd:.01},{fecha:'2026-10-05',costo_usd:.02}]},
 perfil:{usuario:'alexander',nombre:'Alex',foto:null},
 'informes-diarios':[{id:1,tipo:'mañana',creado_en:new Date().toISOString(),contenido:'Informe de prueba'},{id:2,tipo:'tarde',creado_en:'2020-01-01T22:00:00Z',contenido:'Informe anterior'}]
};
let archived=[],posts=[];
w.fetch=async(url,options={})=>{const path=new URL(url).pathname;let data;
 if(options.method==='POST')posts.push(path);
 if(path==='/panel/perfil'&&options.method==='PUT')fixtures.perfil=JSON.parse(options.body);
 if(path==='/panel/perfil/contrasena')data={status:'ok'};
 else
 if(path==='/panel/alertas/papelera')data=archived;
 else if(path==='/panel/alertas/archivar'){data={...JSON.parse(options.body),id:archived.length+1,usuario:'alexander',creado_en:new Date().toISOString()};archived.push(data)}
 else if(path.match(/alertas\/\d+\/restaurar/)){archived=archived.filter(a=>a.id!==Number(path.split('/').at(-2)));data={restaurada:true}}
 else if(path.startsWith('/panel/conversacion/'))data={historial:[{role:'user',content:'Hola',timestamp:new Date().toISOString()}]};
 else data=fixtures[path.split('/').at(-1)]||{};
 return {ok:true,status:200,json:async()=>structuredClone(data)};
};
for(const f of ['panel-personalization.js','daily-report.js','alert-management.js'])w.eval(fs.readFileSync('app/static/'+f,'utf8'));
const inline=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];new Function(inline);
w.eval(inline+`\nwindow.seedDesign=()=>{creds='test';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';};`);
const tick=()=>new Promise(setImmediate);
(async()=>{
 w.seedDesign();await w.refrescarPanel();
 assert.equal(d.getElementById('nav-count-chats'),null);assert.equal(d.getElementById('chat-total-count').textContent,'2');
 d.querySelector('[data-chat-filter-tab="sin_leer"]').click();assert.equal(d.querySelectorAll('#chat-items .chat-item').length,1);
 d.querySelector('[data-chat-filter-tab="humano"]').click();assert.equal(d.querySelector('#chat-items .chat-name b').textContent,'Cliente');
 d.querySelector('[data-chat-filter-tab="todas"]').click();await w.abrirChat('5071');
 d.getElementById('chat-actions-toggle').click();assert.equal(d.getElementById('customer-panel').getAttribute('role'),'dialog');assert.ok(d.getElementById('customer-backdrop').classList.contains('open'));
 d.getElementById('customer-close').click();assert.ok(!d.getElementById('customer-panel').classList.contains('mobile-open'));
 w.showView('packages');await tick();assert.equal(d.querySelectorAll('.request-card').length,2);
 d.querySelector('.open-case').click();assert.ok(d.querySelector('.payment-panel').classList.contains('has-case'));assert.equal(d.querySelector('[data-action="confirmar_pago"]').disabled,true);
 d.getElementById('case-close').click();assert.ok(!d.querySelector('.payment-panel').classList.contains('has-case'));
 w.aplicarFiltroSolicitud('delivery');assert.equal(d.querySelectorAll('.request-card').length,1);
 w.showView('opportunities');await tick();assert.equal(d.querySelectorAll('.opportunity-column').length,3);
 d.querySelector('.opportunity-item').click();assert.ok(d.querySelector('.opportunity-layout').classList.contains('has-opportunity'));
 assert.ok(d.querySelector('.lead-heading #opportunity-close svg'));assert.equal(d.querySelector('.lead-heading #opportunity-close').getAttribute('aria-label'),'Cerrar detalle de oportunidad');d.getElementById('opportunity-close').click();assert.ok(!d.querySelector('.opportunity-layout').classList.contains('has-opportunity'));
 w.aplicarFiltroOportunidad('new');assert.equal(d.querySelectorAll('.opportunity-column').length,1);assert.ok(d.getElementById('opportunity-items').classList.contains('single-stage'));assert.equal(d.getElementById('opportunity-items').style.getPropertyValue('--opportunity-columns'),'1');
 assert.equal(w.tituloOportunidad({empresa:'Proveedorpro (https://proveedorpro.com/app/products)'}),'Proveedorpro');
 w.aplicarFiltroOportunidad('active');assert.equal(d.getElementById('opportunity-items').classList.contains('single-stage'),false);assert.equal(d.getElementById('opportunity-items').style.getPropertyValue('--opportunity-columns'),'3');
 w.showView('costs');await tick();assert.ok(d.querySelector('#cost-chart polyline'));
 w.showView('settings');await w.cargarPerfilCuenta();assert.equal(d.getElementById('account-name').value,'Alex');d.getElementById('account-name').value='Alexander Cúbico';d.getElementById('account-profile-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();assert.equal(d.getElementById('account-profile-status').textContent,'Perfil guardado.');assert.match(d.getElementById('settings-shortcut').textContent,/AC/);
 d.getElementById('account-password-current').value='old-password';d.getElementById('account-password-new').value='nueva-segura-123';d.getElementById('account-password-confirm').value='diferente';d.getElementById('account-password-form').dispatchEvent(new w.Event('submit',{cancelable:true}));assert.match(d.getElementById('account-password-status').textContent,/no coinciden/);assert.equal(posts.includes('/panel/perfil/contrasena'),false);d.getElementById('account-password-confirm').value='nueva-segura-123';d.getElementById('account-password-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();assert.match(d.getElementById('account-password-status').textContent,/actualizada/);assert.equal(d.getElementById('account-password-new').value,'');
 d.querySelector('[data-chat-background="brand"]').click();assert.equal(d.body.dataset.chatBackground,'brand');assert.equal(w.localStorage.getItem('cubico.panel.background.v1'),'brand');
 w.CubicoPersonalization.init(d,w.localStorage);assert.equal(d.body.dataset.chatBackground,'brand');
 d.getElementById('sound-toggle').click();assert.match(d.getElementById('sound-toggle').textContent,/silenciado/);
 w.showView('overview');await w.cargarResumen();assert.equal(d.querySelectorAll('#daily-reports-list .report-preview').length,1);d.getElementById('daily-reports-history-toggle').click();assert.equal(d.getElementById('daily-reports-history').hidden,false);
 d.querySelector('#daily-reports-history .daily-report-open').click();assert.ok(d.getElementById('modal-informe-diario').classList.contains('open'));d.getElementById('daily-report-close').click();
 w.showView('alerts');await tick();d.querySelector('#alerts-list .alert-remove').click();await tick();assert.equal(archived.length,1);d.getElementById('alert-undo-button').click();await tick();assert.equal(archived.length,0);
 assert.equal(posts.filter(p=>/estado|enviar/.test(p)).length,0);
 console.log('All seven panel views: filters, drawer, payment guards, requests, pipeline, costs, preferences, reports/history, archive/undo passed');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
