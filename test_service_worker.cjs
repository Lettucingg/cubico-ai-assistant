const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function recibir(payload, visible) {
  const handlers = {}, avisos = [];
  const self = {
    addEventListener: (nombre, handler) => { handlers[nombre] = handler; },
    clients: { matchAll: async () => [{ visibilityState: visible ? 'visible' : 'hidden' }] },
    registration: { showNotification: async (...args) => { avisos.push(args); } },
  };
  vm.runInNewContext(fs.readFileSync('app/static/service-worker.js', 'utf8'), { self });
  let tarea;
  handlers.push({ data: { json: () => payload }, waitUntil: promise => { tarea = promise; } });
  await tarea;
  return avisos;
}

(async () => {
  const informe = { title: 'Resumen operativo', informe_id: 7, url: '/admin?informe=7' };
  const abierto = await recibir(informe, true);
  assert.equal(abierto.length, 1);
  assert.equal(abierto[0][1].data.url, '/admin?informe=7');
  assert.equal((await recibir(informe, false)).length, 1);
  assert.equal((await recibir({ telefono: '50760000000' }, true)).length, 0);
  assert.equal((await recibir({ telefono: '50760000000' }, false)).length, 1);
  console.log('Avisos de informes y mensajes: 4 casos correctos');
})().catch(error => { console.error(error); process.exitCode = 1; });
