const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM('<section id="driver-route"></section>',{runScripts:'outside-only'}),w=dom.window,d=w.document;
w.eval(fs.readFileSync('app/static/driver-route.js','utf8'));
const stop={id:'one',telefono:'50760000001',nombre:'Cliente de prueba',trackings:['TRACK-1'],direccion:'Calle 1',zona:'centro',cargada:true,token_entrega:'a'.repeat(64)};
let state={fecha:'2026-11-19',zona:'todas',paradas:[stop],pendientes:[],sin_programar:[],usuario:'alexander',consultado_en:'2026-11-19T12:00:00Z',puede_recorrer:true,bloqueos_recorrido:[]},accept=false,fail=false;
const posts=[];
const ui=w.CubicoDriverRoute.init({confirm:()=>accept,get:async()=>({ok:true,json:async()=>state}),post:async(path,body)=>{posts.push({path,body});if(fail)throw Error('Sin conexión');state={...state,paradas:[],puede_recorrer:false};return {ok:true,json:async()=>({status:'ok'})}}});
const tick=()=>new Promise(r=>setImmediate(r));
(async()=>{
 await ui.load();d.querySelector('[data-route-complete]').click();await tick();assert.equal(posts.length,0,'cancel must be read-only');
 accept=true;d.querySelector('[data-route-complete]').click();await tick();
 assert.equal(posts.length,1);assert.equal(posts[0].body.entrega_token,'a'.repeat(64));assert.equal(posts[0].body.accion,'entregar');
 assert.match(d.querySelector('[data-route-status]').textContent,/Entrega registrada/);assert.equal(d.querySelector('[data-route-complete]'),null);
 state={...state,paradas:[stop]};fail=true;await ui.load();d.querySelector('[data-route-complete]').click();await tick();
 assert.match(d.querySelector('[data-route-status]').textContent,/revisa Entregadas antes de repetir/);assert.equal(d.querySelector('[data-route-complete]'),null,'uncertain write must block blind retries');
 w.close();console.log('Delivery completion: explicit confirmation, exact case token, successful removal and uncertain-result blocking passed');
})().catch(e=>{console.error(e);w.close();process.exitCode=1});
