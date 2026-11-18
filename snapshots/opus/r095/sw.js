// «Зёрнышко на экране»: минимальный service worker — чтобы иконку можно было положить на экран телефона
// и чтобы она открывалась даже в метро без сети (последняя сохранённая версия сайта; SMS/мессенджер уйдут, когда появится связь).
// Сначала сеть — цены и витрина всегда свежие, кэш только на случай, если сети нет.
const C = 'zr-v30', SHELL = ['./', 'index.html', 'style.css', 'evening.css','icon.svg', 'icon-180.png', 'icon-192.png','manifest.webmanifest'];
self.addEventListener('install', e => { e.waitUntil(caches.open(C).then(c => c.addAll(SHELL)).catch(() => {})); self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== location.origin) return; // погода, карты и прочее чужое — мимо кэша
  e.respondWith(fetch(r).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(C).then(c => c.put(r.mode === 'navigate' ? 'index.html' : r, copy)); }
    return res;
  }).catch(() => caches.match(r.mode === 'navigate' ? 'index.html' : r, { ignoreSearch: true })));
});
