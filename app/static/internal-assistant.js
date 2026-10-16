/* Private staff queries. No send API is called here. */
(function(root){
  let api, apply, phone=null, epoch=0, busy=false, result=null, revision=0;
  const reviewed=new Map();
  const $=id=>root.document.getElementById(id);
  const money=value=>Number(value).toLocaleString('en-US',{style:'currency',currency:'USD'});
  function status(text){$('bruno-status').textContent=text}
  function controls(){$('bruno-question').readOnly=busy;for(const id of ['bruno-ask','bruno-prepare'])$(id).disabled=busy||!phone;for(const b of root.document.querySelectorAll('[data-bruno-prompt]'))b.disabled=busy||!phone;$('bruno-use').disabled=!result?.borrador||busy}
  function setContext(value){phone=value;epoch++;busy=false;result=null;$('bruno-panel').open=false;$('bruno-question').value='';$('bruno-result').hidden=true;$('bruno-answer').textContent='';$('bruno-draft').value='';$('bruno-evidence').replaceChildren();status('Solo para el equipo. Consultas básicas sin IA; otras consultas generan consumo registrado en Costos.');controls();draftLabel()}
  function draftLabel(){const meta=reviewed.get(phone);$('bruno-reviewed-label').hidden=!meta;$('bruno-reviewed-label').textContent=meta?'Borrador de Bruno · puedes editarlo. Se enviará el texto tal como lo revises.':''}
  function evidence(data){const box=$('bruno-evidence');box.replaceChildren();const add=(label,text)=>{const row=root.document.createElement('p'),b=root.document.createElement('b');b.textContent=label+': ';row.append(b,root.document.createTextNode(text));box.append(row)};
    const f=data.facturas||{},p=data.paquetes||{},last=data.ultimo_pago||{};
    add('Facturación',f.disponible?'Saldo total pendiente '+money(f.saldo_pendiente_total):f.error||'Sin confirmar');
    if(f.disponible)for(const invoice of (f.facturas||[]).filter(x=>Number(x.saldo_pendiente)>0))add(invoice.codigo,money(invoice.saldo_pendiente)+' pendiente · '+invoice.estado);
    if(f.detalle_limitado)add('Detalle','Se muestran hasta 60 facturas. El saldo total incluye todas.');
    add('Paquetes',p.disponible?String(p.cantidad_paquetes)+' registrados':p.error||'Sin confirmar');
    if(p.disponible)for(const parcel of (p.paquetes||[]).slice(0,20))add(parcel.tracking,String(parcel.estado_cargo||'sin estado').replaceAll('_',' ')+' · pago: '+String(parcel.estado_pago||'sin confirmar').replaceAll('_',' '));
    if((p.paquetes||[]).length>20||p.detalle_limitado)add('Detalle','Listado de paquetes limitado. Gestionar permite revisar el detalle del cliente.');
    add('Último pago con fecha',!last.disponible?last.error||'Sin confirmar':last.ultimo_pago?last.ultimo_pago.fecha_pago+' · '+money(last.ultimo_pago.monto):'No hay fecha registrada');
    if(last.historial_fechas_incompleto)add('Atención','Hay pagos sin fecha; no se puede ordenar todo el historial.');
  }
  async function ask(mode){if(busy||!phone)return;const question=$('bruno-question').value.trim();if(!question){status('Escribe qué necesitas consultar.');$('bruno-question').focus();return}if(question.length>2000){status('La consulta puede tener hasta 2000 caracteres.');return}
    const target=phone,version=++epoch;busy=true;result=null;$('bruno-result').hidden=true;status('Consultando los datos actuales de este cliente…');controls();
    try{const response=await api(target,{pregunta:question,modo:mode});let data={};try{data=await response.json()}catch(e){}if(version!==epoch||target!==phone)return;if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo completar la consulta.');if(data.telefono!==target||data.privado!==true)throw Error('El resultado no corresponde a esta conversación. Vuelve a consultar.');
      result=data;$('bruno-result').hidden=false;$('bruno-answer').textContent=data.respuesta||'Sin respuesta';$('bruno-draft-section').hidden=!data.borrador;$('bruno-draft').value=data.borrador||'';evidence(data.datos||{});
      const time=new Date(data.consultado_en);$('bruno-source').textContent='Cliente '+data.codigo_cliente+' · Consultado '+(Number.isNaN(time.getTime())?'ahora':time.toLocaleString('es-PA',{timeZone:'America/Panama'}));status('Consulta privada terminada. Revisa los datos y el borrador; todavía no se ha enviado nada.');
    }catch(e){if(version===epoch&&target===phone)status(e.message||'No se pudo completar la consulta.')}finally{if(version===epoch&&target===phone){busy=false;controls()}}
  }
  function init(request,onDraft){api=request;apply=onDraft;$('bruno-ask').addEventListener('click',()=>ask('consulta'));$('bruno-prepare').addEventListener('click',()=>ask('borrador'));
    for(const b of root.document.querySelectorAll('[data-bruno-prompt]'))b.addEventListener('click',()=>{$('bruno-question').value=b.dataset.brunoPrompt;ask('consulta')});
    $('bruno-use').addEventListener('click',()=>{if(!result?.borrador||result.telefono!==phone)return;if(!apply(result.borrador,phone)){status('Ya hay texto en el editor o está ocupado. Conservamos tu borrador: cópialo o vacía el editor antes de usar este.');return}reviewed.set(phone,{codigo_cliente:result.codigo_cliente,consultado_en:result.consultado_en,revision:++revision});draftLabel();$('bruno-panel').open=false;status('Borrador colocado en el editor. Revísalo y pulsa Enviar cuando esté listo.');});
    $('bruno-copy').addEventListener('click',async()=>{const field=$('bruno-draft');try{await root.navigator.clipboard.writeText(field.value);status('Borrador copiado.')}catch(e){field.focus();field.select();status('Texto seleccionado. Usa Copiar en el menú de tu dispositivo.')}});
    $('message-input').addEventListener('input',()=>{if(!$('message-input').value.trim()){reviewed.delete(phone);draftLabel()}});setContext(null);
  }
  root.CubicoBruno={init,setContext,reset(){reviewed.clear();setContext(null)},meta(value){return reviewed.get(value)},sent(value,meta){if(reviewed.get(value)===meta)reviewed.delete(value);draftLabel()}};
})(window);
