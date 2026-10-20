const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
(async()=>{
 const args=process.env.BROWSER_ARGS_JSON?JSON.parse(process.env.BROWSER_ARGS_JSON):[];
 for(const [width,height] of [[1440,900],[390,844]]){
  const browser=await chromium.launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE,args});
  try{
   const context=await browser.newContext({viewport:{width,height},isMobile:width<761,hasTouch:width<761});
   let item={id:1,empresa:'Empresa de prueba',estado:'nueva',telefono:'50700000000',resumen:'Envíos desde Miami',actualizada_en:'2026-10-20T20:00:00Z'},moves=[],reject=false;
   await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.host==='panel.test'){
     const file=url.pathname==='/admin'?'panel-nuevo-diseno.html':url.pathname.startsWith('/static/')?url.pathname.slice(8):null;
     const filename=file&&path.join(__dirname,'app/static',file);
     if(filename&&fs.existsSync(filename)){const ext=path.extname(filename);return route.fulfill({body:fs.readFileSync(filename),contentType:ext==='.html'?'text/html':ext==='.js'?'text/javascript':ext==='.css'?'text/css':ext==='.svg'?'image/svg+xml':'application/octet-stream'})}
    }
    if(url.host==='bot.cubico.com.pa'&&url.pathname.startsWith('/panel/')){
     const headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Authorization, Content-Type','Access-Control-Allow-Methods':'GET, POST, OPTIONS'};
     if(req.method()==='OPTIONS')return route.fulfill({status:204,headers});
     if(url.pathname==='/panel/oportunidad/1'){
      moves.push(req.postDataJSON());
      if(reject)return route.fulfill({status:409,headers,json:{detail:'Esta oportunidad está siendo revisada por otro operador.'}});
      item={...item,...req.postDataJSON(),asignado_a:'alexander'};return route.fulfill({headers,json:item});
     }
     const data=url.pathname==='/panel/oportunidades'?[item]:['/panel/alertas/paquetes','/panel/alertas/papelera','/panel/solicitudes','/panel/conversaciones'].includes(url.pathname)?[]:{};
     return route.fulfill({headers,json:data});
    }
    return route.abort();
   });
   const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('https://panel.test/admin');
   await page.evaluate(()=>{creds='fixture';usuarioActual='alexander';document.querySelector('.app').style.display='grid';document.getElementById('login-overlay').style.display='none';showView('opportunities')});
   await page.locator('.opportunity-item').waitFor();
   async function drag(destination){
    await page.evaluate(()=>{const board=document.getElementById('opportunity-items');window.scrollTo(0,board.getBoundingClientRect().top+scrollY-90)});
    const source=await page.locator(width<761?'.opportunity-item[data-id="1"] .opportunity-drag-handle':'.opportunity-item[data-id="1"] .opportunity-open').boundingBox();
    const target=await page.locator(`[data-drop-state="${destination}"]`).boundingBox();
    const start={x:source.x+source.width/2,y:source.y+source.height/2},end={x:target.x+target.width/2,y:target.y+Math.min(target.height/2,75)};
    if(width<761){const cdp=await context.newCDPSession(page);await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[start]});for(let i=1;i<=12;i++)await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:start.x+(end.x-start.x)*i/12,y:start.y+(end.y-start.y)*i/12}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach()}
    else {await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:12});await page.mouse.up()}
   }
   await drag('en_revision');await page.waitForFunction(()=>document.querySelector('.opportunity-item').dataset.state==='en_revision');
   assert.equal(moves.length,1);assert.equal(item.estado,'en_revision');assert.equal(await page.locator('.opportunity-layout').evaluate(e=>e.classList.contains('has-opportunity')),false);
   reject=true;await drag('nueva');await page.waitForFunction(()=>document.getElementById('opportunity-move-status').textContent.includes('otro operador'));
   assert.equal(moves.length,2);assert.equal(item.estado,'en_revision');assert.equal(await page.locator('.opportunity-item').getAttribute('data-state'),'en_revision');assert.equal(await page.locator('.opportunity-drag-ghost').count(),0);
   if(process.env.QA_SCREENSHOT_DIR){fs.mkdirSync(process.env.QA_SCREENSHOT_DIR,{recursive:true});await page.screenshot({path:path.join(process.env.QA_SCREENSHOT_DIR,`board-drag-${width}.png`),fullPage:true})}
   assert.deepEqual(errors,[]);console.log(`Real ${width<761?'touch':'mouse'} drag and rejected save passed at ${width}×${height}`);await context.close();
  }finally{await browser.close()}
 }
})().catch(e=>{console.error(e);process.exitCode=1});
