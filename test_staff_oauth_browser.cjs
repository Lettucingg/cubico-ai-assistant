// Browser regression: Referrer-Policy controls Origin on native POST forms.
const assert=require('node:assert/strict'),{execFileSync}=require('node:child_process'),{chromium}=require('playwright');
const python=process.env.QA_PYTHON||'python';
const pages=JSON.parse(execFileSync(python,['-c',`import json
from app.api.staff_oauth import page
data=[]
for phase in ('login','review'):
    state={'phase':phase,'review_nonce':'fixture','identity':{'usuario':'alexander','nombre':'Mi Claude','permisos':['incidencias']}}
    r=page('fixture','fixture',state)
    data.append({'phase':phase,'html':r.body.decode(),'headers':dict(r.headers)})
print(json.dumps(data))`],{encoding:'utf8',env:process.env}));
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.BROWSER_EXECUTABLE,headless:true,args:JSON.parse(process.env.BROWSER_ARGS_JSON||'[]').filter(x=>x!=='--disable-web-security')});
 try{
  const context=await browser.newContext(),p=await context.newPage();let active,posted;
  await p.route('https://bot.cubico.com.pa/**',async route=>{
   if(route.request().method()==='POST'){
    posted={headers:await route.request().allHeaders(),body:route.request().postData()};
    return route.fulfill({contentType:'text/html',body:'Recibido'});
   }
   return route.fulfill({contentType:'text/html',headers:active.headers,body:active.html});
  });
  // The old policy reproduces the production failure, even on a same-site form.
  active={html:'<form method="post" action="/panel/ia/oauth/consentir"><button>Enviar</button></form>',headers:{'Referrer-Policy':'no-referrer'}};
  await p.goto('https://bot.cubico.com.pa/panel/ia/oauth/consentir?solicitud=fixture');await p.getByRole('button').click();
  await p.waitForURL('**/consentir');assert.equal(posted.headers.origin,'null');
  for(active of pages){
   posted=null;await p.goto('https://bot.cubico.com.pa/panel/ia/oauth/consentir?solicitud=fixture');
   if(active.phase==='login')await p.locator('[name=clave]').fill('cubico_fixture_not_real');
   else await p.getByRole('checkbox').check();
   await p.getByRole('button',{name:active.phase==='login'?'Revisar permisos':'Autorizar a Claude',exact:true}).click();
   await p.waitForURL('**/consentir');assert.equal(posted.headers.origin,'https://bot.cubico.com.pa');
   assert.equal(new URLSearchParams(posted.body).get('csrf'),'fixture');
   assert.equal(new URL(p.url()).search,'');
  }
  console.log('Native browser POST: old policy reproduced null Origin; real login and consent forms preserve exact origin and CSRF.');
  // Intercept each redirect hop through CDP: Playwright route handlers only
  // cover the first URL in a redirected request. Never contact a real callback.
  await p.unrouteAll();
  const session=await context.newCDPSession(p),review=pages.find(x=>x.phase==='review');
  let target,policy,returned,interceptionError;
  session.on('Fetch.requestPaused',async event=>{
   try{
    const request=event.request,url=new URL(request.url);
    if(url.host!=='bot.cubico.com.pa'){
     returned=request;
     await session.send('Fetch.fulfillRequest',{requestId:event.requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'text/html'}],body:Buffer.from('Claude callback received').toString('base64')});
    }else if(request.method==='POST'){
     await session.send('Fetch.fulfillRequest',{requestId:event.requestId,responseCode:303,responseHeaders:[{name:'Location',value:target},{name:'Referrer-Policy',value:'no-referrer'}]});
    }else{
     const headers={...review.headers,'content-security-policy':policy};delete headers['content-length'];
     await session.send('Fetch.fulfillRequest',{requestId:event.requestId,responseCode:200,responseHeaders:Object.entries(headers).map(([name,value])=>({name,value})),body:Buffer.from(review.html).toString('base64')});
    }
   }catch(error){interceptionError=error}
  });
  await session.send('Fetch.enable',{patterns:[{urlPattern:'*'}]});
  async function authorize(){
   returned=null;
   await p.goto('https://bot.cubico.com.pa/panel/ia/oauth/consentir?solicitud=fixture');
   await p.getByRole('checkbox').check();
   await p.getByRole('button',{name:'Autorizar a Claude',exact:true}).click();
  }
  for(const blocked of ['old-policy','untrusted-target']){
   target=(blocked==='old-policy'?'https://claude.ai/api/mcp/auth_callback':'https://evil.invalid/callback')+'?code=fixture&state=fixture';
   policy=blocked==='old-policy'?review.headers['content-security-policy'].replace(/form-action[^;]+;/,"form-action 'self';"):review.headers['content-security-policy'];
   const failure=p.waitForEvent('console',{predicate:m=>m.text().includes('form-action')&&m.text().includes('blocked')});
   await authorize();await failure;assert.equal(returned,null);
  }
  for(const callback of ['https://claude.ai/api/mcp/auth_callback','https://claude.com/api/mcp/auth_callback']){
   target=callback+'?code=fixture&state=fixture';policy=review.headers['content-security-policy'];
   await authorize();await p.waitForURL(target);
   assert.equal(returned.method,'GET');assert.equal(returned.postData,undefined);
   assert.equal(returned.headers.Referer,undefined);
   assert.equal(await p.locator('body').textContent(),'Claude callback received');
  }
  assert.equal(interceptionError,undefined);
  await session.send('Fetch.disable');
  console.log('Native 303 navigation: reproduced the old CSP block; both official Claude callbacks load via GET without form data; untrusted destinations remain blocked.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
