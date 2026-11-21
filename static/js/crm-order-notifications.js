(() => {
    const badge = document.getElementById('crm-order-count');
    if (!badge) return;

    const updateOrderCount = async () => {
        const response = await fetch(badge.dataset.countUrl, {
            credentials: 'same-origin',
            cache: 'no-store',
        });
        if (!response.ok) {
            throw new Error(`Buyurtma bildirishnomalarini olishda xatolik: ${response.status}`);
        }

        const data = await response.json();
        const count = Number(data.count);
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.hidden = count < 1;
    };

    updateOrderCount();
    window.setInterval(() => {
        if (document.visibilityState === 'visible') updateOrderCount();
    }, 15000);
})();
