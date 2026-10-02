/* Identifica cada aviso por el evento que lo originó, no por su tiempo en pantalla. */
(function(root){
  const text=v=>String(v??'').slice(0,500);
  const message=m=>[m?.id??null,text(m?.timestamp),text(m?.contenido)];
  function collect(convs,solicitudes,oportunidades){
    const rows=[];
    function add(kind,id,version,titulo,descripcion,target,warn=false){rows.push({kind,clave:JSON.stringify([kind,text(id),version]),titulo:text(titulo).slice(0,300),descripcion:text(descripcion),target,warn})}
    convs.forEach(c=>{
      const name=c.nombre||c.telefono,target={view:'chats',tel:c.telefono};
      if(c.necesita_atencion_humana)add('humano',c.telefono,[text(c.motivo_escalamiento),message(c.ultimo_mensaje_cliente)],name,c.motivo_escalamiento||'Solicitó atención del equipo',target);
      else if(c.tiene_no_leidos)add('mensaje',c.telefono,message(c.ultimo_mensaje_cliente),'Nuevo mensaje · '+name,c.ultimo_mensaje_cliente?.contenido||'Mensaje pendiente',target,true);
      if(c.ultimo_mensaje?.estado_entrega==='failed')add('fallido',c.telefono,[message(c.ultimo_mensaje),text(c.ultimo_mensaje.error_entrega)],'Mensaje no entregado · '+name,c.ultimo_mensaje.error_entrega||'Meta rechazó el último envío',target);
    });
    solicitudes.forEach(s=>{
      const target={view:'packages',tel:s.telefono,type:s.tipo},version=[text(s.actualizado_en),s.monto_reportado??null,!!s.tiene_comprobante,text(s.referencia_pago)];
      if(s.pago_reportado&&!s.pago_confirmado)add('pago',s.telefono+':'+s.tipo,version,(s.tiene_comprobante?'Comprobante por revisar':'Pago por comprobar')+' · '+s.nombre,s.monto_reportado==null?'Monto pendiente de completar':'Monto reportado: $'+Number(s.monto_reportado).toFixed(2),target,true);
      if(s.tipo==='domicilio'&&(!s.direccion||s.direccion==='—'))add('direccion',s.telefono+':'+s.tipo,[text(s.actualizado_en)],'Domicilio sin dirección · '+s.nombre,'Falta confirmar la dirección exacta del cliente.',target);
    });
    oportunidades.filter(o=>o.estado==='nueva').forEach(o=>add('oportunidad',o.id,[text(o.actualizada_en||o.creada_en)],'Nueva oportunidad · '+(o.empresa||o.nombre_contacto||o.telefono),o.resumen||'Posible cliente empresarial',{view:'opportunities',id:o.id},true));
    return rows;
  }
  const groups={humano:'equipo',mensaje:'equipo',fallido:'equipo',pago:'pagos',direccion:'operaciones',oportunidad:'negocios'};
  const labels={equipo:'Atención del equipo',pagos:'Pagos por revisar',operaciones:'Retiros y domicilios',negocios:'Negocios'};
  function filter(rows,search='',group='all'){
    const query=search.trim().toLocaleLowerCase('es');
    return rows.filter(a=>(group==='all'||groups[a.kind]===group)&&(!query||(a.titulo+' '+a.descripcion).toLocaleLowerCase('es').includes(query)));
  }
  root.CubicoAlerts={collect,filter,groups,labels};
  if(typeof module!=='undefined')module.exports=root.CubicoAlerts;
})(typeof window!=='undefined'?window:globalThis);
