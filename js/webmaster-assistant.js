(function () {
    const form = document.getElementById("webmaster-form");
    const commandInput = document.getElementById("webmaster-command");
    const status = document.getElementById("webmaster-status");
    const result = document.getElementById("webmaster-result");
    const submit = form && form.querySelector("button[type='submit']");

    if (!form || !commandInput || !status || !result || !submit) {
        return;
    }

    document.querySelectorAll("[data-webmaster-command]").forEach(function (button) {
        button.addEventListener("click", function () {
            commandInput.value = button.dataset.webmasterCommand || "";
            commandInput.focus();
        });
    });

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        const command = commandInput.value.trim();
        if (!command) {
            return;
        }

        submit.disabled = true;
        status.textContent = "Sending request to the local engine...";
        result.hidden = true;
        result.textContent = "";

        try {
            const response = await fetch("/api/execute", {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ command: command })
            });
            const payload = await response.json();
            if (!response.ok) {
                throw new Error(
                    typeof payload.error === "string"
                        ? payload.error
                        : "The Webmaster returned HTTP " + response.status
                );
            }

            status.textContent = "Completed: " + payload.action;
            result.textContent = JSON.stringify(payload.result, null, 2);
            result.hidden = false;
        } catch (error) {
            status.textContent = error instanceof TypeError
                ? "Unable to reach the local engine. Start hub_server.py."
                : error.message;
            console.error("Webmaster request failed.", error);
        } finally {
            submit.disabled = false;
        }
    });
}());
