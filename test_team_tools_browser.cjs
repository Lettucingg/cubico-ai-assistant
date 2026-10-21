const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{chromium}=require('playwright');
(async()=>{
 for(const width of [360,390,430,1440]){
  const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE,args:JSON.parse(process.env.BROWSER_ARGS_JSON||'[]')});
  try{
   const context=await browser.newContext({viewport:{width,height:900},isMobile:width<761,hasTouch:width<761});
   const now='2026-10-21T15:00:00Z';let ticket={id:1,codigo:'INC-0001',titulo:'El botón de alertas no responde en el celular',descripcion:'Abro una conversación, luego toco Alertas y no cambia de pantalla. '.repeat(8),esperado:'Abrir las alertas sin perder el borrador.',seccion:'chats',tipo:'problema',prioridad:'alta',estado:'pendiente',creador:'alexander',responsable:null,revision:1,contexto:'iPhone · v1.5.0',creado_en:now,actualizado_en:now,historial:[{usuario:'alexander',fecha:now,accion:'Creada'}]};let connections=[];
   await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.host==='panel.test'){
     const name=url.pathname==='/admin'?'panel-nuevo-diseno.html':url.pathname.startsWith('/static/')?url.pathname.slice(8):null,filename=name&&path.join(__dirname,'app/static',name);
     if(filename&&fs.existsSync(filename)){const ext=path.extname(filename);return route.fulfill({body:fs.readFileSync(filename),contentType:ext==='.html'?'text/html':ext==='.js'?'text/javascript':ext==='.css'?'text/css':'application/octet-stream'})}
    }
    if(url.host==='bot.cubico.com.pa'&&url.pathname.startsWith('/panel/')){
     if(req.method()==='OPTIONS')return route.fulfill({headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Allow-Methods':'GET, POST, PATCH, DELETE, OPTIONS'},body:''});
     let json=[];if(url.pathname==='/panel/incidencias'){
      if(req.method()==='POST')ticket={...ticket,...req.postDataJSON()};json=req.method()==='POST'?ticket:{incidencias:[ticket],usuarios:['alexander','luis']};
     }else if(url.pathname==='/panel/incidencias/1'){
      if(req.method()==='PATCH')ticket={...ticket,...req.postDataJSON(),revision:2};json=ticket;
     }else if(url.pathname==='/panel/conexiones-ia'){
      if(req.method()==='POST'){connections=[{id:'abc',nombre:'Mi Claude',permisos:['incidencias'],vence_en:'2027-01-19T15:00:00Z',token:'fixture-not-real'}];json=connections[0]}else json={conexiones:connections};
     }else if(url.pathname==='/panel/version')json=JSON.parse(fs.readFileSync('app/release.json','utf8'));
     return route.fulfill({headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type'},json});
    }
    return route.abort();
   });
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('https://panel.test/admin');
   await page.evaluate(()=>{creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';showView('incidents')});
   await page.locator('[data-ticket="1"]').waitFor();await page.locator('[data-ticket="1"]').click();await page.locator('#tt-edit-form').waitFor();
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   for(const selector of ['#tt-inc-detail','#tt-edit-note','#tt-filter-state']){const rect=await page.locator(selector).boundingBox();assert.ok(rect.x>=0&&rect.x+rect.width<=width+1,selector+JSON.stringify(rect))}
   if(width<761)assert.equal(await page.locator('#tt-edit-note').evaluate(e=>getComputedStyle(e).fontSize),'16px');
   await page.locator('#tt-edit-state').selectOption('en_revision');await page.locator('#tt-edit-owner').selectOption('luis');await page.locator('#tt-edit-note').fill('Confirmado; vamos a corregirlo.');await page.locator('#tt-edit-form button[type=submit]').click();await page.getByText('Seguimiento guardado.',{exact:true}).waitFor();assert.equal(ticket.estado,'en_revision');
   await page.evaluate(()=>{showView('chats');document.getElementById('message-input').value='Respuesta sin enviar'});await page.locator('#tt-quick-report').click();assert.equal(await page.evaluate(()=>document.body.dataset.view),'chats');await page.locator('#tt-inc-new').evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished)));const drawer=await page.locator('#tt-inc-new').boundingBox();assert.ok(drawer.x>=0&&drawer.x+drawer.width<=width+1&&drawer.y>=0&&drawer.height<=900,JSON.stringify(drawer));await page.locator('#tt-inc-minimize').click();const tab=await page.locator('#tt-report-resume').boundingBox();assert.ok(tab.width>=44&&tab.width<=48&&tab.height<=160&&tab.x+tab.width<=width+1&&tab.y>0&&tab.y+tab.height<800,JSON.stringify(tab));assert.equal(await page.locator('#tt-report-resume').getAttribute('aria-label'),'Continuar mi reporte');await page.locator('#tt-report-resume').click();assert.equal(await page.locator('#message-input').inputValue(),'Respuesta sin enviar');assert.equal(await page.locator('#tt-inc-section').inputValue(),'chats');
   if(width<761){const keyboard=await page.evaluate(()=>{const saved=Object.getOwnPropertyDescriptor(window,'visualViewport');Object.defineProperty(window,'visualViewport',{configurable:true,value:{height:420,offsetTop:80}});window.dispatchEvent(new Event('resize'));const drawer=document.getElementById('tt-inc-new').getBoundingClientRect(),close=document.getElementById('tt-inc-close').getBoundingClientRect();Object.defineProperty(window,'visualViewport',saved);window.dispatchEvent(new Event('resize'));return {top:drawer.top,bottom:drawer.bottom,closeTop:close.top,closeBottom:close.bottom}});assert.ok(keyboard.top>=80&&keyboard.bottom<=500&&keyboard.closeBottom<=keyboard.bottom,JSON.stringify(keyboard))}
await page.locator('#tt-inc-title').fill('Nueva incidencia');await page.locator('#tt-inc-description').fill('Un problema reproducible.');
   // Large phone screenshots are resized locally before the report is uploaded.
   const image=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=2200;c.height=2200;const ctx=c.getContext('2d'),image=ctx.createImageData(2200,2200);for(let i=0;i<image.data.length;i+=4){image.data[i]=(i*17)%251;image.data[i+1]=(i*29)%253;image.data[i+2]=(i*37)%255;image.data[i+3]=255}ctx.putImageData(image,0,0);return c.toDataURL('image/png').split(',')[1]});
   await page.locator('#tt-inc-file').setInputFiles({name:'captura.png',mimeType:'image/png',buffer:Buffer.from(image,'base64')});await page.getByText('Captura lista para adjuntar.',{exact:true}).waitFor();await page.locator('#tt-inc-form button[type=submit]').click();await page.waitForFunction(()=>document.getElementById('tt-inc-new').hidden);assert.equal(await page.evaluate(()=>document.body.dataset.view),'chats');assert.equal(await page.locator('#message-input').inputValue(),'Respuesta sin enviar');assert.match(ticket.captura,/^data:image\/(png|jpeg);base64,/);assert.ok(ticket.captura.length<=540000);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.evaluate(()=>{showView('settings')});await page.locator('#tt-ai-name').fill('Mi Claude');await page.locator('#tt-ai-form button[type=submit]').click();await page.locator('#tt-ai-token').waitFor();assert.match(await page.locator('#tt-ai-token').textContent(),/^Bearer /);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.locator('#tt-ai-hide').click();assert.equal(await page.locator('#tt-ai-secret').textContent(),'');
   if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.evaluate(()=>showView('chats'));await page.locator('#tt-quick-report').click();await page.locator('#tt-inc-description').fill('Aquí puedo describir el error mientras tengo la pantalla original a mano.');await page.locator('#tt-inc-new').evaluate(el=>Promise.all(el.getAnimations().map(a=>a.finished)));assert.equal(await page.locator('#tt-inc-new').evaluate(el=>getComputedStyle(el).opacity),'1');await page.locator('#tt-inc-minimize').click();await page.screenshot({animations:'disabled',path:path.join(process.env.QA_SCREENSHOT_DIR,`team-tools-${width}.png`),fullPage:true})}
   assert.deepEqual(errors,[]);console.log(`Incidents, editable follow-up, personal connection and no horizontal overflow at ${width}px`);await context.close();
  }finally{await browser.close()}
 }
})().catch(e=>{console.error(e);process.exitCode=1});
