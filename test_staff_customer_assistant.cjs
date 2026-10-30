const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8'),{url:'https://panel.test',runScripts:'outside-only'}),w=dom.window,d=w.document,$=id=>d.getElementById(id),tick=()=>new Promise(setImmediate);
const drawer=$('general-bruno-drawer');drawer.showModal=()=>{drawer.open=true};drawer.close=()=>{drawer.open=false};
w.eval(fs.readFileSync('app/static/general-assistant.js','utf8'));
let searches=[],queries=[];
const person=(code='CBC-0001')=>({codigo:code,tipo:'cbc',nombre:'Alexander <img src=x>',telefono_referencia:'…1111'});
const response=data=>({ok:true,json:async()=>data});
w.CubicoGeneralBruno.init(body=>new Promise(resolve=>queries.push({body,resolve})),q=>new Promise(resolve=>searches.push({q,resolve})));
const result=(data={})=>({telefono:null,privado:true,alcance:'cliente_interno',cliente:person(),consultado_en:new Date().toISOString(),respuesta:'Dirección configurada',borrador:'Dirección preparada',...data});
(async()=>{
 $('general-bruno-open').click();$('general-bruno-search').value='Alexander';$('general-bruno-search-button').click();assert.equal(searches[0].q,'Alexander');searches.shift().resolve(response({clientes:[person(),person('CBC-0002')]}));await tick();assert.equal($('general-bruno-customers').children.length,2);assert.equal(d.querySelector('#general-bruno-customers img'),null);
 $('general-bruno-customers').children[1].click();assert.match($('general-bruno-selected').textContent,/CBC-0002/);assert.equal(queries.length,0);
 $('general-bruno-question').value='Dame el casillero aéreo';$('general-bruno-prepare').click();assert.equal(queries[0].body.cliente_codigo,'CBC-0002');assert.equal(queries[0].body.cliente_tipo,'cbc');queries.shift().resolve(response(result({cliente:person('CBC-0002')})));await tick();assert.match($('general-bruno-source').textContent,/CBC-0002/);
 $('general-bruno-clear-customer').click();assert.equal($('general-bruno-selected').hidden,true);assert.equal($('general-bruno-output').hidden,true);
 $('general-bruno-question').value='Casillero de Alexander';$('general-bruno-ask').click();assert.equal(queries[0].body.cliente_codigo,undefined);queries.shift().resolve(response(result({alcance:'busqueda_clientes',cliente:undefined,clientes:[person(),person('CBC-0002')],borrador:''})));await tick();$('general-bruno-customers').children[0].click();assert.equal(queries[0].body.cliente_codigo,'CBC-0001');assert.equal(queries[0].body.pregunta,'Casillero de Alexander');queries.shift().resolve(response(result()));await tick();
 $('general-bruno-search').value='Roxana';$('general-bruno-search-button').click();w.CubicoGeneralBruno.reset();searches.shift().resolve(response({clientes:[person()]}));await tick();assert.equal($('general-bruno-customers').children.length,0);assert.equal($('general-bruno-selected').hidden,true);assert.equal($('general-bruno-search-button').disabled,false);
 console.log('Customer assistant: search/select, no first-match choice, escaped names, same question resumed, customer context clear and stale-auth rejection passed');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
