/* Ajusta el chat al espacio visible, incluido el teclado del teléfono. */
(function(root){
  function availableHeight(top,viewportBottom,navigationTop){return Math.max(0,Math.floor(Math.min(viewportBottom,navigationTop)-top-12))}
  function navigationTop(bottom,height){return Math.max(0,Math.floor(bottom-height))}
  function init(doc=root.document,navigate){
    const inbox=doc.querySelector('.inbox'),chats=doc.getElementById('chats'),nav=doc.querySelector('.sidebar'),header=doc.querySelector('.topbar');
    if(!inbox||!nav||!chats)return;
    let pending=false,closedViewportHeight=root.visualViewport?root.visualViewport.height:root.innerHeight;
    const resumeTimers=[];
    function update(){
      pending=false;
      if(doc.hidden)return;
      if(!root.matchMedia('(max-width:760px)').matches){inbox.style.removeProperty('--mobile-inbox-height');nav.style.removeProperty('top');nav.style.removeProperty('bottom');doc.body.style.removeProperty('--mobile-navigation-height');doc.body.classList.remove('chat-keyboard-open','chat-editor-open');inbox.style.removeProperty('--editor-viewport-top');inbox.style.removeProperty('--editor-viewport-height');return}
      const viewport=root.visualViewport;let bottom=viewport?viewport.offsetTop+viewport.height:root.innerHeight;
      const focused=doc.activeElement,editing=focused&&doc.querySelector('.app').contains(focused)&&focused.matches('input,textarea,[contenteditable=true]');
      const chatEditing=Boolean(editing&&inbox.contains(focused)&&chats.classList.contains('active'));
      const keyboard=chatEditing||Boolean(editing&&viewport&&closedViewportHeight-viewport.height>120&&viewport.scale<=1.05);
      doc.body.classList.toggle('chat-editor-open',chatEditing);
      if(chatEditing){inbox.style.setProperty('--editor-viewport-top',(viewport?viewport.offsetTop:0)+'px');inbox.style.setProperty('--editor-viewport-height',(viewport?viewport.height:root.innerHeight)+'px')}
      doc.body.classList.toggle('chat-keyboard-open',keyboard);
      // CSS anchors navigation to the real viewport, never a remembered keyboard height.
      nav.style.top='auto';nav.style.bottom='0px';
      const bounds=nav.getBoundingClientRect();
      const navHeight=keyboard?0:bounds.height;
      const nativeBounds=!keyboard&&Number.isFinite(bounds.bottom)&&bounds.bottom>0;
      if(nativeBounds)bottom=bounds.bottom;
      const navTop=nativeBounds&&Number.isFinite(bounds.top)&&bounds.top>=0?bounds.top:navigationTop(bottom,navHeight);
      if(!editing)closedViewportHeight=Math.max(0,bottom-(viewport?viewport.offsetTop:0));
      if(!keyboard)doc.body.style.setProperty('--mobile-navigation-height',navHeight+'px');
      if(!chats.classList.contains('active'))return;
      const height=availableHeight(inbox.getBoundingClientRect().top,bottom,keyboard?bottom:navTop);
      inbox.style.setProperty('--mobile-inbox-height',height+'px');
    }
    function schedule(){if(doc.hidden)return;if(!pending){pending=true;root.requestAnimationFrame(update)}}
    function resume(){
      if(doc.hidden)return;
      pending=false;
      resumeTimers.splice(0).forEach(id=>root.clearTimeout(id));
      if(!root.matchMedia('(max-width:760px)').matches){update();return}
      const focused=doc.activeElement;
      if(focused&&doc.querySelector('.app').contains(focused)&&focused.matches('input,textarea,[contenteditable=true]'))focused.blur();
      // Safari/PWA updates visualViewport asynchronously after returning from another app.
      update();[120,350,750].forEach(delay=>resumeTimers.push(root.setTimeout(update,delay)));
    }
    doc.addEventListener('visibilitychange',()=>{
      pending=false;
      if(!doc.hidden)resume();else resumeTimers.splice(0).forEach(id=>root.clearTimeout(id));
    });
    root.addEventListener('pageshow',resume);root.addEventListener('focus',resume);
    root.addEventListener('scroll',schedule,{passive:true});root.addEventListener('resize',schedule);root.addEventListener('orientationchange',schedule);
    if(root.visualViewport){root.visualViewport.addEventListener('resize',schedule);root.visualViewport.addEventListener('scroll',schedule)}
    doc.addEventListener('focusin',schedule);doc.addEventListener('focusout',schedule);
    doc.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',schedule));
    if(root.ResizeObserver){const observer=new root.ResizeObserver(schedule);observer.observe(nav);if(header)observer.observe(header)}
    if(root.MutationObserver){const observer=new root.MutationObserver(schedule);observer.observe(chats,{attributes:true,attributeFilter:['class']});observer.observe(doc.querySelector('.app'),{attributes:true,attributeFilter:['style']})}
    if(typeof navigate==='function'){
      // A native button click already handles touch, pen, mouse, keyboard and
      // cancelled scroll gestures. Do not move the fixed bar during a press,
      // prevent pointerup, or discard a later click using a timestamp window.
      nav.addEventListener('click',event=>{
        const target=event.target.nodeType===1?event.target:event.target.parentElement;
        const button=target&&target.closest('.nav button[data-view]');
        if(!button||!nav.contains(button)||button.disabled||event.defaultPrevented)return;
        navigate(button.dataset.view);schedule();
      });
    }
    const done=doc.getElementById('chat-editing-done');if(done)done.addEventListener('click',()=>{if(doc.activeElement&&doc.activeElement.blur)doc.activeElement.blur();schedule()});
    schedule();return {update};
  }
  root.CubicoMobileLayout={init,availableHeight,navigationTop};if(typeof module!=='undefined')module.exports=root.CubicoMobileLayout;
})(typeof window!=='undefined'?window:globalThis);
