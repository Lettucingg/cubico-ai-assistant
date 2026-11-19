/* Ficha operativa: nunca envía mensajes ni registra pagos. */
(function(root){
  const labels={direccion:'Dirección de entrega',barrio:'Barrio o sector',ubicacion_url:'Enlace de ubicación (opcional)',referencias:'Referencias y acceso',dia_solicitado:'Día que pidió el cliente',fecha_solicitada:'Fecha que pidió el cliente',horario_solicitado:'Horario o restricción del cliente',fecha_confirmada:'Fecha del equipo',hora_desde:'Desde (opcional)',hora_hasta:'Hasta (opcional)',motivo_prioridad:'Motivo de prioridad (opcional)'};
  function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function safeLink(value){
    try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443'))return false;
      if(['google.com','www.google.com','goo.gl'].includes(u.hostname))return u.pathname.startsWith('/maps');
      return ['maps.app.goo.gl','maps.google.com','maps.apple.com','waze.com','www.waze.com','ul.waze.com'].includes(u.hostname);
    }catch(e){return false}
  }
  function init({document:doc=root.document,post,afterSave,reload}){
    const box=doc.getElementById('delivery-case');if(!box)return {load(){}};
    const drafts=new Map();let current=null;
    function fields(){return Object.fromEntries([...box.querySelectorAll('[data-delivery-field]')].map(el=>[el.dataset.deliveryField,el.value]));}
    function load(s){
      if(s.tipo!=='domicilio'){box.hidden=true;box.replaceChildren();current=null;return}
      box.hidden=false;
      const ficha=s.ficha_domicilio;
      if(!ficha){box.innerHTML='<p>La ficha de domicilio no está disponible. Actualiza el panel y comprueba la versión del servidor.</p>';current=null;return}
      const draft=drafts.get(ficha.clave);
      const values=Object.assign({},ficha,draft?.datos||{});
      current={telefono:s.telefono,clave:ficha.clave,token:draft?.token||ficha.token};
      function field(name,type='text'){
        const area=['direccion','referencias'].includes(name);
        const limits={direccion:1000,barrio:120,ubicacion_url:1000,referencias:1000,dia_solicitado:80,horario_solicitado:200,motivo_prioridad:250};
        return '<label>'+labels[name]+(area?'<textarea rows="2"':'<input type="'+type+'"')+' data-delivery-field="'+name+'" '+(limits[name]?'maxlength="'+limits[name]+'" ':'')+(name==='direccion'?'required ':'')+(area?'>'+esc(values[name]||'')+'</textarea>':'value="'+esc(values[name]||'')+'">')+'</label>';
      }
      const zones=[['por_definir','Por definir'],['centro','Condado y centro'],['este','Este'],['otra','Otra zona · revisar']];
      const opts=zones.map(([v,t])=>'<option value="'+v+'" '+(values.zona===v?'selected':'')+'>'+t+'</option>').join('');
      const savedLink=safeLink(values.ubicacion_url)?'<p><a class="btn" href="'+esc(values.ubicacion_url)+'" target="_blank" rel="noopener noreferrer">Abrir ubicación de esta entrega</a></p>':'';
      let shared='';
      const pin=ficha.ubicacion_compartida;
      if(pin&&safeLink(pin.url)){
        shared='<div class="delivery-shared"><span>Ubicación compartida en el chat · '+esc(pin.timestamp||'fecha no disponible')+'</span><a href="'+esc(pin.url)+'" target="_blank" rel="noopener noreferrer">Abrir ubicación</a><button type="button" data-use-shared>Usar este enlace en la ficha</button><small>Comprueba que corresponde a esta entrega; puede ser una ubicación anterior.</small></div>';
      }
      const requested=[values.dia_solicitado,values.fecha_solicitada,values.horario_solicitado].filter(Boolean).join(' · ');
      box.innerHTML='<h3>Organizar domicilio</h3><form id="delivery-case-form"><div class="delivery-address"><span class="delivery-eyebrow">DÓNDE ENTREGAMOS</span><p data-address-summary>'+esc(values.direccion||'Falta la dirección de entrega')+'</p>'+savedLink+'<details '+(!values.direccion?'open':'')+'><summary>Editar dirección y ubicación</summary><div class="delivery-fields">'+field('direccion')+field('barrio')+field('ubicacion_url','url')+field('referencias')+'</div>'+shared+'</details></div><section class="delivery-schedule"><h4>Cuándo lo entregamos</h4><div class="delivery-fields"><label>Zona de entrega<select data-delivery-field="zona">'+opts+'</select></label>'+field('fecha_confirmada','date')+'</div><p data-zone-days class="delivery-note"></p><p class="delivery-note" data-schedule-summary>'+esc([values.hora_desde&&'Desde '+values.hora_desde,values.hora_hasta&&'Hasta '+values.hora_hasta,values.prioridad==='alta'&&'Prioridad alta',values.motivo_prioridad].filter(Boolean).join(' · ')||'Sin horario específico ni prioridad alta')+'</p><details><summary>Horario y prioridad · opcional</summary><div class="delivery-fields">'+field('hora_desde','time')+field('hora_hasta','time')+'<label>Prioridad<select data-delivery-field="prioridad"><option value="normal" '+(values.prioridad!=='alta'?'selected':'')+'>Normal</option><option value="alta" '+(values.prioridad==='alta'?'selected':'')+'>Alta · revisar primero</option></select></label>'+field('motivo_prioridad')+'</div></details></section><section class="delivery-request"><span class="delivery-eyebrow">LO QUE PIDIÓ EL CLIENTE</span><p data-request-summary>'+esc(requested||'Sin día u horario solicitado')+'</p><small>Es una preferencia; no una cita confirmada.</small><details><summary>Ver o editar solicitud del cliente</summary><div class="delivery-fields">'+field('dia_solicitado')+field('fecha_solicitada','date')+field('horario_solicitado')+'</div></details></section><p data-delivery-status role="status" aria-live="polite"></p><div class="delivery-buttons"><button class="btn dark" type="submit" data-delivery-save>Guardar domicilio</button><button class="btn" type="button" data-delivery-reload>Descartar cambios y recargar</button></div><p class="delivery-note">Guardar no envía mensajes ni marca el domicilio como coordinado. Los cambios requieren revisar de nuevo la coordinación. Para coordinar deben estar pagados y preparados los paquetes. Domicilios de lunes a viernes.</p></form>';
      box.querySelector('form').addEventListener('invalid',event=>{let parent=event.target.parentElement;while(parent&&parent!==box){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement}},{capture:true});
      const status=box.querySelector('[data-delivery-status]');
      status.textContent=draft?'Tienes cambios sin guardar.':ficha.faltantes?.length?'Para coordinar: '+ficha.faltantes.join(', ')+'.':'Datos listos para revisar y coordinar.';
      function days(){const zone=box.querySelector('[data-delivery-field="zona"]').value;box.querySelector('[data-zone-days]').textContent=zone==='centro'?'Días preferentes: lunes y miércoles. Las excepciones las coordina el equipo.':zone==='este'?'Días preferentes: martes y jueves. Las excepciones las coordina el equipo.':'Selecciona la zona para organizar las entregas.'}
      days();
      box.querySelector('form').addEventListener('input',()=>{drafts.set(current.clave,{datos:fields(),token:current.token});status.textContent='Cambios sin guardar.';box.querySelector('[data-address-summary]').textContent=fields().direccion||'Falta la dirección de entrega';box.querySelector('[data-request-summary]').textContent=[fields().dia_solicitado,fields().fecha_solicitada,fields().horario_solicitado].filter(Boolean).join(' · ')||'Sin día u horario solicitado';const data=fields();box.querySelector('[data-schedule-summary]').textContent=[data.hora_desde&&'Desde '+data.hora_desde,data.hora_hasta&&'Hasta '+data.hora_hasta,data.prioridad==='alta'&&'Prioridad alta',data.motivo_prioridad].filter(Boolean).join(' · ')||'Sin horario específico ni prioridad alta';days()});
      const use=box.querySelector('[data-use-shared]');
      if(use)use.addEventListener('click',()=>{box.querySelector('[data-delivery-field="ubicacion_url"]').value=pin.url;drafts.set(current.clave,{datos:fields(),token:current.token});status.textContent='Enlace copiado a la ficha; falta guardar.'});
      box.querySelector('[data-delivery-reload]').addEventListener('click',()=>{const phone=current.telefono;drafts.delete(current.clave);reload?.(phone)});
      box.querySelector('form').addEventListener('submit',async e=>{
        e.preventDefault();const snapshot={...current},datos=fields(),button=box.querySelector('[data-delivery-save]');
        const controls=[...box.querySelectorAll('input,textarea,select,button')];controls.forEach(el=>el.disabled=true);status.textContent='Guardando ficha…';
        try{
          const response=await post('/panel/solicitud/'+encodeURIComponent(snapshot.telefono)+'/domicilio',{datos,token:snapshot.token});
          const result=await response.json();
          if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'No se pudo guardar la ficha.');
          drafts.delete(snapshot.clave);
          if(current?.clave===snapshot.clave)status.textContent='Ficha guardada. No se envió ningún mensaje.';
          await afterSave?.(snapshot.telefono,result.ficha);
        }catch(error){if(current?.clave===snapshot.clave)status.textContent=error.message||'No se pudo guardar. Se conservan tus cambios.'}
        finally{controls.forEach(el=>el.disabled=false)}
      });
    }
    return {load,hasUnsaved:()=>!!(current&&drafts.has(current.clave))};
  }
  root.CubicoDeliveryCase={init,safeLink};if(typeof module!=='undefined')module.exports=root.CubicoDeliveryCase;
})(typeof window!=='undefined'?window:globalThis);
