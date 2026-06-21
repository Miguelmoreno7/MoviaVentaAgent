const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const messages = document.querySelector("#messages");
const requestState = document.querySelector("#request-state");
const leadInput = document.querySelector("#lead-id");
const channelInput = document.querySelector("#channel");
const resetButton = document.querySelector("#reset-chat");
const quickPrompts = document.querySelectorAll(".quick-prompts button");

const fields = {
  serviceStatus: document.querySelector("#service-status"),
  totalTokens: document.querySelector("#total-tokens"),
  inputTokens: document.querySelector("#input-tokens"),
  outputTokens: document.querySelector("#output-tokens"),
  actionName: document.querySelector("#action-name"),
  leadState: document.querySelector("#lead-state"),
  selectedAction: document.querySelector("#selected-action"),
  sourceCount: document.querySelector("#source-count"),
  sources: document.querySelector("#sources"),
  responseMetadata: document.querySelector("#response-metadata"),
  tokenCalls: document.querySelector("#token-calls"),
  messageCount: document.querySelector("#message-count"),
  messageParts: document.querySelector("#message-parts"),
};

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function renderKeyValues(node, data, preferredKeys = []) {
  const entries = [];
  const seen = new Set();
  preferredKeys.forEach((key) => {
    if (Object.prototype.hasOwnProperty.call(data, key)) {
      entries.push([key, data[key]]);
      seen.add(key);
    }
  });
  Object.entries(data || {}).forEach(([key, value]) => {
    if (!seen.has(key)) entries.push([key, value]);
  });

  if (!entries.length) {
    node.innerHTML = '<div class="empty">No data yet.</div>';
    return;
  }

  node.innerHTML = entries
    .map(
      ([key, value]) => `
        <dt>${escapeHtml(key)}</dt>
        <dd>${escapeHtml(formatValue(value))}</dd>
      `,
    )
    .join("");
}

function renderSources(sources) {
  fields.sourceCount.textContent = `${sources.length} chunks`;
  if (!sources.length) {
    fields.sources.innerHTML = '<div class="empty">No RAG chunks retrieved for this turn.</div>';
    return;
  }
  fields.sources.innerHTML = sources
    .map((source) => {
      const similarity =
        typeof source.similarity === "number" ? `${Math.round(source.similarity * 100)}%` : "n/a";
      const topic = source.metadata?.topic || "rag";
      const industry = source.metadata?.industry ? ` · ${source.metadata.industry}` : "";
      return `
        <article class="source-item">
          <h3>${escapeHtml(source.title || "Untitled source")}</h3>
          <p>${escapeHtml(source.preview || "")}</p>
          <div class="source-meta">
            <span>${escapeHtml(source.source_path || "")}</span>
            <span>${escapeHtml(topic + industry)}</span>
            <span>${similarity}</span>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderTokens(tokenUsage) {
  const total = tokenUsage?.total || {};
  fields.totalTokens.textContent = total.total_tokens || 0;
  fields.inputTokens.textContent = total.input_tokens || 0;
  fields.outputTokens.textContent = total.output_tokens || 0;

  const calls = tokenUsage?.calls || [];
  if (!calls.length) {
    fields.tokenCalls.innerHTML = '<div class="empty">No token usage recorded.</div>';
    return;
  }

  fields.tokenCalls.innerHTML = calls
    .map(
      (call) => `
        <div class="token-row">
          <div>
            <strong>${escapeHtml(call.operation || "call")}</strong>
            <div>${escapeHtml(call.model || "unknown")} · ${escapeHtml(call.provider || "n/a")}</div>
          </div>
          <div>${call.total_tokens || 0}</div>
        </div>
      `,
    )
    .join("");
}

function addMessage(role, text) {
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = text;
  messages.appendChild(item);
  messages.scrollTop = messages.scrollHeight;
}

function addAssistantMessages(parts, fallbackText) {
  const messagesToRender = Array.isArray(parts) && parts.length ? parts : [fallbackText || ""];
  messagesToRender.forEach((part) => addMessage("assistant", part));
}

function setBusy(isBusy) {
  requestState.textContent = isBusy ? "Running" : "Idle";
  form.querySelector("button").disabled = isBusy;
  input.disabled = isBusy;
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  setBusy(true);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        lead_external_id: leadInput.value || "local-ui-lead",
        channel: channelInput.value || "local",
      }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    addAssistantMessages(data.response_messages, data.response);
    renderDiagnostics(data);
  } catch (error) {
    addMessage("error", `Request failed: ${error.message}`);
  } finally {
    setBusy(false);
    input.focus();
  }
}

function renderDiagnostics(data) {
  fields.actionName.textContent = data.action || "none";
  renderKeyValues(fields.leadState, data.lead_state || {}, [
    "current_stage",
    "last_action",
    "business_type",
    "main_channel",
    "pain",
    "urgency",
    "buying_signal",
  ]);
  renderKeyValues(fields.selectedAction, data.selected_action || {}, [
    "macro_action",
    "micro_action",
    "commercial_goal",
    "cta_type",
    "objection_flow_step",
    "next_question",
  ]);
  renderSources(data.retrieved_sources || []);
  fields.responseMetadata.textContent = JSON.stringify(
    {
      response_metadata: data.response_metadata || {},
      retrieval_metadata: data.retrieval_metadata || {},
      knowledge_plan: data.knowledge_plan || {},
      analysis: data.analysis || {},
    },
    null,
    2,
  );
  renderTokens(data.token_usage || {});
  renderMessageParts(data.response_messages || []);
}

function renderMessageParts(parts) {
  fields.messageCount.textContent = `${parts.length} messages`;
  if (!parts.length) {
    fields.messageParts.innerHTML = '<div class="empty">No response messages yet.</div>';
    return;
  }
  fields.messageParts.innerHTML = parts
    .map(
      (part, index) => `
        <article class="message-part">
          <div class="message-part-header">
            <span>Message ${index + 1}</span>
            <span>${part.length} chars</span>
          </div>
          <p>${escapeHtml(part)}</p>
        </article>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadHealth() {
  try {
    const response = await fetch("/health");
    const health = await response.json();
    fields.serviceStatus.textContent = `DB ${health.database_configured ? "on" : "off"} · OpenAI ${
      health.openai_configured ? "on" : "off"
    } · Redis ${health.redis_configured ? "on" : "off"} · WhatsApp ${
      health.whatsapp_enabled ? "on" : "mock"
    }`;
  } catch {
    fields.serviceStatus.textContent = "Service unavailable";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    form.requestSubmit();
  }
});

quickPrompts.forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.textContent || ""));
});

resetButton.addEventListener("click", () => {
  messages.innerHTML = "";
  fields.actionName.textContent = "none";
  renderKeyValues(fields.leadState, {});
  renderKeyValues(fields.selectedAction, {});
  renderSources([]);
  renderTokens({});
  renderMessageParts([]);
  fields.responseMetadata.textContent = "{}";
  leadInput.value = `local-ui-${Date.now()}`;
});

renderKeyValues(fields.leadState, {});
renderKeyValues(fields.selectedAction, {});
renderSources([]);
renderTokens({});
renderMessageParts([]);
leadInput.value = `local-ui-${Date.now()}`;
loadHealth();
