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
      box.innerHTML='<h3>Ficha del domicilio</h3><p class="delivery-note">Guarda la dirección y lo solicitado por el cliente. El enlace de ubicación es opcional.</p><form id="delivery-case-form"><div class="delivery-fields">'+field('direccion')+field('barrio')+'<label>Zona<select data-delivery-field="zona">'+opts+'</select></label>'+field('ubicacion_url','url')+field('referencias')+'</div>'+savedLink+shared+'<fieldset><legend>Solicitado por el cliente · no es una cita confirmada</legend><div class="delivery-fields">'+field('dia_solicitado')+field('fecha_solicitada','date')+field('horario_solicitado')+'</div></fieldset><fieldset><legend>Programación del equipo</legend><p data-zone-days class="delivery-note"></p><div class="delivery-fields">'+field('fecha_confirmada','date')+field('hora_desde','time')+field('hora_hasta','time')+'<label>Prioridad<select data-delivery-field="prioridad"><option value="normal" '+(values.prioridad!=='alta'?'selected':'')+'>Normal</option><option value="alta" '+(values.prioridad==='alta'?'selected':'')+'>Alta · revisar primero</option></select></label>'+field('motivo_prioridad')+'</div></fieldset><p class="delivery-note">Guardar no envía mensajes ni marca el domicilio como coordinado. Los cambios requieren revisar de nuevo la coordinación. Para coordinar deben estar pagados y preparados los paquetes. Domicilios de lunes a viernes.</p><p data-delivery-status role="status" aria-live="polite"></p><div class="delivery-buttons"><button class="btn dark" type="submit" data-delivery-save>Guardar ficha</button><button class="btn" type="button" data-delivery-reload>Descartar cambios y recargar</button></div></form>';
      const status=box.querySelector('[data-delivery-status]');
      status.textContent=draft?'Tienes cambios sin guardar.':ficha.faltantes?.length?'Para coordinar: '+ficha.faltantes.join(', ')+'.':'Datos listos para revisar y coordinar.';
      function days(){const zone=box.querySelector('[data-delivery-field="zona"]').value;box.querySelector('[data-zone-days]').textContent=zone==='centro'?'Días preferentes: lunes y miércoles. Las excepciones las coordina el equipo.':zone==='este'?'Días preferentes: martes y jueves. Las excepciones las coordina el equipo.':'Selecciona la zona para organizar las entregas.'}
      days();
      box.querySelector('form').addEventListener('input',()=>{drafts.set(current.clave,{datos:fields(),token:current.token});status.textContent='Cambios sin guardar.';days()});
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
    return {load};
  }
  root.CubicoDeliveryCase={init,safeLink};if(typeof module!=='undefined')module.exports=root.CubicoDeliveryCase;
})(typeof window!=='undefined'?window:globalThis);
