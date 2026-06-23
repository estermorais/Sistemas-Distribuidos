const AUTH_URL = "/api/auth";
const CHAT_URL = "/api/chat";
const WS_BASE  = `ws://${location.host}/ws`;

// ── State ──────────────────────────────────────────────────────────────────
let state = {
  token: null, userId: null, username: null,
  ws: null, reconnectTimer: null,
  activeTarget: null,
  users: [],
  rooms: [],
  unread: {},
};

// ── Helpers ────────────────────────────────────────────────────────────────
const $   = id => document.getElementById(id);
const esc = s  => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const fmtTime = iso => new Date(iso).toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"});
const fmtDate = iso => {
  const d = new Date(iso), now = new Date();
  if (d.toDateString() === now.toDateString()) return "Hoje";
  const yest = new Date(now); yest.setDate(yest.getDate()-1);
  if (d.toDateString() === yest.toDateString()) return "Ontem";
  return d.toLocaleDateString("pt-BR");
};
const convKey = (type, id) => `${type}:${id}`;

const COLORS = ["#6366F1","#8B5CF6","#EC4899","#F59E0B","#10B981","#3B82F6","#EF4444"];
const avatarColor  = name => { let h = 0; for (let c of (name||"?")) h=(h*31+c.charCodeAt(0))&0xffff; return COLORS[h%COLORS.length]; };
const avatarLetter = name => (name||"?")[0].toUpperCase();

// ── Auth tabs ──────────────────────────────────────────────────────────────
document.querySelectorAll(".atab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".atab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".aform").forEach(f => f.classList.remove("active"));
    tab.classList.add("active");
    $(`${tab.dataset.tab}-form`).classList.add("active");
    $("auth-error").textContent = "";
  });
});

