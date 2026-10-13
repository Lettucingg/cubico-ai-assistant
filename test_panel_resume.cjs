const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM('<div class="app"><aside class="sidebar"><nav class="nav"><button data-view="overview">Resumen</button></nav></aside><main><header class="topbar"></header><section id="chats" class="active"><div class="inbox"><textarea id="message-input"></textarea></div></section></main></div>',{runScripts:'outside-only'}),w=dom.window,d=w.document,nav=d.querySelector('.sidebar'),inbox=d.querySelector('.inbox'),input=d.getElementById('message-input');
w.matchMedia=()=>({matches:true});w.requestAnimationFrame=cb=>cb();const events={},timers=[];w.setTimeout=cb=>{timers.push(cb);return timers.length};w.clearTimeout=()=>{};let hidden=false,actualBottom=844;Object.defineProperty(d,'hidden',{get:()=>hidden});w.visualViewport={height:844,offsetTop:0,scale:1,addEventListener(type,cb){events[type]=cb}};nav.getBoundingClientRect=()=>({height:90,top:actualBottom-90,bottom:actualBottom});inbox.getBoundingClientRect=()=>({top:150});
w.eval(fs.readFileSync('app/static/panel-mobile-layout.js','utf8'));let navigations=0;const layout=w.CubicoMobileLayout.init(d,()=>navigations++);
assert.equal(nav.style.bottom,'0px');assert.equal(nav.style.top,'auto');assert.equal(inbox.style.getPropertyValue('--mobile-inbox-height'),'592px');
input.value='Mi borrador pendiente';input.focus();w.visualViewport.height=430;layout.update();assert.equal(d.body.classList.contains('chat-editor-open'),true);
// App is suspended with a touch still in flight and a reduced keyboard viewport.
const touch=new w.Event('pointerdown',{bubbles:true});Object.assign(touch,{pointerId:1,pointerType:'touch',isPrimary:true,clientX:10,clientY:10});d.querySelector('.nav button').dispatchEvent(touch);hidden=true;d.dispatchEvent(new w.Event('visibilitychange'));
hidden=false;d.dispatchEvent(new w.Event('visibilitychange'));
assert.equal(input.value,'Mi borrador pendiente');assert.equal(d.activeElement===input,false);assert.equal(d.body.classList.contains('chat-editor-open'),false);assert.equal(d.body.classList.contains('chat-keyboard-open'),false);
assert.equal(inbox.style.getPropertyValue('--mobile-inbox-height'),'592px');assert.equal(nav.style.bottom,'0px');assert.equal(navigations,0);
// Native geometry controls closed-keyboard layout even while Safari reports a stale viewport.
w.visualViewport.height=430;actualBottom=780;w.dispatchEvent(new w.PageTransitionEvent('pageshow',{persisted:true}));assert.equal(inbox.style.getPropertyValue('--mobile-inbox-height'),'528px');
actualBottom=844;timers.forEach(cb=>cb());assert.equal(inbox.style.getPropertyValue('--mobile-inbox-height'),'592px');
// Keyboard still works after resume, then restores through native bounds on blur.
input.focus();w.visualViewport.height=400;layout.update();assert.equal(d.body.classList.contains('chat-keyboard-open'),true);input.blur();layout.update();assert.equal(d.body.classList.contains('chat-keyboard-open'),false);assert.equal(inbox.style.getPropertyValue('--mobile-inbox-height'),'592px');
console.log('Resume: stale viewport, keyboard, visibility, bfcache, interrupted gesture, restored bounds and preserved draft passed');dom.window.close();
