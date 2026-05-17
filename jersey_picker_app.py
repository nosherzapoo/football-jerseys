#!/usr/bin/env python3
import csv
import json
import mimetypes
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse


ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(ROOT, "world_cup_2026_kits.csv")
CHOICE_FIELDS = ["better_option", "better_image_path"]


def read_rows():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    for field in CHOICE_FIELDS:
        if field not in fieldnames:
            fieldnames.append(field)
    for index, row in enumerate(rows):
        row["id"] = index
        for field in CHOICE_FIELDS:
            row.setdefault(field, "")
    return fieldnames, rows


def write_choice(row_id, choice):
    if choice not in {"left", "right"}:
        raise ValueError("choice must be left or right")

    fieldnames, rows = read_rows()
    if row_id < 0 or row_id >= len(rows):
        raise IndexError("row id out of range")

    row = rows[row_id]
    selected_path = row["left_half_image_path"] if choice == "left" else row["right_half_image_path"]
    row["better_option"] = choice
    row["better_image_path"] = selected_path

    output_rows = [{key: value for key, value in row.items() if key != "id"} for row in rows]
    fd, temp_path = tempfile.mkstemp(prefix="world_cup_2026_kits_", suffix=".csv", dir=ROOT)
    os.close(fd)
    try:
        with open(temp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(output_rows)
        os.replace(temp_path, CSV_PATH)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    return row


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jersey Half Picker</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f7fb;
      color: #111827;
    }
    body {
      margin: 0;
      padding: 24px;
    }
    .app {
      max-width: 1180px;
      margin: 0 auto;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }
    h1 {
      font-size: 28px;
      margin: 0 0 6px;
    }
    .muted {
      color: #6b7280;
      margin: 0;
    }
    .toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    button {
      border: 1px solid #d1d5db;
      background: white;
      color: #111827;
      border-radius: 999px;
      padding: 10px 15px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 1px 2px rgb(0 0 0 / 0.06);
    }
    button:hover {
      border-color: #9ca3af;
    }
    button.primary {
      background: #111827;
      border-color: #111827;
      color: white;
    }
    .status {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }
    .card {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 18px;
      padding: 16px;
      box-shadow: 0 10px 28px rgb(17 24 39 / 0.08);
    }
    .stat {
      font-size: 24px;
      font-weight: 800;
    }
    .review {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }
    .option {
      position: relative;
      overflow: hidden;
      padding: 0;
      border: 4px solid transparent;
      border-radius: 22px;
      background: white;
      cursor: pointer;
      box-shadow: 0 14px 34px rgb(17 24 39 / 0.12);
    }
    .option.selected {
      border-color: #16a34a;
    }
    .option img {
      display: block;
      width: 100%;
      height: auto;
    }
    .label {
      position: absolute;
      left: 14px;
      top: 14px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgb(17 24 39 / 0.82);
      color: white;
      font-weight: 800;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }
    .picked {
      position: absolute;
      right: 14px;
      top: 14px;
      padding: 8px 12px;
      border-radius: 999px;
      background: #16a34a;
      color: white;
      font-weight: 800;
      display: none;
    }
    .option.selected .picked {
      display: block;
    }
    .meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin: 18px 0;
    }
    .title {
      font-size: 22px;
      font-weight: 900;
    }
    .progress {
      height: 10px;
      background: #e5e7eb;
      border-radius: 999px;
      overflow: hidden;
      margin-bottom: 18px;
    }
    .bar {
      height: 100%;
      width: 0%;
      background: #16a34a;
      transition: width 0.2s ease;
    }
    .hint {
      margin-top: 12px;
      font-size: 14px;
      color: #6b7280;
      text-align: center;
    }
    @media (max-width: 800px) {
      body {
        padding: 14px;
      }
      header, .meta {
        align-items: stretch;
        flex-direction: column;
      }
      .status, .review {
        grid-template-columns: 1fr;
      }
      .toolbar {
        justify-content: flex-start;
      }
    }
  </style>
