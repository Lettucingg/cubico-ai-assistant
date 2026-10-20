const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8'),{url:'https://panel.test',runScripts:'outside-only'}),w=dom.window,d=w.document;
w.eval(fs.readFileSync('app/static/location-settings.js','utf8'));
let resolve,loads=0,saved=[];
w.CubicoLocationSettings.init(async()=>{loads++;return await new Promise(r=>resolve=r)},async(path,body)=>{saved.push(body);return {ok:true,json:async()=>body}});
const $=id=>d.getElementById(id),result=()=>({ok:true,json:async()=>({direccion:'Local confirmado',enlace:'https://maps.app.goo.gl/pin',latitud:null,longitud:null,confirmada:true})});
(async()=>{
 let pending=w.CubicoLocationSettings.load();resolve(result());await pending;
 assert.equal($('local-location-address').value,'Local confirmado');assert($('local-location-confirmed').checked);
 pending=w.CubicoLocationSettings.load();$('local-location-address').value='Texto editado';$('local-location-address').dispatchEvent(new w.Event('input',{bubbles:true}));resolve(result());await pending;assert.equal($('local-location-address').value,'Texto editado');
 $('local-location-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await new Promise(setImmediate);
 assert.equal(saved.length,1);assert.equal(saved[0].latitud,null);assert.equal(saved[0].longitud,null);assert(saved[0].confirmada);
 $('local-location-lat').value='9';$('local-location-form').dispatchEvent(new w.Event('submit',{cancelable:true}));await new Promise(setImmediate);assert.equal(saved.length,1);assert.match($('local-location-status').textContent,/ambas coordenadas/);
 pending=w.CubicoLocationSettings.load();w.CubicoLocationSettings.reset();resolve(result());await pending;assert.equal($('local-location-address').value,'');
 console.log('Location configuration: explicit save, coordinates optional, paired coordinate validation and stale load/reset passed');w.close();
})().catch(e=>{console.error(e);w.close();process.exitCode=1});