// ── Register ───────────────────────────────────────────────────────────────
$("register-form").addEventListener("submit", async e => {
  e.preventDefault();
  setAuthError("");
  try {
    const res = await fetch(`${AUTH_URL}/register`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        username: $("reg-username").value.trim(),
        password: $("reg-password").value,
        email: $("reg-email").value.trim() || null,
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Erro ao cadastrar");
    setAuthError("Conta criada! Faça login.", "#10B981");
    document.querySelector('[data-tab="login"]').click();
    $("login-username").value = $("reg-username").value;
  } catch(err) { setAuthError(err.message); }
});

// ── Login ──────────────────────────────────────────────────────────────────
$("login-form").addEventListener("submit", async e => {
  e.preventDefault();
  setAuthError("");
  const form = new URLSearchParams();
  form.append("username", $("login-username").value.trim());
  form.append("password", $("login-password").value);
  try {
    const res = await fetch(`${AUTH_URL}/login`, {method:"POST", body:form});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Usuário ou senha inválidos");
    state.token    = data.access_token;
    state.userId   = data.user_id;
    state.username = data.username;
    sessionStorage.setItem("token",    data.access_token);
    sessionStorage.setItem("userId",   data.user_id);
    sessionStorage.setItem("username", data.username);
    enterChat();
  } catch(err) { setAuthError(err.message); }
});

function setAuthError(msg, color="#EF4444") {
  const el = $("auth-error");
  el.textContent = msg;
  el.style.color = color;
}

// ── Logout ─────────────────────────────────────────────────────────────────
$("logout-btn").addEventListener("click", () => {
  if (state.ws) state.ws.close();
  clearTimeout(state.reconnectTimer);
  sessionStorage.clear();
  Object.assign(state, {token:null,userId:null,username:null,ws:null,activeTarget:null,users:[],rooms:[],unread:{}});
  $("auth-screen").classList.add("active");
  $("chat-screen").classList.remove("active");
});

// ── Enter chat ─────────────────────────────────────────────────────────────
function enterChat() {
  $("auth-screen").classList.remove("active");
  $("chat-screen").classList.add("active");
  $("me-letter").textContent = avatarLetter(state.username);
  $("me-username").textContent = state.username;
  $("me-avatar").style.background = avatarColor(state.username);
  loadUsers();
  loadRooms();
  connectWS();
}

// ── Rooms ──────────────────────────────────────────────────────────────────
async function loadRooms() {
  try {
    const res = await fetch(`${CHAT_URL}/rooms?token=${state.token}`);
    const rooms = await res.json();
    state.rooms = rooms;
    renderRoomList();
    if (rooms.length) selectTarget("room", rooms[0].name, rooms[0].name);
  } catch(e) { console.error(e); }
}

function renderRoomList() {
  const list = $("rooms-list");
  list.innerHTML = "";
  (state.rooms || []).forEach(r => {
    const key = convKey("room", r.name);
    const unread = state.unread[key] || 0;
    const div = document.createElement("div");
    div.className = "nav-item";
    div.dataset.type = "room";
    div.dataset.id   = r.name;
    div.dataset.name = r.name;
    div.innerHTML = `
      <span class="nav-hash">#</span>
      <span class="nav-label">${esc(r.name)}</span>
      ${unread ? `<span class="unread-badge">${unread}</span>` : ""}`;
    div.addEventListener("click", () => selectTarget("room", r.name, r.name));
    list.appendChild(div);
  });
}

// ── Create Room modal ───────────────────────────────────────────────────────
$("create-room-btn").addEventListener("click", () => {
  $("room-name-input").value = "";
  $("room-error").textContent = "";
  $("modal-overlay").style.display = "flex";
  $("room-name-input").focus();
});

$("modal-cancel").addEventListener("click", () => {
  $("modal-overlay").style.display = "none";
});

$("modal-overlay").addEventListener("click", e => {
  if (e.target === $("modal-overlay")) $("modal-overlay").style.display = "none";
});

$("create-room-form").addEventListener("submit", async e => {
  e.preventDefault();
  $("room-error").textContent = "";
  const name = $("room-name-input").value.trim();
  try {
    const res = await fetch(`${CHAT_URL}/rooms?token=${state.token}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Erro ao criar sala");
    $("modal-overlay").style.display = "none";
    await loadRooms();
    selectTarget("room", data.name, data.name);
  } catch(err) { $("room-error").textContent = err.message; }
});

// ── Delete account ─────────────────────────────────────────────────────────
$("delete-account-btn").addEventListener("click", async () => {
  if (!confirm("Tem certeza? Sua conta será desativada permanentemente.")) return;
  try {
    const res = await fetch(`${AUTH_URL}/users/me`, {
      method: "DELETE",
      headers: {Authorization: `Bearer ${state.token}`},
    });
    if (!res.ok) { const d = await res.json(); throw new Error(d.detail); }
    if (state.ws) state.ws.close();
    clearTimeout(state.reconnectTimer);
    sessionStorage.clear();
    Object.assign(state, {token:null,userId:null,username:null,ws:null,activeTarget:null,users:[],rooms:[],unread:{}});
    $("auth-screen").classList.add("active");
    $("chat-screen").classList.remove("active");
    setAuthError("Conta excluída. Obrigado por usar o Nexus Chat.", "#10B981");
  } catch(err) { alert(err.message); }
});

// ── Users ──────────────────────────────────────────────────────────────────
async function loadUsers() {
  try {
    const res = await fetch(`${AUTH_URL}/users`, {headers:{Authorization:`Bearer ${state.token}`}});
    const users = await res.json();
    state.users = users.filter(u => u.id !== state.userId);
    renderDMList();
    $("dm-section").style.display = state.users.length ? "" : "none";
  } catch(e) { console.error(e); }
}

function renderDMList(filter="") {
  const list = $("dm-list");
  list.innerHTML = "";
  const shown = filter ? state.users.filter(u => u.username.toLowerCase().includes(filter)) : state.users;
  shown.forEach(u => {
    const key = convKey("dm", u.id);
    const unread = state.unread[key] || 0;
    const div = document.createElement("div");
    div.className = "nav-item";
    div.dataset.type = "dm";
    div.dataset.id   = u.id;
    div.dataset.name = u.username;
    div.innerHTML = `
      <div class="dm-avatar" style="background:${avatarColor(u.username)}">${avatarLetter(u.username)}</div>
      <span class="nav-label">${esc(u.username)}</span>
      ${unread ? `<span class="unread-badge">${unread}</span>` : ""}`;
    div.addEventListener("click", () => selectTarget("dm", u.id, u.username));
    list.appendChild(div);
  });
}

$("search-users").addEventListener("input", e => renderDMList(e.target.value.toLowerCase()));

// ── Select target ──────────────────────────────────────────────────────────
function selectTarget(type, id, name) {
  state.activeTarget = {type, id, name};
  const key = convKey(type, id);
  state.unread[key] = 0;

  // Highlight nav
  document.querySelectorAll(".nav-item").forEach(el => {
    el.classList.toggle("active", el.dataset.type === type && String(el.dataset.id) === String(id));
  });
  renderDMList($("search-users").value.toLowerCase());

  // Topbar
  const isRoom = type === "room";
  const topAvatar = $("topbar-avatar");
  topAvatar.textContent = isRoom ? "#" : avatarLetter(name);
  topAvatar.style.background = isRoom ? "#334155" : avatarColor(name);
  $("topbar-name").textContent = isRoom ? `# ${name}` : name;
  $("topbar-sub").textContent  = isRoom ? "canal público" : "mensagem direta";

  // Show view
  $("empty-state").style.display = "none";
  const view = $("chat-view");
  view.style.display = "flex";
  $("messages-container").innerHTML = "";
  lastRenderedDate = null;

  if (type === "dm") loadPrivateMsgs(id);
  else loadRoomMsgs(id);
}


// ── Load history ───────────────────────────────────────────────────────────
async function loadRoomMsgs(room) {
  try {
    const r = await fetch(`${CHAT_URL}/messages?room_id=${room}&token=${state.token}&limit=60`);
    const msgs = await r.json();
    msgs.reverse().forEach(appendMsg);
    scrollBottom();
  } catch(e) { console.error(e); }
}

async function loadPrivateMsgs(otherId) {
  try {
    const r = await fetch(`${CHAT_URL}/messages/private/${otherId}?token=${state.token}&limit=60`);
    const msgs = await r.json();
    msgs.forEach(appendMsg);
    scrollBottom();
  } catch(e) { console.error(e); }
}

// ── WebSocket ──────────────────────────────────────────────────────────────
function connectWS() {
  const url = `${WS_BASE}/${state.userId}?token=${state.token}`;
  state.ws = new WebSocket(url);
  state.ws.onopen  = () => setDot(true);
  state.ws.onclose = () => { setDot(false); state.reconnectTimer = setTimeout(connectWS, 3000); };
  state.ws.onerror = () => setDot(false);
  state.ws.onmessage = ({data}) => {
    const msg = JSON.parse(data);
    if (msg.type === "system") { appendSys(msg.content); return; }

    const at  = state.activeTarget;
    const priv = msg.is_private;
    const inActive = at && (
      (priv && at.type === "dm" && (String(at.id) === String(msg.sender_id) || String(at.id) === String(msg.recipient_id) || msg.sender_id === state.userId))
      ||
      (!priv && at.type === "room" && (!msg.room_id || msg.room_id === at.id))
    );

    if (inActive) { appendMsg(msg); scrollBottom(); }
    else {
      const key = priv
        ? convKey("dm", msg.sender_id === state.userId ? msg.recipient_id : msg.sender_id)
        : convKey("room", msg.room_id || "geral");
      state.unread[key] = (state.unread[key]||0) + 1;
      renderDMList($("search-users").value.toLowerCase());
      updateRoomBadges();
    }
  };
}

function setDot(on) {
  const dot = $("ws-dot");
  dot.className = `ws-dot ${on?"on":"off"}`;
  $("topbar-sub").textContent = on
    ? (state.activeTarget?.type === "room" ? "canal público" : "online")
    : "reconectando…";
}

// ── Send ───────────────────────────────────────────────────────────────────
function doSend() {
  const input   = $("msg-input");
  const content = input.value.trim();
  if (!content || !state.ws || state.ws.readyState !== WebSocket.OPEN || !state.activeTarget) return;
  const at = state.activeTarget;
  const p  = {content};
  if (at.type === "dm") p.recipient_id = at.id; else p.room_id = at.id;
  state.ws.send(JSON.stringify(p));
  input.value = "";
}

$("msg-form").addEventListener("submit", e => { e.preventDefault(); doSend(); });
$("send-btn").addEventListener("click", doSend);
$("msg-input").addEventListener("keydown", e => { if (e.key==="Enter"&&!e.shiftKey){e.preventDefault();doSend();} });

// ── Render ─────────────────────────────────────────────────────────────────
let lastRenderedDate = null;

function appendMsg(msg) {
  const c    = $("messages-container");
  const isOut = msg.sender_id === state.userId;
  const ts    = msg.created_at || msg.timestamp || new Date().toISOString();
  const dStr  = fmtDate(ts);
  const at    = state.activeTarget;
  const isRoom = at?.type === "room";

  if (dStr !== lastRenderedDate) {
    lastRenderedDate = dStr;
    const chip = document.createElement("div");
    chip.className = "date-chip";
    chip.innerHTML = `<span>${dStr}</span>`;
    c.appendChild(chip);
  }

  const row = document.createElement("div");
  row.className = `mrow ${isOut ? "out" : "in"}`;

  // Row avatar (only in rooms for incoming)
  const showAvatar = isRoom && !isOut;
  const avatarHtml = showAvatar
    ? `<div class="row-avatar" style="background:${avatarColor(msg.sender_username)}">${avatarLetter(msg.sender_username)}</div>`
    : "";

  row.innerHTML = `
    ${avatarHtml}
    <div class="bubble">
      ${isRoom && !isOut ? `<span class="bubble-sender" style="color:${avatarColor(msg.sender_username)}">${esc(msg.sender_username)}</span>` : ""}
      <span>${esc(msg.content)}</span>
      <div class="bubble-meta">
        <span class="bubble-time">${fmtTime(ts)}</span>
        ${isOut ? '<span class="tick">✓✓</span>' : ""}
      </div>
    </div>`;
  c.appendChild(row);
}

function appendSys(text) {
  const div = document.createElement("div");
  div.className = "sys-msg";
  div.textContent = text;
  $("messages-container").appendChild(div);
}

function scrollBottom() {
  const c = $("messages-container"); c.scrollTop = c.scrollHeight;
}

function updateRoomBadges() {
  $("rooms-list").querySelectorAll(".nav-item[data-type='room']").forEach(el => {
    const key = convKey("room", el.dataset.id);
    const n   = state.unread[key] || 0;
    let badge = el.querySelector(".unread-badge");
    if (n && state.activeTarget?.id !== el.dataset.id) {
      if (!badge) { badge = document.createElement("span"); badge.className="unread-badge"; el.appendChild(badge); }
      badge.textContent = n;
    } else if (badge) badge.remove();
  });
}

// ── Restore session ────────────────────────────────────────────────────────
(function() {
  const token    = sessionStorage.getItem("token");
  const userId   = sessionStorage.getItem("userId");
  const username = sessionStorage.getItem("username");
  if (token && userId && username) {
    Object.assign(state, {token, userId:parseInt(userId), username});
    enterChat();
  }
})();
