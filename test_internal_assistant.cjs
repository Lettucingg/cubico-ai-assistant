const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8'),{url:'https://panel.test',runScripts:'outside-only'}),w=dom.window,d=w.document;
w.eval(fs.readFileSync('app/static/internal-assistant.js','utf8'));
let queue=[],applied=[];
const tick=()=>new Promise(setImmediate);
const data=(phone='5071',draft='Tu saldo total pendiente es de $10.00.')=>({telefono:phone,codigo_cliente:'CBC-1',privado:true,consultado_en:'2026-10-15T23:00:00Z',respuesta:'Saldo actual: $10.00. <img src=x>',borrador:draft,datos:{facturas:{disponible:true,saldo_pendiente_total:10,facturas:[{codigo:'FAC-1',saldo_pendiente:5,estado:'pendiente'},{codigo:'FAC-2',saldo_pendiente:5,estado:'pendiente'}]},paquetes:{disponible:false,error:'No se pudo consultar'},ultimo_pago:{disponible:true,ultimo_pago:null}}});
const response=value=>({ok:true,json:async()=>value});
w.CubicoBruno.init((phone,body)=>new Promise(resolve=>queue.push({phone,body,resolve})),(text,phone)=>{if(d.getElementById('message-input').value.trim())return false;applied.push({text,phone});d.getElementById('message-input').value=text;return true});
(async()=>{
 w.CubicoBruno.setContext('5071');d.getElementById('bruno-question').value='Saldo';d.getElementById('bruno-prepare').click();d.getElementById('bruno-prepare').click();assert.equal(queue.length,1);assert.equal(queue[0].body.modo,'borrador');assert.equal(d.getElementById('bruno-prepare').disabled,true);
 w.CubicoBruno.setContext('5072');queue.shift().resolve(response(data()));await tick();assert.equal(d.getElementById('bruno-result').hidden,true);assert.equal(applied.length,0);
 w.CubicoBruno.setContext('5071');d.getElementById('bruno-question').value='Saldo';d.getElementById('bruno-prepare').click();queue.shift().resolve(response(data()));await tick();assert.equal(d.getElementById('bruno-result').hidden,false);assert.equal(d.querySelector('#bruno-answer img'),null);assert.match(d.getElementById('bruno-evidence').textContent,/FAC-2/);assert.equal(applied.length,0);
 d.getElementById('message-input').value='Mi borrador existente';d.getElementById('bruno-use').click();assert.equal(applied.length,0);assert.match(d.getElementById('bruno-status').textContent,/Conservamos tu borrador/);
 d.getElementById('message-input').value='';d.getElementById('bruno-use').click();assert.equal(applied.length,1);const meta=w.CubicoBruno.meta('5071');assert.equal(meta.codigo_cliente,'CBC-1');assert.equal(w.CubicoBruno.meta('5072'),undefined);assert.equal(d.getElementById('bruno-reviewed-label').hidden,false);
 w.CubicoBruno.setContext('5072');assert.equal(d.getElementById('bruno-reviewed-label').hidden,true);w.CubicoBruno.setContext('5071');assert.equal(d.getElementById('bruno-reviewed-label').hidden,false);w.CubicoBruno.sent('5071',meta);assert.equal(w.CubicoBruno.meta('5071'),undefined);
 d.getElementById('bruno-question').value='Consulta';d.getElementById('bruno-ask').click();queue.shift().resolve({ok:false,json:async()=>({detail:'Primero vincula al cliente'})});await tick();assert.match(d.getElementById('bruno-status').textContent,/vincula/);assert.equal(d.getElementById('bruno-result').hidden,true);assert.equal(d.getElementById('bruno-ask').disabled,false);
 d.getElementById('bruno-ask').click();w.CubicoBruno.reset();queue.shift().resolve(response(data()));await tick();assert.equal(d.getElementById('bruno-result').hidden,true);assert.equal(w.CubicoBruno.meta('5071'),undefined);
 console.log('Private assistant: duplicate queries, stale chat/auth results, safe rendering, preserved drafts, reviewed metadata and failures passed');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
