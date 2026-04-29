const NAV_ITEMS = [
  ["dashboard", "Dashboard", "dashboard.html"],
  ["notes", "Notes", "notes.html"],
  ["planner", "Planner", "planner.html"],
  ["assistant", "AI Assistant", "assistant.html"],
  ["quiz", "Quiz", "quiz.html"],
  ["flashcards", "Flashcards", "flashcards.html"],
  ["progress", "Progress", "progress.html"],
  ["resources", "Resources", "resources.html"],
  ["chat", "Terminal Chat", "chat.html", "_blank"],
  ["settings", "Settings", "settings.html"]
];

const API_URL = "https://bot.kaungkhantko.top/api/chat";
const CLIENT_ID_KEY = "mentor_client_id";
const page = document.body.dataset.page || "dashboard";
const cfg = window.MENTOR_SUPABASE || {};
const supabase = window.supabase && cfg.url && cfg.anonKey
  ? window.supabase.createClient(cfg.url, cfg.anonKey)
  : null;
const authRedirectUrl = `${window.location.origin}${window.location.pathname.replace(/[^/]*$/, "")}auth.html`;

let session = null;
let user = null;
let profile = null;
let cache = { notes: [], tasks: [], sessions: [], flashcards: [], quizzes: [], resources: [], aiChats: [] };
let channel = null;
let editingNoteId = null;

const todayIso = () => new Date().toISOString().slice(0, 10);
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderMarkdown(value) {
  return escapeHtml(value)
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h2>$1</h2>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/^- (.*)$/gm, "<br>• $1")
    .replace(/\n/g, "<br>");
}

function clientId() {
  const existing = localStorage.getItem(CLIENT_ID_KEY);
  if (existing) return existing;
  const generated = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  localStorage.setItem(CLIENT_ID_KEY, generated);
  return generated;
}

function toast(message) {
  const node = $("#toast");
  if (!node) return;
  node.textContent = message;
  node.classList.remove("hidden");
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => node.classList.add("hidden"), 3600);
}

