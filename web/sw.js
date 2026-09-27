// El service worker de Zeno. Existe por UNA razon: sin el, el navegador no puede recibir avisos
// con la aplicacion cerrada.
//
// NO CACHEA NADA, y es deliberado. Un service worker que guarda copias es la forma mas comun de que
// una aplicacion web sirva la version de ayer despues de desplegar, y eso ya ha pasado en esta casa
// con el icono de una PWA instalada. Aqui todo va a la red siempre: Zeno es una fachada sobre dos
// APIs, no tiene nada que valga la pena guardar sin conexion, y sin conexion no podria contestar
// igualmente.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let d = { titulo: "Zeno", cuerpo: "", url: "/" };
  try { d = { ...d, ...(e.data ? e.data.json() : {}) }; } catch (_) {}
  e.waitUntil(self.registration.showNotification(d.titulo, {
    body: d.cuerpo,
    icon: "/img/icon-192.png",
    badge: "/img/favicon-64.png",
    // Una etiqueta fija hace que un aviso nuevo SUSTITUYA al anterior en la pantalla bloqueada, en
    // vez de apilarse. Tres avisos apilados se descartan todos de un gesto, incluido el que importa.
    tag: "zeno",
    renotify: true,
    data: { url: d.url || "/" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const destino = (e.notification.data && e.notification.data.url) || "/";
  // Si Zeno ya esta abierto en alguna ventana, se enfoca esa en vez de abrir otra: acabar con
  // cuatro pestañas de Zeno abiertas es la forma rapida de dejar de pulsar los avisos.
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((vs) => {
    for (const v of vs) {
      if (v.url.includes(self.location.origin) && "focus" in v) return v.focus();
    }
    return self.clients.openWindow(destino);
  }));
});
