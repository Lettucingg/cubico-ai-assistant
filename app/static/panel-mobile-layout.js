/* Ajusta el chat al espacio visible, incluido el teclado del teléfono. */
(function(root){
  function availableHeight(top,viewportBottom,navigationTop){return Math.max(0,Math.floor(Math.min(viewportBottom,navigationTop)-top-12))}
  function init(doc=root.document){
    const inbox=doc.querySelector('.inbox'),chats=doc.getElementById('chats'),nav=doc.querySelector('.sidebar'),header=doc.querySelector('.topbar');
    if(!inbox||!nav||!chats)return;
    let pending=false;
    function update(){
      pending=false;
      if(!root.matchMedia('(max-width:760px)').matches){inbox.style.removeProperty('--mobile-inbox-height');doc.body.classList.remove('chat-keyboard-open');return}
      const viewport=root.visualViewport,bottom=viewport?viewport.offsetTop+viewport.height:root.innerHeight;
      const focused=doc.activeElement,editing=focused&&inbox.contains(focused)&&focused.matches('input,textarea,[contenteditable=true]');
      const keyboard=Boolean(editing&&viewport&&root.innerHeight-viewport.height>120&&viewport.scale<=1.05);
      doc.body.classList.toggle('chat-keyboard-open',keyboard);
      if(!chats.classList.contains('active'))return;
      const navigationTop=keyboard?bottom:nav.getBoundingClientRect().top;
      const height=availableHeight(inbox.getBoundingClientRect().top,bottom,navigationTop);
      inbox.style.setProperty('--mobile-inbox-height',height+'px');
    }
    function schedule(){if(!pending){pending=true;root.requestAnimationFrame(update)}}
    root.addEventListener('resize',schedule);root.addEventListener('orientationchange',schedule);
    if(root.visualViewport){root.visualViewport.addEventListener('resize',schedule);root.visualViewport.addEventListener('scroll',schedule)}
    doc.addEventListener('focusin',schedule);doc.addEventListener('focusout',schedule);
    doc.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',schedule));
    if(root.ResizeObserver){const observer=new root.ResizeObserver(schedule);observer.observe(nav);if(header)observer.observe(header)}
    if(root.MutationObserver){const observer=new root.MutationObserver(schedule);observer.observe(chats,{attributes:true,attributeFilter:['class']});observer.observe(doc.querySelector('.app'),{attributes:true,attributeFilter:['style']})}
    schedule();return {update};
  }
  root.CubicoMobileLayout={init,availableHeight};if(typeof module!=='undefined')module.exports=root.CubicoMobileLayout;
})(typeof window!=='undefined'?window:globalThis);
