(function(root){
 'use strict';
 let epoch=0,busy=false,preview=null,options;
 const assisted=new Map(),$=id=>root.document.getElementById(id);
 function reset(){epoch++;busy=false;preview=null;if($('rewrite-preview'))$('rewrite-preview').hidden=true;if($('rewrite-text'))$('rewrite-text').disabled=false}
 function init(config){options=config;
  $('rewrite-text').onclick=async()=>{if(busy)return;const phone=config.getPhone(),input=config.getInput(),original=input.value;if(!phone||input.disabled||input.readOnly||!original.trim()){config.notify('Escribe primero el mensaje que quieres mejorar.');return}
   const token=++epoch,session=config.getSession();busy=true;$('rewrite-text').disabled=true;$('rewrite-preview').hidden=true;config.notify('Preparando borrador. No se está enviando ningún mensaje.');
   try{const r=await config.request(phone,{mensaje:original});let result={};try{result=await r.json()}catch(e){}if(token!==epoch||phone!==config.getPhone()||session!==config.getSession())return;
    if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:'No se pudo mejorar el texto.');
    if(result.telefono!==phone||result.enviado!==false||typeof result.borrador!=='string')throw Error('El borrador no corresponde al chat actual.');
    preview={phone,original,text:result.borrador};$('rewrite-result').value=result.borrador;$('rewrite-preview').hidden=false;
   }catch(e){if(token===epoch)config.notify(e.message||'No se pudo mejorar. Tu texto se conserva.')}finally{if(token===epoch){busy=false;$('rewrite-text').disabled=false}}
  };
  $('rewrite-use').onclick=()=>{const p=preview,input=config.getInput();if(!p||config.getPhone()!==p.phone)return;
   if(input.disabled||input.readOnly||input.value!==p.original){config.notify('El texto cambió. Lo conservamos; vuelve a preparar el borrador.');return}
   config.onUse(p.text);assisted.set(p.phone,true);reset();$('bruno-panel').open=false;config.notify('Borrador en el editor. Revísalo y pulsa Enviar.');
  };
  $('rewrite-cancel').onclick=reset;
  config.getInput().addEventListener('input',()=>{if(!config.getInput().value.trim())assisted.delete(config.getPhone())});
  return {reset};
 }
 root.CubicoRewrite={init,reset,isAssisted:phone=>assisted.has(phone),sent:phone=>assisted.delete(phone),clear(){assisted.clear();reset()}};
})(window);