function moneyDate(value) {
  if (!value) return "Today";
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function requireSupabaseMessage() {
  return `
    <article class="card full">
      <h2>Supabase setup required</h2>
      <p class="muted">Add GitHub Pages secrets <code>SUPABASE_URL</code> and <code>SUPABASE_ANON_KEY</code>, then run the SQL in <code>supabase.sql</code>. After that, login, signup, realtime stats, and all data features will work.</p>
    </article>`;
}

async function initAuth() {
  if (!supabase) return;
  const result = await supabase.auth.getSession();
  session = result.data.session;
  user = session && session.user;
  supabase.auth.onAuthStateChange((_event, nextSession) => {
    session = nextSession;
    user = nextSession && nextSession.user;
    if (!user && page !== "login" && $("#app")) window.location.href = "login.html";
  });
}

function authErrorMessage(error) {
  if (!error) return "Authentication failed. Try again.";
  const message = error.message || String(error);
  if (message.toLowerCase().includes("email not confirmed")) {
    return "Email is not confirmed yet. Check your inbox or resend the confirmation email.";
  }
  if (message.toLowerCase().includes("invalid login")) {
    return "Email or password is incorrect. If you just signed up, confirm your email first.";
  }
  return message;
}

async function ensureProfile() {
  if (!supabase || !user) return null;
  const existing = await supabase.from("profiles").select("*").eq("id", user.id).maybeSingle();
  if (existing.error) throw existing.error;
  if (existing.data) {
    profile = existing.data;
    return profile;
  }
  const name = user.user_metadata && user.user_metadata.name ? user.user_metadata.name : "Kaung";
  const inserted = await supabase.from("profiles").insert({ id: user.id, email: user.email, name }).select().single();
  if (inserted.error) throw inserted.error;
  profile = inserted.data;
  return profile;
}

async function fetchAll() {
  if (!supabase || !user) return cache;
  const [notes, tasks, sessionsResult, cards, quizzes, resources, chats] = await Promise.all([
    supabase.from("notes").select("*").eq("user_id", user.id).order("pinned", { ascending: false }).order("updated_at", { ascending: false }),
    supabase.from("tasks").select("*").eq("user_id", user.id).order("due_date", { ascending: true }),
    supabase.from("study_sessions").select("*").eq("user_id", user.id).order("created_at", { ascending: false }),
    supabase.from("flashcards").select("*").eq("user_id", user.id).order("updated_at", { ascending: false }),
    supabase.from("quizzes").select("*").eq("user_id", user.id).order("created_at", { ascending: false }),
    supabase.from("resources").select("*").order("category", { ascending: true }),
    supabase.from("ai_chats").select("*").eq("user_id", user.id).order("created_at", { ascending: false }).limit(20)
  ]);
  for (const result of [notes, tasks, sessionsResult, cards, quizzes, resources, chats]) {
    if (result.error) throw result.error;
  }
  cache = {
    notes: notes.data || [],
    tasks: tasks.data || [],
    sessions: sessionsResult.data || [],
    flashcards: cards.data || [],
    quizzes: quizzes.data || [],
    resources: resources.data || [],
    aiChats: chats.data || []
  };
  return cache;
}

function subscribeRealtime(onChange) {
  if (!supabase || !user || channel) return;
  channel = supabase.channel(`mentor-user-${user.id}`)
    .on("postgres_changes", { event: "*", schema: "public", table: "notes", filter: `user_id=eq.${user.id}` }, onChange)
    .on("postgres_changes", { event: "*", schema: "public", table: "tasks", filter: `user_id=eq.${user.id}` }, onChange)
    .on("postgres_changes", { event: "*", schema: "public", table: "study_sessions", filter: `user_id=eq.${user.id}` }, onChange)
    .on("postgres_changes", { event: "*", schema: "public", table: "flashcards", filter: `user_id=eq.${user.id}` }, onChange)
    .on("postgres_changes", { event: "*", schema: "public", table: "quizzes", filter: `user_id=eq.${user.id}` }, onChange)
    .on("postgres_changes", { event: "*", schema: "public", table: "ai_chats", filter: `user_id=eq.${user.id}` }, onChange)
    .subscribe();
}

function renderShell(title, subtitle) {
  const app = $("#app");
  if (!app) return;
  app.innerHTML = `
    <aside class="sidebar">
      <div class="brand">
        <strong>MENTOR</strong>
        <span>terminal student workspace</span>
      </div>
      <nav class="nav" aria-label="Main navigation">
        ${NAV_ITEMS.map(([id, label, href, target]) => `<a class="${id === page ? "active" : ""}" href="${href}" ${target ? `target="${target}" rel="noopener"` : ""}>${label}</a>`).join("")}
      </nav>
    </aside>
    <main class="main">
      <div class="topline">
        <div class="window-dots"><span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span></div>
        <span class="muted">root@mentor:~/${page}# ${user ? escapeHtml(user.email) : "guest"}</span>
      </div>
      <section class="page-title">
        <h1>${title}</h1>
        <p>${subtitle}</p>
      </section>
      <section id="content">${supabase ? '<article class="card full"><p class="muted">Loading realtime data...</p></article>' : requireSupabaseMessage()}</section>
    </main>
    <form id="commandForm" class="command-bar" autocomplete="off">
      <label class="prompt" for="command">root@mentor:~#</label>
      <input id="command" name="command" type="text" placeholder="help, dashboard, notes, new note, tasks, timer, ask, quiz, flashcards, chat, settings">
      <button type="submit">run</button>
    </form>
    <div id="toast" class="toast hidden" role="status"></div>
  `;
  $("#commandForm").addEventListener("submit", handleCommand);
}

async function boot(title, subtitle, render) {
  renderShell(title, subtitle);
  if (!supabase) return;
  try {
    await initAuth();
    if (!user) {
      window.location.href = "login.html";
      return;
    }
    await ensureProfile();
    await fetchAll();
    render();
    subscribeRealtime(async () => {
      await fetchAll();
      render();
    });
  } catch (error) {
    $("#content").innerHTML = `
      <article class="card full">
        <h2>Setup issue</h2>
        <p class="muted">${escapeHtml(error.message || String(error))}</p>
        <p class="muted">Make sure <code>supabase.sql</code> has been run and email auth is enabled in Supabase.</p>
      </article>`;
  }
}

function stats() {
  const totalMinutes = cache.sessions.reduce((sum, item) => sum + Number(item.minutes || 0), 0);
  const todayMinutes = cache.sessions.filter((item) => String(item.session_date).slice(0, 10) === todayIso()).reduce((sum, item) => sum + Number(item.minutes || 0), 0);
  const completedTasks = cache.tasks.filter((task) => task.done).length;
  const tasksLeft = cache.tasks.filter((task) => !task.done).length;
  const known = cache.flashcards.filter((card) => card.known).length;
  const xp = Number(profile && profile.xp ? profile.xp : 0) + totalMinutes + completedTasks * 10 + known * 5;
  return {
    totalMinutes,
    todayMinutes,
    tasksLeft,
    streak: Number(profile && profile.streak ? profile.streak : 0),
    level: Math.max(1, Math.floor(xp / 300) + 1),
    xp,
    flashcardAccuracy: cache.flashcards.length ? Math.round((known / cache.flashcards.length) * 100) : 0,
    quizAverage: cache.quizzes.length ? Math.round(cache.quizzes.reduce((sum, quiz) => sum + Number(quiz.score || 0), 0) / cache.quizzes.length) : 0
  };
}

function dashboard() {
  boot("Welcome back, Kaung", "Realtime study command center with live goals, tasks, notes, XP, and AI help.", () => {
    const s = stats();
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card"><h2>Today’s Study Goal</h2><span class="metric">${Math.round(s.todayMinutes / 60 * 10) / 10}h / 2h</span><div class="progress-track"><div class="progress-fill" style="--value:${Math.min(100, s.todayMinutes / 120 * 100)}%"></div></div></article>
        <article class="card"><h2>Current Streak</h2><span class="metric">${s.streak} days</span><p class="muted">Updates from your profile row</p></article>
        <article class="card"><h2>Tasks Left</h2><span class="metric">${s.tasksLeft}</span><p class="muted">Realtime from Supabase tasks</p></article>
        <article class="card wide"><h2>Today’s tasks</h2><ul class="list">${cache.tasks.slice(0, 5).map(taskRow).join("") || "<li>No tasks yet.</li>"}</ul></article>
        <article class="card"><h2>Pomodoro timer</h2><div class="timer-display">25:00</div><div class="actions"><button data-cmd="timer">Start</button><button class="secondary" data-cmd="planner">Plan</button></div></article>
        <article class="card"><h2>XP / Level</h2><span class="metric">Lv ${s.level}</span><div class="progress-track"><div class="progress-fill" style="--value:${s.xp % 300 / 300 * 100}%"></div></div><p class="muted">${s.xp} XP</p></article>
        <article class="card"><h2>Recent notes</h2><ul class="list">${cache.notes.slice(0, 2).map(noteItem).join("") || "<li>No notes yet.</li>"}</ul></article>
        <article class="card wide"><h2>Quick AI ask</h2><textarea id="quickAsk" placeholder="Explain OSI model simply"></textarea><div class="actions"><button data-quick-ai="Explain Mode">Explain</button><button data-quick-ai="Quiz Mode">Quiz</button><button data-quick-ai="Roadmap Mode">Roadmap</button></div></article>
      </div>`;
    wireButtons();
    wireQuickAi();
  });
}

function taskRow(task) {
  return `<li><label><input type="checkbox" data-task-done="${task.id}" ${task.done ? "checked" : ""}> <strong>${escapeHtml(task.title)}</strong></label><br><span class="muted">${escapeHtml(task.priority || "Normal")} priority ${task.due_date ? ` · due ${moneyDate(task.due_date)}` : ""}</span></li>`;
}

function noteItem(note) {
  const tags = Array.isArray(note.tags) ? note.tags : [];
  return `<li><strong>${note.pinned ? "Pinned: " : ""}${escapeHtml(note.title)}</strong><br><span class="muted">Updated: ${moneyDate(note.updated_at)}</span><div class="tag-row">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div></li>`;
}

function notes() {
  boot("Smart Notes", "Realtime markdown notes with tags, search, pin, edit, delete, and AI actions.", () => {
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card full">
          <form id="noteForm" class="form-grid">
            <input id="noteSearch" placeholder="Search notes" type="search">
            <input id="noteTags" placeholder="Tags: Linux, Exam">
            <input id="noteTitle" class="full" placeholder="Note title" required>
            <textarea id="noteContent" class="full" placeholder="Markdown supported: ## Heading, - list, **important**"></textarea>
            <label class="check"><input id="notePinned" type="checkbox"> Pin important note</label>
            <button id="noteSubmit">Create note</button>
            <button id="cancelEdit" type="button" class="secondary hidden">Cancel edit</button>
          </form>
        </article>
        <div id="notesList" class="grid full"></div>
      </div>`;
    const renderNotes = () => {
      const query = ($("#noteSearch").value || "").toLowerCase();
      $("#notesList").innerHTML = cache.notes.filter((note) => `${note.title} ${note.content} ${(note.tags || []).join(" ")}`.toLowerCase().includes(query)).map((note) => `
        <article class="card note-card">
          <h2>${note.pinned ? "Pinned: " : ""}${escapeHtml(note.title)}</h2>
          <p class="muted">Updated: ${moneyDate(note.updated_at)}</p>
          <div>${renderMarkdown(note.content)}</div>
          <div class="tag-row">${(note.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
          <div class="actions">
            <button data-note-ai="Summary Mode" data-note="${note.id}">Summarize</button>
            <button data-note-ai="Quiz Mode" data-note="${note.id}">Quiz</button>
            <button data-note-ai="Flashcard Mode" data-note="${note.id}">Flashcards</button>
            <button class="secondary" data-edit-note="${note.id}">Edit</button>
            <button class="secondary" data-pin-note="${note.id}">${note.pinned ? "Unpin" : "Pin"}</button>
            <button class="secondary" data-delete-note="${note.id}">Delete</button>
          </div>
        </article>`).join("") || '<article class="card full"><p class="muted">No matching notes.</p></article>';
      wireNoteButtons();
    };
    $("#noteForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const payload = {
        title: $("#noteTitle").value.trim(),
        content: $("#noteContent").value.trim(),
        tags: $("#noteTags").value.split(",").map((tag) => tag.trim()).filter(Boolean),
        pinned: $("#notePinned").checked
      };
      if (editingNoteId) {
        await supabase.from("notes").update(payload).eq("id", editingNoteId).eq("user_id", user.id);
        editingNoteId = null;
        $("#noteSubmit").textContent = "Create note";
        $("#cancelEdit").classList.add("hidden");
      } else {
        await supabase.from("notes").insert({ ...payload, user_id: user.id });
      }
      event.target.reset();
      toast("Note saved");
    });
    $("#cancelEdit").addEventListener("click", () => {
      editingNoteId = null;
      $("#noteForm").reset();
      $("#noteSubmit").textContent = "Create note";
      $("#cancelEdit").classList.add("hidden");
    });
    $("#noteSearch").addEventListener("input", renderNotes);
    renderNotes();
  });
}

