{% load static %}const CACHE_VERSION = 'v1';
const STATIC_CACHE = 'static-' + CACHE_VERSION;
const PAGES_CACHE = 'pages-' + CACHE_VERSION;
const IMAGES_CACHE = 'images-' + CACHE_VERSION;
const IMAGES_CACHE_LIMIT = 200;

const PRECACHE_URLS = [
  '/',
  '/offline/',
  '/core-rules/',
  '/cards/',
  '/api/cards/all/',
  '{% static "css/style.css" %}',
  '{% static "css/bootstrap.min.css" %}',
  '{% static "logo.png" %}',
  '{% static "favicon.png" %}',
  '{% static "icons/icon-192x192.png" %}',
];

const CDN_HOSTS = [
  'cdn.jsdelivr.net',
  'www.googletagmanager.com',
];

// IndexedDB for offline annotation sync
const DB_NAME = 'scoutscode-offline';
const DB_VERSION = 1;
const SYNC_STORE = 'pending-requests';

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      e.target.result.createObjectStore(SYNC_STORE, { autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function addToSyncQueue(data) {
  return openDB().then(db => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(SYNC_STORE, 'readwrite');
      tx.objectStore(SYNC_STORE).add(data);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  });
}

function getAllPending() {
  return openDB().then(db => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(SYNC_STORE, 'readonly');
      const req = tx.objectStore(SYNC_STORE).getAll();
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  });
}

function clearSyncQueue() {
  return openDB().then(db => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(SYNC_STORE, 'readwrite');
      tx.objectStore(SYNC_STORE).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  });
}

// Install: precache app shell
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => {
          return (key.startsWith('static-') || key.startsWith('pages-') || key.startsWith('images-'))
            && key !== STATIC_CACHE && key !== PAGES_CACHE && key !== IMAGES_CACHE;
        }).map(key => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch handler
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET/non-POST
  if (request.method !== 'GET' && request.method !== 'POST') return;

  // POST requests: network only with offline queue for annotations
  if (request.method === 'POST') {
    if (url.pathname === '/api/save-annotation/') {
      event.respondWith(
        fetch(request.clone()).catch(() => {
          // Queue for later sync
          return request.clone().text().then(body => {
            return addToSyncQueue({
              url: request.url,
              body: body,
              headers: { 'Content-Type': request.headers.get('Content-Type') },
              timestamp: Date.now(),
            });
          }).then(() => {
            return new Response(JSON.stringify({ success: true, queued: true }), {
              headers: { 'Content-Type': 'application/json' },
            });
          });
        })
      );
    }
    return;
  }

  // Static assets: cache first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // CDN resources: cache first
  if (CDN_HOSTS.some(host => url.host === host)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Card images (external): cache as browsed
  if (request.destination === 'image' && url.origin !== self.location.origin) {
    event.respondWith(cacheFirstWithLimit(request, IMAGES_CACHE, IMAGES_CACHE_LIMIT));
    return;
  }

  // Rule section detail pages: network first, offline redirect to /core-rules/#anchor
  if (/^\/(cr|tr)sections\//.test(url.pathname)) {
    event.respondWith(networkFirstWithRuleFallback(request, url.pathname));
    return;
  }

  // Card detail pages: network first, offline renders from cached card data
  if (/^\/cards\/[^/]+\/$/.test(url.pathname) && url.pathname !== '/cards/') {
    event.respondWith(networkFirstWithCardFallback(request, url.pathname));
    return;
  }

  // HTML pages: network first with cache fallback
  if (request.headers.get('Accept') && request.headers.get('Accept').includes('text/html')) {
    event.respondWith(networkFirst(request, PAGES_CACHE));
    return;
  }

  // API JSON: network first
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, PAGES_CACHE));
    return;
  }

  // Default: network first
  event.respondWith(networkFirst(request, PAGES_CACHE));
});

// Cache first strategy
function cacheFirst(request, cacheName) {
  return caches.match(request).then(cached => {
    if (cached) return cached;
    return fetch(request).then(response => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(cacheName).then(cache => cache.put(request, clone));
      }
      return response;
    });
  });
}

// Cache first with size limit (for images)
function cacheFirstWithLimit(request, cacheName, limit) {
  return caches.match(request).then(cached => {
    if (cached) return cached;
    return fetch(request).then(response => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(cacheName).then(cache => {
          cache.put(request, clone);
          // Evict oldest if over limit
          cache.keys().then(keys => {
            if (keys.length > limit) {
              cache.delete(keys[0]);
            }
          });
        });
      }
      return response;
    });
  });
}

// Network first with cache fallback and offline page
function networkFirst(request, cacheName) {
  return fetch(request).then(response => {
    if (response.ok) {
      const clone = response.clone();
      caches.open(cacheName).then(cache => cache.put(request, clone));
    }
    return response;
  }).catch(() => {
    return caches.match(request).then(cached => {
      if (cached) return cached;
      // If HTML request, show offline page
      if (request.headers.get('Accept') && request.headers.get('Accept').includes('text/html')) {
        return caches.match('/offline/');
      }
      return new Response('Offline', { status: 503 });
    });
  });
}

