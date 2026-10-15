const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const html=fs.readFileSync('app/static/panel-nuevo-diseno.html','utf8');
const body=html.slice(html.indexOf('    async function actualizarEstadoPush(){'),html.indexOf('    async function cambiarPush(){'));
const dom=new JSDOM('<p id="push-status"></p><button id="push-toggle"></button>',{url:'https://panel.test',runScripts:'outside-only'}),w=dom.window;
w.matchMedia=()=>({matches:false});w.Notification={permission:'granted'};
w.eval(`let pushSuscrito=false;let saveOK=true;let saves=0;
const entornoPushDisponible=()=>true;
const registroPush=async()=>({pushManager:{getSubscription:async()=>({toJSON:()=>({endpoint:'test',keys:{}})})}});
const apiGet=async()=>({ok:true,json:async()=>({disponible:true})});
const apiPost=async(path)=>{if(path!='/panel/push/suscripcion')throw Error('Unexpected path');saves++;return {ok:saveOK}};
${body}
window.state=()=>({pushSuscrito,saves});window.fail=()=>saveOK=false;`);
(async()=>{await w.actualizarEstadoPush();assert.equal(w.state().pushSuscrito,true);assert.equal(w.state().saves,1);assert.match(w.document.getElementById('push-status').textContent,/registrado en tu cuenta/);
w.fail();await w.actualizarEstadoPush();assert.equal(w.state().pushSuscrito,false);assert.match(w.document.getElementById('push-status').textContent,/No se pudo confirmar/);dom.window.close();console.log('Push registration confirmed server-side; failed save not shown as active: passed');})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1});
