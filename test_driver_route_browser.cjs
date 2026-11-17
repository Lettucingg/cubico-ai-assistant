/* Actual mobile layout, with fixture API only. No live messages or mutations. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const point=id=>({id,telefono:'50760000001',nombre:'Cliente de prueba '+id,codigo_cliente:'CBC-TEST',trackings:['TRACK-'+id,'TRACK-OTHER-'+id],direccion:'Avenida de prueba, edificio de prueba, recepción principal',zona:'centro',barrio:'San Francisco',referencias:'Entrada de visitantes, recepción en planta baja',ubicacion_url:'https://www.google.com/maps/search/?api=1&query=8.99,-79.5',fecha_confirmada:'2026-11-16',hora_desde:'07:00',hora_hasta:'08:00',horario_solicitado:'Antes de las 9',prioridad:'alta',motivo_prioridad:'Horario solicitado por el cliente',cargada:false});
(async()=>{
  const options={headless:true};if(process.env.BROWSER_EXECUTABLE)options.executablePath=process.env.BROWSER_EXECUTABLE;
  if(process.env.BROWSER_ARGS_JSON)options.args=JSON.parse(process.env.BROWSER_ARGS_JSON);
  const browser=await chromium.launch(options);
  try{
    for(const width of [360,390,430,1280]){
      const context=await browser.newContext({viewport:{width,height:844},hasTouch:true,isMobile:width<600});
      const posts=[],errors=[];
      let data={fecha:'2026-11-16',hoy:'2026-11-16',zona:'todas',usuario:'alexander',token:'fixture0',revision:0,consultado_en:'2026-11-16T12:00:00Z',paradas:[point('a'),point('b')],pendientes:[],sin_programar:[],puede_recorrer:false,bloqueos_recorrido:['Verifica los paquetes cargados']};
      await context.route('**/*',async route=>{
        const request=route.request(),url=new URL(request.url());
        if(url.host==='panel.test'){
          const filename=url.pathname==='/admin'?'panel-nuevo-diseno.html':url.pathname.startsWith('/static/')?url.pathname.slice(8):null;
          if(filename&&!filename.includes('..')){const local=path.join(__dirname,'app/static',filename);if(fs.existsSync(local)){const ext=path.extname(local);return route.fulfill({body:fs.readFileSync(local),contentType:ext==='.html'?'text/html':ext==='.js'?'text/javascript':ext==='.css'?'text/css':ext==='.svg'?'image/svg+xml':ext==='.png'?'image/png':'application/octet-stream'})}}
        }
        if(url.host==='bot.cubico.com.pa'&&url.pathname.startsWith('/panel/')){
          const headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Allow-Methods':'GET, POST, PUT, DELETE, OPTIONS'};
          if(request.method()==='OPTIONS')return route.fulfill({status:204,headers});
          if(url.pathname==='/panel/ruta'){
            if(request.method()==='POST'){posts.push(url.pathname);const body=request.postDataJSON();data.paradas=body.orden.map(id=>({...data.paradas.find(p=>p.id===id),cargada:body.cargadas.includes(id)}));data.puede_recorrer=data.paradas.every(p=>p.cargada);data.bloqueos_recorrido=data.puede_recorrer?[]:['Verifica los paquetes cargados'];data.token='fixture'+(++data.revision)}
            return route.fulfill({json:data,headers});
          }
          let result={};
          if(['/panel/solicitudes','/panel/conversaciones','/panel/actividad','/panel/oportunidades','/panel/alertas/paquetes','/panel/alertas/papelera','/panel/informes-diarios'].includes(url.pathname))result=[];
          if(url.pathname==='/panel/uso')result={chats:[],dias:[]};
          if(url.pathname==='/panel/version')result=JSON.parse(fs.readFileSync('app/release.json','utf8'));
          return route.fulfill({json:result,headers});
        }
        return route.abort();
      });
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.goto('https://panel.test/admin');
      await page.evaluate(()=>{creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';showView('packages')});
      await page.locator('#packages [data-view=route]').click();
      await page.waitForSelector('.route-stop');
      assert.equal(await page.locator('[data-route-start]').isDisabled(),true);
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,`${width}px list overflows`);
      const undersized=await page.locator('#driver-route .btn').evaluateAll(items=>items.filter(el=>el.getBoundingClientRect().height<44).map(el=>el.textContent));
      assert.deepEqual(undersized,[],`${width}px small driver controls`);
      await page.locator('[data-route-loaded=a]').check();
      await page.waitForFunction(()=>!document.querySelector('#driver-route[aria-busy=true]'));
      await page.locator('[data-route-loaded=b]').check();
      await page.waitForFunction(()=>!document.querySelector('[data-route-start]').disabled);
      await page.locator('[data-route-start]').click();
      await page.waitForFunction(()=>document.body.classList.contains('driver-focus'));
      const next=page.locator('[data-route-step="1"]');
      await next.scrollIntoViewIfNeeded();
      assert.equal(await next.evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}),true,`${width}px next control obstructed`);
      await next.click();
      await page.waitForFunction(()=>document.querySelector('.route-focus-heading')?.textContent.includes('Parada 2 de 2'));
      assert.equal(await page.locator('#driver-route').evaluate(el=>el.scrollWidth<=el.clientWidth+1),true,`${width}px focus overflows`);
      assert.deepEqual(posts,['/panel/ruta','/panel/ruta']);
      if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,'driver-route-'+width+'.png')})}
      await page.locator('[data-route-exit]').click();
      await page.locator('#route [data-view=packages]').click();
      assert.equal(await page.evaluate(()=>document.body.classList.contains('driver-focus')),false);
      assert.deepEqual(errors,[],`${width}px browser errors`);
      await context.close();
    }
    console.log('Chromium: 360/390/430/1280px route entry, load checklist, 44px targets, focus/next/exit and no overflow passed');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