// Replay queued requests when back online
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'REPLAY_QUEUE') {
    event.waitUntil(replayQueue());
  }
});

function replayQueue() {
  return getAllPending().then(items => {
    if (!items.length) return;
    return Promise.all(items.map(item => {
      return fetch(item.url, {
        method: 'POST',
        headers: item.headers,
        body: item.body,
        credentials: 'same-origin',
      }).catch(() => {}); // silently fail individual replays
    })).then(() => clearSyncQueue());
  });
}

// Network first for rule sections, fallback to /core-rules/#rule-{section}
function networkFirstWithRuleFallback(request, pathname) {
  return fetch(request).then(response => {
    if (response.ok) {
      const clone = response.clone();
      caches.open(PAGES_CACHE).then(cache => cache.put(request, clone));
    }
    return response;
  }).catch(() => {
    return caches.match(request).then(cached => {
      if (cached) return cached;
      // Extract section number from /crsections/448.1/ or /trsections/100/
      const match = pathname.match(/\/(?:cr|tr)sections\/([^/]+)\//);
      if (match) {
        const section = match[1];
        const anchor = 'rule-' + section;
        return Response.redirect('/core-rules/#' + anchor, 302);
      }
      return caches.match('/offline/');
    });
  });
}

// Network first for card detail, fallback to client-rendered page from cached data
function networkFirstWithCardFallback(request, pathname) {
  return fetch(request).then(response => {
    if (response.ok) {
      const clone = response.clone();
      caches.open(PAGES_CACHE).then(cache => cache.put(request, clone));
    }
    return response;
  }).catch(() => {
    return caches.match(request).then(cached => {
      if (cached) return cached;
      // Extract card_id from /cards/{card_id}/
      const match = pathname.match(/\/cards\/([^/]+)\//);
      if (!match) return caches.match('/offline/');
      const cardId = match[1];
      // Build an offline card detail page
      const html = buildOfflineCardPage(cardId);
      return new Response(html, {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    });
  });
}

function buildOfflineCardPage(cardId) {
  return `<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Card Detail (Offline) - ScoutsCode</title>
  <link rel="stylesheet" href="/static/css/bootstrap.min.css">
  <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
  <div class="container mt-4" id="card-container">
    <p class="text-muted">Loading card data offline...</p>
  </div>
  <script>
    (function() {
      var cardId = ${JSON.stringify(cardId)};
      var container = document.getElementById("card-container");

      function renderCard(cards) {
        if (!cards) {
          container.innerHTML = '<div class="alert alert-warning">Card data not available offline.</div>';
          return;
        }
      var card = cards.find(function(c) { return c.card_id === cardId; });
      if (!card) {
        container.innerHTML = '<div class="alert alert-warning">Card not found in offline data.</div>';
        return;
      }
      var domains = card.domains ? card.domains.join(", ") : "";
      var errata = "";
      if (card.errata_text) {
        errata = '<div class="alert alert-info mt-3"><strong>Errata:</strong> ' + card.errata_text + '</div>';
      }
      container.innerHTML = '<nav aria-label="breadcrumb"><ol class="breadcrumb">'
        + '<li class="breadcrumb-item"><a href="/">Home</a></li>'
        + '<li class="breadcrumb-item"><a href="/cards/">Cards</a></li>'
        + '<li class="breadcrumb-item active">' + card.name + '</li></ol></nav>'
        + '<div class="row"><div class="col-md-4">'
        + '<img src="' + card.image_url + '" alt="' + card.name + '" class="img-fluid rounded" />'
        + '</div><div class="col-md-8"><h1>' + card.name + '</h1>'
        + '<table class="table"><tbody>'
        + '<tr><th>Type</th><td>' + (card.card_type || "") + '</td></tr>'
        + '<tr><th>Set</th><td>' + (card.card_set || "") + '</td></tr>'
        + '<tr><th>Rarity</th><td>' + (card.rarity || "") + '</td></tr>'
        + '<tr><th>Domain</th><td>' + domains + '</td></tr>'
        + '<tr><th>Energy</th><td>' + (card.energy !== null ? card.energy : "-") + '</td></tr>'
        + '<tr><th>Power</th><td>' + (card.power !== null ? card.power : "-") + '</td></tr>'
        + '<tr><th>Collector #</th><td>' + (card.collector_number || "") + '</td></tr>'
        + '</tbody></table>'
        + (card.ability ? '<h5>Ability</h5><p>' + card.ability + '</p>' : '')
        + errata
        + '<p class="text-muted mt-3"><em>Viewing offline cached data</em></p>'
        + '</div></div>'
        + '<div class="mt-4"><a href="/cards/" class="btn btn-secondary">Back to Cards</a></div>';
      }

      // Try localStorage first, then fall back to cached API response
      var raw = localStorage.getItem("cardData");
      if (raw) {
        renderCard(JSON.parse(raw));
      } else {
        fetch("/api/cards/all/").then(function(r) { return r.json(); })
          .then(renderCard)
          .catch(function() { renderCard(null); });
      }
    })();
  </script>
</body>
</html>`;
}
