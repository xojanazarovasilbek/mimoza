(() => {
    const panel = document.getElementById('push-notification-panel');
    if (!panel) return;

    const enableButton = panel.querySelector('[data-push-enable]');
    const disableButton = panel.querySelector('[data-push-disable]');
    const status = panel.querySelector('[data-push-status]');
    const csrfToken = panel.querySelector('[name="csrfmiddlewaretoken"]').value;

    const setStatus = (message) => {
        status.textContent = message;
    };

    const setSubscribed = (subscribed) => {
        enableButton.hidden = subscribed;
        disableButton.hidden = !subscribed;
    };

    const sendSubscription = async (url, data) => {
        const response = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify(data),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'So‘rov bajarilmadi.');
        return result;
    };

    const applicationServerKey = (key) => {
        const base64 = key.replace(/-/g, '+').replace(/_/g, '/');
        const padded = base64 + '='.repeat((4 - base64.length % 4) % 4);
        const binary = window.atob(padded);
        return Uint8Array.from(binary, (character) => character.charCodeAt(0));
    };

    const main = async () => {
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            enableButton.disabled = true;
            setStatus('Bu brauzer push bildirishnomalarini qo‘llab-quvvatlamaydi.');
            return;
        }

        const registration = await navigator.serviceWorker.register(panel.dataset.workerUrl);
        const readyRegistration = await navigator.serviceWorker.ready;
        const currentSubscription = await readyRegistration.pushManager.getSubscription();
        setSubscribed(Boolean(currentSubscription));

        enableButton.addEventListener('click', async () => {
            try {
                const permission = await window.Notification.requestPermission();
                if (permission !== 'granted') {
                    setStatus('Bildirishnoma ruxsati berilmadi.');
                    return;
                }
                const subscription = currentSubscription || await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: applicationServerKey(panel.dataset.vapidPublicKey),
                });
                await sendSubscription(panel.dataset.subscribeUrl, { subscription: subscription.toJSON() });
                setSubscribed(true);
                setStatus('Push bildirishnomalari yoqildi.');
            } catch (error) {
                setStatus(error.message);
            }
        });

        disableButton.addEventListener('click', async () => {
            try {
                const subscription = await readyRegistration.pushManager.getSubscription();
                if (subscription) {
                    await sendSubscription(panel.dataset.unsubscribeUrl, { endpoint: subscription.endpoint });
                    await subscription.unsubscribe();
                }
                setSubscribed(false);
                setStatus('Push bildirishnomalari o‘chirildi.');
            } catch (error) {
                setStatus(error.message);
            }
        });
    };

    if (!panel.dataset.vapidPublicKey) {
        enableButton.disabled = true;
        setStatus('Push kalitlari serverda sozlanmagan.');
        return;
    }

    main().catch((error) => {
        enableButton.disabled = true;
        setStatus(error.message);
    });
})();
