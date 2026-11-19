/* Fixture-only checks: no real customer data, payments or messages. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const ficha={clave:'fixture-delivery',token:'fixture-token',direccion:'Residencial El Bosque, calle El Laurel, casa 17 H. Entrada por la garita principal.',barrio:'El Bosque',zona:'centro',ubicacion_url:'https://maps.app.goo.gl/fixture',referencias:'Avisar en recepción',dia_solicitado:'lunes',fecha_solicitada:'2026-11-23',horario_solicitado:'Antes de las 9:00',fecha_confirmada:'2026-11-23',hora_desde:'07:00',hora_hasta:'09:00',prioridad:'normal',motivo_prioridad:'',faltantes:[],listo_para_coordinar:true};
const delivery={telefono:'50700000001',nombre:'Cliente domicilio de prueba',tipo:'domicilio',paquetes:'TRACKING-DOMICILIO',direccion:ficha.direccion,ficha_domicilio:ficha,pago_resuelto:true,pago_confirmado_sistema:true,paquetes_preparados:true,domicilio_coordinado:false,monto_pendiente:0,facturas_pendientes:[]};
const payment={telefono:'50700000002',nombre:'Cliente pago de prueba',tipo:'pago',paquetes:'TRACKING-PAGO',pago_reportado:true,pago_confirmado:false,pago_resuelto:false,monto_pendiente:13.50,monto_reportado:13.50,metodo_reportado:'Yappy',referencia_reportada:'PRUEBA-123',comprobante_media_id:'fixture-proof',facturas_pendientes:[{codigo:'FAC-TEST-1',saldo_pendiente:5.40,paquetes:[{tracking:'TRACKING-1'}]},{codigo:'FAC-TEST-2',saldo_pendiente:8.10,paquetes:[{tracking:'TRACKING-2'}]}]};
(async()=>{
 const options={headless:true};if(process.env.BROWSER_EXECUTABLE)options.executablePath=process.env.BROWSER_EXECUTABLE;
 if(process.env.BROWSER_ARGS_JSON)options.args=JSON.parse(process.env.BROWSER_ARGS_JSON);
 const browser=await chromium.launch(options);
 try{for(const width of [360,390,430,1280]){
  const context=await browser.newContext({viewport:{width,height:900},isMobile:width<760,hasTouch:true});
  const posts=[],errors=[];
  await context.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());
   const name=url.pathname==='/admin'?'panel-nuevo-diseno.html':url.pathname.startsWith('/static/')?url.pathname.slice(8):null;
   const filename=name&&path.join(__dirname,'app/static',name);
   if(url.host==='panel.test'&&filename&&fs.existsSync(filename))return route.fulfill({body:fs.readFileSync(filename),contentType:filename.endsWith('.html')?'text/html':filename.endsWith('.css')?'text/css':filename.endsWith('.js')?'text/javascript':'application/octet-stream'});
   if(url.host==='bot.cubico.com.pa'&&url.pathname.startsWith('/panel/')){
    const headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Allow-Methods':'GET, POST, OPTIONS'};
    if(req.method()==='OPTIONS')return route.fulfill({status:204,headers});
    let data={};
    if(req.method()==='POST'){posts.push({path:url.pathname,body:req.postDataJSON()});data={ficha};}
    else if(url.pathname==='/panel/solicitudes')data=[delivery,payment];
    else if(['/panel/conversaciones','/panel/actividad','/panel/oportunidades','/panel/alertas/paquetes','/panel/alertas/papelera'].includes(url.pathname))data=[];
    else if(url.pathname==='/panel/version')data=JSON.parse(fs.readFileSync('app/release.json','utf8'));
    return route.fulfill({json:data,headers});
   }
   return route.abort();
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://panel.test/admin');
  await page.evaluate(data=>{creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';solicitudes=data;showView('packages',false);renderSolicitudes()},[delivery,payment]);
  await page.locator('#request-search').fill('00000002');assert.equal(await page.locator('.request-card').count(),1);
  await page.locator('#request-search').fill('');assert.equal(await page.locator('.request-card').count(),2);
  await page.locator('.package-tab[data-package-filter=delivery]').click();assert.equal(await page.locator('.request-card').count(),1);
  assert.match(await page.locator('.request-card').innerText(),/Organizar domicilio/);
  await page.locator('.open-case').click();
  await page.locator('#delivery-case-form').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-address-summary]').innerText(),ficha.direccion);
  assert.equal(await page.locator('[data-delivery-field=direccion]').isVisible(),false);
  assert.equal(await page.locator('[data-delivery-field=zona]').isVisible(),true);
  assert.equal(await page.locator('[data-delivery-field=fecha_confirmada]').inputValue(),ficha.fecha_confirmada);
  assert.equal(await page.locator('[data-delivery-field=fecha_solicitada]').isVisible(),false);
  assert.equal(await page.locator('[data-delivery-field=hora_desde]').isVisible(),false);
  const clipped=await page.locator('#delivery-case input:visible,#delivery-case select:visible,#delivery-case textarea:visible').evaluateAll(els=>els.some(e=>{const a=e.getBoundingClientRect(),b=e.closest('label').getBoundingClientRect();return a.right>b.right+1||a.left<b.left-1}));
  assert.equal(clipped,false,`${width}px clipped delivery fields`);
  if(width<760)assert.equal(await page.locator('#package-rows').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`${width}px overflow`);
  if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,`delivery-${width}.png`),fullPage:true})}
  await page.locator('.delivery-address summary').click();
  await page.locator('[data-delivery-field=direccion]').fill('');
  await page.locator('.delivery-address summary').click();
  await page.locator('[data-delivery-save]').click();
  assert.equal(await page.locator('[data-delivery-field=direccion]').isVisible(),true,'invalid required field must open its editor');
  assert.equal(posts.length,0,'missing address must not save');
  await page.locator('[data-delivery-field=direccion]').fill('Dirección corregida de prueba');
  await page.locator('[data-delivery-save]').click();
  await page.waitForFunction(()=>document.getElementById('toast').textContent.includes('Ficha guardada'));
  assert.equal(posts.length,1);assert.match(posts[0].path,/\/domicilio$/);assert.equal(posts[0].body.datos.direccion,'Dirección corregida de prueba');assert.equal(posts[0].body.datos.fecha_solicitada,ficha.fecha_solicitada);
  await page.locator('#case-close').click();
  await page.locator('.package-tab[data-package-filter=payment]').click();
  await page.locator('.open-case').click();
  assert.equal(await page.locator('#delivery-case').isVisible(),false);
  assert.equal(await page.locator('#case-amount').innerText(),'$13.50');
  assert.equal(await page.locator('#case-reported').innerText(),'$13.50');
  const confirm=page.locator('[data-action=confirmar_pago]');assert.equal(await confirm.isDisabled(),true);
  await page.locator('[data-invoice-code="FAC-TEST-1"] input[type=checkbox]').check();
  assert.equal(await confirm.isDisabled(),true);
  await page.locator('[data-invoice-code="FAC-TEST-2"] input[type=checkbox]').check();
  assert.equal(await confirm.isDisabled(),false);
  page.once('dialog',async dialog=>{assert.match(dialog.message(),/banco/);await dialog.dismiss()});
  await confirm.click();assert.equal(posts.length,1,'cancelling confirmation must not register payment');
  assert.equal(await page.locator('#case-amount').innerText(),'$13.50','selection must not subtract from balance');
  assert.deepEqual(errors,[]);await context.close();console.log(`Solicitudes ${width}px: search, categories, compact domicile, separate preferences, safe save and multi-invoice payment guards passed`);
 }}finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
