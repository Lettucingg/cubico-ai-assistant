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
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
