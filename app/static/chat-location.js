(function(global){
  'use strict';
  function init({document:doc,getPhone,hasControl,canSend,apiGet,apiPost,onAccepted,notify,onConfigure}){
    const allowed=canSend||hasControl;
    const dialog=doc.createElement('dialog');
    dialog.className='location-dialog';dialog.setAttribute('aria-labelledby','location-title');
    dialog.innerHTML='<header><h2 id="location-title">Ubicación del local</h2><button type="button" class="btn" data-location-close aria-label="Cerrar ubicación">×</button></header><p data-location-recipient></p><section data-location-point hidden><svg class="location-pin" viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg><b data-location-name></b><p data-location-address></p><a data-location-map target="_blank" rel="noopener noreferrer">Revisar el punto en el mapa ↗</a></section><p data-location-status role="status" aria-live="polite"></p><button type="button" class="btn" data-location-configure hidden>Configurar ubicación del local</button><button type="button" class="btn dark" data-location-send disabled>Enviar ubicación</button>';
    doc.body.appendChild(dialog);
    const find=s=>dialog.querySelector(s),send=find('[data-location-send]'),status=find('[data-location-status]');
    let generation=0,preview=null,busy=false;
    const attempts=new Map();
    find('[data-location-configure]').onclick=()=>{generation++;dialog.close();if(onConfigure)onConfigure()};
    find('[data-location-close]').onclick=()=>{generation++;dialog.close()};
    async function open(){
      if(busy){notify('La ubicación se está enviando. No necesitas pulsar de nuevo.');return}
      const phone=getPhone();if(!phone)return;
      const token=++generation;preview=null;send.disabled=true;find('[data-location-configure]').hidden=true;
      find('[data-location-point]').hidden=true;find('[data-location-recipient]').textContent='Para: '+phone;
      status.textContent='Cargando ubicación confirmada…';if(!dialog.open)dialog.showModal();
      try{
        const r=await apiGet('/panel/ubicacion-local');if(!r.ok)throw Error('No se pudo cargar la ubicación.');
        const point=await r.json();if(token!==generation||!dialog.open)return;
        if(!point.disponible){find('[data-location-configure]').hidden=!onConfigure;status.textContent='Falta configurar el punto exacto del local. El equipo debe confirmar la dirección y sus coordenadas antes de enviarlo.';return}
        const lat=point.ubicacion.latitude,lon=point.ubicacion.longitude;
        const linkOnly=point.tipo==='enlace';
        if(!linkOnly&&(typeof lat!=='number'||typeof lon!=='number'||!Number.isFinite(lat)||!Number.isFinite(lon)||Math.abs(lat)>90||Math.abs(lon)>180))throw Error('El punto configurado no es válido.');
        preview={phone,point};find('[data-location-name]').textContent=point.ubicacion.name;
        find('[data-location-address]').textContent=point.ubicacion.address;
        const link=linkOnly?new URL(point.enlace):new URL('https://www.google.com/maps/search/?api=1&query='+lat+','+lon);
        if(link.protocol!=='https:')throw Error('El enlace del mapa no es válido.');find('[data-location-map]').href=link.href;
        find('[data-location-point]').hidden=false;
        status.textContent=allowed(phone)?(linkOnly?'Revisa el enlace antes de enviarlo. Se compartirá como enlace de ubicación.':'Revisa el pin antes de enviarlo. Se compartirá como mapa en WhatsApp.'):'Cierra esta ventana y toma el control del chat en Gestionar para enviar la ubicación.';
        send.disabled=!allowed(phone);
      }catch(e){if(token===generation)status.textContent=e.message||'No se pudo cargar la ubicación.'}
    }
    send.onclick=async()=>{
      if(busy||!preview||!allowed(preview.phone)||getPhone()!==preview.phone)return;
      const {phone,point}=preview,key=phone+':'+point.revision;
      if(!attempts.has(key))attempts.set(key,global.crypto?.randomUUID?.()||Date.now()+'-'+Math.random());
      busy=true;send.disabled=true;status.textContent='Enviando ubicación a WhatsApp…';
      try{
        const r=await apiPost('/panel/enviar-ubicacion/'+encodeURIComponent(phone),{mensaje:point.revision,request_id:attempts.get(key)});
        if(!r.ok){let data={};try{data=await r.json()}catch(e){}throw Error(data.detail||'No pudimos confirmar el envío. Revisa el historial antes de reenviar.')}
        status.textContent='WhatsApp aceptó la ubicación. Revisa Entregado o Leído en el historial.';
        notify('Ubicación enviada a WhatsApp');attempts.delete(key);preview=null;
        await onAccepted(phone);
      }catch(e){status.textContent=e.message||'Envío sin confirmar. Revisa el historial antes de reenviar.'}
      finally{busy=false;/* Reopen preview to retry with the same request id. */}
    };
    return {open};
  }
  global.CubicoLocation={init};
})(window);
