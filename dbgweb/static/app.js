const statusIndicator = document.getElementById("status-indicator");
const providerSelect = document.getElementById("provider-select");
const workspaceList = document.getElementById("workspace-list");
const terminalContainer = document.getElementById("debugger-terminal");
const chatHistory = document.getElementById("chat-history");
const chatForm = document.getElementById("chat-form");
const chatMessage = document.getElementById("chat-message");
const startSessionButton = document.getElementById("start-session");
const dividers = document.querySelectorAll(".divider");
const minPaneWidths = {
  "explorer-pane": 180,
  "chat-pane": 220,
};

let sessionId = null;
let debuggerSocket = null;
let chatSocket = null;
let currentPath = ".";
let selectedProgram = "";
let terminal = null;
let currentInput = "";
let terminalInitialized = false;
let fitAddon = null;
let fitRequestId = null;
let lastWasCarriageReturn = false;
let debuggerReplayBuffer = [];

const api = {
  async getStatus() {
    const resp = await fetch("/api/status");
    if (!resp.ok) {
      throw new Error(`status request failed: ${resp.status}`);
    }
    return resp.json();
  },
  async getProviders() {
    const resp = await fetch("/api/providers");
    if (!resp.ok) {
      throw new Error(`providers request failed: ${resp.status}`);
    }
    return resp.json();
  },
  async getWorkspace(path = ".") {
    const url = new URL("/api/workspace", window.location.origin);
    url.searchParams.set("path", path);
    const resp = await fetch(url.toString());
    if (!resp.ok) {
      throw new Error(`workspace request failed: ${resp.status}`);
    }
    return resp.json();
  },
  async createSession(payload) {
    const resp = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`session request failed: ${resp.status} ${text}`);
    }
    return resp.json();
  },
  async sendCommand(id, command) {
    const resp = await fetch(`/api/sessions/${id}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`command failed: ${resp.status} ${text}`);
    }
    return resp.json();
  },
  async sendChat(id, message) {
    const resp = await fetch(`/api/sessions/${id}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`chat failed: ${resp.status} ${text}`);
    }
    return resp.json();
  },
};

function setStatus(text, ok = true) {
  statusIndicator.textContent = text;
  statusIndicator.classList.toggle("error", !ok);
}

function populateProviders(data) {
  providerSelect.innerHTML = "";
  if (!data.providers || data.providers.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No providers";
    providerSelect.appendChild(option);
    return;
  }
  for (const provider of data.providers) {
    const option = document.createElement("option");
    option.value = provider.id;
    option.textContent = provider.description
      ? `${provider.id} — ${provider.description}`
      : provider.id;
    providerSelect.appendChild(option);
  }
}

function renderWorkspace(data) {
  workspaceList.innerHTML = "";
  currentPath = data.path || ".";

  const breadcrumb = document.createElement("li");
  breadcrumb.textContent = currentPath === "." ? "Workspace" : currentPath;
  breadcrumb.className = "workspace-path";
  workspaceList.appendChild(breadcrumb);

  if (currentPath !== ".") {
    const up = document.createElement("li");
    up.className = "workspace-up";
    up.innerHTML = `<span>⬆️ ..</span><span>Dir</span>`;
    up.addEventListener("click", () => {
      const parent = currentPath.split("/").slice(0, -1).join("/") || ".";
      api.getWorkspace(parent).then(renderWorkspace).catch(console.error);
    });
    workspaceList.appendChild(up);
  }

  for (const entry of data.entries) {
    const li = document.createElement("li");
    li.dataset.path = entry.path;
    li.dataset.isDir = entry.is_dir ? "1" : "0";
    li.className = entry.path === selectedProgram ? "selected" : "";
    li.innerHTML = `
      <span>${entry.is_dir ? "📁" : "📄"} ${entry.name}</span>
      <span>${entry.is_dir ? "Dir" : "File"}</span>
    `;
    li.addEventListener("click", () => {
      if (entry.is_dir) {
        api.getWorkspace(entry.path).then(renderWorkspace).catch(console.error);
      } else {
        selectedProgram = entry.path;
        document.getElementById("program-input").value = entry.path;
        renderWorkspace({ ...data, entries: data.entries });
      }
    });
    workspaceList.appendChild(li);
  }
}

function queueTerminalFit() {
  if (!fitAddon || typeof fitAddon.fit !== "function") {
    return;
  }
  if (fitRequestId) {
    return;
  }
  fitRequestId = window.requestAnimationFrame(() => {
    fitRequestId = null;
    try {
      fitAddon.fit();
    } catch (err) {
      console.error("terminal resize failed", err);
    }
  });
}