function wireNoteButtons() {
  $$("[data-delete-note]").forEach((button) => button.addEventListener("click", async () => {
    await supabase.from("notes").delete().eq("id", button.dataset.deleteNote).eq("user_id", user.id);
    toast("Note deleted");
  }));
  $$("[data-pin-note]").forEach((button) => button.addEventListener("click", async () => {
    const note = cache.notes.find((item) => item.id === button.dataset.pinNote);
    await supabase.from("notes").update({ pinned: !note.pinned }).eq("id", note.id).eq("user_id", user.id);
  }));
  $$("[data-edit-note]").forEach((button) => button.addEventListener("click", () => {
    const note = cache.notes.find((item) => item.id === button.dataset.editNote);
    if (!note) return;
    editingNoteId = note.id;
    $("#noteTitle").value = note.title || "";
    $("#noteContent").value = note.content || "";
    $("#noteTags").value = (note.tags || []).join(", ");
    $("#notePinned").checked = Boolean(note.pinned);
    $("#noteSubmit").textContent = "Save changes";
    $("#cancelEdit").classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }));
  $$("[data-note-ai]").forEach((button) => button.addEventListener("click", async () => {
    const note = cache.notes.find((item) => item.id === button.dataset.note);
    const reply = await askAi(`${note.title}\n${note.content}`, button.dataset.noteAi);
    await supabase.from("ai_chats").insert({ user_id: user.id, mode: button.dataset.noteAi, prompt: note.title, response: reply });
    toast("AI result saved in Assistant history");
  }));
}

