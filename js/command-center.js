(function () {
    const metricCards = Array.from(document.querySelectorAll(".metric-card[data-platform]"));

    const metricFields = {
        youtube: { field: "youtube_subscribers", label: "Subscribers" },
        discord: { field: "discord_online", label: "Members online" },
        meta: { field: "meta_followers", label: "Followers" }
    };

    const metricProviders = {
        youtube: metricFields.youtube,
        discord: metricFields.discord,
        meta: metricFields.meta,
        patreon: { field: "patreon_supporters", label: "Supporters" }
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
        let metrics;
        try {
            const response = await fetch("/api/metrics", {
                headers: { Accept: "application/json" }
            });
            if (!response.ok) {
                throw new Error("Metrics service returned HTTP " + response.status);
            }
            metrics = await response.json();
        } catch (error) {
            metricCards.forEach(function (card) {
                const stateElement = card.querySelector(".connection-state");
                if (stateElement) {
                    stateElement.textContent = "DATA UNAVAILABLE";
                }
            });
            console.error("Unable to load command center metrics.", error);
            return;
        }

        await Promise.all(metricCards.map(async function (card) {
            const platform = card.dataset.platform;
            const provider = metricProviders[platform];

            if (!provider) {
                console.error("No metric provider is registered for platform:", platform);
                return;
            }

            try {
                const value = metrics[provider.field];
                const metric = Number.isSafeInteger(value) && value >= 0
                    ? { value: value, label: provider.label }
                    : null;
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
