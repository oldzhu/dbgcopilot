const statusIndicator = document.getElementById("status-indicator");
const providerSelect = document.getElementById("provider-select");
const workspaceList = document.getElementById("workspace-list");
const terminalContainer = document.getElementById("debugger-terminal");
const chatHistory = document.getElementById("chat-history");
const chatForm = document.getElementById("chat-form");
const chatMessage = document.getElementById("chat-message");
const autoApproveToggle = document.getElementById("chat-auto-approve");
const chatConfigButton = document.getElementById("chat-config-button");
const chatConfigPanel = document.getElementById("chat-config-panel");
const chatConfigClose = document.getElementById("chat-config-close");
const providerSelectTrigger = document.getElementById("provider-select-trigger");
const providerOptionsList = document.getElementById("provider-options");
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
let terminalSupportsKeystream = false;
let fallbackControls = null;
let providerSelectTooltip = null;
let providerSelectWrapper = null;
let providerDropdownOpen = false;
let providerOptionElements = [];
const providerPlaceholderText = "Select a provider";
let desiredAutoApprove = false;

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
  async closeSession(id) {
    const resp = await fetch(`/api/sessions/${id}`, {
      method: "DELETE",
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`close session failed: ${resp.status} ${text}`);
    }
    return resp.json();
  },
  async setAutoApprove(id, enabled) {
    const resp = await fetch(`/api/sessions/${id}/auto-approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`auto-approve update failed: ${resp.status} ${text}`);
    }
    return resp.json();
  },
};

function setStatus(text, ok = true) {
  statusIndicator.textContent = text;
  statusIndicator.classList.toggle("error", !ok);
}

async function applyAutoApprove(enabled, options = {}) {
  const { silent = false } = options;
  desiredAutoApprove = enabled;
  if (autoApproveToggle) {
    autoApproveToggle.checked = enabled;
  }
  if (!sessionId) {
    return;
  }
  try {
    await api.setAutoApprove(sessionId, enabled);
    if (!silent) {
      appendChatEntry("assistant", `[chat] auto-approve ${enabled ? "enabled" : "disabled"}`);
    }
  } catch (err) {
    console.error(err);
    if (autoApproveToggle) {
      autoApproveToggle.checked = !enabled;
    }
    desiredAutoApprove = autoApproveToggle ? autoApproveToggle.checked : false;
    appendChatEntry("assistant", `[error] auto-approve update failed: ${err.message}`);
  }
}

function populateProviders(data) {
  providerSelect.innerHTML = "";
  if (providerOptionsList) {
    providerOptionsList.innerHTML = "";
    providerOptionsList.hidden = true;
  }
  providerDropdownOpen = false;
  providerOptionElements = [];
  if (!providerSelectWrapper || !providerSelectTooltip) {
    providerSelectWrapper = providerSelect.closest(".select-wrapper");
    providerSelectTooltip = providerSelectWrapper
      ? providerSelectWrapper.querySelector(".select-tooltip")
      : null;
  }
  const previousValue = providerSelect.value || "";
  if (!data.providers || data.providers.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No providers";
    providerSelect.appendChild(option);
    if (providerSelectTrigger) {
      providerSelectTrigger.textContent = "No providers";
      providerSelectTrigger.disabled = true;
    }
    hideProviderTooltip();
    return;
  }

  hideProviderTooltip();
  if (providerSelectTrigger) {
    providerSelectTrigger.disabled = false;
    providerSelectTrigger.textContent = providerPlaceholderText;
    providerSelectTrigger.setAttribute("aria-expanded", "false");
  }

  data.providers.forEach((provider, index) => {
    const description = provider.description || "";

    const selectOption = document.createElement("option");
    selectOption.value = provider.id;
    selectOption.textContent = provider.id;
    selectOption.dataset.description = description;
    providerSelect.appendChild(selectOption);

    if (!providerOptionsList) {
      return;
    }

    const optionItem = document.createElement("li");
    optionItem.className = "select-option";
    optionItem.setAttribute("role", "option");
    optionItem.dataset.value = provider.id;
    optionItem.dataset.description = description;
    optionItem.tabIndex = -1;
    optionItem.textContent = provider.id;

    optionItem.addEventListener("mouseenter", () => showProviderTooltip(description));
    optionItem.addEventListener("mouseleave", () => {
      if (!providerDropdownOpen) {
        hideProviderTooltip();
      }
    });
    optionItem.addEventListener("focus", () => showProviderTooltip(description));
    optionItem.addEventListener("blur", () => {
      if (!providerDropdownOpen) {
        hideProviderTooltip();
      }
    });
    optionItem.addEventListener("click", () => {
      selectProvider(provider.id);
    });
    optionItem.addEventListener("keydown", (event) => handleProviderOptionKeydown(event, index));

    providerOptionsList.appendChild(optionItem);
    providerOptionElements.push({ value: provider.id, element: optionItem, description });
  });

  const hasPrevious = providerOptionElements.some((item) => item.value === previousValue);
  const initialValue = hasPrevious ? previousValue : providerOptionElements[0]?.value || "";
  selectProvider(initialValue, { closeDropdown: false, silent: true });
}

function showProviderTooltip(description) {
  if (!providerSelectTooltip || !providerSelectWrapper) {
    return;
  }
  const text = (description || "").trim();
  if (text) {
    providerSelectTooltip.textContent = text;
    providerSelectWrapper.classList.add("focused");
  } else {
    hideProviderTooltip();
  }
}

function hideProviderTooltip() {
  if (!providerSelectTooltip || !providerSelectWrapper) {
    return;
  }
  providerSelectTooltip.textContent = "";
  providerSelectWrapper.classList.remove("focused");
}

function markSelectedProvider(value) {
  providerOptionElements.forEach(({ value: optionValue, element }) => {
    const selected = optionValue === value;
    element.setAttribute("aria-selected", selected ? "true" : "false");
    element.classList.toggle("is-selected", selected);
  });
}

function selectProvider(value, options = {}) {
  const { closeDropdown: shouldCloseDropdown = true, silent = false } = options;
  if (!providerSelect) {
    return;
  }
  const match = providerOptionElements.find((item) => item.value === value);
  if (!match) {
    providerSelect.value = "";
    if (providerSelectTrigger) {
      providerSelectTrigger.textContent = providerPlaceholderText;
    }
    markSelectedProvider(null);
    hideProviderTooltip();
    if (shouldCloseDropdown) {
      closeProviderDropdown({ returnFocus: true });
    }
    return;
  }

  providerSelect.value = match.value;
  markSelectedProvider(match.value);
  if (providerSelectTrigger) {
    providerSelectTrigger.textContent = match.value;
  }
  if (!silent) {
    hideProviderTooltip();
  }
  if (shouldCloseDropdown) {
    closeProviderDropdown({ returnFocus: true });
  }
}

function handleProviderOptionKeydown(event, index) {
  if (!providerOptionElements.length) {
    return;
  }
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    const selected = providerOptionElements[index];
    if (selected) {
      selectProvider(selected.value);
    }
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    focusProviderOptionByIndex(index + 1);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    focusProviderOptionByIndex(index - 1);
    return;
  }
  if (event.key === "Home") {
    event.preventDefault();
    focusProviderOptionByIndex(0);
    return;
  }
  if (event.key === "End") {
    event.preventDefault();
    focusProviderOptionByIndex(providerOptionElements.length - 1);
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeProviderDropdown({ returnFocus: true });
    return;
  }
  if (event.key === "Tab") {
    closeProviderDropdown({ returnFocus: false });
  }
}

function focusProviderOptionByIndex(index) {
  if (!providerOptionElements.length) {
    return;
  }
  const normalizedIndex = ((index % providerOptionElements.length) + providerOptionElements.length) %
    providerOptionElements.length;
  const option = providerOptionElements[normalizedIndex];
  if (option) {
    focusWithoutScroll(option.element);
    showProviderTooltip(option.description);
  }
}

function openProviderDropdown() {
  if (!providerOptionsList || providerDropdownOpen || !providerOptionElements.length) {
    return;
  }
  providerOptionsList.hidden = false;
  providerDropdownOpen = true;
  if (providerSelectTrigger) {
    providerSelectTrigger.setAttribute("aria-expanded", "true");
  }
  const currentValue = providerSelect.value;
  const match = providerOptionElements.find((item) => item.value === currentValue);
  const targetOption = match || providerOptionElements[0];
  if (targetOption) {
    focusWithoutScroll(targetOption.element);
    showProviderTooltip(targetOption.description);
  }
}

function closeProviderDropdown(options = {}) {
  const { returnFocus = false } = options;
  if (!providerDropdownOpen) {
    return;
  }
  if (providerOptionsList) {
    providerOptionsList.hidden = true;
  }
  providerDropdownOpen = false;
  hideProviderTooltip();
  if (providerSelectTrigger) {
    providerSelectTrigger.setAttribute("aria-expanded", "false");
    if (returnFocus) {
      focusWithoutScroll(providerSelectTrigger);
    }
  }
}

function toggleProviderDropdown() {
  if (providerDropdownOpen) {
    closeProviderDropdown({ returnFocus: true });
  } else {
    openProviderDropdown();
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
    console.warn("xterm.js not available; using fallback debugger console");
    terminalSupportsKeystream = false;
    terminal = createFallbackTerminal();
    if (terminal && typeof terminal.focus === "function") {
      terminal.focus();
    }
    terminalInitialized = true;
    return;
  }
  terminalSupportsKeystream = true;
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
  if (typeof terminal.onData === "function") {
    terminal.onData(handleTerminalInput);
  }
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

function appendChatEntry(role, text) {
  const entry = document.createElement("div");
  entry.className = `chat-entry ${role}`;
  const speaker = role === "user" ? "You" : "Copilot";

  const label = document.createElement("div");
  label.className = "chat-entry-label";
  label.textContent = speaker;
  entry.appendChild(label);

  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.textContent = text;
  entry.appendChild(bubble);

  chatHistory.appendChild(entry);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

function appendChatProposal(data) {
  const entry = document.createElement("div");
  entry.className = "chat-entry assistant proposal";

  const prefix = document.createElement("div");
  prefix.className = "chat-entry-label";
  prefix.textContent = "Copilot";
  entry.appendChild(prefix);

  const card = document.createElement("div");
  card.className = "chat-proposal-card";

  const heading = document.createElement("div");
  heading.className = "chat-proposal-heading";
  heading.textContent = "Proposed debugger command";
  card.appendChild(heading);

  if (data.explanation) {
    const explanation = document.createElement("p");
    explanation.className = "chat-proposal-explanation";
    explanation.textContent = data.explanation;
    card.appendChild(explanation);
  }

  const commandBlock = document.createElement("pre");
  commandBlock.className = "chat-proposal-command";
  const commandLabel = data.label || "debugger";
  commandBlock.textContent = `${commandLabel}> ${data.command}`;
  card.appendChild(commandBlock);

  const actions = document.createElement("div");
  actions.className = "chat-proposal-actions";
  const buttons = [
    { label: "Approve", value: "y", friendly: "Approve (y)" },
    { label: "Skip", value: "n", friendly: "Skip (n)" },
    { label: "Auto-Approve", value: "a", friendly: "Auto-approve (a)" },
  ];

  buttons.forEach(({ label: btnLabel, value, friendly }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = btnLabel;
    button.addEventListener("click", () => handleProposalAction(entry, value, friendly));
    actions.appendChild(button);
  });
  card.appendChild(actions);

  const status = document.createElement("div");
  status.className = "chat-proposal-status";
  status.textContent = "Awaiting your decision.";
  card.appendChild(status);

  entry.appendChild(card);
  chatHistory.appendChild(entry);
  chatHistory.scrollTop = chatHistory.scrollHeight;
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
  if (!terminalSupportsKeystream) {
    return;
  }
  if (!currentInput) {
    return;
  }
  currentInput = currentInput.slice(0, -1);
  terminal?.write("\b \b");
}

async function submitInput() {
  if (!terminalSupportsKeystream) {
    return;
  }
  const term = ensureTerminal();
  if (!term) {
    return;
  }
  term.write("\r\n");
  const command = currentInput;
  currentInput = "";
  await dispatchDebuggerCommand(command);
}

function handleTerminalInput(data) {
  if (!terminalSupportsKeystream) {
    return;
  }
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

async function handleProposalAction(entry, value, friendly) {
  if (!sessionId) {
    appendChatEntry("assistant", "[chat] start a session first");
    return;
  }

  const status = entry.querySelector(".chat-proposal-status");
  const buttons = entry.querySelectorAll(".chat-proposal-actions button");
  buttons.forEach((button) => {
    button.disabled = true;
  });
  if (status) {
    status.textContent = "Submitting...";
  }

  try {
    await api.sendChat(sessionId, value);
    appendChatEntry("user", friendly);
    if (status) {
      status.textContent = `You chose: ${friendly}`;
    }
    entry.dataset.state = "resolved";
  } catch (err) {
    console.error(err);
    if (status) {
      status.textContent = `Error: ${err.message}`;
    }
    buttons.forEach((button) => {
      button.disabled = false;
    });
  }
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

  disconnectWebSockets();

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
    const message = typeof event.data === "string" ? event.data : "";
    if (!message) {
      return;
    }
    try {
      const parsed = JSON.parse(message);
      if (parsed && parsed.type === "command_proposal" && parsed.command) {
        appendChatProposal(parsed);
        return;
      }
    } catch (err) {
      // Non-JSON payloads fall back to plain text rendering.
    }
    appendChatEntry("assistant", message);
  });
  chatSocket.addEventListener("open", () => {
    appendChatEntry("assistant", "[chat] connected");
  });
  chatSocket.addEventListener("close", () => {
    appendChatEntry("assistant", "[chat] disconnected");
  });
}

function disconnectWebSockets() {
  if (debuggerSocket) {
    debuggerSocket.close();
    debuggerSocket = null;
  }
  if (chatSocket) {
    chatSocket.close();
    chatSocket = null;
  }
}

function updateSessionControls(active) {
  startSessionButton.textContent = active ? "Stop Session" : "Start Session";
  startSessionButton.dataset.sessionState = active ? "active" : "idle";
  startSessionButton.setAttribute("aria-pressed", active ? "true" : "false");
}

function openChatConfig() {
  if (!chatConfigPanel) {
    return;
  }
  closeProviderDropdown({ returnFocus: false });
  chatConfigPanel.hidden = false;
  focusWithoutScroll(chatConfigPanel);
  if (chatConfigButton) {
    chatConfigButton.setAttribute("aria-expanded", "true");
  }
}

function closeChatConfig(options = {}) {
  const { returnFocus = false } = options;
  if (!chatConfigPanel || chatConfigPanel.hidden) {
    return;
  }
  chatConfigPanel.hidden = true;
  closeProviderDropdown({ returnFocus: false });
  if (chatConfigButton) {
    chatConfigButton.setAttribute("aria-expanded", "false");
    if (returnFocus) {
      focusWithoutScroll(chatConfigButton);
    }
  }
  hideProviderTooltip();
}

function toggleChatConfig() {
  if (!chatConfigPanel) {
    return;
  }
  if (chatConfigPanel.hidden) {
    openChatConfig();
  } else {
    closeChatConfig({ returnFocus: true });
  }
}

function focusWithoutScroll(element) {
  if (!element || typeof element.focus !== "function") {
    return;
  }
  try {
    element.focus({ preventScroll: true });
  } catch (err) {
    element.focus();
  }
}

if (chatConfigButton) {
  chatConfigButton.addEventListener("click", (event) => {
    event.preventDefault();
    toggleChatConfig();
  });
}

if (chatConfigClose) {
  chatConfigClose.addEventListener("click", () => closeChatConfig({ returnFocus: true }));
}

if (autoApproveToggle) {
  desiredAutoApprove = autoApproveToggle.checked;
  autoApproveToggle.addEventListener("change", async () => {
    desiredAutoApprove = autoApproveToggle.checked;
    if (!sessionId) {
      setStatus(
        desiredAutoApprove
          ? "auto-approve will be enabled when a session starts"
          : "auto-approve disabled (no active session)",
        true
      );
      return;
    }
    await applyAutoApprove(desiredAutoApprove);
  });
}

if (providerSelectTrigger) {
  providerSelectTrigger.addEventListener("click", (event) => {
    if (providerSelectTrigger.disabled) {
      return;
    }
    event.preventDefault();
    toggleProviderDropdown();
  });

  providerSelectTrigger.addEventListener("keydown", (event) => {
    if (providerSelectTrigger.disabled) {
      return;
    }
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openProviderDropdown();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      openProviderDropdown();
      if (providerOptionElements.length) {
        focusProviderOptionByIndex(providerOptionElements.length - 1);
      }
    }
  });
}

if (providerOptionsList) {
  providerOptionsList.addEventListener("mouseleave", () => {
    if (providerDropdownOpen) {
      hideProviderTooltip();
    }
  });
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (providerDropdownOpen) {
    const insideWrapper = providerSelectWrapper && providerSelectWrapper.contains(target);
    if (!insideWrapper) {
      closeProviderDropdown({ returnFocus: false });
    }
  }
  if (!chatConfigPanel || chatConfigPanel.hidden) {
    return;
  }
  const clickedInsidePanel = chatConfigPanel.contains(target);
  const clickedButton = chatConfigButton && chatConfigButton.contains(target);
  if (clickedInsidePanel || clickedButton) {
    return;
  }
  closeChatConfig({ returnFocus: false });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (providerDropdownOpen) {
      event.preventDefault();
      closeProviderDropdown({ returnFocus: true });
      return;
    }
    closeChatConfig({ returnFocus: true });
  }
});

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
  if (startSessionButton.disabled) {
    return;
  }
  startSessionButton.disabled = true;

  if (sessionId) {
    const activeSession = sessionId;
    try {
      await api.closeSession(activeSession);
      disconnectWebSockets();
      sessionId = null;
      setStatus("session: none");
      writeDebuggerStatus(`[debugger] session ${activeSession} stopped`);
      appendChatEntry("assistant", `[chat] session ${activeSession} stopped`);
      updateSessionControls(false);
    } catch (err) {
      console.error(err);
      setStatus(`stop error: ${err.message}`, false);
      writeDebuggerStatus(`[error] ${err.message}`);
      startSessionButton.disabled = false;
      return;
    }
    startSessionButton.disabled = false;
    return;
  }

  const payload = {
    debugger: document.getElementById("debugger-select").value,
    provider: providerSelect.value,
    model: document.getElementById("model-input").value.trim() || null,
    api_key: document.getElementById("api-key-input").value.trim() || null,
    program: document.getElementById("program-input").value.trim() || null,
    auto_approve: desiredAutoApprove,
  };

  if (["delve", "radare2"].includes(payload.debugger) && !payload.program) {
    appendChatEntry(
      "assistant",
      `[chat] ${payload.debugger} requires the program field to point to the binary you want to debug.`
    );
    setStatus(`${payload.debugger}: program path required`, false);
    startSessionButton.disabled = false;
    return;
  }

  if (!payload.provider) {
    appendChatEntry("assistant", "[chat] select an LLM provider first");
    startSessionButton.disabled = false;
    return;
  }

  if (!payload.api_key) {
    window.alert(
      "API key is required to start a session. Click the gear icon beside 'Coliot Chat' to open settings and add your key."
    );
    appendChatEntry(
      "assistant",
      "[chat] set an API key via the gear icon beside 'Coliot Chat' before starting a session"
    );
    setStatus("api key required", false);
    startSessionButton.disabled = false;
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
    updateSessionControls(true);
    await dispatchDebuggerCommand("");
    if (desiredAutoApprove) {
      await applyAutoApprove(true, { silent: true });
    }
  } catch (err) {
    console.error(err);
    setStatus(`session error: ${err.message}`, false);
    appendChatEntry("assistant", `[error] ${err.message}`);
    updateSessionControls(false);
  } finally {
    startSessionButton.disabled = false;
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
      const targetBeforeDivider = divider.previousElementSibling === targetPane;

      const onMove = (moveEvent) => {
        const rawDelta = moveEvent.clientX - startX;
        const delta = targetBeforeDivider ? rawDelta : -rawDelta;
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
      const targetBeforeDivider = divider.previousElementSibling === targetPane;
      const adjustedDelta = targetBeforeDivider ? delta : -delta;
      const nextWidth = Math.max(minWidth, currentWidth + adjustedDelta);
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

async function dispatchDebuggerCommand(command) {
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

const ANSI_CODE_PATTERN = /\x1b\[([0-9;]*)m/g;
const ANSI_STRIP_PATTERN = /\x1b\[[0-9;]*m/g;

const ANSI_FG_MAP = {
  30: "#000000",
  31: "#cd3131",
  32: "#0dbc79",
  33: "#e5e510",
  34: "#2472c8",
  35: "#bc3fbc",
  36: "#11a8cd",
  37: "#e5e5e5",
  90: "#666666",
  91: "#f14c4c",
  92: "#23d18b",
  93: "#f5f543",
  94: "#3b8eea",
  95: "#d670d6",
  96: "#29b8db",
  97: "#f2f2f2",
};

const ANSI_BG_MAP = {
  40: "#000000",
  41: "#cd3131",
  42: "#0dbc79",
  43: "#e5e510",
  44: "#2472c8",
  45: "#bc3fbc",
  46: "#11a8cd",
  47: "#e5e5e5",
  100: "#666666",
  101: "#f14c4c",
  102: "#23d18b",
  103: "#f5f543",
  104: "#3b8eea",
  105: "#d670d6",
  106: "#29b8db",
  107: "#f2f2f2",
};

const DEFAULT_FG_COLOR = "#d4d4d4";
const DEFAULT_BG_COLOR = "#1b1b1b";

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function stripAnsiCodes(text) {
  return (text || "").replace(ANSI_STRIP_PATTERN, "");
}

function createAnsiState() {
  return {
    bold: false,
    italic: false,
    underline: false,
    inverse: false,
    fg: null,
    bg: null,
    fgCss: null,
    bgCss: null,
  };
}

function applyAnsiCodes(state, codes) {
  if (!codes.length) {
    codes = [0];
  }
  for (let i = 0; i < codes.length; i += 1) {
    const code = codes[i];
    if (!Number.isFinite(code)) {
      continue;
    }
    if (code === 0) {
      Object.assign(state, createAnsiState());
      continue;
    }
    switch (code) {
      case 1:
        state.bold = true;
        break;
      case 3:
        state.italic = true;
        break;
      case 4:
        state.underline = true;
        break;
      case 7:
        state.inverse = true;
        break;
      case 21:
      case 22:
        state.bold = false;
        break;
      case 23:
        state.italic = false;
        break;
      case 24:
        state.underline = false;
        break;
      case 27:
        state.inverse = false;
        break;
      case 39:
        state.fg = null;
        state.fgCss = null;
        break;
      case 49:
        state.bg = null;
        state.bgCss = null;
        break;
      default:
        if (code >= 30 && code <= 37) {
          state.fg = code;
          state.fgCss = null;
        } else if (code >= 90 && code <= 97) {
          state.fg = code;
          state.fgCss = null;
        } else if (code >= 40 && code <= 47) {
          state.bg = code;
          state.bgCss = null;
        } else if (code >= 100 && code <= 107) {
          state.bg = code;
          state.bgCss = null;
        }
        break;
    }
  }
}

function buildAnsiAttributes(state) {
  const classes = [];
  const styles = [];
  if (!state) {
    return { classes, styleText: "" };
  }
  if (state.bold) {
    classes.push("ansi-bold");
  }
  if (state.italic) {
    classes.push("ansi-italic");
  }
  if (state.underline) {
    classes.push("ansi-underline");
  }

  let fg = state.fg;
  let bg = state.bg;
  let fgCss = state.fgCss;
  let bgCss = state.bgCss;

  if (state.inverse) {
    const tmpFg = fg;
    const tmpBg = bg;
    const tmpFgCss = fgCss;
    const tmpBgCss = bgCss;
    fg = tmpBg;
    bg = tmpFg;
    fgCss = tmpBgCss;
    bgCss = tmpFgCss;
    if (!fg && !fgCss) {
      fgCss = DEFAULT_BG_COLOR;
    }
    if (!bg && !bgCss) {
      bgCss = DEFAULT_FG_COLOR;
    }
  }

  if (fgCss) {
    styles.push(`color: ${fgCss}`);
  } else if (typeof fg === "number" && ANSI_FG_MAP[fg]) {
    classes.push(`ansi-fg-${fg}`);
  }

  if (bgCss) {
    styles.push(`background-color: ${bgCss}`);
  } else if (typeof bg === "number" && ANSI_BG_MAP[bg]) {
    classes.push(`ansi-bg-${bg}`);
  }

  return {
    classes,
    styleText: styles.join("; "),
  };
}

function wrapAnsiChunk(chunk, state) {
  if (!chunk) {
    return "";
  }
  const escaped = escapeHtml(chunk);
  const { classes, styleText } = buildAnsiAttributes(state);
  if (!classes.length && !styleText) {
    return escaped;
  }
  const classAttr = classes.length ? ` class="${classes.join(" ")}"` : "";
  const styleAttr = styleText ? ` style="${styleText}"` : "";
  return `<span${classAttr}${styleAttr}>${escaped}</span>`;
}

function ansiToHtml(text) {
  const input = text ?? "";
  if (!input) {
    return "";
  }
  ANSI_CODE_PATTERN.lastIndex = 0;
  const state = createAnsiState();
  let result = "";
  let lastIndex = 0;
  let match;
  while ((match = ANSI_CODE_PATTERN.exec(input)) !== null) {
    if (match.index > lastIndex) {
      result += wrapAnsiChunk(input.slice(lastIndex, match.index), state);
    }
    const codes = (match[1] || "0")
      .split(";")
      .map((part) => Number.parseInt(part, 10))
      .filter((n) => !Number.isNaN(n));
    applyAnsiCodes(state, codes);
    lastIndex = ANSI_CODE_PATTERN.lastIndex;
  }
  if (lastIndex < input.length) {
    result += wrapAnsiChunk(input.slice(lastIndex), state);
  }
  return result;
}

function setAnsiContent(element, text) {
  if (!element) {
    return;
  }
  const html = ansiToHtml(text);
  element.innerHTML = html;
  const plain = stripAnsiCodes(text ?? "");
  element.setAttribute("data-plain-text", plain);
}

function createFallbackTerminal() {
  const container = terminalContainer;
  if (!container) {
    return null;
  }
  container.innerHTML = "";
  container.classList.add("terminal-fallback-container");

  const output = document.createElement("div");
  output.className = "terminal-fallback-output";
  container.appendChild(output);

  const inputLine = document.createElement("div");
  inputLine.className = "terminal-fallback-input-line";

  const prompt = document.createElement("span");
  prompt.className = "terminal-fallback-prompt";
  prompt.textContent = "";

  const input = document.createElement("span");
  input.className = "terminal-fallback-input";
  input.contentEditable = "true";
  input.spellcheck = false;
  input.setAttribute("role", "textbox");
  input.setAttribute("aria-label", "Debugger command input");

  inputLine.appendChild(prompt);
  inputLine.appendChild(input);
  container.appendChild(inputLine);

  const controls = {
    output,
    input,
    prompt,
    buffer: "",
    currentPrompt: "",
    lastPrompt: "> ",
    defaultPrompt: "> ",
  };

  function focusInput() {
    input.focus();
    const selection = window.getSelection();
    if (!selection) {
      return;
    }
    const range = document.createRange();
    range.selectNodeContents(input);
    range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function appendLine(text) {
    const block = document.createElement("pre");
    const raw = text ?? "";
    const html = ansiToHtml(raw);
    block.innerHTML = html || "&nbsp;";
    block.setAttribute("data-plain-text", stripAnsiCodes(raw));
    output.appendChild(block);
    output.scrollTop = output.scrollHeight;
  }

  function setPrompt(text) {
    const raw = text ?? "";
    controls.currentPrompt = raw;
    if (raw) {
      controls.lastPrompt = raw;
      input.dataset.placeholder = "";
    } else {
      input.dataset.placeholder = "waiting for debugger...";
    }
    setAnsiContent(prompt, raw);
    const plain = stripAnsiCodes(raw);
    if (plain) {
      prompt.setAttribute("aria-label", plain);
    } else {
      prompt.removeAttribute("aria-label");
    }
  }

  async function submitCommand(command) {
    const displayPrompt = controls.currentPrompt || controls.lastPrompt || controls.defaultPrompt;
    appendLine(`${displayPrompt}${command}`);
    input.textContent = "";
    controls.buffer = "";
    setPrompt("");
    await dispatchDebuggerCommand(command);
  }

  input.addEventListener("keydown", async (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const command = input.textContent ?? "";
      await submitCommand(command);
      focusInput();
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
    }
  });

  input.addEventListener("input", () => {
    const sanitized = input.textContent?.replace(/\n/g, " ") ?? "";
    if (sanitized !== input.textContent) {
      input.textContent = sanitized;
      focusInput();
    }
  });

  container.addEventListener("mousedown", (event) => {
    if (output.contains(event.target)) {
      return;
    }
    window.requestAnimationFrame(focusInput);
  });

  fallbackControls = controls;
  setPrompt("");
  focusInput();

  return {
    write(text) {
      if (!text) {
        return;
      }
      const normalized = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      const combined = controls.buffer + normalized;
      const segments = combined.split("\n");
      controls.buffer = normalized.endsWith("\n") ? "" : segments.pop() ?? "";
      segments.forEach((segment) => appendLine(segment));
      if (controls.buffer) {
        setPrompt(controls.buffer);
      } else if (!controls.currentPrompt) {
        setPrompt("");
      }
      focusInput();
    },
    reset() {
      output.innerHTML = "";
      input.textContent = "";
      controls.buffer = "";
      controls.lastPrompt = controls.defaultPrompt;
      setPrompt("");
      focusInput();
    },
    focus() {
      focusInput();
    },
  };
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
    if (providerOptionsList) {
      providerOptionsList.innerHTML = "";
    }
    if (providerSelectTrigger) {
      providerSelectTrigger.textContent = "providers unavailable";
      providerSelectTrigger.disabled = true;
      providerSelectTrigger.setAttribute("aria-expanded", "false");
    }
    hideProviderTooltip();
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
  updateSessionControls(false);
  initializeTerminal();
  setupResizers();
  bootstrap();
});
