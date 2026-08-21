(function () {
  const timeEl = document.getElementById("systemTime");
  const filterButtons = Array.from(document.querySelectorAll(".filter-btn"));
  const cards = Array.from(document.querySelectorAll(".dossier-card"));
  const modal = document.getElementById("dossierModal");
  const modalTitle = document.getElementById("modalTitle");
  const modalBody = document.getElementById("modalBody");
  const closeModalBtn = document.getElementById("closeModal");
  const inspectButtons = Array.from(document.querySelectorAll(".inspect-btn"));
  const terminalFeed = document.getElementById("terminalFeed");
  const terminalForm = document.getElementById("terminalForm");
  const terminalInput = document.getElementById("terminalInput");
  const themeToggle = document.getElementById("themeToggle");
  const audioToggle = document.getElementById("audioToggle");
  const canvas = document.getElementById("hud-bg-canvas");
  const hudCursor = document.getElementById("hudCursor");
  const THEME_KEY = "pantheon_hud_theme";
  const AUDIO_KEY = "pantheon_hud_audio";

  const dossierDetails = {
    GHOSTWIRE: "Strategic command anchor. Oversees campaign doctrine, narrative vectors, and release cadence.",
    NOVAFRAME: "Visual systems operator. Maintains lookdev, preview architecture, and wireframe render telemetry.",
    RAZORBYTE: "Field operations specialist. Handles recon sweeps, security probes, and rapid response protocols.",
    SYNTHLACE: "Signal and audio intelligence. Crafts waveform signatures and encrypted atmospheric story pulses."
  };

  const commandMap = {
    help: [
      "Available commands: help, clear, status, roster, ping",
      "Try: status"
    ],
    status: [
      "Node health: stable",
      "Vault integrity: 100%",
      "Encrypted channel: synchronized"
    ],
    roster: [
      "Roster online: GHOSTWIRE, NOVAFRAME, RAZORBYTE, SYNTHLACE"
    ],
    ping: [
      "Pinging pantheon-net...",
      "Reply from node-08: time=12ms secure=true"
    ],
    theme: [
      "Theme protocol detected.",
      "Use theme spectral or theme obsidian"
    ]
  };

  const autoFeedLines = [
    "SIGINT: crowd telemetry normalized across gate-12.",
    "BROADCAST: dossier relay encrypted with rotating keys.",
    "OPS: orbital uplink calibration complete.",
    "CREATIVE_NODE: waveform fingerprints pushed to archive.",
    "SECURITY: no anomaly escalation required."
  ];

  let audioEnabled = false;
  let audioContext = null;

  function ensureAudioContext() {
    if (!audioContext) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) {
        return null;
      }
      audioContext = new Ctx();
    }
    if (audioContext.state === "suspended") {
      audioContext.resume();
    }
    return audioContext;
  }

  function playTone(config) {
    if (!audioEnabled) {
      return;
    }
    const ctx = ensureAudioContext();
    if (!ctx) {
      return;
    }

    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    oscillator.type = config.type || "triangle";
    oscillator.frequency.setValueAtTime(config.from, ctx.currentTime);
    oscillator.frequency.exponentialRampToValueAtTime(config.to || config.from, ctx.currentTime + config.duration);

    gainNode.gain.setValueAtTime(0.0001, ctx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(config.volume || 0.03, ctx.currentTime + 0.01);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + config.duration);

    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);

    oscillator.start(ctx.currentTime);
    oscillator.stop(ctx.currentTime + config.duration + 0.01);
  }

  function setAudio(enabled) {
    audioEnabled = !!enabled;
    if (audioToggle) {
      audioToggle.textContent = audioEnabled ? "[AUDIO: ON]" : "[AUDIO: OFF]";
      audioToggle.setAttribute("data-enabled", audioEnabled ? "true" : "false");
    }
    localStorage.setItem(AUDIO_KEY, audioEnabled ? "on" : "off");
  }

  function pad(value, width) {
    return String(value).padStart(width, "0");
  }

  function updateClock() {
    const now = new Date();
    const stamp =
      now.getUTCFullYear() + "-" +
      pad(now.getUTCMonth() + 1, 2) + "-" +
      pad(now.getUTCDate(), 2) + " " +
      pad(now.getUTCHours(), 2) + ":" +
      pad(now.getUTCMinutes(), 2) + ":" +
      pad(now.getUTCSeconds(), 2) + ":" +
      pad(now.getUTCMilliseconds(), 3) + " UTC";
    timeEl.textContent = stamp;
  }

  function setFilter(filterValue) {
    filterButtons.forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.filter === filterValue);
    });

    cards.forEach(function (card) {
      const tags = (card.dataset.category || "").split(" ");
      const matches = filterValue === "all" || tags.includes(filterValue);
      card.classList.toggle("hidden", !matches);
    });
  }

  function appendLine(text, kind) {
    const line = document.createElement("p");
    if (kind === "system") {
      line.innerHTML = '<span class="prompt">SYS:</span> ' + text;
    } else if (kind === "error") {
      line.innerHTML = '<span class="prompt">ERR:</span> ' + text;
      line.style.color = "#ff6a8f";
    } else {
      line.innerHTML = text;
    }
    terminalFeed.appendChild(line);
    terminalFeed.scrollTop = terminalFeed.scrollHeight;
  }

  function applyTheme(themeName) {
    const finalTheme = themeName === "obsidian" ? "obsidian" : "spectral";
    if (finalTheme === "obsidian") {
      document.body.setAttribute("data-theme", "obsidian");
    } else {
      document.body.removeAttribute("data-theme");
    }
    if (themeToggle) {
      themeToggle.textContent = finalTheme === "obsidian" ? "[THEME: OBSIDIAN]" : "[THEME: SPECTRAL]";
    }
    localStorage.setItem(THEME_KEY, finalTheme);
  }

  function toggleTheme() {
    const current = document.body.getAttribute("data-theme") === "obsidian" ? "obsidian" : "spectral";
    applyTheme(current === "obsidian" ? "spectral" : "obsidian");
  }

  function executeCommand(rawValue) {
    const value = rawValue.trim().toLowerCase();
    appendLine('<span class="prompt">GUEST@PANTHEON_NET:~$</span> ' + rawValue, "input");

    if (!value) {
      appendLine("No command entered.", "error");
      return;
    }

    if (value === "clear") {
      terminalFeed.innerHTML = "";
      appendLine("Terminal buffer cleared.", "system");
      playTone({ from: 220, to: 180, duration: 0.1, volume: 0.04, type: "sawtooth" });
      return;
    }

    if (value.startsWith("theme ")) {
      const mode = value.replace("theme ", "").trim();
      if (mode === "spectral" || mode === "obsidian") {
        applyTheme(mode);
        appendLine("Theme switched to " + mode + ".", "system");
        playTone({ from: 880, to: 1240, duration: 0.08, volume: 0.035 });
      } else {
        appendLine("Unknown theme mode. Use spectral or obsidian.", "error");
        playTone({ from: 180, to: 120, duration: 0.12, volume: 0.035, type: "square" });
      }
      return;
    }

    const responses = commandMap[value];
    if (!responses) {
      appendLine('Command not recognized: "' + value + '". Use help.', "error");
      playTone({ from: 160, to: 120, duration: 0.13, volume: 0.03, type: "square" });
      return;
    }

    responses.forEach(function (responseLine) {
      appendLine(responseLine, "system");
    });
    playTone({ from: 520, to: 760, duration: 0.08, volume: 0.03 });
  }

  filterButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      setFilter(button.dataset.filter || "all");
    });
  });

  inspectButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      const member = button.dataset.member || "UNKNOWN";
      modalTitle.textContent = "DOSSIER_DETAIL // " + member;
      modalBody.textContent = dossierDetails[member] || "No dossier data found for selected unit.";
      if (typeof modal.showModal === "function") {
        modal.showModal();
      }
      playTone({ from: 700, to: 980, duration: 0.07, volume: 0.035 });
    });
  });

  closeModalBtn.addEventListener("click", function () {
    modal.close();
    playTone({ from: 420, to: 260, duration: 0.08, volume: 0.025 });
  });

  modal.addEventListener("click", function (event) {
    const rect = modal.getBoundingClientRect();
    const outside =
      event.clientX < rect.left ||
      event.clientX > rect.right ||
      event.clientY < rect.top ||
      event.clientY > rect.bottom;
    if (outside) {
      modal.close();
    }
  });

  terminalForm.addEventListener("submit", function (event) {
    event.preventDefault();
    executeCommand(terminalInput.value);
    terminalInput.value = "";
  });

  terminalInput.addEventListener("keydown", function (event) {
    if (event.key.length === 1 || event.key === "Backspace") {
      playTone({ from: 340, to: 410, duration: 0.035, volume: 0.012, type: "square" });
    }
  });

  if (audioToggle) {
    audioToggle.addEventListener("click", function () {
      setAudio(!audioEnabled);
      playTone({ from: 640, to: 920, duration: 0.07, volume: 0.03 });
    });
  }

  const hoverTargets = Array.from(document.querySelectorAll("button, .dossier-card, .media-card, .hud-panel"));
  hoverTargets.forEach(function (target) {
    target.addEventListener("mouseenter", function () {
      if (hudCursor) {
        hudCursor.classList.add("locked");
      }
      playTone({ from: 520, to: 670, duration: 0.045, volume: 0.015 });
    });
    target.addEventListener("mouseleave", function () {
      if (hudCursor) {
        hudCursor.classList.remove("locked");
      }
    });
    target.addEventListener("click", function () {
      playTone({ from: 420, to: 760, duration: 0.05, volume: 0.025, type: "triangle" });
    });
  });

  if (hudCursor) {
    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let currentX = targetX;
    let currentY = targetY;

    window.addEventListener("mousemove", function (event) {
      targetX = event.clientX;
      targetY = event.clientY;
    });

    function renderCursor() {
      currentX += (targetX - currentX) * 0.23;
      currentY += (targetY - currentY) * 0.23;
      hudCursor.style.left = currentX + "px";
      hudCursor.style.top = currentY + "px";
      requestAnimationFrame(renderCursor);
    }

    renderCursor();
  }

  function initBackgroundCanvas() {
    if (!canvas) {
      return;
    }

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) {
      return;
    }

    let width = 0;
    let height = 0;
    let sweepAngle = 0;
    const nodes = [];
    const nodeCount = 42;

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = width + "px";
      canvas.style.height = height + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      nodes.length = 0;
      for (let i = 0; i < nodeCount; i += 1) {
        nodes.push({
          x: Math.random() * width,
          y: Math.random() * height,
          r: 0.7 + Math.random() * 1.6,
          phase: Math.random() * Math.PI * 2,
          speed: 0.0004 + Math.random() * 0.001
        });
      }
    }

    function drawFrame(ts) {
      ctx.clearRect(0, 0, width, height);

      ctx.strokeStyle = "rgba(0, 229, 255, 0.07)";
      ctx.lineWidth = 1;
      const gap = 70;
      for (let x = 0; x < width; x += gap) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gap) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      for (let i = 0; i < nodes.length; i += 1) {
        const node = nodes[i];
        const alpha = 0.22 + Math.sin(ts * node.speed + node.phase) * 0.16;
        ctx.fillStyle = "rgba(0,255,157," + Math.max(0.08, alpha).toFixed(3) + ")";
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
        ctx.fill();

        if (i % 5 === 0 && nodes[i + 1]) {
          ctx.strokeStyle = "rgba(0, 229, 255, 0.05)";
          ctx.beginPath();
          ctx.moveTo(node.x, node.y);
          ctx.lineTo(nodes[i + 1].x, nodes[i + 1].y);
          ctx.stroke();
        }
      }

      const cx = width * 0.8;
      const cy = height * 0.22;
      const radius = Math.min(width, height) * 0.22;
      sweepAngle += 0.01;

      ctx.strokeStyle = "rgba(0,255,157,0.12)";
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();

      const ex = cx + Math.cos(sweepAngle) * radius;
      const ey = cy + Math.sin(sweepAngle) * radius;
      const grad = ctx.createLinearGradient(cx, cy, ex, ey);
      grad.addColorStop(0, "rgba(0,255,157,0.02)");
      grad.addColorStop(1, "rgba(0,255,157,0.22)");
      ctx.strokeStyle = grad;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(ex, ey);
      ctx.stroke();

      requestAnimationFrame(drawFrame);
    }

    window.addEventListener("resize", resize);
    resize();
    requestAnimationFrame(drawFrame);
  }

  if (themeToggle) {
    themeToggle.addEventListener("click", toggleTheme);
  }

  const storedTheme = localStorage.getItem(THEME_KEY);
  applyTheme(storedTheme === "obsidian" ? "obsidian" : "spectral");
  setAudio(localStorage.getItem(AUDIO_KEY) === "on");

  document.querySelectorAll(".glitch-target").forEach(function (el) {
    el.setAttribute("data-glitch", el.textContent || "");
  });

  initBackgroundCanvas();

  let feedIndex = 0;
  setInterval(function () {
    appendLine(autoFeedLines[feedIndex % autoFeedLines.length], "system");
    feedIndex += 1;
  }, 6200);

  updateClock();
  setInterval(updateClock, 1);
  setFilter("all");

  /**
   * Attempt Super Admin Login
   * Verifies if username is 'blackbasilisk42' and password is 'PantheonMaster26'
   * If matched: sets localStorage 'userRole' to 'admin' and redirects to admin.html
   * @param {string} username - Admin username
   * @param {string} password - Admin password
   * @returns {boolean}
   */
  function attemptAdminLogin(username, password) {
    if (username === 'blackbasilisk42' && password === 'PantheonMaster26') {
      localStorage.setItem('userRole', 'admin');
      localStorage.setItem('pantheon_active_session', 'blackbasilisk42');
      localStorage.setItem('pantheon_director_authenticated', 'true');
      window.location.href = 'admin.html';
      return true;
    }
    return false;
  }

  /**
   * Check Admin Access
   * Runs on page load. If localStorage.getItem('userRole') === 'admin',
   * reveals the hidden Admin Dashboard navigation link.
   */
  function checkAdminAccess() {
    const userRole = localStorage.getItem('userRole');
    const adminLinks = document.querySelectorAll('.nav-admin-link, #nav-admin-dashboard');
    if (!adminLinks.length) return;

    let isAdmin = (userRole === 'admin');
    if (!isAdmin) {
      const activeCallsign = localStorage.getItem('pantheon_active_session');
      if (activeCallsign) {
        const accounts = JSON.parse(localStorage.getItem('pantheon_accounts') || '{}');
        const user = accounts[activeCallsign.toLowerCase()];
        if (user && (user.role === 'admin' || user.isAdmin)) {
          isAdmin = true;
        }
      }
      if (!isAdmin && localStorage.getItem('pantheon_director_authenticated') === 'true') {
        isAdmin = true;
      }
    }

    adminLinks.forEach(function (link) {
      link.style.display = isAdmin ? 'block' : 'none';
    });
  }

  /**
   * Admin Logout
   * Clears the userRole localStorage item and updates nav visibility.
   */
  function adminLogout() {
    localStorage.removeItem('userRole');
    localStorage.removeItem('pantheon_director_authenticated');
    checkAdminAccess();
    if (window.location.pathname.endsWith('admin.html')) {
      window.location.href = 'login.html';
    }
  }

  // Expose globally
  window.attemptAdminLogin = attemptAdminLogin;
  window.checkAdminAccess = checkAdminAccess;
  window.adminLogout = adminLogout;
  window.applyNavRBAC = checkAdminAccess;

  // Run on page load
  checkAdminAccess();
})();