function initializeTerminal() {
  if (terminalInitialized || !terminalContainer) {
    return;
  }
  if (!window.Terminal) {
    console.error("xterm.js failed to load");
    return;
  }
  terminal = new window.Terminal({
    cursorBlink: true,
    scrollback: 2000,
    convertEol: true,
    fontFamily: "Fira Mono, Courier New, monospace",
    fontSize: 14,
    theme: {
      background: "#1b1b1b",
      foreground: "#d4d4d4",
      cursor: "#9cdcfe",
    },
  });
  terminal.open(terminalContainer);
  terminal.focus();
  if (window.FitAddon && window.FitAddon.FitAddon) {
    fitAddon = new window.FitAddon.FitAddon();
    terminal.loadAddon(fitAddon);
    queueTerminalFit();
    window.addEventListener("resize", queueTerminalFit);
  }
  terminal.onData(handleTerminalInput);
  terminalContainer.addEventListener("click", () => {
    terminal?.focus();
  });
  terminalInitialized = true;
}

function ensureTerminal() {
  if (!terminalInitialized) {
    initializeTerminal();
  }
  return terminal;
}

function writeDebuggerStatus(text) {
  const term = ensureTerminal();
  if (!term) {
    return;
  }
  term.write(`${text}\r\n`);
  queueTerminalFit();
}

function appendDebuggerOutput(text) {
  if (!text) {
    return;
  }
  const term = ensureTerminal();
  if (!term) {
    return;
  }
  const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  term.write(normalized.replace(/\n/g, "\r\n"));
  queueTerminalFit();
}

function handleBackspace() {
  if (!currentInput) {
    return;
  }
  currentInput = currentInput.slice(0, -1);
  terminal?.write("\b \b");
}

async function submitInput() {
  const term = ensureTerminal();
  if (!term) {
    return;
  }
  term.write("\r\n");
  const command = currentInput;
  currentInput = "";
  if (!sessionId) {
    writeDebuggerStatus("[debugger] start a session first");
    return;
  }
  try {
    await api.sendCommand(sessionId, command);
  } catch (err) {
    console.error(err);
    writeDebuggerStatus(`[error] ${err.message}`);
  }
}

function handleTerminalInput(data) {
  if (!terminal) {
    return;
  }
  if (!data) {
    return;
  }
  if (data === "\x1b[A" || data === "\x1b[B" || data === "\x1b[C" || data === "\x1b[D") {
    // History and cursor navigation will arrive in a later pass.
    return;
  }
  for (const ch of data) {
    if (ch === "\r" || ch === "\n") {
      if (ch === "\n" && lastWasCarriageReturn) {
        lastWasCarriageReturn = false;
        continue;
      }
      lastWasCarriageReturn = ch === "\r";
      submitInput();
      continue;
    }
    lastWasCarriageReturn = false;
    if (ch === "\u0003") {
      writeDebuggerStatus("[debugger] interrupt not yet supported");
      continue;
    }
    if (ch === "\x7f") {
      handleBackspace();
      continue;
    }
    if (ch.charCodeAt(0) < 32) {
      continue;
    }
    currentInput += ch;
    terminal.write(ch);
  }
}

function appendChatEntry(role, text) {
  const entry = document.createElement("div");
  entry.className = `chat-entry ${role}`;
  entry.textContent = `${role === "user" ? "You" : "Assistant"}: ${text}`;
  chatHistory.appendChild(entry);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

function clearConsole() {
  const term = ensureTerminal();
  if (!term) {
    return;
  }
  term.reset();
  currentInput = "";
  term.focus();
  lastWasCarriageReturn = false;
  queueTerminalFit();
  debuggerReplayBuffer = [];
}

function clearChat() {
  chatHistory.innerHTML = "";
}

function connectWebSockets(id) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const base = `${protocol}://${window.location.host}`;

  if (debuggerSocket) {
    debuggerSocket.close();
  }
  if (chatSocket) {
    chatSocket.close();
  }

  ensureTerminal();

  debuggerSocket = new WebSocket(`${base}/ws/debugger/${id}`);
  debuggerSocket.addEventListener("message", (event) => {
    const message = typeof event.data === "string" ? event.data : "";
    if (!message) {
      return;
    }
    if (debuggerReplayBuffer.length && debuggerReplayBuffer[0] === message) {
      debuggerReplayBuffer.shift();
      return;
    }
    appendDebuggerOutput(message);
  });
  debuggerSocket.addEventListener("open", () => {
    writeDebuggerStatus("[debugger] connected");
    queueTerminalFit();
  });
  debuggerSocket.addEventListener("close", () => {
    writeDebuggerStatus("[debugger] disconnected");
  });

  chatSocket = new WebSocket(`${base}/ws/chat/${id}`);
  chatSocket.addEventListener("message", (event) => {
    if (event.data) {
      appendChatEntry("assistant", event.data);
    }
  });
  chatSocket.addEventListener("open", () => {
    appendChatEntry("assistant", "[chat] connected");
  });
  chatSocket.addEventListener("close", () => {
    appendChatEntry("assistant", "[chat] disconnected");
  });
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = chatMessage.value.trim();
  if (!message) {
    return;
  }
  if (!sessionId) {
    appendChatEntry("assistant", "[chat] start a session first");
    return;
  }
  appendChatEntry("user", message);
  chatMessage.value = "";
  try {
    await api.sendChat(sessionId, message);
  } catch (err) {
    console.error(err);
    appendChatEntry("assistant", `[error] ${err.message}`);
  }
});

