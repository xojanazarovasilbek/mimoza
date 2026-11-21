(() => {
    const deliveryChoice = document.getElementById('delivery-required');
    const deliveryHelp = document.getElementById('delivery-help');
    if (!deliveryChoice || !deliveryHelp) return;

    const updateDeliveryHelp = () => {
        deliveryHelp.hidden = deliveryChoice.value !== 'yes';
    };

    deliveryChoice.addEventListener('change', updateDeliveryHelp);
    updateDeliveryHelp();
})();
