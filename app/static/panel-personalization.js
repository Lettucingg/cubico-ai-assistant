/* Preferencias locales de presentación; no cambian datos ni estados de los casos. */
(function(root){
  const key='cubico.panel.background.v1',allowed=['plain','cubes','brand'];
  function init(doc=root.document,storage){
    if(storage===undefined){try{storage=root.localStorage}catch(e){storage=null}}
    let current='cubes';try{const saved=storage.getItem(key);if(allowed.includes(saved))current=saved}catch(e){}
    function apply(value){current=allowed.includes(value)?value:'cubes';doc.body.dataset.chatBackground=current;doc.querySelectorAll('[data-chat-background]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.chatBackground===current)))}
    const paths={overview:'<path d="m3 10 9-7 9 7M5 9v12h14V9M9 21v-8h6v8"/>',chats:'<path d="M21 11a8 8 0 0 1-8 8H6l-4 3 1-7a8 8 0 1 1 18-4z"/>',packages:'<path d="m12 3 9 5v8l-9 5-9-5V8zM3 8l9 5 9-5M12 13v8"/>',opportunities:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h2m4 0h2M8 11h2m4 0h2M10 21v-6h4v6"/>',costs:'<path d="M3 3v18h18M6 15l4-5 4 3 6-8"/>',alerts:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',settings:'<path d="m9 3-1 3-3 1v4l-2 2 2 3 3 1 1 4h6l1-4 3-1 2-3-2-2V7l-3-1-1-3z"/><circle cx="12" cy="12" r="3"/>'};
    doc.querySelectorAll('.nav [data-view]').forEach(b=>{const slot=b.querySelector('span:first-child');if(slot&&paths[b.dataset.view])slot.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+paths[b.dataset.view]+'</svg>'});
    const bell=doc.getElementById('notifications');if(bell){bell.firstChild.textContent='';bell.insertAdjacentHTML('afterbegin','<svg viewBox="0 0 24 24" aria-hidden="true">'+paths.alerts+'</svg>')}
    apply(current);
    doc.querySelectorAll('[data-chat-background]').forEach(b=>b.addEventListener('click',()=>{apply(b.dataset.chatBackground);let saved=true;try{storage.setItem(key,current)}catch(e){saved=false}doc.getElementById('background-status').textContent=saved?'Fondo guardado en este navegador.':'Fondo aplicado. Este navegador no permite guardar la preferencia.'}));
    return {apply,get current(){return current}};
  }
  root.CubicoPersonalization={init};if(typeof module!=='undefined')module.exports=root.CubicoPersonalization;
})(typeof window!=='undefined'?window:globalThis);
