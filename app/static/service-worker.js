const CACHE_VERSION = 'cubico-control-v1';

self.addEventListener('install', event => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', event => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (error) {
    data = { title: 'Cúbico Control', body: 'Tienes una alerta nueva.' };
  }

  event.waitUntil((async () => {
    const ventanas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    if (ventanas.some(cliente => cliente.visibilityState === 'visible')) return;
    await self.registration.showNotification(data.title || 'Cúbico Control', {
      body: data.body || 'Tienes una alerta nueva.',
      icon: '/static/logo.png',
      badge: '/static/logo.png',
      tag: data.tag || 'cubico-alerta',
      renotify: true,
      data: { url: data.url || '/admin' }
    });
  })());
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const destino = new URL(event.notification.data?.url || '/admin', self.location.origin).href;
  event.waitUntil((async () => {
    const ventanas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const ventana of ventanas) {
      if ('navigate' in ventana) await ventana.navigate(destino);
      if ('focus' in ventana) return ventana.focus();
    }
    return self.clients.openWindow(destino);
  })());
});
