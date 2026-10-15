/* Identifica cada aviso por el evento que lo originó, no por su tiempo en pantalla. */
(function(root){
  const text=v=>String(v??'').slice(0,500);
  const message=m=>[m?.id??null,text(m?.timestamp),text(m?.contenido)];
  function collect(convs,solicitudes,oportunidades){
    const rows=[];
    function add(kind,id,version,titulo,descripcion,target,warn=false){rows.push({kind,clave:JSON.stringify([kind,text(id),version]),titulo:text(titulo).slice(0,300),descripcion:text(descripcion),target,warn})}
    convs.forEach(c=>{
      const name=c.nombre||c.telefono,target={view:'chats',tel:c.telefono};
      if(c.necesita_atencion_humana)add('humano',c.telefono,[text(c.motivo_escalamiento),message(c.ultimo_mensaje_cliente)],(/mal identificado/i.test(c.motivo_escalamiento||'')?'Paquete mal identificado · ':'')+name,c.motivo_escalamiento||'Solicitó atención del equipo',target);
      else if(c.tiene_no_leidos)add('mensaje',c.telefono,message(c.ultimo_mensaje_cliente),'Nuevo mensaje · '+name,c.ultimo_mensaje_cliente?.contenido||'Mensaje pendiente',target,true);
      if(c.ultimo_mensaje?.estado_entrega==='failed')add('fallido',c.telefono,[message(c.ultimo_mensaje),text(c.ultimo_mensaje.error_entrega)],'Mensaje no entregado · '+name,c.ultimo_mensaje.error_entrega||'Meta rechazó el último envío',target);
    });
    solicitudes.forEach(s=>{
      const target={view:'packages',tel:s.telefono,type:s.tipo},version=[text(s.actualizado_en),s.monto_reportado??null,!!s.tiene_comprobante,text(s.referencia_pago)];
      if(s.pago_reportado&&!s.pago_confirmado)add('pago',s.telefono+':'+s.tipo,version,(s.tiene_comprobante?'Comprobante por revisar':'Pago por comprobar')+' · '+s.nombre,s.monto_reportado==null?'Monto pendiente de completar':'Monto reportado: $'+Number(s.monto_reportado).toFixed(2),target,true);
      if(s.tipo==='domicilio'&&(!s.direccion||s.direccion==='—'))add('direccion',s.telefono+':'+s.tipo,[text(s.actualizado_en)],'Domicilio sin dirección · '+s.nombre,'Falta confirmar la dirección exacta del cliente.',target);
    });
    oportunidades.filter(o=>o.estado==='nueva').forEach(o=>add('oportunidad',o.id,[text(o.actualizada_en||o.creada_en)],'Nueva oportunidad · '+(o.empresa||o.nombre_contacto||o.telefono),o.resumen||'Posible cliente empresarial',{view:'opportunities',id:o.id},true));
    return rows.map(a=>({...a,contexto:context(a,convs.find(c=>c.telefono===a.target.tel))}));
  }
  const groups={humano:'equipo',mensaje:'equipo',fallido:'equipo',pago:'pagos',direccion:'operaciones',malid:'equipo',demora_miami:'equipo',oportunidad:'negocios'};
  const labels={equipo:'Atención del equipo',pagos:'Pagos por revisar',operaciones:'Retiros y domicilios',negocios:'Negocios'};
  function filter(rows,search='',group='all'){
    const query=search.trim().toLocaleLowerCase('es');
    return rows.filter(a=>(group==='all'||groups[a.kind]===group)&&(!query||(a.titulo+' '+a.descripcion+' '+JSON.stringify(a.contexto||{})).toLocaleLowerCase('es').includes(query)));
  }

  function context(a,c){
    if(a.kind==='humano'&&c?.contexto_atencion)return c.contexto_atencion;
    const guides={
      mensaje:['Mensaje pendiente',['Leer el último mensaje y comprobar si ya recibió respuesta.'],'Revisar la consulta antes de redactar una respuesta.'],
      fallido:['Mensaje no entregado',['Revisar el error de entrega y el estado actual del mensaje.','Si venció la ventana de WhatsApp, usar una plantilla aprobada; evitar reenvíos duplicados.'],'Hay un mensaje que no llegó a entregarse. Revisa el contenido antes de volver a enviarlo.'],
      pago:['Pago por comprobar',['Comparar monto, referencia y destinatario del comprobante con el pago recibido.','Consultar el saldo actualizado antes de confirmar el pago o liberar la entrega.'],'Voy a revisar tu comprobante y confirmar el pago recibido antes de actualizar el saldo.'],
      direccion:['Dirección pendiente',['Pedir dirección completa, referencia y contacto para la entrega.','Confirmar disponibilidad de reparto antes de prometer una fecha.'],'¿Me compartes la dirección completa y una referencia para revisar la entrega a domicilio?'],
      oportunidad:['Oportunidad comercial',['Revisar la necesidad del negocio y los datos que faltan.','Asignar un responsable y preparar una propuesta con tarifas confirmadas.'],'Para preparar tu propuesta, necesitamos confirmar origen, tipo de mercancía y volumen aproximado.'],
      malid:['Paquete mal identificado',['Revisar el tracking y confirmar el destinatario con bodega.','Corregir la asociación al cliente y comprobar el resultado.'],'El registro de tu paquete requiere revisar su identificación antes de confirmar cómo continuar.'],
      demora_miami:['Demora en Miami',['Actualizar la consulta del tracking.','Confirmar con operaciones si hay salida o llegada posterior; no prometer fechas sin confirmar.'],'El último registro disponible indica Miami. Necesitamos comprobar si hay movimientos posteriores.'],
      humano:['Revisión del equipo',['Leer el historial y aclarar qué solicitud sigue pendiente.','Consultar los datos actuales antes de responder.'],'Voy a revisar tu solicitud para darte una respuesta precisa.']
    };
    const g=guides[a.kind]||guides.humano;
    return {categoria:g[0],motivo:a.descripcion,ultimo_cliente:c?.ultimo_mensaje_cliente?{texto:c.ultimo_mensaje_cliente.contenido,fecha:c.ultimo_mensaje_cliente.timestamp}:null,
      ultima_respuesta:c?.ultimo_mensaje&&c.ultimo_mensaje.rol!=='user'?{texto:c.ultimo_mensaje.contenido,fecha:c.ultimo_mensaje.timestamp,estado_entrega:c.ultimo_mensaje.estado_entrega}:null,
      pasos:g[1],borrador:g[2],nota:'Guía orientativa: verifica el estado actual y si el equipo ya intervino. Los mensajes mostrados son los últimos del chat. No se envía nada automáticamente.'};
  }
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function detail(ctx){
    if(!ctx)return '';
    const quote=(label,m)=>m?'<div class="attention-quote"><b>'+label+'</b><p>'+escape(m.texto||'Mensaje sin texto; revisar el adjunto en el chat.')+'</p><small>'+escape(m.fecha||'Fecha sin registrar')+(m.estado_entrega?' · '+escape(m.estado_entrega):'')+'</small></div>':'';
    return '<details class="attention-detail"><summary>Contexto y respuesta orientativa</summary><div class="attention-body"><b>Por qué requiere atención</b><p>'+escape(ctx.motivo)+'</p>'+quote('Último mensaje del cliente',ctx.ultimo_cliente)+quote('Última respuesta registrada',ctx.ultima_respuesta)+'<b>Qué hacer</b><ol>'+(ctx.pasos||[]).map(p=>'<li>'+escape(p)+'</li>').join('')+'</ol><b>Borrador para revisar y adaptar</b><p class="attention-draft">'+escape(ctx.borrador)+'</p><small>'+escape(ctx.nota)+'</small></div></details>';
  }
  root.CubicoAlerts={collect,filter,groups,labels,context,detail};
  if(typeof module!=='undefined')module.exports=root.CubicoAlerts;
})(typeof window!=='undefined'?window:globalThis);