function planner() {
  boot("Study Planner", "Realtime subject planner, deadline tracker, weekly schedule, and task priority.", () => {
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card full">
          <form id="taskForm" class="form-grid">
            <input id="taskTitle" placeholder="Task title" required>
            <input id="taskSubject" placeholder="Subject">
            <select id="taskPriority"><option>High</option><option>Medium</option><option>Low</option></select>
            <input id="taskDue" type="date">
            <button>Add task</button>
          </form>
        </article>
        <article class="card wide"><h2>Weekly schedule</h2><ul class="list">${cache.tasks.map(taskRow).join("") || "<li>No planned tasks yet.</li>"}</ul></article>
        <article class="card"><h2>Next Exam</h2><span class="metric">${nextExamText()}</span><p class="muted">Based on earliest high priority deadline</p></article>
      </div>`;
    $("#taskForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      await supabase.from("tasks").insert({ user_id: user.id, title: $("#taskTitle").value.trim(), subject: $("#taskSubject").value.trim(), priority: $("#taskPriority").value, due_date: $("#taskDue").value || null });
      event.target.reset();
    });
    wireTaskChecks();
  });
}

function nextExamText() {
  const next = cache.tasks.filter((task) => task.due_date && !task.done).sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)))[0];
  if (!next) return "No deadline";
  const days = Math.ceil((new Date(next.due_date) - new Date(todayIso())) / 86400000);
  return `${next.subject || next.title} - ${Math.max(0, days)} days`;
}

function wireTaskChecks() {
  $$("[data-task-done]").forEach((box) => box.addEventListener("change", async () => {
    await supabase.from("tasks").update({ done: box.checked }).eq("id", box.dataset.taskDone).eq("user_id", user.id);
  }));
}

function assistant() {
  boot("AI Study Assistant", "Live AI modes with saved chat history in Supabase.", () => {
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card full"><div class="mode-row">${["Explain Mode", "Quiz Mode", "Summary Mode", "Flashcard Mode", "Roadmap Mode", "Exam Prep Mode"].map((mode) => `<button data-mode="${mode}">${mode}</button>`).join("")}</div></article>
        <article class="card wide"><h2 id="assistantMode">Explain Mode</h2><textarea id="assistantPrompt" placeholder="Explain OSI model simply"></textarea><div class="actions"><button id="assistantRun">Ask AI</button><button class="secondary" data-cmd="quiz">Make quiz</button></div></article>
        <article class="card"><h2>Output</h2><p id="assistantOutput" class="muted">Ask anything. The answer is saved to ai_chats.</p></article>
        <article class="card full"><h2>Recent AI chats</h2><ul class="list">${cache.aiChats.map((chat) => `<li><strong>${escapeHtml(chat.mode)}</strong><br>${escapeHtml(chat.prompt)}<br><span class="muted">${escapeHtml((chat.response || "").slice(0, 180))}</span></li>`).join("") || "<li>No chats yet.</li>"}</ul></article>
      </div>`;
    $$("[data-mode]").forEach((button) => button.addEventListener("click", () => $("#assistantMode").textContent = button.dataset.mode));
    $("#assistantRun").addEventListener("click", async () => {
      const mode = $("#assistantMode").textContent;
      const prompt = $("#assistantPrompt").value.trim();
      if (!prompt) return toast("Type a study question first");
      $("#assistantOutput").textContent = "Running AI assistant...";
      const reply = await askAi(prompt, mode);
      $("#assistantOutput").textContent = reply;
      await supabase.from("ai_chats").insert({ user_id: user.id, mode, prompt, response: reply });
    });
    wireButtons();
  });
}

