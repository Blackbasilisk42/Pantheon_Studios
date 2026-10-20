(function () {
    if (!document.querySelector(".webmaster-widget")) {
        const widget = document.createElement("aside");
        widget.className = "webmaster-widget";
        widget.setAttribute("aria-label", "Webmaster assistant");
        widget.innerHTML = `
            <details open>
                <summary>LOCAL WEBMASTER</summary>
                <div class="webmaster-panel">
                    <h2>Execution Console</h2>
                    <p>Send a request to the local Webmaster engine.</p>
                    <div class="webmaster-suggestions" aria-label="Example requests">
                        <button type="button" data-webmaster-command="Update Kaige's dossier">DOSSIER</button>
                        <button type="button" data-webmaster-command="Run news update">NEWS UPDATE</button>
                        <button type="button" data-webmaster-command="Check for broken elements">SITE CHECK</button>
                    </div>
                    <form id="webmaster-form">
                        <label for="webmaster-command">Execution request</label>
                        <input id="webmaster-command" name="command" type="text" maxlength="1000" required autocomplete="off">
                        <button class="webmaster-submit" type="submit">RUN REQUEST</button>
                    </form>
                    <p id="webmaster-status" role="status" aria-live="polite">Ready to send a local request.</p>
                    <pre id="webmaster-result" aria-live="polite" hidden></pre>
                </div>
            </details>
        `;
        document.body.append(widget);
    }

    const form = document.getElementById("webmaster-form");
    const commandInput = document.getElementById("webmaster-command");
    const status = document.getElementById("webmaster-status");
    const result = document.getElementById("webmaster-result");
    const submit = form && form.querySelector("button[type='submit']");

    if (!form || !commandInput || !status || !result || !submit) {
        return;
    }

    const panel = document.querySelector(".webmaster-widget details");
    if (panel && window.matchMedia("(max-width: 700px)").matches) {
        panel.open = false;
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
            const response = await fetch("http://127.0.0.1:5000/api/execute", {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ command: command })
            });
            const contentType = response.headers.get("content-type") || "";
            if (!contentType.toLowerCase().includes("json")) {
                throw new Error(
                    "The server returned HTML instead of a JSON API response. " +
                    "Run " +
                    ".\\.venv\\Scripts\\python.exe server.py, then open " +
                    "http://127.0.0.1:5000/command-center.html."
                );
            }
            const payload = await response.json();
            if (!payload || typeof payload !== "object") {
                throw new Error("The Webmaster returned an invalid response.");
            }
            if (!response.ok) {
                throw new Error(
                    typeof payload.message === "string"
                        ? payload.message
                        : typeof payload.error === "string"
                            ? payload.error
                        : "The Webmaster returned HTTP " + response.status
                );
            }

            status.textContent = "Completed: " + payload.action;
            result.textContent = typeof payload.message === "string"
                ? payload.message
                : JSON.stringify(payload.result, null, 2);
            if (
                payload.navigation &&
                payload.navigation.type === "navigate" &&
                typeof payload.navigation.target === "string"
            ) {
                const navigationLink = document.createElement("a");
                navigationLink.href = payload.navigation.target;
                navigationLink.textContent = "Open " + payload.navigation.target;
                result.append(document.createTextNode("\n"), navigationLink);
            }
            result.hidden = false;
        } catch (error) {
            status.textContent = error instanceof TypeError
                ? "Unable to reach the local engine. Start server.py."
                : error instanceof Error
                    ? error.message
                    : String(error);
            console.error("Webmaster request failed.", error);
        } finally {
            submit.disabled = false;
        }
    });
}());
