window.CubicoRelease = (() => {
  let get, generation=0;
  const panelVersion=document.body.dataset.panelVersion;
  const $=id=>document.getElementById(id);
  async function load(){if(!get)return;const current=++generation;try{const r=await get('/panel/version');if(!r.ok)throw Error();const data=await r.json();if(current!==generation)return;if(typeof data.version!=='string'||!Array.isArray(data.novedades))throw Error();const different=data.version!==panelVersion;
    $('app-installed-version').textContent='v'+data.version;
    $('app-release-date').textContent='Actualización: '+new Date(data.fecha+'T12:00:00-05:00').toLocaleDateString('es-PA',{timeZone:'America/Panama',day:'numeric',month:'long',year:'numeric'});
    $('app-release-title').textContent=data.titulo;
    $('app-release-changes').replaceChildren(...data.novedades.map(text=>{const li=document.createElement('li');li.textContent=text;return li}));
    $('app-release-status').textContent=different?`Tu panel es v${panelVersion}; el servidor está en v${data.version}. Recarga para cargar los cambios.`:'Panel y servidor tienen la misma versión.';
    $('app-release-status').classList.toggle('release-warning',different);$('app-release-reload').hidden=!different;
    $('app-release-banner').hidden=!different;$('app-release-banner-text').textContent=different?`El servidor está en v${data.version}. Recarga el panel para cargar esa versión.`:'';
    $('app-version-footer').textContent='Cúbico · v'+data.version;
  }catch{if(current!==generation)return;$('app-release-status').textContent='No se pudo comprobar la versión del servidor. Intenta nuevamente.';$('app-version-footer').textContent='Panel · v'+panelVersion;$('app-installed-version').textContent='Sin confirmar';$('app-release-date').textContent='';$('app-release-title').textContent='';$('app-release-changes').replaceChildren();$('app-release-reload').hidden=true;$('app-release-banner').hidden=true;}}
  function init(apiGet){get=apiGet;$('app-release-check').onclick=load;for(const id of ['app-release-reload','app-release-banner-reload'])$(id).onclick=()=>window.location.reload();}
  return {init,load};
})();
