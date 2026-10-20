/* Real layout / touch regression. Requires Playwright and its Chromium browser.
 * NODE_PATH=/path/to/node_modules node test_panel_mobile_browser.cjs
 * Optional: BROWSER_EXECUTABLE=/path/to/chromium, BROWSER_ARGS_JSON='[...]',
 * QA_SCREENSHOT_DIR=/absolute/path (screenshots contain fixture data only).
 */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const base={costo_usd:3.216,eventos:297,llamadas_ia:224,mensajes:148,tokens:2426029,cache_read:3000,cache_write:5000,segundos_audio:60,sin_precio:1,errores:0,entregados:134,conversaciones_ia:20,promedio_por_chat:.16,latencia_media_ms:1200};
const costs={desde:'2026-10-01',hasta:'2026-10-18',totales:base,anterior:{...base,desde:'2026-09-13',hasta:'2026-09-30',costo_usd:2},serie:[{...base,fecha:'2026-10-01'}],proveedores:[{...base,nombre:'anthropic'}],funciones:[{...base,nombre:'respuesta_automatica'}],modelos:[{...base,nombre:'claude-sonnet-5'}],chats:[],horas:Array(24).fill(0),dias_semana:Array(7).fill(0),picos:{dia:{...base,fecha:'2026-10-01'},mes:{...base,fecha:'2026-10'},ano:{...base,fecha:'2026'}},gastos_confirmados:[],total_confirmado:0,historicos_sin_desglose:0};
const conversation={telefono:'50700000000',nombre:'Cliente de prueba',codigo_cliente_verificado:'CBC-TEST',tiene_no_leidos:true,ultimo_mensaje_cliente:{contenido:'Consulta de prueba',timestamp:'2026-10-19T15:00:00Z'},ultimo_mensaje:{contenido:'Consulta de prueba',rol:'user'}};
const screenshotDir=process.env.QA_SCREENSHOT_DIR;
(async()=>{
 const options={headless:true};if(process.env.BROWSER_EXECUTABLE)options.executablePath=process.env.BROWSER_EXECUTABLE;
 if(process.env.BROWSER_ARGS_JSON)options.args=JSON.parse(process.env.BROWSER_ARGS_JSON);
 for(const [width,height] of [[1440,900],[360,800],[390,844],[430,932]]){
  const browser=await chromium.launch(options);
  try{
   const context=await browser.newContext({viewport:{width,height},isMobile:width<761,hasTouch:width<761,deviceScaleFactor:1});
   let config={direccion:'',enlace:'',confirmada:false,latitud:null,longitud:null},textSends=[],locationSends=0;
   await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.host==='panel.test'){
     const name=url.pathname==='/admin'?'panel-nuevo-diseno.html':url.pathname.startsWith('/static/')?url.pathname.slice(8):null;
     const filename=name&&path.join(__dirname,'app/static',name);
     if(filename&&fs.existsSync(filename)){const ext=path.extname(filename);return route.fulfill({body:fs.readFileSync(filename),contentType:ext==='.html'?'text/html':ext==='.css'?'text/css':ext==='.js'?'text/javascript':ext==='.svg'?'image/svg+xml':'application/octet-stream'})}
    }
    if(url.host==='bot.cubico.com.pa'&&url.pathname.startsWith('/panel/')){
     const headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Allow-Methods':'GET, POST, PUT, DELETE, OPTIONS'};
     if(req.method()==='OPTIONS')return route.fulfill({status:204,headers});
     let data={};
     if(url.pathname==='/panel/configuracion/ubicacion'){if(req.method()==='PUT')config=req.postDataJSON();data=config;}
     else if(url.pathname==='/panel/ubicacion-local')data={disponible:config.confirmada,tipo:'enlace',revision:'fixture-pin',ubicacion:{name:'Cúbico',address:config.direccion},enlace:config.enlace};
     else if(url.pathname.startsWith('/panel/mejorar-borrador/'))data={telefono:conversation.telefono,borrador:'Puedes coordinar el retiro con Teresa.',enviado:false};
     else if(url.pathname.startsWith('/panel/enviar-texto/')){textSends.push(req.postDataJSON());data={status:'enviado'};}
     else if(url.pathname.startsWith('/panel/enviar-ubicacion/')){locationSends++;data={status:'enviado'};}
     else if(url.pathname==='/panel/costos')data=costs;
     else if(url.pathname==='/panel/conversaciones'||url.pathname==='/panel/actividad')data=[conversation];
     else if(['/panel/solicitudes','/panel/oportunidades','/panel/alertas/paquetes','/panel/alertas/papelera'].includes(url.pathname))data=[];
     else if(url.pathname.startsWith('/panel/conversacion/'))data={historial:[{role:'user',content:'Consulta de prueba',timestamp:'2026-10-19T15:00:00Z'}]};
     else if(url.pathname==='/panel/uso')data={chats:[],dias:[],conversaciones:0,costo_usd:0,tokens_totales:0};
     else if(url.pathname==='/panel/version')data=JSON.parse(fs.readFileSync('app/release.json','utf8'));
     return route.fulfill({json:data,headers});
    }
    return route.abort(); // No real API calls, fonts or third-party requests.
   });
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto('https://panel.test/admin');


   await page.evaluate(c=>{creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';renderLista([c]);showView('settings')},conversation);
   await page.locator('#local-location-address').fill('Local de prueba');await page.locator('#local-location-url').fill('https://maps.app.goo.gl/test-pin');
   await page.locator('#local-location-confirmed').check();await page.locator('#local-location-save').click();
   await page.waitForFunction(()=>document.getElementById('local-location-status').textContent.includes('Ya puedes enviarla'));
   assert.equal(config.confirmada,true);assert.equal(config.latitud,null);
   await page.locator('.sidebar .nav button[data-view=chats]').click();await page.locator('.chat-item').first().click();
   await page.locator('#message-input').fill('Coordina con Teresa para el retiro.');
   await page.locator('#bruno-panel > summary').click();await page.locator('#rewrite-text').click();
   await page.locator('#rewrite-preview').waitFor({state:'visible'});assert.equal(textSends.length,0);
   assert.equal(await page.locator('#message-input').inputValue(),'Coordina con Teresa para el retiro.');
   await page.locator('#rewrite-use').click();assert.equal(await page.locator('#message-input').inputValue(),'Puedes coordinar el retiro con Teresa.');
   await page.locator('#send').click();await page.waitForFunction(()=>document.getElementById('send-feedback-text').textContent.includes('aceptó'));
   assert.equal(textSends.length,1);assert.equal(textSends[0].mensaje,'Puedes coordinar el retiro con Teresa.');assert.equal(textSends[0].asistido,true);
   await page.locator('#attach-btn').click();await page.locator('#attach-location').click();
   await page.locator('[data-location-point]').waitFor({state:'visible'});
   assert.equal(await page.locator('[data-location-map]').getAttribute('href'),'https://maps.app.goo.gl/test-pin');
   assert.equal(locationSends,0);await page.locator('[data-location-send]').click();
   await page.waitForFunction(()=>document.querySelector('[data-location-status]').textContent.includes('aceptó'));
   assert.equal(locationSends,1);
   if(screenshotDir){fs.mkdirSync(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,`location-link-${width}.png`)})}
   await page.locator('[data-location-close]').click();assert.deepEqual(errors,[]);
   console.log(`${width}px: location setup/link preview/send and draft review/exact send passed (mock APIs only)`);
  }finally{await browser.close()}
 }
})().catch(e=>{console.error(e);process.exitCode=1});
