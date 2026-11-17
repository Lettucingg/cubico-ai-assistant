/* Vista personal para revisar carga y abrir navegación. No confirma entregas. */
(function(root){
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const zones={todas:'Todas las zonas',centro:'Condado y centro',este:'Este',otra:'Otra zona',por_definir:'Por definir'};
  function safeMap(value){
    try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443'))return false;
      if(['google.com','www.google.com','goo.gl'].includes(u.hostname))return u.pathname.startsWith('/maps');
      return ['maps.app.goo.gl','maps.google.com','maps.apple.com','waze.com','www.waze.com','ul.waze.com'].includes(u.hostname);
    }catch(e){return false}
  }
  function links(p){
    const map=safeMap(p.ubicacion_url)?p.ubicacion_url:'';
    let waze='https://www.waze.com/ul?q='+encodeURIComponent(p.direccion)+'&navigate=yes',wazeLabel='Buscar dirección en Waze';
    if(map){const u=new URL(map),q=u.searchParams.get('query')||u.searchParams.get('q')||'';
      if(['waze.com','www.waze.com','ul.waze.com'].includes(u.hostname)){waze=map;wazeLabel='Abrir ubicación en Waze'}
      else if(/^[-+]?\d+(?:\.\d+)?,[-+]?\d+(?:\.\d+)?$/.test(q)){
        const [lat,lon]=q.split(',').map(Number);if(Math.abs(lat)<=90&&Math.abs(lon)<=180){waze='https://www.waze.com/ul?ll='+encodeURIComponent(q)+'&navigate=yes';wazeLabel='Navegar en Waze'}
      }
    }
    return {map:map||'https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(p.direccion),mapLabel:map?'Abrir ubicación del cliente':'Buscar dirección en Maps',waze,wazeLabel};
  }
  function init({document:doc=root.document,get,post,openCase,openChat,copy=value=>root.navigator.clipboard.writeText(value)}){
    const box=doc.getElementById('driver-route');if(!box)return {load(){},close(){}};
    let data=null,busy=false,mode=false,currentId=null,sequence=0,navigation=0;
    box.innerHTML='<div class="route-toolbar"><label>Día<input type="date" data-route-date></label><label>Zona<select data-route-zone>'+Object.entries(zones).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('')+'</select></label><button type="button" class="btn" data-route-refresh>Actualizar</button></div><p class="route-status" data-route-status role="status" aria-live="polite"></p><div data-route-content></div>';
    const date=box.querySelector('[data-route-date]'),zone=box.querySelector('[data-route-zone]'),status=box.querySelector('[data-route-status]'),content=box.querySelector('[data-route-content]');
    function controls(disabled){busy=disabled;box.setAttribute('aria-busy',String(disabled));box.querySelectorAll('button,input,select').forEach(el=>el.disabled=disabled)}
    function close(){navigation++;mode=false;currentId=null;doc.body.classList.remove('driver-focus');render()}
    function action(p){const l=links(p);return '<div class="route-links"><a class="btn dark" target="_blank" rel="noopener noreferrer" href="'+esc(l.map)+'">'+l.mapLabel+'</a><a class="btn" target="_blank" rel="noopener noreferrer" href="'+esc(l.waze)+'">'+l.wazeLabel+'</a>'+(/^\d{8,15}$/.test(p.telefono)?'<a class="btn" href="tel:+'+p.telefono+'">Llamar</a>':'')+'<button type="button" class="btn" data-route-copy="'+esc(p.id)+'">Copiar dirección</button><button type="button" class="btn" data-route-chat="'+esc(p.id)+'">Abrir chat</button><button type="button" class="btn" data-route-case="'+esc(p.id)+'">Ver solicitud</button></div>'}
    function details(p){return '<p class="route-address">'+esc(p.direccion)+'</p><details class="route-extra"><summary>Horario, paquetes y referencias</summary><p>'+esc(p.barrio)+' · '+esc(zones[p.zona]||p.zona)+'</p>'+(p.referencias?'<p><b>Acceso:</b> '+esc(p.referencias)+'</p>':'')+'<p><b>Equipo:</b> '+esc(p.fecha_confirmada||'Sin fecha confirmada')+(p.hora_desde?' · '+esc(p.hora_desde)+'–'+esc(p.hora_hasta):' · Sin hora fijada')+'</p>'+((p.dia_solicitado||p.fecha_solicitada||p.horario_solicitado)?'<p class="route-request"><b>Pidió el cliente:</b> '+esc([p.dia_solicitado,p.fecha_solicitada,p.horario_solicitado].filter(Boolean).join(' · '))+'</p>':'')+(p.prioridad==='alta'?'<p class="route-priority">Prioridad alta'+(p.motivo_prioridad?': '+esc(p.motivo_prioridad):'')+'</p>':'')+'<details><summary>'+p.trackings.length+' '+(p.trackings.length===1?'paquete':'paquetes')+' · ver trackings</summary><ul>'+p.trackings.map(t=>'<li>'+esc(t)+'</li>').join('')+'</ul></details></details>'}
    function render(){
      if(!data){content.replaceChildren();return}
      if(mode&&(!data.puede_recorrer||!data.paradas.some(p=>p.id===currentId))){mode=false;doc.body.classList.remove('driver-focus')}
      const stops=data.paradas;
      if(mode){const index=stops.findIndex(p=>p.id===currentId),p=stops[index];
        content.innerHTML='<article class="route-focus-card"><div class="route-focus-heading"><span>Parada '+(index+1)+' de '+stops.length+'</span><button type="button" class="btn" data-route-exit>Volver a la lista</button></div><h2>'+esc(p.nombre)+'</h2><p>'+esc(p.codigo_cliente)+'</p><p class="route-paid">Pago comprobado · carga verificada</p>'+details(p)+action(p)+'<div class="route-step"><button type="button" class="btn" data-route-step="-1" '+(index===0?'disabled':'')+'>Anterior</button><button type="button" class="btn dark" data-route-step="1" '+(index===stops.length-1?'disabled':'')+'>Siguiente entrega</button></div><p class="route-note">Cambiar de parada no marca entregado. Confirma la entrega desde la solicitud cuando corresponda. Usa los controles con el vehículo detenido.</p></article>';
      }else{
        const checked=stops.filter(p=>p.cargada).length;
        content.innerHTML='<button type="button" class="btn dark" data-route-add>+ Agregar entrega a mi ruta</button><div class="route-summary"><b>'+stops.length+' listas · '+checked+' con carga verificada · '+data.pendientes.length+' por revisar</b><span>Plan personal de '+esc(data.usuario)+'</span><span>Consultado: '+esc(new Date(data.consultado_en).toLocaleTimeString('es-PA',{timeZone:'America/Panama',hour:'2-digit',minute:'2-digit'}))+' · Panamá</span></div><p class="route-note">Orden '+(data.orden_manual?'ajustado por ti':'sugerido por horario y prioridad')+'. Puedes mover las paradas; no se calcula tráfico ni la ruta más corta. La carga es una lista personal y no registra la salida en Cúbico.</p><button type="button" class="btn dark route-start" data-route-start '+(!data.puede_recorrer?'disabled':'')+'>Empezar entregas</button><p class="route-note">'+esc(data.bloqueos_recorrido.join(' · '))+'</p><div class="route-stops">'+(stops.length?stops.map((p,i)=>'<article class="route-stop"><header><span class="route-number">'+(i+1)+'</span><div><h3>'+esc(p.nombre)+'</h3><span>'+esc(p.codigo_cliente)+'</span></div><div class="route-move"><button type="button" class="btn" data-route-move="'+esc(p.id)+'" data-direction="-1" aria-label="Subir parada" '+(i===0?'disabled':'')+'>↑</button><button type="button" class="btn" data-route-move="'+esc(p.id)+'" data-direction="1" aria-label="Bajar parada" '+(i===stops.length-1?'disabled':'')+'>↓</button></div></header>'+details(p)+'<p class="route-paid">Pago comprobado en facturación</p><label class="route-check"><input type="checkbox" data-route-loaded="'+esc(p.id)+'" '+(p.cargada?'checked':'')+'> Paquetes revisados y cargados</label>'+action(p)+'</article>').join(''):'<p class="board-empty">No hay entregas listas para esta fecha y zona.</p>')+'</div><details class="route-review"><summary>Por revisar para este día ('+data.pendientes.length+')</summary>'+review(data.pendientes)+'</details><details class="route-review" data-route-unplanned><summary>Agregar / programar entregas ('+data.sin_programar.length+')</summary><p>Elige una solicitud y guarda su fecha y zona en la ficha. Para una entrega nueva, abre su chat → Gestionar → Domicilio. Luego puedes ajustar el orden con las flechas.</p>'+review(data.sin_programar)+'</details>';
      }
    }
    function review(items){return items.map(p=>'<article class="route-review-item"><h3>'+esc(p.nombre)+' · '+esc(p.codigo_cliente)+'</h3><p>'+esc(p.direccion)+'</p><p>'+esc(p.pendientes.join(' · '))+'</p><button type="button" class="btn" data-route-case="'+esc(p.id)+'">Revisar solicitud</button></article>').join('')||'<p>Ninguna.</p>'}
    async function load(){
      if(busy)return false;const serial=++sequence;controls(true);status.textContent='Comprobando entregas y pagos…';
      try{const q=new URLSearchParams({zona:zone.value});if(date.value)q.set('fecha',date.value);
        const r=await get('/panel/ruta?'+q);const result=await r.json();if(!r.ok)throw Error(result.detail||'No se pudo comprobar la ruta');
        if(serial!==sequence)return false;data=result;date.value=result.fecha;status.textContent='Ruta actualizada. No se enviaron mensajes.';render();return true;
      }catch(e){if(serial!==sequence)return false;data=null;mode=false;doc.body.classList.remove('driver-focus');content.replaceChildren();status.textContent=(e.message||'Error de conexión')+'. Actualiza antes de continuar.';return false}
      finally{if(serial===sequence){controls(false);render()}}
    }
    async function save(order,loaded){
      if(busy||!data)return;const serial=sequence;controls(true);status.textContent='Guardando tu plan…';
      try{const r=await post('/panel/ruta',{fecha:data.fecha,zona:data.zona,token:data.token,orden:order,cargadas:loaded});const result=await r.json();if(serial!==sequence)return;if(!r.ok)throw Error(result.detail||'No se pudo guardar el plan');data=result;status.textContent='Plan guardado. No se registró despacho, entrega ni pago.'}
      catch(e){if(serial!==sequence)return;data=null;mode=false;doc.body.classList.remove('driver-focus');status.textContent=(e.message||'No se pudo guardar')+'. Pulsa Actualizar para revisar el estado.'}
      finally{if(serial===sequence){controls(false);render()}}
    }
    function find(id){return data&&[...data.paradas,...data.pendientes,...data.sin_programar].find(p=>p.id===id)}
    box.addEventListener('change',e=>{
      if(e.target===date||e.target===zone){close();load();return}
      const id=e.target.dataset.routeLoaded;if(id&&data&&!busy){const loaded=data.paradas.filter(p=>p.id===id?e.target.checked:p.cargada).map(p=>p.id);save(data.paradas.map(p=>p.id),loaded)}
    });
    box.addEventListener('click',async e=>{
      const button=e.target.closest('button');if(!button||busy)return;
      if(button.hasAttribute('data-route-add')){const list=box.querySelector('[data-route-unplanned]');if(list){list.open=true;list.scrollIntoView({behavior:'smooth',block:'start'})}return}
      if(button.hasAttribute('data-route-refresh')){await load();return}
      if(button.hasAttribute('data-route-exit')){close();return}
      if(button.hasAttribute('data-route-start')){const scope=navigation;if(await load()&&scope===navigation&&data.puede_recorrer){mode=true;currentId=data.paradas[0].id;doc.body.classList.add('driver-focus');render();box.scrollTop=0}return}
      if(button.hasAttribute('data-route-step')){const delta=Number(button.dataset.routeStep),id=currentId,scope=navigation;if(await load()&&mode&&scope===navigation){const index=data.paradas.findIndex(p=>p.id===id),next=data.paradas[index+delta];if(next){currentId=next.id;render();box.scrollTop=0}}return}
      if(button.dataset.routeMove&&data){const ids=data.paradas.map(p=>p.id),i=ids.indexOf(button.dataset.routeMove),j=i+Number(button.dataset.direction);if(j>=0&&j<ids.length){[ids[i],ids[j]]=[ids[j],ids[i]];await save(ids,data.paradas.filter(p=>p.cargada).map(p=>p.id))}return}
      const p=find(button.dataset.routeCopy||button.dataset.routeChat||button.dataset.routeCase);if(!p)return;
      if(button.dataset.routeCopy){try{await copy(p.direccion);status.textContent='Dirección copiada.'}catch(e){status.textContent='No se pudo copiar. Puedes seleccionar la dirección.'}}
      if(button.dataset.routeChat){close();openChat?.(p.telefono)}
      if(button.dataset.routeCase){close();openCase?.(p.telefono)}
    });
    doc.addEventListener('visibilitychange',()=>{if(doc.visibilityState==='visible'&&mode&&!busy)load()});
    function reset(){sequence++;close();data=null;date.value='';zone.value='todas';status.textContent='';controls(false);render()}
    return {load,close,reset};
  }
  root.CubicoDriverRoute={init,links,safeMap};if(typeof module!=='undefined')module.exports=root.CubicoDriverRoute;
})(typeof window!=='undefined'?window:globalThis);