async function askAi(message, mode = "Explain Mode") {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: `[${mode}] ${message}`, client_id: clientId(), language: "default" })
  });
  if (!response.ok) throw new Error("AI request failed");
  const data = await response.json();
  return data.reply || data.message || "No reply returned.";
}

function timerPage() {
  boot("Pomodoro Focus", "Real completed focus sessions are saved to Supabase and update XP/progress live.", () => {
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card wide"><h2>Focus timer</h2><div id="timer" class="timer-display">25:00</div><div class="actions"><button id="startTimer">Start 25</button><button id="breakTimer" class="secondary">5 min break</button><button id="longBreak" class="secondary">Long break</button><label class="check"><input id="music" type="checkbox"> Focus music</label></div></article>
        <article class="card"><h2>Saved sessions</h2><span class="metric">${cache.sessions.length}</span><p class="muted">${stats().totalMinutes} total minutes</p></article>
      </div>`;
    let remaining = 1500;
    let interval;
    const draw = () => $("#timer").textContent = `${String(Math.floor(remaining / 60)).padStart(2, "0")}:${String(remaining % 60).padStart(2, "0")}`;
    const start = (seconds) => {
      clearInterval(interval);
      remaining = seconds;
      draw();
      interval = setInterval(async () => {
        remaining -= 1;
        draw();
        if (remaining <= 0) {
          clearInterval(interval);
          await supabase.from("study_sessions").insert({ user_id: user.id, minutes: Math.round(seconds / 60), session_date: todayIso(), kind: seconds >= 1500 ? "focus" : "break" });
          toast(`Great work! +${seconds >= 1500 ? 20 : 5} XP. Focus time saved.`);
        }
      }, 1000);
    };
    $("#startTimer").addEventListener("click", () => start(1500));
    $("#breakTimer").addEventListener("click", () => start(300));
    $("#longBreak").addEventListener("click", () => start(900));
  });
}

function flashcards() {
  boot("Flashcards", "Realtime flashcards with known and not known review tracking.", () => {
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card full"><form id="cardForm" class="form-grid"><input id="cardQ" placeholder="Question" required><input id="cardA" placeholder="Answer" required><button>Add flashcard</button><button class="secondary" type="button" id="aiCards">AI generate from Python loops</button></form></article>
        ${cache.flashcards.map((card) => `<article class="card"><h2>Q: ${escapeHtml(card.question)}</h2><p class="flashcard-face">A: ${escapeHtml(card.answer)}</p><div class="actions"><button data-card-known="${card.id}">Known</button><button class="secondary" data-card-unknown="${card.id}">Not Known</button></div></article>`).join("") || '<article class="card full"><p class="muted">No flashcards yet.</p></article>'}
      </div>`;
    $("#cardForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      await supabase.from("flashcards").insert({ user_id: user.id, question: $("#cardQ").value.trim(), answer: $("#cardA").value.trim(), known: false });
      event.target.reset();
    });
    $("#aiCards").addEventListener("click", async () => {
      const reply = await askAi("Make 5 flashcards for Python loops. Format as Q: ... A: ...", "Flashcard Mode");
      await supabase.from("ai_chats").insert({ user_id: user.id, mode: "Flashcard Mode", prompt: "Python loops flashcards", response: reply });
      toast("AI flashcards saved in Assistant history");
    });
    $$("[data-card-known], [data-card-unknown]").forEach((button) => button.addEventListener("click", async () => {
      const id = button.dataset.cardKnown || button.dataset.cardUnknown;
      await supabase.from("flashcards").update({ known: Boolean(button.dataset.cardKnown), next_review_at: new Date(Date.now() + 86400000).toISOString() }).eq("id", id).eq("user_id", user.id);
    }));
  });
}

