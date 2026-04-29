const NAV_ITEMS = [
  ["dashboard", "Dashboard", "dashboard.html"],
  ["notes", "Notes", "notes.html"],
  ["planner", "Planner", "planner.html"],
  ["assistant", "AI Assistant", "assistant.html"],
  ["quiz", "Quiz", "quiz.html"],
  ["flashcards", "Flashcards", "flashcards.html"],
  ["progress", "Progress", "progress.html"],
  ["resources", "Resources", "resources.html"],
  ["portfolio", "Portfolio", "portfolio.html"],
  ["settings", "Settings", "settings.html"]
];

const STORE = "kaung_study_os";
const CLIENT_ID_KEY = "kaung_study_client_id";
const API_URL = "https://bot.kaungkhantko.top/api/chat";
const page = document.body.dataset.page || "dashboard";

const seed = {
  notes: [
    { id: "n1", title: "Linux Commands", content: "ls, cd, pwd, grep, chmod, systemctl, journalctl", tags: ["Linux", "Exam"], pinned: true, updated: "Today" },
    { id: "n2", title: "OSI Model", content: "Physical, Data Link, Network, Transport, Session, Presentation, Application.", tags: ["Networking"], pinned: false, updated: "Yesterday" }
  ],
  tasks: [
    { id: "t1", title: "Review subnetting", priority: "High", done: false },
    { id: "t2", title: "Make Python loop flashcards", priority: "Medium", done: false },
    { id: "t3", title: "Quiz firewall rules", priority: "High", done: false }
  ],
  flashcards: [
    { id: "f1", q: "What is NAT?", a: "Network Address Translation", known: false },
    { id: "f2", q: "Which OSI layer uses IP?", a: "Layer 3, Network layer", known: true }
  ],
  sessions: [{ date: "Mon", minutes: 90 }, { date: "Tue", minutes: 120 }, { date: "Wed", minutes: 70 }, { date: "Thu", minutes: 130 }, { date: "Fri", minutes: 60 }, { date: "Sat", minutes: 150 }, { date: "Sun", minutes: 95 }],
  xp: 1200,
  level: 4,
  streak: 5
};

function state() {
  const saved = JSON.parse(localStorage.getItem(STORE) || "null");
  if (saved) return saved;
  localStorage.setItem(STORE, JSON.stringify(seed));
  return structuredClone(seed);
}

function save(next) {
  localStorage.setItem(STORE, JSON.stringify(next));
}

function clientId() {
  const existing = localStorage.getItem(CLIENT_ID_KEY);
  if (existing) return existing;
  const generated = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  localStorage.setItem(CLIENT_ID_KEY, generated);
  return generated;
}

function $(selector) {
  return document.querySelector(selector);
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function toast(message) {
  const node = $("#toast");
  if (!node) return;
  node.textContent = message;
  node.classList.remove("hidden");
  clearTimeout(window.toastTimer);
  window.toastTimer = setTimeout(() => node.classList.add("hidden"), 3200);
}

async function askAi(message, mode = "Explain Mode") {
  const prompt = `[${mode}] ${message}`;
  const response = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: prompt, clientId: clientId(), language: "default" })
  });
  if (!response.ok) throw new Error("AI request failed");
  const data = await response.json();
  return data.reply || data.message || "No reply returned.";
}

function renderShell(title, subtitle) {
  const app = $("#app");
  if (!app) return;
  app.innerHTML = `
    <aside class="sidebar">
      <div class="brand">
        <strong>Kaung Study OS</strong>
        <span>terminal student workspace</span>
      </div>
      <nav class="nav" aria-label="Main navigation">
        ${NAV_ITEMS.map(([id, label, href]) => `<a class="${id === page ? "active" : ""}" href="${href}">${label}</a>`).join("")}
      </nav>
    </aside>
    <main class="main">
      <div class="topline">
        <div class="window-dots"><span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span></div>
        <span class="muted">root@study:~/${page}# online</span>
      </div>
      <section class="page-title">
        <h1>${title}</h1>
        <p>${subtitle}</p>
      </section>
      <section id="content"></section>
    </main>
    <form id="commandForm" class="command-bar" autocomplete="off">
      <label class="prompt" for="command">root@study:~#</label>
      <input id="command" name="command" type="text" placeholder="help, dashboard, notes, new note, timer, ask, quiz, flashcards, portfolio">
      <button type="submit">run</button>
    </form>
    <div id="toast" class="toast hidden" role="status"></div>
  `;
  $("#commandForm").addEventListener("submit", handleCommand);
}

