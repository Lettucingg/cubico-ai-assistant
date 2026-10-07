const assert=require('node:assert/strict'),fs=require('node:fs'),{JSDOM}=require('jsdom');
const dom=new JSDOM('<div class="inbox"><textarea id="message-input" rows="1"></textarea><div id="draft-tools" hidden><button id="draft-select-all">Seleccionar</button><button id="draft-copy">Copiar</button></div></div>',{runScripts:'outside-only'}),w=dom.window,d=w.document,input=d.getElementById('message-input');
let contentHeight=44,viewportResize,sends=0,changed,copied,status;
Object.defineProperty(input,'scrollHeight',{get:()=>contentHeight});Object.defineProperty(d.querySelector('.inbox'),'clientHeight',{get:()=>600});
w.visualViewport={height:844,addEventListener:(event,cb)=>viewportResize=cb};
Object.defineProperty(w.navigator,'clipboard',{value:{writeText:async text=>copied=text},configurable:true});
w.eval(fs.readFileSync('app/static/chat-text-editor.js','utf8'));
const editor=w.CubicoTextEditor.init(d,{onSend:()=>sends++,onChange:text=>changed=text,onCopy:text=>status=text});
(async()=>{
 assert.equal(input.style.height,'44px');assert.equal(d.getElementById('draft-tools').hidden,true);
 input.value='Primera línea\nSegunda línea\n'+('Texto largo '.repeat(200));contentHeight=600;input.dispatchEvent(new w.Event('input'));
 assert.equal(changed,input.value);assert.equal(input.style.height,'220px');assert.equal(input.style.overflowY,'auto');assert.equal(d.getElementById('draft-tools').hidden,false);
 input.scrollTop=180;input.setSelectionRange(8,15);editor.resize();assert.equal(input.scrollTop,180);assert.equal(input.selectionStart,8);assert.equal(input.selectionEnd,15);
 w.visualViewport.height=400;viewportResize();assert.equal(input.style.height,'136px');assert.equal(input.scrollTop,180);
 d.getElementById('draft-select-all').click();assert.equal(input.selectionStart,0);assert.equal(input.selectionEnd,input.value.length);
 d.getElementById('draft-copy').click();await new Promise(setImmediate);assert.equal(copied,input.value);assert.equal(status,'Texto copiado');
 w.navigator.clipboard.writeText=async()=>{throw Error('denied')};d.getElementById('draft-copy').click();await new Promise(setImmediate);assert.equal(input.selectionEnd,input.value.length);assert.match(status,/menú del teléfono/);
 function key(options){const event=new w.KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,...options});input.dispatchEvent(event);return event}
 assert.equal(key({}).defaultPrevented,false);assert.equal(key({shiftKey:true}).defaultPrevented,false);assert.equal(sends,0);
 assert.equal(key({ctrlKey:true,isComposing:true}).defaultPrevented,false);assert.equal(sends,0);
 assert.equal(key({ctrlKey:true}).defaultPrevented,true);assert.equal(sends,1);key({metaKey:true});assert.equal(sends,2);key({ctrlKey:true,repeat:true});assert.equal(sends,2);
 input.readOnly=true;key({ctrlKey:true});assert.equal(sends,2);input.readOnly=false;input.disabled=true;key({ctrlKey:true});assert.equal(sends,2);
 input.value='';contentHeight=44;editor.resize();assert.equal(input.style.height,'44px');assert.equal(d.getElementById('draft-tools').hidden,true);
 console.log('Long drafts: resize, keyboard viewport, selection, copy/fallback, multiline and guarded sending passed');dom.window.close();
})().catch(error=>{console.error(error);dom.window.close();process.exitCode=1});