startSessionButton.addEventListener("click", async () => {
  const payload = {
    debugger: document.getElementById("debugger-select").value,
    provider: providerSelect.value,
    model: document.getElementById("model-input").value.trim() || null,
    api_key: document.getElementById("api-key-input").value.trim() || null,
    program: document.getElementById("program-input").value.trim() || null,
  };

  if (!payload.provider) {
    appendChatEntry("assistant", "[chat] select an LLM provider first");
    return;
  }

  try {
    const data = await api.createSession(payload);
    sessionId = data.session_id;
    clearConsole();
    clearChat();
    writeDebuggerStatus(`[debugger] session ${sessionId} created`);
    replayInitialDebuggerMessages(data.initial_messages || []);
    appendChatEntry("assistant", `[chat] session ${sessionId} ready`);
    setStatus(`session: ${sessionId}`);
    connectWebSockets(sessionId);
    try {
      await api.sendCommand(sessionId, "");
    } catch (signalError) {
      console.error("failed to prime debugger prompt", signalError);
    }
  } catch (err) {
    console.error(err);
    setStatus(`session error: ${err.message}`, false);
    appendChatEntry("assistant", `[error] ${err.message}`);
  }
});

function setupResizers() {
  dividers.forEach((divider) => {
    const targetId = divider.dataset.target;
    const targetPane = targetId ? document.getElementById(targetId) : null;
    if (!targetPane) {
      return;
    }

    const detachHandlers = (pointerId, moveHandler, upHandler) => {
      divider.releasePointerCapture(pointerId);
      divider.removeEventListener("pointermove", moveHandler);
      divider.removeEventListener("pointerup", upHandler);
      divider.removeEventListener("pointercancel", upHandler);
    };

    divider.addEventListener("pointerdown", (event) => {
      if (!targetPane) {
        return;
      }
      event.preventDefault();
      const pointerId = event.pointerId;
      const startX = event.clientX;
      const startWidth = targetPane.getBoundingClientRect().width;
      const minWidth = minPaneWidths[targetId] || 160;

      const onMove = (moveEvent) => {
        const delta = moveEvent.clientX - startX;
        const nextWidth = Math.max(minWidth, startWidth + delta);
        targetPane.style.flexBasis = `${nextWidth}px`;
        targetPane.style.width = `${nextWidth}px`;
        queueTerminalFit();
      };

      const onUp = () => detachHandlers(pointerId, onMove, onUp);

      divider.setPointerCapture(pointerId);
      divider.addEventListener("pointermove", onMove);
      divider.addEventListener("pointerup", onUp);
      divider.addEventListener("pointercancel", onUp);
    });

    divider.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
        return;
      }
      const minWidth = minPaneWidths[targetId] || 160;
      const currentWidth = targetPane.getBoundingClientRect().width;
      const step = event.shiftKey ? 40 : 20;
      const delta = event.key === "ArrowLeft" ? -step : step;
      const nextWidth = Math.max(minWidth, currentWidth + delta);
      targetPane.style.flexBasis = `${nextWidth}px`;
      targetPane.style.width = `${nextWidth}px`;
      event.preventDefault();
      queueTerminalFit();
    });
  });
}

function replayInitialDebuggerMessages(messages) {
  if (!Array.isArray(messages) || messages.length === 0) {
    debuggerReplayBuffer = [];
    return;
  }
  ensureTerminal();
  const normalized = messages.filter((msg) => typeof msg === "string" && msg.length > 0);
  debuggerReplayBuffer = normalized.slice();
  normalized.forEach((msg) => appendDebuggerOutput(msg));
}

async function bootstrap() {
  try {
    const status = await api.getStatus();
    setStatus(`status: ${status.status}`);
  } catch (err) {
    console.error(err);
    setStatus("status: offline", false);
  }

  try {
    const data = await api.getProviders();
    populateProviders(data);
  } catch (err) {
    console.error(err);
    providerSelect.innerHTML = "";
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "providers unavailable";
    providerSelect.appendChild(option);
  }

  try {
    const tree = await api.getWorkspace(".");
    renderWorkspace(tree);
  } catch (err) {
    console.error(err);
    workspaceList.innerHTML = "<li>workspace unavailable</li>";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initializeTerminal();
  setupResizers();
  bootstrap();
});
