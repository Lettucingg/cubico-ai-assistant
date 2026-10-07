/* Conserva la edición y selección nativas de iOS/Android. */
(function(root){
  function init(doc=root.document,{onSend=()=>{},onCopy=()=>{},onChange=()=>{}}={}){
    const input=doc.getElementById('message-input'),tools=doc.getElementById('draft-tools');
    if(!input)return;
    function resize(){
      const oldScroll=input.scrollTop;
      const viewport=root.visualViewport?.height||root.innerHeight||700;
      const inbox=doc.querySelector('.inbox');
      const space=inbox?.clientHeight||viewport;
      const cap=Math.max(44,Math.min(220,Math.floor(viewport*.34),Math.floor(space*.42)));
      input.style.height='auto';
      const height=Math.min(cap,Math.max(44,input.scrollHeight));
      input.style.height=height+'px';
      input.style.overflowY=input.scrollHeight>height?'auto':'hidden';
      input.scrollTop=oldScroll;
      if(tools)tools.hidden=!input.value;
    }
    function selectAll(){input.focus();input.select();input.setSelectionRange(0,input.value.length)}
    input.addEventListener('input',()=>{onChange(input.value);resize()});
    input.addEventListener('keydown',event=>{
      if(event.key==='Enter'&&!event.isComposing&&event.keyCode!==229&&(event.ctrlKey||event.metaKey)){
        event.preventDefault();if(!event.repeat&&!input.disabled&&!input.readOnly)onSend();
      }
    });
    doc.getElementById('draft-select-all')?.addEventListener('click',selectAll);
    doc.getElementById('draft-copy')?.addEventListener('click',async()=>{
      const text=input.value;if(!text)return;
      try{if(!root.navigator.clipboard?.writeText)throw Error();await root.navigator.clipboard.writeText(text);onCopy('Texto copiado')}
      catch(e){selectAll();onCopy('Texto seleccionado. Usa Copiar en el menú del teléfono.')}
    });
    doc.getElementById('messages')?.addEventListener('click',async event=>{
      const button=event.target.closest('[data-copy-message]');if(!button)return;
      const text=button.closest('.bubble').querySelector('.message-text');if(!text)return;
      try{if(!root.navigator.clipboard?.writeText)throw Error();await root.navigator.clipboard.writeText(text.textContent);onCopy('Mensaje copiado')}
      catch(e){const range=doc.createRange();range.selectNodeContents(text);const selection=root.getSelection();selection.removeAllRanges();selection.addRange(range);onCopy('Mensaje seleccionado. Usa Copiar en el menú del teléfono.')}
    });
    root.addEventListener('resize',resize);
    root.visualViewport?.addEventListener('resize',resize);
    resize();return {resize,selectAll};
  }
  root.CubicoTextEditor={init};
})(typeof window!=='undefined'?window:globalThis);
