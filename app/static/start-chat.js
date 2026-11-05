(()=>{
  let api,openChat,templates=[],busy=false,requestId=null,uncertain=false;
  const el=id=>document.getElementById('nc-'+id);
  function say(text){el('status').textContent=text}
  function selected(){return templates[Number(el('template').value)]}
  function values(){return Array.from(el('variables').querySelectorAll('input')).map(input=>input.value.trim())}
  function preview(){
    const row=selected();if(!row)return;
    const params=values();const body=row.texto.replace(/{{([0-9]+)}}/g,(_,number)=>params[Number(number)-1]||'['+number+']');
    el('preview').textContent=[body,row.pie,...row.botones.map(button=>button.texto+': '+button.url)].filter(Boolean).join('\n\n');
    el('image').hidden=!row.imagen;el('image-note').hidden=!row.imagen;
  }
  function changedTemplate(){
    const row=selected();el('variables').replaceChildren();if(!row)return;
    for(let i=0;i<row.variables;i++){
      const label=document.createElement('label');label.textContent=i===0&&/^Hola,?\s*\{\{1\}\}/i.test(row.texto)?'Nombre de la persona':'Dato '+(i+1)+' del mensaje';
      const input=document.createElement('input');input.type='text';input.required=true;input.maxLength=300;input.autocomplete='off';input.addEventListener('input',preview);label.append(input);el('variables').append(label);
    }
    preview();
  }
  async function show(){
    if(busy)return;
    requestId=crypto.randomUUID();uncertain=false;el('form').reset();templates=[];el('template').replaceChildren();
    el('variables').replaceChildren();el('preview').textContent='';el('image').hidden=true;el('image-note').hidden=true;el('send').disabled=true;
    el('dialog').showModal();say('Consultando plantillas aprobadas…');
    try{
      const response=await api('/panel/iniciar-chat/plantillas');const data=await response.json();
      if(!response.ok)throw Error(data.detail||'No se pudieron cargar las plantillas');
      templates=data;
      templates.forEach((row,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=row.nombre+' · '+row.idioma+' · '+row.categoria;el('template').append(option)});
      changedTemplate();el('send').disabled=!templates.length;
      say(templates.length?'Completa el número, revisa el mensaje y confirma el permiso de contacto.':'No hay plantillas aprobadas compatibles con este envío.');
      el('phone').focus();
    }catch(error){say(error.message)}
  }
  function lock(value){busy=value;el('form').querySelectorAll('input,select,button').forEach(node=>node.disabled=value);el('send').disabled=value||uncertain}
  async function send(event){
    event.preventDefault();if(busy||uncertain||!el('form').reportValidity())return;
    const row=selected();if(!row)return;
    const raw=el('phone').value.replace(/[ +()\-]/g,'');
    const number=/^[2-9][0-9]{7}$/.test(raw)?'507'+raw:raw;
    if(!/^[1-9][0-9]{7,14}$/.test(number)){say('Revisa el número y el código de país.');return}
    const body={request_id:requestId,plantilla:row.nombre,idioma:row.idioma,huella:row.huella,valores:values(),permiso_contacto:el('consent').checked};
    lock(true);say('Enviando la plantilla… No vuelvas a pulsar Enviar.');
    try{
      const response=await api('/panel/iniciar-chat/'+number,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const data=await response.json();
      if(!response.ok){if(response.status>=500||response.status===409)uncertain=true;throw Error(data.detail||'No se confirmó el envío')}
      el('dialog').close();await openChat(data.telefono,data.mensaje);
      say(data.mensaje);
    }catch(error){uncertain=true;say(error.message+'. Revisa el chat antes de iniciar otro envío. No se reintentará automáticamente.')}
    finally{lock(false)}
  }
  function init(request,onOpen){
    api=request;openChat=onOpen;el('open').addEventListener('click',show);el('template').addEventListener('change',changedTemplate);
    el('form').addEventListener('submit',send);el('close').addEventListener('click',()=>{if(!busy)el('dialog').close()});
    el('dialog').addEventListener('cancel',event=>{if(busy)event.preventDefault()});
  }
  window.CubicoStartChat={init};
})();
