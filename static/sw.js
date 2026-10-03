const CACHE_NAME = 'bm-tracker-v33';
const ASSETS_TO_CACHE = [
  '/',
  '/partidos',
  '/equipos',
  '/nuevo_partido',
  '/temporada',
  '/comparar',
  '/porteria',
  '/static/css/styles.css',
  '/static/js/app.js',
  '/static/js/queue.js',
  '/static/js/stats.js',
  '/static/js/timer.js',
  '/static/js/comparar.js',
  '/static/js/porteria.js',
  '/static/vendor/chart.min.js',
  '/manifest.webmanifest'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      // Descarga forzada de red: el precache nunca puede resucitar HTML/JS viejos
      .then(cache => cache.addAll(ASSETS_TO_CACHE.map(u => new Request(u, { cache: 'reload' }))).catch(err => console.log('Cache addAll non-critical notice:', err)))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  // Ignore non-GET requests in SW
  if (request.method !== 'GET') {
    return;
  }

  // 1. API routes: Network first, fallback to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request).catch(() => caches.match(request))
    );
    return;
  }

  // 2. HTML navigation requests & pages: Network first, fallback to cache safely
  if (request.mode === 'navigate' || (request.headers.get('accept') && request.headers.get('accept').includes('text/html')) ||
      ['/', '/partidos', '/equipos', '/nuevo_partido', '/temporada', '/stats', '/comparar', '/porteria'].includes(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response && response.status === 200 && response.type === 'basic') {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, responseClone));
          }
          return response;
        })
        .catch(async () => {
          const cachedResponse = await caches.match(request);
          if (cachedResponse) return cachedResponse;
          const pathnameCache = await caches.match(url.pathname);
          if (pathnameCache) return pathnameCache;
          return caches.match('/') || new Response('Offline', { status: 503, statusText: 'Offline' });
        })
    );
    return;
  }

  // 3. Static assets (CSS, JS, images): Cache first, fallback to network
  event.respondWith(
    caches.match(request).then(cachedResponse => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(request).then(response => {
        if (response && response.status === 200 && response.type === 'basic') {
          const responseToCache = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, responseToCache));
        }
        return response;
      }).catch(err => {
        console.warn('Fetch failed for asset:', request.url, err);
      });
    })
  );
});
