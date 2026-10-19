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
     if(url.pathname==='/panel/costos')data=costs;
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

   await page.evaluate(c=>{creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';
     const names=['Ana Pérez','Carlos Méndez','María López','Jorge Díaz','Luis Torres','Teresa Ruiz','Daniel Ríos','Lucía Gómez'];
     renderLista(names.map((nombre,i)=>({...c,nombre,telefono:i?String(50700000000+i):c.telefono,tiene_no_leidos:i<2,necesita_atencion_humana:i===2,ultimo_mensaje_cliente:{contenido:i?'Gracias, quedó todo claro.':'Perfecto, paso esta tarde.',timestamp:'2026-10-19T21:40:00Z'}})));showView('chats');},conversation);
   const rowHeight=await page.locator('.chat-item').first().evaluate(el=>el.getBoundingClientRect().height);
   assert(rowHeight<=95,'Chat rows must remain compact');
   await page.locator('.chat-item').first().click();
   await page.waitForFunction(()=>document.getElementById('messages').textContent.includes('Consulta de prueba'));
   await page.evaluate(()=>{document.getElementById('conv-name').textContent='Ana Pérez';renderMensajes([
     {role:'user',content:'Hola, ¿ya puedo retirar mi paquete?',timestamp:'2026-10-19T21:40:00Z'},
     {role:'assistant',autor_tipo:'bruno',content:'Sí, tu paquete está listo para retirar.',timestamp:'2026-10-19T21:41:00Z',estado_entrega:'delivered'},
     {role:'user',content:'Perfecto, paso esta tarde.',timestamp:'2026-10-19T21:42:00Z'},
     {role:'assistant',autor_tipo:'bruno',content:'¡Te esperamos, Ana!',timestamp:'2026-10-19T21:42:00Z',estado_entrega:'read'}]);});
   assert.equal(await page.locator('#bruno-panel').getAttribute('open'),null);
   assert(await page.locator('#bruno-panel').evaluate(el=>el.getBoundingClientRect().height<45),'Bruno entry must stay compact');
   await page.locator('#bruno-panel > summary').click();assert.equal(await page.locator('#bruno-question').isVisible(),true);
   await page.locator('#bruno-panel > summary').click();
   const sendRect=await page.locator('#send').boundingBox(),editor=await page.locator('#message-input').boundingBox();
   assert(editor.width>=120,'Composer text field too narrow');assert(sendRect.y>=0&&sendRect.y+sendRect.height<=height,'Send button outside viewport');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'Page overflow');
   assert.equal(await page.locator('.message-delivery.read').getAttribute('title'),'Leído');
   await page.locator('#chat-actions-toggle').click();assert.equal(await page.locator('#customer-panel').isVisible(),true);
   await page.locator('#customer-close').click();
   if(screenshotDir){fs.mkdirSync(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,`chat-${width}.png`)})}
   if(width<761){await page.locator('#message-input').fill('Mensaje largo de prueba. '.repeat(40));await page.setViewportSize({width,height:480});await page.waitForFunction(()=>document.body.classList.contains('chat-editor-open'));
     await page.waitForFunction(()=>{const r=document.getElementById('send').getBoundingClientRect();return r.y>=0&&r.bottom<=innerHeight},null,{timeout:3000});
     await page.locator('#chat-editing-done').click();await page.setViewportSize({width,height});
     await page.locator('#mobile-chat-back').click();assert.equal(await page.locator('.chat-list').isVisible(),true);}
   assert.deepEqual(errors,[],`${width}px: JavaScript errors`);
   console.log(`${width}px: compact chat list, Bruno, delivery marks, management, composer fit and mobile keyboard passed`);
  }finally{await browser.close()}
 }
})().catch(e=>{console.error(e);process.exitCode=1});
