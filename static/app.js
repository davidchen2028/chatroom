/**
 * WebSocket 客户端 —— 建立长连接，接收服务端推送的辩论消息。
 * 对比：如果用普通 HTTP，只能每隔几秒 fetch 一次，既慢又浪费流量。
 */

const topicInput = document.getElementById("topicInput");
const startBtn = document.getElementById("startBtn");
const clearBtn = document.getElementById("clearBtn");
const messagesEl = document.getElementById("messages");
const statusBar = document.getElementById("statusBar");

let ws = null;
let debating = false;
let typingEl = null;

function connect() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${location.host}/ws`);

  ws.onopen = () => {
    setStatus("已连接 · 输入话题后启动辩论");
    startBtn.disabled = false;
  };

  ws.onclose = () => {
    setStatus("连接断开，3 秒后重连…");
    startBtn.disabled = true;
    debating = false;
    setTimeout(connect, 3000);
  };

  ws.onerror = () => setStatus("连接出错");

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleMessage(data);
  };
}

function setStatus(text, active = false) {
  statusBar.textContent = text;
  statusBar.classList.toggle("active", active);
}

function removeTyping() {
  if (typingEl) {
    typingEl.remove();
    typingEl = null;
  }
}

function appendMessage({ role, name, color, content, round, className = "" }) {
  const el = document.createElement("div");
  el.className = `msg ${className}`.trim();
  if (color) el.style.borderLeftColor = color;

  const roundTag = round ? `<span class="msg-round">第 ${round} 轮</span>` : "";
  const nameTag = name ? `<span class="msg-name">${escapeHtml(name)}</span>` : "";

  el.innerHTML = `
    <div class="msg-header">${nameTag}${roundTag}</div>
    <div class="msg-content">${escapeHtml(content)}</div>
  `;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function handleMessage(data) {
  switch (data.type) {
    case "status":
      setStatus(data.content, true);
      appendMessage({ content: data.content, className: "status" });
      break;

    case "typing":
      removeTyping();
      typingEl = appendMessage({
        name: data.name,
        color: data.color,
        content: "正在思考…",
        className: "typing",
      });
      setStatus(`${data.name} 正在输入…`, true);
      break;

    case "message":
      removeTyping();
      appendMessage({
        role: data.role,
        name: data.name,
        color: data.color,
        content: data.content,
        round: data.round,
      });
      setStatus(`${data.name} 发言完毕`);
      break;

    case "error":
      removeTyping();
      debating = false;
      startBtn.disabled = false;
      appendMessage({ content: data.content, className: "error" });
      setStatus("出错了");
      break;

    case "done":
      removeTyping();
      debating = false;
      startBtn.disabled = false;
      appendMessage({ content: data.content, className: "done" });
      setStatus("辩论结束 · 可以换一个新话题");
      break;
  }
}

startBtn.addEventListener("click", () => {
  const topic = topicInput.value.trim();
  if (!topic) {
    alert("请先输入辩论话题");
    return;
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    alert("WebSocket 未连接，请稍候");
    return;
  }
  if (debating) return;

  debating = true;
  startBtn.disabled = true;
  messagesEl.innerHTML = "";
  ws.send(JSON.stringify({ type: "start_debate", topic }));
  setStatus("辩论启动中…", true);
});

clearBtn.addEventListener("click", () => {
  messagesEl.innerHTML = "";
  setStatus("记录已清空");
});

connect();
