/* Registro operativo de entregas confirmadas en el panel. */
(function(root){
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function init({document:doc=root.document,get,openChat}){
  const box=doc.getElementById('delivery-history');if(!box)return {load(){},reset(){}};
  let sequence=0;
  box.innerHTML='<label>Fecha de entrega<input type="date" data-delivered-date></label><button class="btn" type="button" data-delivered-refresh>Consultar</button><p class="delivery-note">Se guardan las confirmaciones hechas desde esta actualización. Las entregas antiguas sin registro no aparecen aquí.</p><p role="status" data-delivered-status></p><div data-delivered-list></div>';
  const date=box.querySelector('[data-delivered-date]'),status=box.querySelector('[data-delivered-status]'),list=box.querySelector('[data-delivered-list]');
  async function load(){const serial=++sequence;list.replaceChildren();status.textContent='Consultando entregas…';
   try{const r=await get('/panel/entregas'+(date.value?'?fecha='+encodeURIComponent(date.value):'')),data=await r.json();if(serial!==sequence)return;if(!r.ok)throw Error(data.detail||'No se pudieron consultar las entregas');date.value=data.fecha;
    status.textContent=data.hay_mas?'Mostrando las 200 entregas más recientes de este día.':data.entregas.length+' '+(data.entregas.length===1?'entrega confirmada':'entregas confirmadas');
    list.innerHTML=data.entregas.map(p=>'<article class="delivered-card"><span class="status-pill ready">'+(p.entrega_anterior_reportada?'Entrega anterior reportada':'✓ Entregado')+'</span><h3>'+esc(p.nombre)+'</h3><p>'+esc(p.codigo_cliente)+' · '+esc(p.tipo==='domicilio'?'Domicilio':'Retiro en oficina')+'</p><p>'+esc(p.direccion)+'</p><p><b>'+(p.entrega_anterior_reportada?'Registrado el ':'')+esc(new Date(p.confirmado_en).toLocaleString('es-PA',{timeZone:'America/Panama'}))+'</b> · '+esc(p.confirmado_por)+'</p><details><summary>Ver paquetes</summary><p>'+esc(p.paquetes)+'</p></details><button class="btn" type="button" data-delivered-chat="'+esc(p.telefono)+'">Abrir conversación</button></article>').join('')||'<p>No hay entregas registradas en esta fecha.</p>';
   }catch(e){if(serial===sequence){list.replaceChildren();status.textContent=e.message||'No se pudo consultar. Intenta de nuevo.'}}
  }
  box.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.hasAttribute('data-delivered-refresh'))load();if(b.dataset.deliveredChat)openChat?.(b.dataset.deliveredChat)});
  date.addEventListener('change',load);
  return {load,reset(){sequence++;date.value='';list.replaceChildren();status.textContent=''}};
 }
 root.CubicoDeliveryHistory={init};
})(typeof window!=='undefined'?window:globalThis);
