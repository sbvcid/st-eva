/**
 * ST-EVA Service Worker (PWA)
 * Caches frontend app shell and static UI assets.
 * 
 * STRICT POLICY:
 * NEVER cache /api/ endpoints (SEC data, SQLite observations, admission/valuation results).
 * All financial analysis queries are strictly network-only.
 */

const CACHE_NAME = 'st-eva-shell-v1';
const ASSETS_CACHE_NAME = 'st-eva-assets-v1';

const APP_SHELL_FILES = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/icon-maskable-192.png',
  '/icons/icon-maskable-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(APP_SHELL_FILES);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && key !== ASSETS_CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // 1. API Calls: STRICT NETWORK-ONLY (Never Cache Financial or Admission Data)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request).catch(() => {
        return new Response(
          JSON.stringify({
            detail: 'Offline: Financial analysis and admission verification require an active network connection.',
            offline: true
          }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          }
        );
      })
    );
    return;
  }

  // 2. Navigation Requests (HTML / App Shell)
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(async () => {
        const cache = await caches.open(CACHE_NAME);
        const cachedShell = await cache.match('/index.html');
        return cachedShell || new Response('Offline: ST-EVA App Shell Unavailable', { status: 503 });
      })
    );
    return;
  }

  // 3. Static Assets (CSS, JS, Fonts, Icons)
  if (
    url.pathname.startsWith('/assets/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.css')
  ) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          // Stale-while-revalidate for background updates
          fetch(request).then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              caches.open(ASSETS_CACHE_NAME).then((cache) => {
                cache.put(request, networkResponse);
              });
            }
          }).catch(() => {/* Ignore background network errors */});
          return cachedResponse;
        }

        // Cache miss: fetch from network and cache
        return fetch(request).then((networkResponse) => {
          if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
            return networkResponse;
          }
          const responseToCache = networkResponse.clone();
          caches.open(ASSETS_CACHE_NAME).then((cache) => {
            cache.put(request, responseToCache);
          });
          return networkResponse;
        });
      })
    );
    return;
  }

  // Fallback default
  event.respondWith(fetch(request));
});

