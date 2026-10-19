/* Native click navigation, including recovery after cancelled pointer gestures. */
const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM('<div class="app"><aside class="sidebar"><nav class="nav"><button data-view="overview"><svg><path/></svg></button><button data-view="chats">Chats</button><button data-view="costs" disabled>Costos</button></nav></aside><main><header class="topbar"></header><section id="chats" class="active"><div class="inbox"></div></section></main></div>',{runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window,d=w.document,nav=d.querySelector('.sidebar'),button=d.querySelector('[data-view=overview]');
w.matchMedia=()=>({matches:true});w.requestAnimationFrame=cb=>cb();w.visualViewport={height:844,offsetTop:0,scale:1,addEventListener(){}};nav.getBoundingClientRect=()=>({height:90});d.querySelector('.inbox').getBoundingClientRect=()=>({top:150});
w.eval(fs.readFileSync('app/static/panel-mobile-layout.js','utf8'));const calls=[],layout=w.CubicoMobileLayout.init(d,id=>calls.push(id));
function pointer(type,target,x=10,y=10,pointerType='touch'){const e=new w.Event(type,{bubbles:true,cancelable:true});Object.assign(e,{pointerId:1,pointerType,isPrimary:true,clientX:x,clientY:y});target.dispatchEvent(e);return e}
function click(target=button,detail=1){const e=new w.MouseEvent('click',{bubbles:true,cancelable:true,detail});target.dispatchEvent(e);return e}
for(const pointerType of ['touch','pen','mouse']){
 const count=calls.length;pointer('pointerdown',button,10,10,pointerType);assert.equal(nav.style.top,'auto');assert.equal(nav.style.bottom,'0px');
 w.visualViewport.height=620;layout.update();assert.equal(nav.style.top,'auto');assert.equal(nav.style.bottom,'0px');
 const up=pointer('pointerup',button,10,10,pointerType);assert.equal(up.defaultPrevented,false);assert.equal(calls.length,count);
 assert.equal(click().defaultPrevented,false);assert.equal(calls.length,count+1);
}
// Browser cancels a gesture during scroll; no click is generated. The next
// real click must work, even when it follows immediately on the same button.
let count=calls.length;pointer('pointerdown',button);pointer('pointermove',w,40,40);pointer('pointercancel',w);assert.equal(calls.length,count);click();assert.equal(calls.length,count+1);
count=calls.length;pointer('pointerdown',button);pointer('pointerup',w);layout.update();click();assert.equal(calls.length,count+1);
count=calls.length;click(button,0);assert.equal(calls.length,count+1); // Keyboard / assistive tech.
click(button.querySelector('path'));assert.equal(calls.at(-1),'overview'); // Nested SVG target.
count=calls.length;click(d.querySelector('[data-view=costs]'));assert.equal(calls.length,count); // Disabled native control.
w.matchMedia=()=>({matches:false});layout.update();d.querySelector('[data-view=chats]').click();assert.equal(calls.at(-1),'chats');assert.equal(nav.style.top,'');assert.equal(nav.style.bottom,'');
console.log('Native navigation: stable bar, touch/pen/mouse click, cancelled scroll recovery, outside release, keyboard, SVG target and desktop passed');dom.window.close();
