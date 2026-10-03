/* Presentación compartida por el historial y la vista del informe. */
(function (root) {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = value => Number.isFinite(Number(value)) ? Number(value).toLocaleString('es-PA') : '—';
  function render(informe) {
    const datos = informe.datos;
    const fecha = new Date(informe.creado_en).toLocaleString('es-PA', {timeZone:'America/Panama',day:'numeric',month:'long',hour:'numeric',minute:'2-digit'});
    const cabecera = '<div class="report-brand">CÚBICO <span>INFORME DEL NEGOCIO</span></div><h2>'+ (informe.tipo==='mañana'?'Tu día, bajo control.':'Así va Cúbico hoy.') +'</h2><p class="report-date">'+escape(fecha)+' · Panamá</p>';
    if (!datos) return cabecera+'<p class="report-note">Este informe anterior conserva su formato original.</p><div class="report-legacy">'+escape(informe.contenido)+'</div>';
    const conectado = informe.estado_meta==='conexión con Meta disponible';
    const pendientes = [['humanos_pendientes','Atención humana','alerts'],['pagos_pendientes','Pagos por confirmar','packages'],['retiros_pendientes','Retiros pendientes','packages'],['domicilios_pendientes','Domicilios pendientes','packages']];
    const hayPendientes = pendientes.some(([key])=>Number(datos[key])>0);
    const bloqueEstado = '<div class="report-state '+(conectado?'':'report-warning')+'"><span class="report-indicator"></span><div><strong>'+ (conectado?'Bruno generó tu informe':'Revisa la conexión de Bruno')+'</strong><p>'+(conectado?'Conexión con WhatsApp disponible al generar este informe.':'No se pudo confirmar la conexión con WhatsApp al generar este informe.')+'</p></div></div>';
    const actividad = informe.tipo==='mañana' ? '' : '<h4>Actividad de hoy</h4><div class="report-stats"><div><b>'+number(datos.conversaciones_hoy)+'</b><span>Chats con actividad</span></div><div><b>'+number(datos.oportunidades_nuevas)+'</b><span>Oportunidades nuevas</span></div><div><b>$'+Number(datos.costo_hoy||0).toFixed(2)+'</b><span>Costo de IA</span></div></div>';
    const cola = '<h4>'+(hayPendientes?'Lo que necesita tu equipo':'Pendientes actuales')+'</h4><div class="report-queue">'+pendientes.map(([key,label,view])=>'<button type="button" data-report-view="'+view+'"><span>'+label+'</span><b class="'+(Number(datos[key])>0?'has-pending':'')+'">'+number(datos[key])+'</b><span aria-hidden="true">↗</span></button>').join('')+'</div>';
    return cabecera+bloqueEstado+actividad+cola+'<p class="report-note">Estado al momento del informe. La conexión con WhatsApp no comprueba por sí sola que la IA esté respondiendo. Este resumen refleja la actividad del panel; no incluye ventas ni ingresos totales.</p>';
  }
  function dayInPanama(value) {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return null;
    return new Intl.DateTimeFormat('en-CA', {timeZone:'America/Panama',year:'numeric',month:'2-digit',day:'2-digit'}).format(date);
  }
  function splitByDay(reports, now = new Date()) {
    const today = dayInPanama(now);
    return {today: reports.filter(r => dayInPanama(r.creado_en) === today),
      previous: reports.filter(r => dayInPanama(r.creado_en) !== today)};
  }
  root.CubicoReport = {render, splitByDay};
  if (typeof module !== 'undefined') module.exports = root.CubicoReport;
})(typeof window !== 'undefined' ? window : globalThis);
