'use strict';
const CACHE='alpicturia-public-v1';
const PUBLIC=['/static/app.css','/static/fonts.css','/static/app.js','/static/icon.svg','/static/icon-192.png','/static/icon-512.png','/static/offline.html'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(PUBLIC))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('alpicturia-public-')&&key!==CACHE).map(key=>caches.delete(key))))));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==self.location.origin)return;
 // Never cache authentication, selfies, photographs, galleries or API responses.
 if(PUBLIC.includes(url.pathname)){
  event.respondWith(fetch(event.request).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy))}return response}).catch(()=>caches.match(event.request)));
 }else if(event.request.mode==='navigate'){
  event.respondWith(fetch(event.request).catch(()=>caches.match('/static/offline.html')));
 }
});
