// Theme toggle (shared across both pages)
(function initTheme() {
  const stored = localStorage.getItem("theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const theme = stored || (prefersDark ? "dark" : "light");
  document.documentElement.setAttribute("data-theme", theme);

  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme");
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    });
  }
})();

// --- Voting page logic ---
(function initVotingPage() {
  const arena = document.getElementById("arena");
  if (!arena) return;

  const cards = {
    left: arena.querySelector('[data-side="left"]'),
    right: arena.querySelector('[data-side="right"]'),
  };
  const skipLink = document.getElementById("skip");

  let currentToken = null;
  let busy = false;
  let nextPair = null; // prefetched

  function fillCard(side, jersey) {
    const card = cards[side];
    const img = card.querySelector("img");
    img.src = jersey.image;
    img.alt = `${jersey.country} ${jersey.kit_type} kit`;
    card.querySelector(".country").textContent = jersey.country;
    card.querySelector(".kit-type").textContent = jersey.kit_type;
    card.classList.remove("picked", "fading");
  }

  async function fetchPair() {
    const res = await fetch("/api/pair");
    if (!res.ok) throw new Error("pair fetch failed");
    return res.json();
  }

  async function loadPair(prefetched) {
    busy = true;
    try {
      const pair = prefetched || (await fetchPair());
      currentToken = pair.token;
      fillCard("left", pair.left);
      fillCard("right", pair.right);
      // Wait for both images to be at least decoded before enabling, to avoid layout pops.
      const imgs = [cards.left.querySelector("img"), cards.right.querySelector("img")];
      await Promise.all(imgs.map(i => (i.decode ? i.decode().catch(() => {}) : Promise.resolve())));
      cards.left.disabled = false;
      cards.right.disabled = false;
      // Begin prefetching the next pair so the swap feels instant.
      fetchPair().then(p => (nextPair = p)).catch(() => {});
    } catch (e) {
      console.error(e);
    } finally {
      busy = false;
    }
  }

  async function vote(side) {
    if (busy || !currentToken) return;
    busy = true;
    cards.left.disabled = true;
    cards.right.disabled = true;
    cards[side].classList.add("picked");
    const other = side === "left" ? "right" : "left";
    cards[other].classList.add("fading");

    try {
      const res = await fetch("/api/vote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: currentToken, winner: side }),
      });
      if (res.status === 429) {
        await new Promise(r => setTimeout(r, 600));
      }
    } catch (e) {
      console.error(e);
    }

    await new Promise(r => setTimeout(r, 200));
    cards.left.classList.remove("picked", "fading");
    cards.right.classList.remove("picked", "fading");

    const useNext = nextPair;
    nextPair = null;
    busy = false;
    await loadPair(useNext);
  }

  cards.left.addEventListener("click", () => vote("left"));
  cards.right.addEventListener("click", () => vote("right"));

  // Keyboard: ← / → to vote, space to skip
  document.addEventListener("keydown", (e) => {
    if (e.target && e.target.tagName === "INPUT") return;
    if (e.key === "ArrowLeft") vote("left");
    else if (e.key === "ArrowRight") vote("right");
    else if (e.key === " ") { e.preventDefault(); skip(); }
  });

  async function skip() {
    if (busy) return;
    busy = true;
    cards.left.disabled = true;
    cards.right.disabled = true;
    cards.left.classList.add("fading");
    cards.right.classList.add("fading");
    await new Promise(r => setTimeout(r, 150));
    const useNext = nextPair;
    nextPair = null;
    busy = false;
    await loadPair(useNext);
  }
  if (skipLink) skipLink.addEventListener("click", (e) => { e.preventDefault(); skip(); });

  loadPair();
})();

// --- Leaderboard page logic ---
(function initLeaderboardPage() {
  const ranksEl = document.getElementById("ranks");
  if (!ranksEl) return;

  async function load() {
    ranksEl.innerHTML = "";
    try {
      const board = await fetch("/api/leaderboard").then(r => r.json());
      render(board.jerseys);
    } catch (e) {
      console.error(e);
    }
  }

  function render(rows) {
    const frag = document.createDocumentFragment();
    for (const r of rows) {
      const li = document.createElement("li");
      li.className = "row";
      li.innerHTML = `
        <div class="rank">${r.rank}</div>
        <div class="thumb"><img loading="lazy" alt="" /></div>
        <div class="name">
          <span class="c"></span>
          <span class="k"></span>
        </div>
        <div class="num">
          <span class="big"></span>
        </div>
      `;
      li.querySelector("img").src = r.image;
      li.querySelector(".c").textContent = r.country;
      li.querySelector(".k").textContent = r.kit_type;
      li.querySelector(".big").textContent = Math.round(r.rating);
      frag.appendChild(li);
    }
    ranksEl.appendChild(frag);
  }

  load();
})();
