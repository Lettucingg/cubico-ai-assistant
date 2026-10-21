const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const options={headless:true,executablePath:process.env.BROWSER_EXECUTABLE,args:JSON.parse(process.env.BROWSER_ARGS_JSON||'[]')};
 for(const [width,height] of [[360,800],[390,844],[430,932],[1440,900]]){
  const browser=await chromium.launch(options);
  try{
   const context=await browser.newContext({viewport:{width,height},isMobile:width<761,hasTouch:width<761});
   await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.host==='panel.test'){
     const name=url.pathname==='/admin'?'panel-nuevo-diseno.html':url.pathname.startsWith('/static/')?url.pathname.slice(8):null,filename=name&&path.join(__dirname,'app/static',name);
     if(filename&&fs.existsSync(filename)){const ext=path.extname(filename);return route.fulfill({body:fs.readFileSync(filename),contentType:ext==='.html'?'text/html':ext==='.js'?'text/javascript':ext==='.css'?'text/css':ext==='.svg'?'image/svg+xml':'application/octet-stream'})}
    }
    if(url.host==='bot.cubico.com.pa'&&url.pathname.startsWith('/panel/'))return route.fulfill({headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type'},json:[]});
    return route.abort();
   });
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('https://panel.test/admin');
   await page.evaluate(()=>{
    creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';
    convs=[{telefono:'50700000000',nombre:'Cliente de prueba',necesita_atencion_humana:true,motivo_escalamiento:'Necesita confirmar qué incluye la tarifa para una carga comercial desde China: impuestos, seguro, preparación y entrega. No hay una solución confirmada.',ultimo_mensaje_cliente:{contenido:'¿Me pueden confirmar qué falta para coordinar la entrega?',timestamp:'2026-10-20T22:06:11.648Z'},ultimo_mensaje:{rol:'assistant',contenido:'Dejé la consulta al equipo para revisar los datos y confirmar una solución antes de coordinar la entrega. '.repeat(10),timestamp:'2026-10-20T22:06:15.472Z',estado_entrega:'read'}}];
    solicitudes=[{telefono:'50700000000',nombre:'Cliente de prueba',tipo:'retiro',pago_reportado:true,pago_confirmado:false,monto_reportado:58.75,tiene_comprobante:true,actualizado_en:'2026-10-20T22:00:00Z'}];
    papeleraCargada=true;showView('alerts');renderAlertas();
   });
   await page.locator('#alerts .alert-item').first().waitFor();
   await page.evaluate(()=>document.querySelectorAll('#alerts .attention-detail').forEach(e=>e.open=true));
   const measurements=await page.evaluate(()=>[...document.querySelectorAll('#alerts .alert-item')].map(card=>{
    const copy=card.querySelector('.alert-copy'),actions=card.querySelector('.alert-actions'),body=card.querySelector('.attention-body'),rect=card.getBoundingClientRect();
    return {card:rect.width,copy:copy.getBoundingClientRect().width,copyBottom:copy.getBoundingClientRect().bottom,actionsTop:actions.getBoundingClientRect().top,bodyClient:body?.clientHeight,bodyScroll:body?.scrollHeight,overflow:getComputedStyle(body).overflowY};
   }));
   if(width<761){
    for(const m of measurements){assert.ok(m.copy>=m.card-40,JSON.stringify(m));assert.ok(m.actionsTop>=m.copyBottom,JSON.stringify(m));assert.ok(m.bodyClient>=m.bodyScroll-1,JSON.stringify(m));assert.equal(m.overflow,'visible')}
    const filter=await page.locator('#alert-filter').boundingBox(),toolbar=await page.locator('.alert-toolbar').boundingBox();assert.ok(filter.width>=toolbar.width-35);
    assert.equal(await page.locator('#alert-filter').evaluate(e=>getComputedStyle(e).fontSize),'16px');
   }
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   assert.ok(!(await page.locator('#alerts .attention-quote small').first().textContent()).includes('T22:'));
   assert.match(await page.locator('#alerts .attention-quote small').last().textContent(),/Leído/);
   if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,`alerts-spacing-${width}.png`),fullPage:true})}
   if(width<761){
    await page.evaluate(()=>{showView('overview');document.querySelectorAll('#overview-alerts .attention-detail').forEach(e=>e.open=true)});
    assert.ok(await page.locator('#overview-alerts .alert-item').first().evaluate(card=>{const copy=card.querySelector('.alert-copy'),actions=card.querySelector('.alert-actions');return copy.getBoundingClientRect().width>=card.getBoundingClientRect().width-40&&actions.getBoundingClientRect().top>=copy.getBoundingClientRect().bottom}));
   }
   assert.deepEqual(errors,[]);console.log(`Alert content width, footer actions, natural scrolling and filters passed at ${width}×${height}`);await context.close();
  }finally{await browser.close()}
 }
})().catch(e=>{console.error(e);process.exitCode=1});
