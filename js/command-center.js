(function () {
    const metricCards = Array.from(document.querySelectorAll(".metric-card[data-platform]"));

    const metricProviders = {
        youtube: async function () { return null; },
        discord: async function () { return null; },
        meta: async function () { return null; },
        patreon: async function () { return null; }
    };

    function renderMetric(card, metric) {
        const valueElement = card.querySelector("[data-metric-value]");
        const labelElement = card.querySelector("[data-metric-label]");
        const stateElement = card.querySelector(".connection-state");

        if (!valueElement || !labelElement || !stateElement) {
            console.error("Command center metric card is missing required display elements.", card);
            return;
        }

        if (!metric) {
            stateElement.textContent = "NOT CONNECTED";
            return;
        }

        valueElement.textContent = String(metric.value);
        labelElement.textContent = metric.label;
        stateElement.textContent = "LIVE DATA";
    }

    async function initializeMetrics() {
        await Promise.all(metricCards.map(async function (card) {
            const platform = card.dataset.platform;
            const provider = metricProviders[platform];

            if (!provider) {
                console.error("No metric provider is registered for platform:", platform);
                return;
            }

            try {
                const metric = await provider();
                renderMetric(card, metric);
            } catch (error) {
                const stateElement = card.querySelector(".connection-state");
                if (stateElement) {
                    stateElement.textContent = "DATA UNAVAILABLE";
                }
                console.error("Unable to load command center metric for " + platform + ".", error);
            }
        }));
    }

    initializeMetrics();
}());
