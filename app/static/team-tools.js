/* Shared incident tracking and personal external-AI connections. No automatic send. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const sections={overview:'Resumen',chats:'Chats',packages:'Solicitudes',opportunities:'Negocios',costs:'Costos',alerts:'Alertas',operations:'Situación actual',settings:'Configuración',incidents:'Incidencias',general:'General'};
  const states={pendiente:'Pendiente',en_revision:'En revisión',resuelta:'Resuelta',descartada:'Descartada'};
  let request, context, generation=0, ticket=null, users=[], busy=false, image=null, loadCount=0, connectionsCount=0,detailCount=0,pictureCount=0,readingImage=false,draftActive=false,returnFocus=null;
  const date=x=>x?new Date(x).toLocaleString('es-PA',{timeZone:'America/Panama',dateStyle:'medium',timeStyle:'short'}):'Sin uso';
  function options(values,selected){return Object.entries(values).map(([k,v])=>`<option value="${esc(k)}" ${selected===k?'selected':''}>${esc(v)}</option>`).join('')}
  async function api(path,method='GET',body){const r=await request(path,{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'No se pudo completar la operación.');return data}
  function error(id,e){$(id).textContent=e.message||'No se pudo completar. Intenta de nuevo.'}
  function reset(){closeReport(false);draftActive=false;$('tt-report-resume').hidden=true;generation++;loadCount++;connectionsCount++;detailCount++;pictureCount++;readingImage=false;ticket=null;image=null;busy=false;for(const id of ['tt-inc-list','tt-inc-detail','tt-ai-list','tt-ai-secret'])$(id).replaceChildren();$('tt-ai-secret').hidden=true;$('tt-inc-detail').hidden=true;$('tt-inc-new').hidden=true;$('tt-inc-form').reset();$('tt-ai-form').reset();$('tt-inc-file').value='';for(const id of ['tt-inc-status','tt-edit-status','tt-ai-status','tt-list-status'])if($(id))$(id).textContent='';}
  async function load(){const epoch=generation, seq=++loadCount;$('tt-list-status').textContent='Cargando incidencias…';try{const query=new URLSearchParams();if($('tt-filter-state').value)query.set('estado',$('tt-filter-state').value);if($('tt-filter-section').value)query.set('seccion',$('tt-filter-section').value);const d=await api('/panel/incidencias?'+query);if(epoch!==generation||seq!==loadCount)return;users=d.usuarios;$('tt-inc-list').innerHTML=d.incidencias.map(i=>`<article class="tt-item"><div class="tt-meta">${esc(i.codigo)} · ${esc(sections[i.seccion])} · ${esc(states[i.estado])} · Prioridad ${esc(i.prioridad)}</div><h4>${esc(i.titulo)}</h4><p>${esc(i.descripcion.slice(0,220))}${i.descripcion.length>220?'…':''}</p><div class="tt-meta">${esc(i.creador)} · ${esc(date(i.actualizado_en))} · Responsable: ${esc(i.responsable||'Sin asignar')}</div><footer><button class="btn" type="button" data-ticket="${i.id}">Abrir y dar seguimiento</button></footer></article>`).join('')||'<p>No hay incidencias con estos filtros.</p>';$('tt-list-status').textContent=`${d.incidencias.length} incidencias · Se muestran hasta 200 por filtro.`}catch(e){if(epoch===generation&&seq===loadCount)error('tt-list-status',e)}}
  async function open(id){const epoch=generation,seq=++detailCount;$('tt-list-status').textContent='Abriendo incidencia…';try{const d=await api('/panel/incidencias/'+id);if(epoch!==generation||seq!==detailCount)return;ticket=d;$('tt-inc-detail').hidden=false;$('tt-inc-detail').innerHTML=`<div class="tt-detail-heading"><h3>${esc(d.codigo)} · ${esc(d.titulo)}</h3><button class="btn" type="button" id="tt-detail-close">Cerrar detalle</button></div><p class="tt-meta">${esc(sections[d.seccion])} · ${esc(d.tipo)} · Creada por ${esc(d.creador)} · ${esc(date(d.creado_en))}</p><p style="white-space:pre-wrap">${esc(d.descripcion)}</p>${d.esperado?`<h4>Qué debería ocurrir</h4><p style="white-space:pre-wrap">${esc(d.esperado)}</p>`:''}<details><summary>Contexto técnico registrado</summary><p class="tt-meta">${esc(d.contexto)}</p></details>${d.captura?'<img id="tt-detail-shot" class="tt-shot" alt="Captura adjunta a la incidencia">':''}<form id="tt-edit-form" class="tt-form"><div class="tt-two"><label>Estado<select id="tt-edit-state">${options(states,d.estado)}</select></label><label>Prioridad<select id="tt-edit-priority">${options({baja:'Baja',normal:'Normal',alta:'Alta'},d.prioridad)}</select></label></div><label>Responsable<select id="tt-edit-owner">${options({'':'Sin asignar',...Object.fromEntries(users.map(u=>[u,u]))},d.responsable||'')}</select></label><label>Agregar seguimiento<textarea id="tt-edit-note" maxlength="4000" placeholder="Qué se revisó, qué falta o cómo se resolvió"></textarea></label><div class="tt-row"><button class="btn dark" type="submit">Guardar seguimiento</button><button class="btn" type="button" id="tt-export">Descargar reporte</button></div></form><p id="tt-edit-status" class="tt-status" role="status"></p><h4>Historial</h4>${d.historial.map(h=>`<div class="tt-note"><b>${esc(h.usuario)}</b> · ${esc(date(h.fecha))}\n${esc(h.accion)}${h.nota?'\n'+esc(h.nota):''}</div>`).join('')}`;if(d.captura)$('tt-detail-shot').src=d.captura;$('tt-detail-close').onclick=()=>{detailCount++;$('tt-inc-detail').hidden=true;ticket=null};$('tt-edit-form').onsubmit=save;$('tt-export').onclick=download;$('tt-inc-detail').scrollIntoView({block:'start',behavior:'smooth'});$('tt-list-status').textContent=''}catch(e){if(epoch===generation)error('tt-list-status',e)}}
  async function save(e){e.preventDefault();if(busy||!ticket)return;busy=true;const epoch=generation,old=ticket,button=e.target.querySelector('[type=submit]');button.disabled=true;$('tt-edit-status').textContent='Guardando…';try{const d=await api('/panel/incidencias/'+old.id,'PATCH',{revision:old.revision,estado:$('tt-edit-state').value,prioridad:$('tt-edit-priority').value,responsable:$('tt-edit-owner').value||null,nota:$('tt-edit-note').value});if(epoch!==generation)return;if(ticket?.id===old.id){ticket=d;await open(d.id);$('tt-edit-status').textContent='Seguimiento guardado.'}await load()}catch(err){if(epoch===generation)error('tt-edit-status',err)}finally{if(epoch===generation){busy=false;button.disabled=false}}}
  function download(){if(!ticket)return;const d={...ticket};delete d.captura;const blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=d.codigo+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
  function drawerViewport(){
    const viewport=window.visualViewport,drawer=$('tt-inc-new');
    drawer.style.setProperty('--tt-vtop',(viewport?.offsetTop||0)+'px');
    drawer.style.setProperty('--tt-vheight',(viewport?.height||window.innerHeight)+'px');
  }
  function closeReport(restore=true){
    const drawer=$('tt-inc-new');
    if(drawer.contains(document.activeElement))document.activeElement.blur();
    drawer.hidden=true;for(const id of ['tt-report','tt-quick-report','tt-report-resume'])$(id).setAttribute('aria-expanded','false');$('tt-report-resume').hidden=!draftActive;
    if(restore&&returnFocus?.isConnected)returnFocus.focus({preventScroll:true});
  }
  function discardReport(){
    pictureCount++;readingImage=false;draftActive=false;image=null;
    $('tt-inc-form').reset();$('tt-inc-file').value='';$('tt-inc-status').textContent='';
    $('tt-inc-form').querySelector('[type=submit]').disabled=false;
    closeReport();
  }
  function newReport(captured){
    returnFocus=document.activeElement;
    if(!draftActive){
      pictureCount++;readingImage=false;const c=captured?.context?captured:context();
      $('tt-inc-form').reset();$('tt-inc-section').value=sections[c.view]?c.view:'general';
      $('tt-inc-context').value=c.context;$('tt-inc-file').value='';image=null;
      $('tt-inc-form').querySelector('[type=submit]').disabled=false;$('tt-inc-status').textContent='';
      $('tt-drawer-origin').textContent='Reportando desde '+(sections[c.view]||'General')+'. Puedes minimizar para revisar la pantalla.';
      $('tt-inc-new').querySelector('.tt-drawer-body').scrollTop=0;draftActive=true;
    }
    drawerViewport();$('tt-inc-new').hidden=false;for(const id of ['tt-report','tt-quick-report','tt-report-resume'])$(id).setAttribute('aria-expanded','true');$('tt-report-resume').hidden=true;
    $('tt-inc-new').focus({preventScroll:true});
  }
  async function submit(e){
    e.preventDefault();if(busy||readingImage)return;busy=true;
    const epoch=generation,button=e.target.querySelector('[type=submit]');button.disabled=true;
    $('tt-inc-status').textContent='Guardando incidencia…';
    try{
      const d=await api('/panel/incidencias','POST',{titulo:$('tt-inc-title').value,descripcion:$('tt-inc-description').value,esperado:$('tt-inc-expected').value,seccion:$('tt-inc-section').value,tipo:$('tt-inc-type').value,prioridad:$('tt-inc-priority').value,contexto:$('tt-inc-context').value,captura:image});
      if(epoch!==generation)return;
      discardReport();
      if(typeof window.say==='function')window.say(d.codigo+' guardada. Puedes verla en Incidencias y mejoras.');
      // Keep the current page, chat, scroll position and composer draft untouched.
      if(document.body.dataset.view==='incidents'){await load();await open(d.id)}
    }catch(err){if(epoch===generation){error('tt-inc-status',err);$('tt-inc-new').hidden=false;$('tt-report-resume').hidden=true;drawerViewport()}}
    finally{if(epoch===generation){busy=false;button.disabled=false}}
  }
  async function picture(file){
    if(!file)return null;
    if(!['image/jpeg','image/png'].includes(file.type)||file.size>12000000)throw Error('Usa una captura JPG o PNG de hasta 12 MB.');
    const raw=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(Error('No se pudo leer la imagen.'));r.readAsDataURL(file)});
    if(file.size<=400000)return raw;
    const img=await new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(Error('No se pudo abrir la imagen.'));i.src=raw});
    const canvas=document.createElement('canvas');const scale=Math.min(1,1600/Math.max(img.width,img.height));canvas.width=Math.max(1,Math.round(img.width*scale));canvas.height=Math.max(1,Math.round(img.height*scale));
    const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(img,0,0,canvas.width,canvas.height);
    for(const quality of [.85,.7,.5,.35]){const result=canvas.toDataURL('image/jpeg',quality);if(result.length<=530000)return result}
    throw Error('La captura sigue siendo muy grande. Recorta la parte relevante antes de adjuntarla.');
  }
  async function loadAI(){const epoch=generation,seq=++connectionsCount;try{const d=await api('/panel/conexiones-ia');if(epoch!==generation||seq!==connectionsCount)return;$('tt-ai-list').innerHTML=d.conexiones.map(c=>`<div class="tt-item"><h4>${esc(c.nombre)}</h4><p class="tt-meta">${esc(c.permisos.join(', '))} · ${c.revocado?'Revocada':c.vencido?'Vencida':'Activa'}<br>Vence: ${esc(date(c.vence_en))}<br>Último uso: ${esc(date(c.ultimo_uso))}${c.ultima_herramienta?' · '+esc(c.ultima_herramienta):''}</p>${!c.revocado&&!c.vencido?`<button class="btn" type="button" data-revoke="${esc(c.id)}">Revocar acceso</button>`:''}</div>`).join('')||'<p>Aún no tienes conexiones personales.</p>'}catch(e){if(epoch===generation)error('tt-ai-status',e)}}
  async function issue(e){e.preventDefault();if(busy)return;busy=true;const epoch=generation,button=e.target.querySelector('[type=submit]');button.disabled=true;$('tt-ai-secret').replaceChildren();$('tt-ai-secret').hidden=true;$('tt-ai-status').textContent='Creando conexión…';try{const scopes=[...document.querySelectorAll('[name=tt-scope]:checked')].map(x=>x.value);const d=await api('/panel/conexiones-ia','POST',{nombre:$('tt-ai-name').value,permisos:scopes});if(epoch!==generation)return;$('tt-ai-secret').hidden=false;$('tt-ai-secret').innerHTML='<b>Clave para autorizar tu Claude · Se muestra una sola vez</b><p>Copia este valor. Al agregar el conector con «Sign in now», pégalo en la página de autorización de Cúbico y revisa sus permisos:</p><p class="tt-secret" id="tt-ai-token"></p><button class="btn" id="tt-ai-copy" type="button">Copiar valor</button> <button class="btn" id="tt-ai-hide" type="button">Ya la guardé · Ocultar</button>';$('tt-ai-token').textContent='Bearer '+d.token;$('tt-ai-copy').onclick=async()=>{try{await navigator.clipboard.writeText($('tt-ai-token').textContent);$('tt-ai-status').textContent='Clave copiada.'}catch(e){$('tt-ai-status').textContent='Selecciona el valor completo para copiarlo.'}};$('tt-ai-hide').onclick=()=>{$('tt-ai-secret').replaceChildren();$('tt-ai-secret').hidden=true};$('tt-ai-status').textContent='Conexión creada. Agrégala a tu Claude siguiendo los pasos de abajo.';await loadAI()}catch(err){if(epoch===generation)error('tt-ai-status',err)}finally{if(epoch===generation){busy=false;button.disabled=false}}}
  function init(req,ctx){request=req;context=ctx;$('tt-inc-section').innerHTML=options(sections,'general');$('tt-filter-section').innerHTML='<option value="">Todas las secciones</option>'+options(sections);$('tt-filter-state').innerHTML='<option value="">Todos los estados</option>'+options(states,'pendiente');$('tt-inc-form').onsubmit=submit;$('tt-report').onclick=()=>newReport();$('tt-quick-report').onclick=()=>newReport(context());
    for(const id of ['tt-inc-cancel','tt-inc-minimize','tt-inc-close'])$(id).onclick=()=>closeReport();
    $('tt-inc-discard').onclick=()=>{if(!busy)discardReport()};$('tt-report-resume').onclick=()=>newReport();
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('tt-inc-new').hidden){e.preventDefault();closeReport()}});
    window.addEventListener('resize',drawerViewport);window.visualViewport?.addEventListener('resize',drawerViewport);window.visualViewport?.addEventListener('scroll',drawerViewport);
    $('tt-filter-state').onchange=load;$('tt-filter-section').onchange=load;$('tt-inc-refresh').onclick=load;$('tt-inc-list').onclick=e=>{const b=e.target.closest('[data-ticket]');if(b)open(b.dataset.ticket)};$('tt-inc-file').onchange=async e=>{image=null;const epoch=generation,seq=++pictureCount,button=$('tt-inc-form').querySelector('[type=submit]');readingImage=true;button.disabled=true;$('tt-inc-status').textContent='Preparando captura…';try{const result=await picture(e.target.files[0]);if(epoch===generation&&seq===pictureCount){image=result;$('tt-inc-status').textContent=result?'Captura lista para adjuntar.':''}}catch(err){if(epoch===generation&&seq===pictureCount){e.target.value='';error('tt-inc-status',err)}}finally{if(epoch===generation&&seq===pictureCount){readingImage=false;button.disabled=false}}};$('tt-ai-form').onsubmit=issue;$('tt-ai-list').onclick=async e=>{const b=e.target.closest('[data-revoke]');if(!b||busy)return;const epoch=generation;b.disabled=true;try{await api('/panel/conexiones-ia/'+b.dataset.revoke,'DELETE');if(epoch!==generation)return;$('tt-ai-secret').replaceChildren();$('tt-ai-secret').hidden=true;$('tt-ai-status').textContent='Acceso revocado.';await loadAI()}catch(err){if(epoch===generation)error('tt-ai-status',err)}finally{b.disabled=false}};}
  window.CubicoTeamTools={init,load,loadAI,reset,newReport};
})();