function quiz() {
  boot("Quiz Generator", "Generate quizzes from notes or topics and save real score history.", () => {
    const last = cache.quizzes[0];
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card wide"><h2>Create quiz</h2><textarea id="quizTopic" placeholder="Firewall rules or Linux commands"></textarea><div class="actions"><button id="makeQuiz">Generate quiz</button><button id="saveScore" class="secondary">Save score 8/10</button></div></article>
        <article class="card"><h2>Latest score</h2><span class="metric">${last ? `${last.score}%` : "0%"}</span><p class="muted">Weak topic: ${escapeHtml(last ? last.weak_topic || "None" : "None yet")}</p></article>
        <article class="card full"><h2>Preview</h2><ul id="quizPreview" class="list"><li>Generate a quiz to see questions here.</li></ul></article>
      </div>`;
    $("#makeQuiz").addEventListener("click", async () => {
      const topic = $("#quizTopic").value.trim() || "Networking";
      const reply = await askAi(`Create a mixed quiz for ${topic}`, "Quiz Mode");
      $("#quizPreview").innerHTML = `<li>${escapeHtml(reply)}</li>`;
      await supabase.from("ai_chats").insert({ user_id: user.id, mode: "Quiz Mode", prompt: topic, response: reply });
    });
    $("#saveScore").addEventListener("click", async () => {
      await supabase.from("quizzes").insert({ user_id: user.id, topic: $("#quizTopic").value.trim() || "Networking", score: 80, total_questions: 10, weak_topic: "Firewall rules", suggested_review: "Network Security" });
      toast("Quiz score saved");
    });
  });
}

function progress() {
  boot("Progress Tracker", "Realtime progress from study sessions, completed tasks, quiz scores, and flashcard accuracy.", () => {
    const s = stats();
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card"><h2>Study hours</h2><span class="metric">${Math.round(s.totalMinutes / 60 * 10) / 10}h</span></article>
        <article class="card"><h2>Quiz average</h2><span class="metric">${s.quizAverage}%</span></article>
        <article class="card"><h2>Flashcard accuracy</h2><span class="metric">${s.flashcardAccuracy}%</span></article>
        <article class="card wide"><h2>Weekly study time</h2><div class="chart">${weeklyBars()}</div></article>
        <article class="card"><h2>Weak subjects</h2><ul class="list">${cache.quizzes.slice(0, 4).map((quiz) => `<li>${escapeHtml(quiz.weak_topic || quiz.topic)}</li>`).join("") || "<li>No weak subjects yet.</li>"}</ul></article>
      </div>`;
  });
}

