/* Pointer-based board movement: mouse cards, touch handles and keyboard arrows. */
(function(root){
  function init(board,move,notify){
    let drag=null,ghost=null,target=null,frame=0,busy=false,suppress=null;
    const doc=root.document, status=doc.getElementById('opportunity-move-status');
    const report=text=>{if(status)status.textContent=text;notify(text)};
    const columns=()=>[...board.querySelectorAll('[data-drop-state]')];
    function highlight(next){if(target)target.classList.remove('drop-target');target=next;if(target)target.classList.add('drop-target')}
    function hit(x,y){const node=doc.elementFromPoint(x,y);const column=node?.closest('[data-drop-state]');return column&&board.contains(column)?column:null}
    function clean(){if(drag?.active)suppress=drag.card;if(frame)root.cancelAnimationFrame(frame);frame=0;ghost?.remove();ghost=null;drag?.card.classList.remove('is-dragging');highlight(null);drag=null;board.classList.remove('is-dragging')}
    function scroll(){
      if(!drag?.active)return;
      const {x,y}=drag,rect=board.getBoundingClientRect();
      if(y<65)root.scrollBy(0,-14);else if(y>root.innerHeight-65)root.scrollBy(0,14);
      if(board.scrollWidth>board.clientWidth){if(x<rect.left+36)board.scrollLeft-=14;else if(x>rect.right-36)board.scrollLeft+=14}
      highlight(hit(x,y));frame=root.requestAnimationFrame(scroll);
    }
    async function commit(card,column,restoreFocus=false){
      if(busy||!column||!card.isConnected||card.dataset.moveLocked==='true')return;
      if((column.dataset.acceptStates||'').split(',').includes(card.dataset.state))return;
      const id=Number(card.dataset.id),state=column.dataset.dropState;
      busy=true;board.setAttribute('aria-busy','true');card.classList.add('is-saving');
      if(status)status.textContent='Guardando movimiento…';
      try{const saved=await move(id,state);if(saved!==false){report('Oportunidad movida a '+column.dataset.dropLabel+'.');if(restoreFocus)board.querySelector(`[data-id="${id}"] .opportunity-drag-handle`)?.focus({preventScroll:true})}}
      catch(error){report(error.message||'No se pudo confirmar el movimiento. Actualiza el tablero antes de reintentar.')}
      finally{busy=false;board.removeAttribute('aria-busy');card.classList.remove('is-saving')}
    }
    board.addEventListener('dragstart',e=>e.preventDefault());
    board.addEventListener('pointerdown',e=>{
      suppress=null;
      if(busy||drag||e.isPrimary===false||e.button!==0)return;
      const card=e.target.closest('.opportunity-item');if(!card||!board.contains(card)||card.dataset.moveLocked==='true')return;
      if(e.pointerType!=='mouse'&&!e.target.closest('.opportunity-drag-handle'))return;
      drag={card,id:e.pointerId,startX:e.clientX,startY:e.clientY,x:e.clientX,y:e.clientY,active:false};
    });
    doc.addEventListener('pointermove',e=>{
      if(!drag||e.pointerId!==drag.id)return;
      drag.x=e.clientX;drag.y=e.clientY;
      if(!drag.active&&Math.hypot(drag.x-drag.startX,drag.y-drag.startY)<8)return;
      e.preventDefault();
      if(!drag.active){
        drag.active=true;drag.card.classList.add('is-dragging');board.classList.add('is-dragging');
        ghost=drag.card.cloneNode(true);ghost.classList.add('opportunity-drag-ghost');ghost.setAttribute('aria-hidden','true');ghost.inert=true;
        ghost.style.width=Math.min(drag.card.getBoundingClientRect().width||240,320)+'px';doc.body.append(ghost);frame=root.requestAnimationFrame(scroll);
      }
      ghost.style.left=Math.min(drag.x+12,root.innerWidth-100)+'px';ghost.style.top=drag.y+12+'px';highlight(hit(drag.x,drag.y));
    },{passive:false});
    doc.addEventListener('pointerup',e=>{
      if(!drag||e.pointerId!==drag.id)return;
      const {card,active}=drag,column=active?hit(e.clientX,e.clientY):null;
      if(active)suppress=card;
      clean();if(active)void commit(card,column);
    });
    doc.addEventListener('pointercancel',clean);
    board.addEventListener('click',e=>{
      if(busy||suppress?.contains(e.target)||e.target.closest('.opportunity-drag-handle')){e.preventDefault();e.stopImmediatePropagation();suppress=null}
    },true);
    board.addEventListener('keydown',e=>{
      suppress=null;
      const handle=e.target.closest('.opportunity-drag-handle');if(!handle||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;
      e.preventDefault();const card=handle.closest('.opportunity-item'),items=columns(),index=items.indexOf(card.closest('[data-drop-state]'));
      void commit(card,items[index+(['ArrowLeft','ArrowUp'].includes(e.key)?-1:1)],true);
    });
    doc.addEventListener('keydown',e=>{if(e.key==='Escape')clean()});
    root.addEventListener('blur',clean);doc.addEventListener('visibilitychange',()=>{if(doc.hidden)clean()});
    return {cancel:clean,isBusy:()=>busy,isDragging:()=>!!drag?.active};
  }
  root.CubicoOpportunityDrag={init};
})(window);
