function renderMarkdown(md) {
  return DOMPurify.sanitize(marked.parse(md));
}

const sessionId = crypto.randomUUID();
const chatEl = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");

function scrollChat() {
  window.requestAnimationFrame(() =>
    chatEl.scrollIntoView({ behavior: "smooth", block: "end" })
  );
}

function addUserBubble(text) {
  const wrap = document.createElement("div");
  wrap.className = "self-end max-w-[80%] bg-indigo-600 text-white rounded-2xl rounded-br-sm px-4 py-2";
  wrap.textContent = text;
  chatEl.appendChild(wrap);
  scrollChat();
}

function addAssistantContainer() {
  const wrap = document.createElement("div");
  wrap.className = "self-start max-w-[90%] flex flex-col gap-1";

  const toolStrip = document.createElement("div");
  toolStrip.className = "flex flex-wrap";
  wrap.appendChild(toolStrip);

  const bubble = document.createElement("div");
  bubble.className =
    "bubble prose prose-sm max-w-none bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-2";
  bubble.dataset.md = "";
  wrap.appendChild(bubble);

  chatEl.appendChild(wrap);
  scrollChat();
  return { toolStrip, bubble };
}

function appendMarkdown(bubble, chunk) {
  bubble.dataset.md = (bubble.dataset.md || "") + chunk;
  bubble.innerHTML = renderMarkdown(bubble.dataset.md);
}

function addPill(strip, label, kind) {
  const pill = document.createElement("span");
  pill.className = `pill${kind === "result" ? " result" : ""}`;
  pill.textContent = label;
  strip.appendChild(pill);
  scrollChat();
}

function fmtToolCall(name, inputObj) {
  let inputStr = "";
  try {
    inputStr = JSON.stringify(inputObj);
  } catch {
    inputStr = String(inputObj);
  }
  return `🔧 ${name}(${inputStr})`;
}

function fmtToolResult(name, resultStr) {
  let preview = resultStr;
  if (preview && preview.length > 120) {
    preview = `${preview.slice(0, 117)}…`;
  }
  return `↳ ${name} → ${preview}`;
}

async function send(message) {
  addUserBubble(message);
  const { toolStrip, bubble } = addAssistantContainer();
  sendBtn.disabled = true;
  input.disabled = true;

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!res.ok || !res.body) {
      appendMarkdown(bubble, `**Error:** ${res.status} ${res.statusText}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      while (true) {
        const idx = buf.indexOf("\n\n");
        if (idx === -1) break;
        const frame = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;

        let evt;
        try {
          evt = JSON.parse(payload);
        } catch {
          continue;
        }

        if (evt.type === "text") {
          appendMarkdown(bubble, evt.content);
          scrollChat();
        } else if (evt.type === "tool_call") {
          addPill(toolStrip, fmtToolCall(evt.name, evt.input), "call");
        } else if (evt.type === "tool_result") {
          addPill(toolStrip, fmtToolResult(evt.name, evt.result), "result");
        } else if (evt.type === "error") {
          appendMarkdown(bubble, `\n\n**[error]** ${evt.content}`);
          scrollChat();
        }
      }
    }
  } catch (err) {
    appendMarkdown(bubble, `**Network error:** ${err}`);
  } finally {
    sendBtn.disabled = false;
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const msg = input.value.trim();
  if (!msg) return;
  input.value = "";
  send(msg);
});

document.querySelectorAll(".suggest").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    const q = btn.dataset.q;
    if (q) send(q);
  });
});

input.focus();
