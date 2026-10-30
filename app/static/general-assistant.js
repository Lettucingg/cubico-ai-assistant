/* Authenticated staff queries. Search never verifies a WhatsApp customer or sends. */
(function(root){
  const $=id=>root.document.getElementById(id);
  let request, searchRequest, busy=false, result=null, opener=null, epoch=0, searchEpoch=0;
  let customer=null, pendingMode='consulta';
  function status(text){$('general-bruno-status').textContent=text}
  function close(){const drawer=$('general-bruno-drawer');drawer.close();opener?.focus()}
  function controls(){
    $('general-bruno-question').readOnly=busy;
    for(const id of ['general-bruno-ask','general-bruno-prepare','general-bruno-search-button','general-bruno-clear-customer'])$(id).disabled=busy;
    for(const button of $('general-bruno-customers').querySelectorAll('button'))button.disabled=busy;
  }
  function selected(value){
    customer=value;
    $('general-bruno-selected').hidden=!value;
    $('general-bruno-clear-customer').hidden=!value;
    $('general-bruno-selected').textContent=value?'Cliente: '+value.nombre+' · '+value.codigo+' · '+value.tipo:'';
  }
  function candidates(items,resume=false){
    const box=$('general-bruno-customers');box.replaceChildren();
    for(const item of items||[]){
      const button=root.document.createElement('button');button.type='button';button.className='btn';
      button.textContent=item.nombre+' · '+item.codigo+' · '+item.tipo+' · '+item.telefono_referencia;
      button.addEventListener('click',()=>{
        if(busy)return;searchEpoch++;selected(item);box.replaceChildren();controls();result=null;$('general-bruno-output').hidden=true;
        if(resume)ask(pendingMode);else status('Cliente seleccionado. Puedes preguntar por su casillero, saldo o paquetes. No se modificó su chat.');
      });box.append(button);
    }
  }
  function render(data){
    result=data;
    if(data.cliente){selected(data.cliente);$('general-bruno-customers').replaceChildren()}
    if(data.alcance==='busqueda_clientes'){selected(null);candidates(data.clientes,true)}
    $('general-bruno-output').hidden=false;$('general-bruno-answer').textContent=data.respuesta||'';
    $('general-bruno-draft').value=data.borrador||'';$('general-bruno-draft-wrap').hidden=!data.borrador;
    $('general-bruno-copy').disabled=false;
    const scope=data.alcance==='tracking_publico'?'Tracking público':data.cliente?'Consulta interna · '+data.cliente.nombre+' · '+data.cliente.codigo:'Consulta general';
    $('general-bruno-source').textContent=scope+' · '+new Date(data.consultado_en).toLocaleString('es-PA',{timeZone:'America/Panama'});
    status(data.alcance==='busqueda_clientes'?'Elige un resultado para continuar con tu pregunta.':'Listo. Consulta privada; no se envió ningún mensaje.');
  }
  async function search(){
    if(busy||!searchRequest)return;
    const query=$('general-bruno-search').value.trim();
    if(query.length<3){status('Escribe al menos tres caracteres para buscar al cliente.');return}
    const version=++searchEpoch,auth=epoch;
    $('general-bruno-search-button').disabled=true;status('Buscando en el registro de clientes…');
    try{
      const response=await searchRequest(query);const data=await response.json();
      if(version!==searchEpoch||auth!==epoch)return;
      if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo consultar el registro.');
      if(!Array.isArray(data.clientes))throw Error('La búsqueda no devolvió un listado válido.');
      candidates(data.clientes);status(data.clientes.length?'Selecciona el cliente correcto.'+(data.detalle_limitado?' Hay más coincidencias; precisa la búsqueda.':''):'No se encontraron clientes activos con esa referencia.');
    }catch(e){if(version===searchEpoch&&auth===epoch)status(e.message||'No se pudo buscar al cliente.')}
    finally{if(version===searchEpoch&&auth===epoch)$('general-bruno-search-button').disabled=busy}
  }
  async function ask(mode){
    if(busy)return;
    const text=$('general-bruno-question').value.trim();
    if(!text){status('Escribe tu pregunta.');$('general-bruno-question').focus();return}
    const version=epoch;pendingMode=mode;searchEpoch++;busy=true;result=null;$('general-bruno-output').hidden=true;
    status('Consultando… Puedes cerrar y volver a abrir sin perder la consulta.');controls();
    try{
      const body={pregunta:text,modo:mode};if(customer){body.cliente_codigo=customer.codigo;body.cliente_tipo=customer.tipo}
      const response=await request(body);let data={};try{data=await response.json()}catch(e){}
      if(version!==epoch)return;
      if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo completar la consulta.');
      if(data.privado!==true||data.telefono!==null)throw Error('El resultado no corresponde a una consulta general.');
      render(data);
    }catch(e){if(version===epoch)status(e.message||'No se pudo consultar. Se conserva tu pregunta; puedes reintentar.')}
    finally{if(version===epoch){busy=false;controls()}}
  }
  function init(api,searchApi){
    request=api;searchRequest=searchApi;
    $('general-bruno-open').addEventListener('click',event=>{opener=event.currentTarget;const drawer=$('general-bruno-drawer');if(!drawer.open)drawer.showModal();$('general-bruno-question').focus()});
    $('general-bruno-close').addEventListener('click',close);
    $('general-bruno-drawer').addEventListener('click',event=>{if(event.target===$('general-bruno-drawer')){const rect=event.target.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right)close()}});
    $('general-bruno-ask').addEventListener('click',()=>ask('consulta'));
    $('general-bruno-prepare').addEventListener('click',()=>ask('borrador'));
    $('general-bruno-search-button').addEventListener('click',search);
    $('general-bruno-search').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();search()}});
    $('general-bruno-clear-customer').addEventListener('click',()=>{if(busy)return;searchEpoch++;selected(null);controls();result=null;$('general-bruno-output').hidden=true;candidates([]);status('Consulta general. No hay cliente seleccionado.')});
    $('general-bruno-copy').addEventListener('click',async()=>{
      if(!result)return;const text=result.borrador||result.respuesta;
      try{await root.navigator.clipboard.writeText(text);status('Texto copiado. Pégalo en el chat correspondiente y revísalo antes de enviar.')}
      catch(e){const field=$('general-bruno-draft');$('general-bruno-draft-wrap').hidden=false;field.value=text;field.focus();field.select();status('Texto seleccionado. Usa Copiar en el menú del dispositivo.')}
    });
    for(const button of root.document.querySelectorAll('[data-general-bruno-prompt]'))button.addEventListener('click',()=>{if(busy)return;selected(null);candidates([]);$('general-bruno-question').value=button.dataset.generalBrunoPrompt;ask('consulta')});
  }
  root.CubicoGeneralBruno={init,reset(){epoch++;searchEpoch++;busy=false;result=null;selected(null);candidates([]);controls();$('general-bruno-search').value='';$('general-bruno-answer').textContent='';$('general-bruno-draft').value='';status('Consulta privada del equipo.');$('general-bruno-question').value='';$('general-bruno-output').hidden=true;if($('general-bruno-drawer').open)close()}};
})(window);
