const state = { sessionId: null, markers: [], replacements: {} };

function storageKey() {
  return `docuwriter_session_${state.sessionId}`;
}

function save() {
  if (state.sessionId) localStorage.setItem(storageKey(), JSON.stringify(state));
}

function load() {
  if (!state.sessionId) return;
  const saved = localStorage.getItem(storageKey());
  if (saved) Object.assign(state, JSON.parse(saved));
}

function render() {
  const reader = document.getElementById("reader");
  reader.innerHTML = "";
  let page = null;
  (state.blocks || []).forEach((item) => {
    if (item.page_number !== null && item.page_number !== page) {
      page = item.page_number;
      const badge = document.createElement("div");
      badge.className = "page-badge";
      badge.textContent = `— Page ${page} —`;
      reader.append(badge);
    }
  });
  state.markers.forEach((marker) => {
    const block = document.createElement("article");
    block.className = "marker";
    const title = document.createElement("strong");
    title.textContent = marker.section_path || "Sans section";
    const before = document.createElement("p");
    before.textContent = `Avant : ${marker.raw_tag}`;
    const textarea = document.createElement("textarea");
    textarea.value = state.replacements[marker.placeholder_id] || "";
    textarea.placeholder = "Proposition générée ou texte saisi manuellement";
    textarea.addEventListener("input", () => {
      state.replacements[marker.placeholder_id] = textarea.value;
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
      save();
    });
    const regenerate = document.createElement("button");
    regenerate.textContent = "Régénérer ce bloc";
    regenerate.onclick = () => regenerateMarker(marker);
    const exportButton = document.createElement("button");
    exportButton.textContent = state.filename?.toLowerCase().endsWith(".pdf")
      ? "Exporter le PDF final" : "Exporter le Word final";
    exportButton.onclick = exportFinal;
    block.append(title, before, textarea, regenerate, exportButton);
    reader.append(block);
  });
}

async function loadDemo() {
  const response = await fetch("/api/sessions/demo", { method: "POST" });
  Object.assign(state, await response.json());
  state.replacements = {};
  load();
  document.getElementById("generate").disabled = false;
  render();
}

async function regenerateMarker(marker) {
  const response = await fetch(`/api/sessions/${state.sessionId}/regenerate-marker`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ marker, provider: "ollama", model: "llama3.1" })
  });
  const replacement = await response.json();
  state.replacements[replacement.placeholder_id] = replacement.proposed_replacement;
  save(); render();
}

async function exportFinal() {
  const replacements = Object.entries(state.replacements).map(([placeholder_id, proposed_replacement]) => ({
    placeholder_id, proposed_replacement
  }));
  const response = await fetch(`/api/sessions/${state.sessionId}/export-final`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markers: state.markers, replacements, highlight: true })
  });
  const result = await response.json();
  const link = document.createElement("a");
  link.href = result.document_url || result.docx_url; link.download = ""; link.click();
}

async function uploadDocument() {
  const target = document.getElementById("target-file").files[0];
  if (!target) return;
  const form = new FormData();
  form.append("target_file", target);
  for (const file of document.getElementById("context-files").files) {
    form.append("context_files", file);
  }
  const response = await fetch("/api/sessions", { method: "POST", body: form });
  Object.assign(state, await response.json());
  state.replacements = {};
  save(); document.getElementById("generate").disabled = false; render();
}

async function generate() {
  const response = await fetch(`/api/sessions/${state.sessionId}/generate-stream`, { method: "POST" });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const messages = buffer.split("\n\n"); buffer = messages.pop();
    messages.filter(Boolean).forEach((message) => {
      const event = JSON.parse(message.replace(/^data: /, ""));
      if (event.type === "started") {
        document.getElementById("bar").max = event.total_batches;
      } else if (event.type === "batch_completed") {
        completed += event.replacements.length;
        event.replacements.forEach((item) => {
          state.replacements[item.placeholder_id] = item.proposed_replacement;
        });
        document.getElementById("bar").value = event.batch_index;
        document.getElementById("progress").textContent =
          `Lot ${event.batch_index}/${event.total_batches} terminé — ${completed}/${state.markers.length} zones complétées`;
        save(); render();
      }
    });
  }
}

document.getElementById("demo").onclick = loadDemo;
document.getElementById("upload").onclick = uploadDocument;
document.getElementById("generate").onclick = generate;
