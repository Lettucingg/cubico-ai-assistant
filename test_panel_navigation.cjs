/* NODE_PATH=/path/to/node_modules node test_panel_navigation.cjs */
const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM('<div class="app"><aside class="sidebar"><nav class="nav"><button data-view="overview"><svg><path/></svg></button><button data-view="chats">Chats</button></nav></aside><main><header class="topbar"></header><section id="chats" class="active"><div class="inbox"></div></section></main></div>',{runScripts:'outside-only'});
const w=dom.window,d=w.document,nav=d.querySelector('.sidebar'),button=d.querySelector('[data-view=overview]');
w.matchMedia=()=>({matches:true});w.requestAnimationFrame=cb=>cb();w.visualViewport={height:844,offsetTop:0,scale:1,addEventListener(){}};nav.getBoundingClientRect=()=>({height:90});d.querySelector('.inbox').getBoundingClientRect=()=>({top:150});
w.eval(fs.readFileSync('app/static/panel-mobile-layout.js','utf8'));const calls=[],layout=w.CubicoMobileLayout.init(d,id=>calls.push(id));
function pointer(type,target,x=10,y=10,pointerType='touch'){const e=new w.Event(type,{bubbles:true,cancelable:true});Object.assign(e,{pointerId:1,pointerType,isPrimary:true,clientX:x,clientY:y});target.dispatchEvent(e)}
for(const pointerType of ['touch','pen']){
 pointer('pointerdown',button,10,10,pointerType);const original=nav.style.top;w.visualViewport.height=620;layout.update();assert.equal(nav.style.top,original);pointer('pointerup',button,10,10,pointerType);assert.equal(calls.at(-1),'overview');const count=calls.length;button.dispatchEvent(new w.MouseEvent('click',{bubbles:true,detail:1}));assert.equal(calls.length,count);assert.equal(nav.style.top,'530px');
}
const count=calls.length;pointer('pointerdown',button);pointer('pointermove',w,40,40);pointer('pointerup',button,40,40);button.dispatchEvent(new w.MouseEvent('click',{bubbles:true,detail:1}));assert.equal(calls.length,count);
pointer('pointerdown',button);pointer('pointercancel',w);w.visualViewport.height=844;layout.update();assert.equal(nav.style.top,'754px');assert.equal(calls.length,count);
button.dispatchEvent(new w.MouseEvent('click',{bubbles:true,detail:0}));assert.equal(calls.length,count+1); // Keyboard activation remains available.
w.matchMedia=()=>({matches:false});pointer('pointerdown',button,10,10,'mouse');pointer('pointerup',button,10,10,'mouse');d.querySelector('[data-view=chats]').click();assert.equal(calls.at(-1),'chats');
console.log('Navigation taps: touch/pen, stable target, no duplicate, drag/cancel, keyboard and desktop passed');dom.window.close();