function weeklyBars() {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const totals = Object.fromEntries(days.map((day) => [day, 0]));
  cache.sessions.forEach((item) => {
    const day = days[new Date(item.session_date || item.created_at).getDay()];
    totals[day] += Number(item.minutes || 0);
  });
  return days.map((day) => `<div class="bar"><span style="height:${Math.max(20, totals[day])}px"></span><span>${day}</span></div>`).join("");
}

function resources() {
  boot("Student Resource Hub", "Realtime library resources from Supabase.", () => {
    const fallback = [
      ["Programming", "Python loops, data structures, and project practice", "Beginner", 45],
      ["Cyber Security", "Networking, firewall rules, and Linux hardening", "Intermediate", 60],
      ["AI", "Prompting, model basics, and study automation", "Beginner", 35],
      ["English / IELTS", "Writing practice and vocabulary review", "Intermediate", 50],
      ["Linux", "Commands, permissions, services, and logs", "Beginner", 40],
      ["Web Development", "HTML, CSS, JavaScript, deploy workflow", "Beginner", 70],
      ["University Assignments", "Research, outlines, citations, and presentation prep", "All levels", 30]
    ].map(([category, description, difficulty, estimated_minutes]) => ({ title: category, category, description, difficulty, estimated_minutes }));
    const items = cache.resources.length ? cache.resources : fallback;
    $("#content").innerHTML = `<div class="grid">${items.map((item) => `<article class="card resource"><h2>${escapeHtml(item.title)}</h2><p>${escapeHtml(item.description)}</p><div class="tag-row"><span class="tag">${escapeHtml(item.difficulty)}</span><span class="tag">${item.estimated_minutes} min</span></div><button data-cmd="planner">Start</button></article>`).join("")}</div>`;
    wireButtons();
  });
}

function settings() {
  boot("Settings", "Profile, theme, language, and account controls.", () => {
    $("#content").innerHTML = `
      <div class="grid">
        <article class="card"><h2>Profile</h2><form id="profileForm" class="form-grid"><input id="profileName" value="${escapeHtml(profile.name || "")}" placeholder="Name"><select id="language"><option value="en">English</option><option value="my">Burmese</option></select><button>Save profile</button></form></article>
        <article class="card"><h2>Theme</h2><select id="theme"><option value="kali">Kali</option><option value="matrix">Matrix</option><option value="cyberpunk">Cyberpunk</option></select><button id="logout" class="secondary">Logout</button></article>
        <article class="card full"><h2>Realtime database</h2><p class="muted">Connected tables: profiles, notes, tasks, study_sessions, flashcards, quizzes, resources, ai_chats.</p></article>
      </div>`;
    $("#profileForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      await supabase.from("profiles").update({ name: $("#profileName").value.trim(), language: $("#language").value }).eq("id", user.id);
      toast("Profile saved");
    });
    $("#logout").addEventListener("click", async () => {
      await supabase.auth.signOut();
      window.location.href = "login.html";
    });
  });
}

