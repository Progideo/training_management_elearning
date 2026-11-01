/* Portal side: never interprets package markup or executes package JavaScript. */
(() => {
    const cfg = JSON.parse(document.getElementById('config').textContent);
    const frame = document.getElementById('content');
    const status = document.getElementById('status');
    window.addEventListener('message', event => {
        if (event.origin !== cfg.origin || event.source !== frame.contentWindow) return;
        const message = event.data;
        if (!message || typeof message !== 'object' || message.nonce !== cfg.nonce) return;
        if (message.type === 'ready') status.textContent = 'Contenu chargé dans son espace isolé.';
    });
})();
