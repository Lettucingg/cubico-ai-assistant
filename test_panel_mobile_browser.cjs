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
 for(const [width,height] of [[360,800],[390,844],[430,932]]){
  const browser=await chromium.launch(options);
  try{
   const context=await browser.newContext({viewport:{width,height},isMobile:true,hasTouch:true,deviceScaleFactor:1});
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
   await page.evaluate(c=>{creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';renderLista([c]);showView('costs')},conversation);
   await page.waitForFunction(()=>document.getElementById('bc-kpis').textContent.includes('3.2160'));
   // Check real input geometry; CSS string assertions cannot catch native widths.
   await page.locator('.bc-controls').scrollIntoViewIfNeeded();
   const overflow=await page.locator('.bc-controls input,.bc-controls select').evaluateAll(inputs=>inputs.map(input=>{const r=input.getBoundingClientRect(),label=input.closest('label').getBoundingClientRect();return {id:input.id,left:r.left,right:r.right,labelLeft:label.left,labelRight:label.right}}).filter(r=>r.left<r.labelLeft-1||r.right>r.labelRight+1));
   assert.deepEqual(overflow,[],`${width}px: cost fields overflow their grid tracks`);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`${width}px: page horizontal overflow`);
   if(screenshotDir){fs.mkdirSync(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,`costs-${width}.png`)})}
   // A zero-opacity toast used to sit over the bottom bar and intercept taps.
   // Check actual hit targets, not just event dispatch on a synthetic button.
   const covered=await page.locator('.sidebar .nav button').evaluateAll(buttons=>buttons.filter(b=>{const r=b.getBoundingClientRect();if(!r.width||!r.height)return false;const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return !b.contains(hit)}).map(b=>b.dataset.view));
   assert.deepEqual(covered,[],`${width}px: invisible layer blocks navigation`);
   // All native taps must work after scrolling the Costs page.
   await page.locator('#bc-hours').scrollIntoViewIfNeeded();
   for(const [index,view] of ['overview','chats','packages','opportunities','costs','chats','overview','costs'].entries()){
    if(index===2)await page.evaluate(()=>say('Aviso de prueba visible'));
    if(index===5)await page.evaluate(()=>document.getElementById('toast').classList.remove('show'));
    await page.locator(`.sidebar .nav button[data-view="${view}"]`).tap();
    await page.waitForFunction(id=>document.querySelector('.view.active')?.id===id,view);
    assert.equal(await page.locator('.sidebar').evaluate(el=>Math.abs(el.getBoundingClientRect().bottom-innerHeight)<2),true);
   }
   // A cancelled scroll gesture on the bar must not poison the following tap.
   const cdp=await context.newCDPSession(page),rect=await page.locator('.sidebar .nav button[data-view=overview]').boundingBox();
   const x=rect.x+rect.width/2,y=rect.y+rect.height/2;
   await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});
   await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-70}]});
   await cdp.send('Input.dispatchTouchEvent',{type:'touchCancel',touchPoints:[]});
   await page.locator('.sidebar .nav button[data-view=chats]').tap();
   await page.waitForFunction(()=>document.getElementById('chats').classList.contains('active'));
   await page.locator('.chat-item').first().tap();await page.locator('#message-input').fill('Borrador conservado');
   await page.setViewportSize({width,height:480});
   await page.waitForFunction(()=>document.body.classList.contains('chat-editor-open'));
   assert.equal(await page.locator('.sidebar').isVisible(),false);
   await page.locator('#chat-editing-done').tap();await page.setViewportSize({width,height});
   await page.waitForFunction(()=>!document.body.classList.contains('chat-keyboard-open'));
   await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));
   assert.equal(await page.locator('#message-input').inputValue(),'Borrador conservado');
   await page.locator('.sidebar .nav button[data-view=costs]').tap();
   await page.waitForFunction(()=>document.getElementById('costs').classList.contains('active'));
   assert.deepEqual(errors,[],`${width}px: JavaScript errors`);
   console.log(`Chromium touch ${width}×${height}: bounded dates, all navigation tabs, cancelled swipe, keyboard-sized viewport and resume passed`);
   await context.close();
  }finally{await browser.close()}
 }
})().catch(e=>{console.error(e);process.exitCode=1});