async function loginPage() {
  if (!supabase) {
    $("#loginStatus").textContent = "Supabase config is missing. Add secrets and redeploy.";
    return;
  }
  try {
    await initAuth();
    if (user) window.location.href = "dashboard.html";
  } catch (error) {
    $("#loginStatus").textContent = authErrorMessage(error);
  }
  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = $("#email").value.trim();
    const password = $("#password").value;
    const name = $("#name").value.trim() || "Kaung";
    const mode = event.submitter.dataset.mode;
    $("#loginStatus").textContent = "Working...";
    const result = mode === "signup"
      ? await supabase.auth.signUp({ email, password, options: { data: { name }, emailRedirectTo: authRedirectUrl } })
      : await supabase.auth.signInWithPassword({ email, password });
    if (result.error) {
      $("#loginStatus").textContent = authErrorMessage(result.error);
      return;
    }
    session = result.data.session;
    user = result.data.user;
    if (!session && mode === "signup") {
      $("#loginStatus").textContent = "Signup created. Check your email if confirmation is enabled.";
      return;
    }
    await ensureProfile();
    window.location.href = "dashboard.html";
  });
  const resend = $("#resendConfirm");
  if (resend) {
    resend.addEventListener("click", async () => {
      const email = $("#email").value.trim();
      if (!email) {
        $("#loginStatus").textContent = "Enter your email first.";
        return;
      }
      const result = await supabase.auth.resend({ type: "signup", email, options: { emailRedirectTo: authRedirectUrl } });
      $("#loginStatus").textContent = result.error ? authErrorMessage(result.error) : "Confirmation email sent. Check your inbox.";
    });
  }
  const reset = $("#resetPassword");
  if (reset) {
    reset.addEventListener("click", async () => {
      const email = $("#email").value.trim();
      if (!email) {
        $("#loginStatus").textContent = "Enter your email first.";
        return;
      }
      const result = await supabase.auth.resetPasswordForEmail(email, { redirectTo: authRedirectUrl });
      $("#loginStatus").textContent = result.error ? authErrorMessage(result.error) : "Password reset email sent.";
    });
  }
}

async function authCallbackPage() {
  if (!supabase) {
    $("#authStatus").textContent = "Supabase config is missing.";
    return;
  }
  try {
    const result = await supabase.auth.getSession();
    session = result.data.session;
    user = session && session.user;
    if (!user) {
      $("#authStatus").textContent = "Auth link opened, but no session was created. Try logging in again.";
      return;
    }
    await ensureProfile();
    $("#authStatus").textContent = "Authenticated. Opening dashboard...";
    window.location.href = "dashboard.html";
  } catch (error) {
    $("#authStatus").textContent = authErrorMessage(error);
  }
}

function handleCommand(event) {
  event.preventDefault();
  const input = $("#command");
  const command = input.value.trim().toLowerCase();
  input.value = "";
  const routes = {
    help: "dashboard.html",
    dashboard: "dashboard.html",
    notes: "notes.html",
    "new note": "notes.html",
    tasks: "planner.html",
    timer: "timer.html",
    ask: "assistant.html",
    quiz: "quiz.html",
    flashcards: "flashcards.html",
    planner: "planner.html",
    progress: "progress.html",
    resources: "resources.html",
    chat: "chat.html",
    settings: "settings.html"
  };
  const key = Object.keys(routes).find((item) => command === item || command.startsWith(`${item} `));
  if (key) window.location.href = routes[key];
  else toast("Commands: help, dashboard, notes, new note, tasks, timer, ask, quiz, flashcards, planner, progress, resources, chat, settings");
}

function wireButtons() {
  $$("[data-cmd]").forEach((button) => button.addEventListener("click", () => {
    const routes = { timer: "timer.html", planner: "planner.html", quiz: "quiz.html", chat: "chat.html" };
    window.location.href = routes[button.dataset.cmd] || "assistant.html";
  }));
  wireTaskChecks();
}

function wireQuickAi() {
  $$("[data-quick-ai]").forEach((button) => button.addEventListener("click", async () => {
    const box = $("#quickAsk");
    const question = box.value.trim() || box.placeholder;
    button.disabled = true;
    try {
      box.value = await askAi(question, button.dataset.quickAi);
      await supabase.from("ai_chats").insert({ user_id: user.id, mode: button.dataset.quickAi, prompt: question, response: box.value });
    } finally {
      button.disabled = false;
    }
  }));
}

function landing() {
  $$("[data-command]").forEach((button) => button.addEventListener("click", () => window.location.href = button.dataset.command));
}

const renderers = { dashboard, notes, planner, assistant, timer: timerPage, flashcards, quiz, progress, resources, settings };
if (page === "login") loginPage();
else if (page === "auth") authCallbackPage();
else if ($("#app")) (renderers[page] || dashboard)();
else landing();