</head>
<body>
  <main class="app">
    <header>
      <div>
        <h1>Jersey Half Picker</h1>
        <p class="muted">Choose the better crop. Each choice is saved to the CSV immediately.</p>
      </div>
      <div class="toolbar">
        <button id="prev">Previous</button>
        <button id="next">Next</button>
        <button id="nextUnpicked" class="primary">Next Unpicked</button>
      </div>
    </header>

    <section class="status">
      <div class="card"><div class="stat" id="reviewed">0</div><p class="muted">reviewed</p></div>
      <div class="card"><div class="stat" id="remaining">0</div><p class="muted">remaining</p></div>
      <div class="card"><div class="stat" id="position">0 / 0</div><p class="muted">current</p></div>
    </section>

    <div class="progress"><div class="bar" id="bar"></div></div>

    <section class="card">
      <div class="meta">
        <div>
          <div class="title" id="name">Loading...</div>
          <p class="muted" id="saved">Loading CSV data</p>
        </div>
        <a id="original" href="#" target="_blank"><button>Open Original</button></a>
      </div>

      <div class="review">
        <button class="option" id="leftChoice" aria-label="Choose left half">
          <span class="label">Left</span>
          <span class="picked">Selected</span>
          <img id="leftImage" alt="">
        </button>
        <button class="option" id="rightChoice" aria-label="Choose right half">
          <span class="label">Right</span>
          <span class="picked">Selected</span>
          <img id="rightImage" alt="">
        </button>
      </div>
      <p class="hint">Keyboard shortcuts: Left Arrow chooses left, Right Arrow chooses right, N jumps to next unpicked.</p>
    </section>
  </main>

  <script>
    let kits = [];
    let current = 0;

    const $ = (id) => document.getElementById(id);

    async function loadKits() {
      const response = await fetch("/api/kits");
      kits = await response.json();
      current = Math.max(0, kits.findIndex((kit) => !kit.better_option));
      if (current === -1) current = 0;
      render();
    }

    function selectedCount() {
      return kits.filter((kit) => kit.better_option).length;
    }

    function render() {
      if (!kits.length) return;
      const kit = kits[current];
      const selected = kit.better_option;
      $("name").textContent = `${kit.country_name} ${kit.kit_type}`;
      $("saved").textContent = selected ? `Saved better option: ${selected}` : "No choice saved yet";
      $("leftImage").src = `/${kit.left_half_image_path}`;
      $("rightImage").src = `/${kit.right_half_image_path}`;
      $("leftImage").alt = `${kit.country_name} ${kit.kit_type} left half`;
      $("rightImage").alt = `${kit.country_name} ${kit.kit_type} right half`;
      $("original").href = `/${kit.original_image_path}`;
      $("leftChoice").classList.toggle("selected", selected === "left");
      $("rightChoice").classList.toggle("selected", selected === "right");

      const reviewed = selectedCount();
      $("reviewed").textContent = reviewed;
      $("remaining").textContent = kits.length - reviewed;
      $("position").textContent = `${current + 1} / ${kits.length}`;
      $("bar").style.width = `${(reviewed / kits.length) * 100}%`;
    }

    async function choose(choice) {
      const kit = kits[current];
      const response = await fetch("/api/choice", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: kit.id, choice})
      });
      if (!response.ok) {
        alert("Could not save the choice.");
        return;
      }
      const updated = await response.json();
      kits[current].better_option = updated.better_option;
      kits[current].better_image_path = updated.better_image_path;
      render();
      setTimeout(nextUnpicked, 120);
    }

    function previous() {
      current = (current - 1 + kits.length) % kits.length;
      render();
    }

    function next() {
      current = (current + 1) % kits.length;
      render();
    }

    function nextUnpicked() {
      for (let offset = 1; offset <= kits.length; offset++) {
        const index = (current + offset) % kits.length;
        if (!kits[index].better_option) {
          current = index;
          render();
          return;
        }
      }
      next();
    }

    $("leftChoice").addEventListener("click", () => choose("left"));
    $("rightChoice").addEventListener("click", () => choose("right"));
    $("prev").addEventListener("click", previous);
    $("next").addEventListener("click", next);
    $("nextUnpicked").addEventListener("click", nextUnpicked);
    document.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") choose("left");
      if (event.key === "ArrowRight") choose("right");
      if (event.key.toLowerCase() === "n") nextUnpicked();
    });

    loadKits();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_text(HTML, "text/html; charset=utf-8")
            return
        if parsed.path == "/api/kits":
            _, rows = read_rows()
            self.send_json(rows)
            return
        self.serve_file(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/choice":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            row = write_choice(int(payload["id"]), payload["choice"])
            self.send_json(row)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def serve_file(self, request_path):
        relative = unquote(request_path.lstrip("/"))
        full_path = os.path.abspath(os.path.join(ROOT, relative))
        if not full_path.startswith(ROOT + os.sep) or not os.path.isfile(full_path):
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, payload, content_type):
        data = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Jersey picker running at http://127.0.0.1:{port}")
    print("Choices are saved into world_cup_2026_kits.csv")
    server.serve_forever()