function dashboard() {
  const s = state();
  renderShell("Welcome back, Kaung", "Today’s Study Goal: 2 hours. Current Streak: 5 days. Next Exam: Networking - 4 days left.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card"><h2>Study Goal</h2><span class="metric">2h</span><p class="muted">70 minutes completed today</p></article>
      <article class="card"><h2>Current Streak</h2><span class="metric">${s.streak} days</span><p class="muted">Keep the daily session alive</p></article>
      <article class="card"><h2>Tasks Left</h2><span class="metric">${s.tasks.filter((t) => !t.done).length}</span><p class="muted">Networking exam in 4 days</p></article>
      <article class="card wide"><h2>Today’s tasks</h2><ul class="list">${s.tasks.map((task) => `<li><strong>${escapeHtml(task.title)}</strong><br><span class="muted">${task.priority} priority</span></li>`).join("")}</ul></article>
      <article class="card"><h2>Pomodoro timer</h2><div class="timer-display" id="miniTimer">25:00</div><div class="actions"><button data-cmd="timer">Start</button><button class="secondary" data-cmd="planner">Plan</button></div></article>
      <article class="card"><h2>XP / Level</h2><span class="metric">Lv ${s.level}</span><div class="progress-track"><div class="progress-fill" style="--value:72%"></div></div><p class="muted">${s.xp} XP earned</p></article>
      <article class="card"><h2>Recent notes</h2><ul class="list">${s.notes.slice(0, 2).map(noteItem).join("")}</ul></article>
      <article class="card wide"><h2>Quick AI ask</h2><textarea id="quickAsk" placeholder="Explain OSI model simply"></textarea><div class="actions"><button data-quick-ai="Explain Mode">Explain</button><button data-quick-ai="Quiz Mode">Quiz</button><button data-quick-ai="Roadmap Mode">Roadmap</button></div></article>
    </div>`;
  wireButtons();
  document.querySelectorAll("[data-quick-ai]").forEach((button) => button.addEventListener("click", async () => {
    const box = $("#quickAsk");
    const question = box.value.trim() || box.placeholder;
    button.disabled = true;
    toast("Asking AI assistant...");
    try {
      const reply = await askAi(question, button.dataset.quickAi);
      box.value = reply;
      toast("AI reply loaded");
    } catch {
      toast("AI endpoint is not reachable right now");
    } finally {
      button.disabled = false;
    }
  }));
}

function noteItem(note) {
  return `<li><strong>${note.pinned ? "Pinned: " : ""}${escapeHtml(note.title)}</strong><br><span class="muted">${escapeHtml(note.updated)}</span><div class="tag-row">${note.tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div></li>`;
}

function notes() {
  const s = state();
  renderShell("Smart Notes", "Create, edit, delete, search, tag, pin, and use AI actions on study notes.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card full">
        <div class="form-grid">
          <input id="noteSearch" placeholder="Search notes">
          <input id="noteTags" placeholder="Tags: Linux, Exam">
          <input id="noteTitle" class="full" placeholder="Note title">
          <textarea id="noteContent" class="full" placeholder="Markdown supported: ## Heading, - list, **important**"></textarea>
          <button id="saveNote">Create note</button>
          <button id="pinNote" class="secondary" type="button">Pin important note</button>
        </div>
      </article>
      <div id="notesList" class="grid full"></div>
    </div>`;
  function renderNotes() {
    const query = $("#noteSearch").value.toLowerCase();
    const fresh = state();
    $("#notesList").innerHTML = fresh.notes
      .filter((note) => `${note.title} ${note.content} ${note.tags.join(" ")}`.toLowerCase().includes(query))
      .map((note) => `
        <article class="card note-card">
          <h2>${note.pinned ? "Pinned: " : ""}${escapeHtml(note.title)}</h2>
          <p class="muted">Updated: ${escapeHtml(note.updated)}</p>
          <p>${escapeHtml(note.content)}</p>
          <div class="tag-row">${note.tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
          <div class="actions">
            <button data-note-ai="Summarize" data-title="${escapeHtml(note.title)}">Summarize</button>
            <button data-note-ai="Quiz" data-title="${escapeHtml(note.title)}">Quiz</button>
            <button data-note-ai="Flashcards" data-title="${escapeHtml(note.title)}">Flashcards</button>
            <button class="secondary" data-delete-note="${note.id}">Delete</button>
          </div>
        </article>`).join("");
    wireButtons();
    document.querySelectorAll("[data-delete-note]").forEach((button) => button.addEventListener("click", () => {
      const next = state();
      next.notes = next.notes.filter((note) => note.id !== button.dataset.deleteNote);
      save(next);
      renderNotes();
      toast("Note deleted");
    }));
  }
  $("#saveNote").addEventListener("click", (event) => {
    event.preventDefault();
    const title = $("#noteTitle").value.trim();
    if (!title) return toast("Add a note title first");
    const next = state();
    next.notes.unshift({ id: crypto.randomUUID(), title, content: $("#noteContent").value.trim(), tags: $("#noteTags").value.split(",").map((tag) => tag.trim()).filter(Boolean), pinned: false, updated: "Today" });
    save(next);
    $("#noteTitle").value = "";
    $("#noteContent").value = "";
    renderNotes();
    toast("Note created");
  });
  $("#pinNote").addEventListener("click", () => toast("New notes can be pinned from the saved note menu after Firebase is connected"));
  $("#noteSearch").addEventListener("input", renderNotes);
  renderNotes();
}

function planner() {
  renderShell("Study Planner", "Calendar-style goals, subject planner, deadline tracker, weekly schedule, and task priority.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card"><h2>Daily goal</h2><span class="metric">2h</span><p class="muted">Networking deadline: 4 days</p></article>
      <article class="card wide"><h2>Monday</h2><ul class="list"><li>7:00 PM: Python</li><li>8:00 PM: Networking</li><li>9:00 PM: Quiz Review</li></ul></article>
      ${["Tuesday: Linux commands", "Wednesday: Web security", "Thursday: AI revision", "Friday: IELTS writing", "Saturday: Portfolio project", "Sunday: Mock exam"].map((item) => `<article class="card"><h2>${item.split(":")[0]}</h2><p>${item.split(":")[1]}</p><span class="tag">Medium priority</span></article>`).join("")}
    </div>`;
}

function assistant() {
  renderShell("AI Study Assistant", "Explain, quiz, summarize, make flashcards, generate roadmaps, and prepare for exams.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card full">
        <div class="mode-row">
          ${["Explain Mode", "Quiz Mode", "Summary Mode", "Flashcard Mode", "Roadmap Mode", "Exam Prep Mode"].map((mode) => `<button data-mode="${mode}">${mode}</button>`).join("")}
        </div>
      </article>
      <article class="card wide"><h2 id="assistantMode">Explain Mode</h2><textarea id="assistantPrompt" placeholder="Explain OSI model simply"></textarea><div class="actions"><button id="assistantRun">Ask AI</button><button class="secondary" data-cmd="quiz">Make quiz</button></div></article>
      <article class="card"><h2>Output</h2><p id="assistantOutput" class="muted">AI response preview will appear here. Connect this to OpenRouter or Firebase Functions for live generation.</p></article>
    </div>`;
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => $("#assistantMode").textContent = button.dataset.mode));
  $("#assistantRun").addEventListener("click", async () => {
    const mode = $("#assistantMode").textContent;
    const prompt = $("#assistantPrompt").value.trim() || "Explain OSI model simply";
    $("#assistantOutput").textContent = "Running AI assistant...";
    try {
      $("#assistantOutput").textContent = await askAi(prompt, mode);
    } catch {
      $("#assistantOutput").textContent = `${mode}: ${prompt}. Key idea, simple explanation, example, and next review step.`;
      toast("AI endpoint is not reachable, showing local fallback");
    }
  });
  wireButtons();
}

function timerPage() {
  renderShell("Pomodoro Focus", "25-minute focus, 5-minute break, long break, focus music option, and saved completed sessions.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card wide"><h2>Focus timer</h2><div id="timer" class="timer-display">25:00</div><div class="actions"><button id="startTimer">Start 25</button><button id="breakTimer" class="secondary">5 min break</button><button id="longBreak" class="secondary">Long break</button></div></article>
      <article class="card"><h2>Session reward</h2><p>Great work!</p><span class="metric">+20 XP</span><p class="muted">Focus time saved: 25 minutes</p></article>
      <article class="card full"><h2>Focus options</h2><div class="tag-row"><span class="tag">Focus music</span><span class="tag">Distraction blocker reminder</span><span class="tag">Save completed sessions</span></div></article>
    </div>`;
  let remaining = 1500;
  let interval;
  function draw() {
    const m = Math.floor(remaining / 60).toString().padStart(2, "0");
    const sec = (remaining % 60).toString().padStart(2, "0");
    $("#timer").textContent = `${m}:${sec}`;
  }
  function start(seconds) {
    clearInterval(interval);
    remaining = seconds;
    draw();
    interval = setInterval(() => {
      remaining -= 1;
      draw();
      if (remaining <= 0) {
        clearInterval(interval);
        const next = state();
        next.xp += 20;
        next.sessions.push({ date: "Today", minutes: seconds / 60 });
        save(next);
        toast("Great work! +20 XP. Focus time saved.");
      }
    }, 1000);
  }
  $("#startTimer").addEventListener("click", () => start(1500));
  $("#breakTimer").addEventListener("click", () => start(300));
  $("#longBreak").addEventListener("click", () => start(900));
}

function flashcards() {
  const s = state();
  renderShell("Flashcards", "Manual and AI-generated cards with flip review, known and not known tracking, and review schedule.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card full"><div class="form-grid"><input id="cardQ" placeholder="Question"><input id="cardA" placeholder="Answer"><button id="addCard">Add flashcard</button><button class="secondary" data-cmd="ask make flashcards for Python loops">AI generate</button></div></article>
      ${s.flashcards.map((card) => `<article class="card"><h2>Q: ${escapeHtml(card.q)}</h2><p class="flashcard-face">A: ${escapeHtml(card.a)}</p><div class="actions"><button data-known="${card.id}">Known</button><button class="secondary" data-unknown="${card.id}">Not Known</button></div></article>`).join("")}
    </div>`;
  $("#addCard").addEventListener("click", () => {
    const q = $("#cardQ").value.trim();
    const a = $("#cardA").value.trim();
    if (!q || !a) return toast("Add both question and answer");
    const next = state();
    next.flashcards.unshift({ id: crypto.randomUUID(), q, a, known: false });
    save(next);
    flashcards();
  });
  wireButtons();
}

function quiz() {
  renderShell("Quiz Generator", "Create multiple choice, true/false, short answer, and fill-in-the-blank quizzes from notes or topics.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card wide"><h2>Create quiz</h2><textarea id="quizTopic" placeholder="Firewall rules or Linux commands"></textarea><div class="actions"><button id="makeQuiz">Generate quiz</button><button class="secondary">Multiple choice</button><button class="secondary">True / false</button><button class="secondary">Short answer</button></div></article>
      <article class="card"><h2>After quiz</h2><span class="metric">8/10</span><p>Weak topic: Firewall rules</p><p class="muted">Suggested review: Network Security</p></article>
      <article class="card full"><h2>Preview</h2><ul id="quizPreview" class="list"><li>1. Which command lists active firewall rules?</li><li>2. True or false: NAT changes IP address information.</li><li>3. Fill in the blank: OSI Layer 3 is the ____ layer.</li></ul></article>
    </div>`;
  $("#makeQuiz").addEventListener("click", () => toast("Quiz generated from topic preview"));
}

function progress() {
  const s = state();
  renderShell("Progress Tracker", "Track study hours, completed tasks, quiz scores, flashcard accuracy, streaks, and weak subjects.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card"><h2>Study hours</h2><span class="metric">12.5h</span></article>
      <article class="card"><h2>Quiz score</h2><span class="metric">82%</span></article>
      <article class="card"><h2>Flashcard accuracy</h2><span class="metric">76%</span></article>
      <article class="card wide"><h2>Weekly study time</h2><div class="chart">${s.sessions.slice(0, 7).map((day) => `<div class="bar"><span style="height:${Math.max(24, day.minutes)}px"></span><span>${day.date}</span></div>`).join("")}</div></article>
      <article class="card"><h2>Weak subjects</h2><ul class="list"><li>Firewall rules</li><li>Subnet masks</li><li>Python loops</li></ul></article>
    </div>`;
}

function resources() {
  const items = [
    ["Programming", "Python loops, data structures, and project practice", "Beginner", "45 min"],
    ["Cyber Security", "Networking, firewall rules, and Linux hardening", "Intermediate", "60 min"],
    ["AI", "Prompting, model basics, and study automation", "Beginner", "35 min"],
    ["English / IELTS", "Writing practice and vocabulary review", "Intermediate", "50 min"],
    ["Linux", "Commands, permissions, services, and logs", "Beginner", "40 min"],
    ["Web Development", "HTML, CSS, JavaScript, deploy workflow", "Beginner", "70 min"],
    ["University Assignments", "Research, outlines, citations, and presentation prep", "All levels", "30 min"]
  ];
  renderShell("Student Resource Hub", "A focused library for programming, cyber security, AI, English, Linux, web development, and assignments.");
  $("#content").innerHTML = `<div class="grid">${items.map(([title, desc, difficulty, time]) => `<article class="card resource"><h2>${title}</h2><p>${desc}</p><div class="tag-row"><span class="tag">${difficulty}</span><span class="tag">${time}</span></div><button>Start</button></article>`).join("")}</div>`;
}

function portfolio() {
  renderShell("Kaung Khant Ko", "Portfolio mode for personal brand, projects, skills, resume, GitHub, and contact.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card wide"><h2>About</h2><p>Student builder focused on AI tools, cybersecurity, web apps, automation, and useful study systems.</p></article>
      <article class="card"><h2>Contact</h2><p>kaungkhantko.studio</p><p>GitHub: kaungkhantko26</p></article>
      <article class="card"><h2>Skills</h2><div class="tag-row"><span class="tag">Python</span><span class="tag">Firebase</span><span class="tag">Web</span><span class="tag">AI</span><span class="tag">Linux</span></div></article>
      <article class="card"><h2>Resume</h2><p class="muted">Add resume PDF link here.</p><button>Open resume</button></article>
      <article class="card full"><h2>Projects</h2><ul class="list"><li>CookAI Telegram assistant</li><li>Terminal website chatbot</li><li>Kaung Study OS</li></ul></article>
    </div>`;
}

function settings() {
  renderShell("Settings", "Theme, language, profile, and Firebase-ready database structure.");
  $("#content").innerHTML = `
    <div class="grid">
      <article class="card"><h2>Profile</h2><input value="Kaung"><input value="kaung@example.com"><button>Save profile</button></article>
      <article class="card"><h2>Theme</h2><select><option>Kali</option><option>Matrix</option><option>Cyberpunk</option></select><select><option>English</option><option>Burmese</option></select></article>
      <article class="card full"><h2>Firebase collections</h2><p class="muted">users, notes, tasks, studySessions, flashcards, quizzes, resources, aiChats</p><pre>{
  users/{userId}: { name, email, level, xp, streak, preferredTheme, language },
  notes/{noteId}: { userId, title, content, tags, pinned, createdAt, updatedAt }
}</pre></article>
    </div>`;
}

function handleCommand(event) {
  event.preventDefault();
  const input = $("#command");
  const raw = input.value.trim();
  const command = raw.toLowerCase();
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
    portfolio: "portfolio.html",
    settings: "settings.html"
  };
  const key = Object.keys(routes).find((item) => command === item || command.startsWith(`${item} `));
  if (key) window.location.href = routes[key];
  else toast("Commands: help, dashboard, notes, new note, tasks, timer, ask, quiz, flashcards, planner, progress, resources, portfolio, settings");
}

function wireButtons() {
  document.querySelectorAll("[data-cmd]").forEach((button) => {
    button.addEventListener("click", () => {
      const cmd = button.dataset.cmd;
      const routes = { timer: "timer.html", planner: "planner.html", quiz: "quiz.html" };
      window.location.href = routes[cmd] || "assistant.html";
    });
  });
  document.querySelectorAll("[data-ai], [data-note-ai]").forEach((button) => {
    button.addEventListener("click", () => toast(`${button.dataset.ai || button.dataset.noteAi} prepared for AI assistant`));
  });
}

function initLanding() {
  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("click", () => {
      const route = button.dataset.command;
      window.location.href = route;
    });
  });
}

const renderers = { dashboard, notes, planner, assistant, timer: timerPage, flashcards, quiz, progress, resources, portfolio, settings };
if ($("#app")) {
  (renderers[page] || dashboard)();
} else {
  initLanding();
}
