/**
 * Battery indicator - polls /api/system/battery and updates UI.
 */
(function () {
    const POLL_INTERVAL = 15000;
    const FETCH_TIMEOUT = 5000;
    const FILL_MAX_WIDTH = 18;
    const STATE_CLASSES = ['battery-normal', 'battery-medium', 'battery-low', 'battery-critical', 'battery-charging'];

    let pollTimer = null;
    let failCount = 0;

    function getElements() {
        return {
            indicator: document.getElementById('battery-indicator'),
            fill: document.getElementById('battery-fill'),
            charging: document.getElementById('battery-charging'),
            pct: document.getElementById('battery-pct'),
            warn: document.getElementById('battery-warn'),
        };
    }

    function updateUI(data) {
        const el = getElements();
        if (!el.indicator) return;

        failCount = 0;
        const soc = Math.round(data.soc);

        // Percentage text
        el.pct.textContent = soc + '%';

        // Fill bar width
        const fillWidth = Math.round((data.soc / 100) * FILL_MAX_WIDTH);
        el.fill.setAttribute('width', Math.max(0, Math.min(FILL_MAX_WIDTH, fillWidth)));

        // Remove all state classes
        STATE_CLASSES.forEach(function (cls) {
            el.indicator.classList.remove(cls);
        });

        // Determine state
        if (data.charging) {
            el.indicator.classList.add('battery-charging');
        } else if (soc > 50) {
            el.indicator.classList.add('battery-normal');
        } else if (soc > 20) {
            el.indicator.classList.add('battery-medium');
        } else if (soc > 10) {
            el.indicator.classList.add('battery-low');
        } else {
            el.indicator.classList.add('battery-critical');
        }

        // Charging icon
        if (data.charging) {
            el.charging.classList.remove('hidden');
        } else {
            el.charging.classList.add('hidden');
        }

        // Warning icon
        if (!data.charging && soc <= 20) {
            el.warn.classList.remove('hidden');
        } else {
            el.warn.classList.add('hidden');
        }

        // Show indicator
        el.indicator.classList.remove('hidden');
    }

    function handleError() {
        failCount++;
        if (failCount >= 3) {
            var el = getElements();
            if (el.pct) el.pct.textContent = '?';
        }
    }

    function fetchBattery() {
        var controller = new AbortController();
        var timeout = setTimeout(function () { controller.abort(); }, FETCH_TIMEOUT);

        fetch('/api/system/battery', { signal: controller.signal })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                clearTimeout(timeout);
                if (data.available) {
                    updateUI(data);
                } else {
                    disableBattery();
                }
            })
            .catch(function () {
                clearTimeout(timeout);
                handleError();
            });
    }

    function disableBattery() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
        document.body.classList.add('no-battery');
        var el = getElements();
        if (el.indicator) el.indicator.classList.add('hidden');
    }

    function init() {
        var controller = new AbortController();
        var timeout = setTimeout(function () { controller.abort(); }, FETCH_TIMEOUT);

        fetch('/api/system/battery', { signal: controller.signal })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                clearTimeout(timeout);
                if (data.available) {
                    updateUI(data);
                    pollTimer = setInterval(fetchBattery, POLL_INTERVAL);
                } else {
                    disableBattery();
                }
            })
            .catch(function () {
                clearTimeout(timeout);
                disableBattery();
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.stopBatteryPolling = function () {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    };
})();
