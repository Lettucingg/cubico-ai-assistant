(function(root){
 'use strict';
 let epoch=0,api,write;
 const $=id=>root.document.getElementById(id);
 function status(text){$('local-location-status').textContent=text}
 async function load(){const token=++epoch;try{const r=await api('/panel/configuracion/ubicacion');if(!r.ok)throw Error('No se pudo cargar la ubicación.');const p=await r.json();if(token!==epoch)return;
  $('local-location-address').value=p.direccion||'';$('local-location-url').value=p.enlace||'';
  $('local-location-lat').value=p.latitud??'';$('local-location-lon').value=p.longitud??'';
  $('local-location-confirmed').checked=p.confirmada===true;status(p.confirmada?'Ubicación confirmada por el equipo.':'Pendiente de confirmar. Bruno no compartirá una dirección antigua.');
 }catch(e){if(token===epoch)status(e.message)}}
 function init(get,put){api=get;write=put;
  $('local-location-form').addEventListener('input',()=>{epoch++;status('Cambios sin guardar. Revisa el punto antes de confirmarlo.')});
  $('local-location-form').addEventListener('submit',async event=>{event.preventDefault();const btn=$('local-location-save');if(btn.disabled)return;
   const lat=$('local-location-lat').value,lon=$('local-location-lon').value;
   const body={direccion:$('local-location-address').value.trim(),enlace:$('local-location-url').value.trim(),latitud:lat===''?null:Number(lat),longitud:lon===''?null:Number(lon),confirmada:$('local-location-confirmed').checked};
   if((lat==='')!==(lon==='')){status('Completa ambas coordenadas o deja las dos vacías.');return}
   const token=++epoch;btn.disabled=true;status('Guardando ubicación…');
   try{const r=await write('/panel/configuracion/ubicacion',body);let data={};try{data=await r.json()}catch(e){}if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Revisa la dirección, el enlace y las coordenadas.');if(token===epoch)status(body.confirmada?'Ubicación guardada y confirmada. Ya puedes enviarla desde ＋ → Ubicación del local.':'Ubicación desactivada. Bruno no la compartirá.');}
   catch(e){if(token===epoch)status(e.message||'No se pudo guardar.')}finally{btn.disabled=false}
  });
 }
 root.CubicoLocationSettings={init,load,reset(){epoch++;if($('local-location-form')){$('local-location-form').reset();status('')}}};
})(window);
