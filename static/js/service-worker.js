self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    const target = new URL(data.url || '/', self.location.origin);
    const url = target.origin === self.location.origin ? target.href : self.location.origin;
    event.waitUntil(self.registration.showNotification(data.title || 'Mimoza Floral', {
        body: data.body || '',
        icon: '/static/images/mimoza-logo-wide.png',
        badge: '/static/images/mimoza-logo-wide.png',
        data: { url },
    }));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const target = new URL(event.notification.data.url, self.location.origin);
    const url = target.origin === self.location.origin ? target.href : self.location.origin;
    event.waitUntil(self.clients.openWindow(url));
});
