const state = { sessionId: null, blocks: [], markers: [], replacements: {}, filename: "" };

function save() {
  if (state.sessionId) localStorage.setItem(`docuwriter_session_${state.sessionId}`, JSON.stringify(state));
}

function applySessionPayload(payload) {
  Object.assign(state, payload);
  state.sessionId = payload.session_id || payload.sessionId || null;
  state.replacements = {};
}

function markerNumber(marker) {
  return state.markers.findIndex(item => item.placeholder_id === marker.placeholder_id) + 1;
}

function renderBlocks() {
  const reader = document.getElementById("reader");
  reader.innerHTML = "";
  let page = null;
  (state.blocks || []).forEach((block, blockIndex) => {
    if (block.page_number !== null && block.page_number !== page) {
      page = block.page_number;
      const separator = document.createElement("div");
      separator.className = "page-badge";
      separator.textContent = `— Page ${page} —`;
      reader.append(separator);
    }
    if (block.block_type === "table") {
      const table = document.createElement("table");
      table.className = "table-grid";
      (block.rows || []).forEach((rowData, rowIndex) => {
        const row = table.insertRow();
        rowData.forEach((text, colIndex) => {
          const cell = row.insertCell();
          cell.className = "table-cell";
          cell.textContent = text;
          cell.dataset.tableIndex = block.table_index ?? "";
          cell.dataset.rowIndex = rowIndex;
          cell.dataset.colIndex = colIndex;
          cell.onclick = () => createTableMarker(block, rowIndex, colIndex);
        });
      });
      reader.append(table);
      reader.append(createInsertButton(block, blockIndex));
      return;
    }
    const element = document.createElement(
      block.block_type === "heading" ? "h3" : "p"
    );
    element.className = "reader-block";
    element.textContent = block.text;
    element.dataset.blockId = block.block_id;
    element.dataset.paragraphIndex = block.paragraph_index ?? "";
    reader.append(element);
    reader.append(createInsertButton(block, blockIndex));
  });
  renderMarkedProposals();
}

function createInsertButton(block, blockIndex) {
  const button = document.createElement("button");
  button.className = "insert-button";
  button.textContent = "+ Insérer une zone IA ici";
  button.onclick = () => {
    const instruction = prompt("Consigne pour la nouvelle zone", "Ajouter une section");
    if (instruction) addMarker({
      placeholder_id: crypto.randomUUID(),
      section_path: block.section_path || "Insertion",
      user_instruction: instruction,
      original_hint: instruction,
      raw_tag: "",
      location_type: block.block_type === "table" ? "table" : "paragraph",
      mode: "insert_after",
      paragraph_index: block.paragraph_index,
      page_number: block.page_number,
      start_offset: null,
      end_offset: null,
      table_coords: block.block_type === "table"
        ? [block.table_index, 0, 0] : null,
    });
  };
  return button;
}

function renderMarkedProposals() {
  state.markers.forEach(marker => {
    const card = document.createElement("article");
    card.className = "marker";
    card.dataset.markerId = marker.placeholder_id;
    const title = document.createElement("strong");
    title.textContent = `#${markerNumber(marker)} ${marker.section_path || "Sans section"}`;
    const before = document.createElement("p");
    before.textContent = `Avant : ${marker.raw_tag || "Nouvelle zone"}`;
    const textarea = document.createElement("textarea");
    textarea.className = "replacement-textarea";
    textarea.value = state.replacements[marker.placeholder_id] || "";
    textarea.oninput = () => {
      state.replacements[marker.placeholder_id] = textarea.value;
      save();
    };
    const regenerate = document.createElement("button");
    regenerate.textContent = "Régénérer ce bloc";
    regenerate.onclick = () => regenerateMarker(marker);
    const exportButton = document.createElement("button");
    exportButton.textContent = state.filename?.toLowerCase().endsWith(".pdf")
      ? "Exporter le document final" : "Exporter le document final";
    exportButton.onclick = exportFinal;
    card.append(title, before, textarea, regenerate, exportButton);
    document.getElementById("reader").append(card);
  });
  renderInspector();
}

function renderInspector() {
  const list = document.getElementById("marker-list");
  list.innerHTML = "";
  state.markers.forEach(marker => {
    const card = document.createElement("article");
    card.className = "inspector-marker";
    const title = document.createElement("strong");
    title.textContent = `#${markerNumber(marker)} ${marker.section_path || "Sans section"}`;
    const textarea = document.createElement("textarea");
    textarea.value = marker.user_instruction || marker.original_hint || "";
    textarea.oninput = () => {
      marker.user_instruction = textarea.value;
      marker.original_hint = textarea.value;
      save();
    };
    const remove = document.createElement("button");
    remove.textContent = "Supprimer";
    remove.onclick = () => {
      state.markers = state.markers.filter(item => item.placeholder_id !== marker.placeholder_id);
      delete state.replacements[marker.placeholder_id];
      save();
      render();
    };
    card.append(title, textarea, remove);
    list.append(card);
  });
  const badge = document.getElementById("tag-badge");
  const existing = state.markers.filter(marker => marker.has_existing_tags).length;
  badge.textContent = existing
    ? `${existing} balise(s) préexistante(s) détectée(s)`
    : "Aucune balise préexistante";
}

function render() {
  renderBlocks();
}

async function addMarker(payload) {
  const response = await fetch(`/api/sessions/${state.sessionId}/markers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const marker = await response.json();
  marker.user_instruction = payload.user_instruction || payload.original_hint || "";
  state.markers.push(marker);
  save();
  render();
}

async function createTableMarker(block, rowIndex, colIndex) {
  const instruction = prompt("Consigne pour cette cellule", "Préciser le contenu de cette cellule");
  if (!instruction) return;
  await addMarker({
    placeholder_id: crypto.randomUUID(),
    section_path: block.section_path || "Tableau",
    user_instruction: instruction,
    original_hint: instruction,
    raw_tag: "",
    location_type: "table",
    mode: "table_cell",
    table_coords: [block.table_index, rowIndex, colIndex],
    paragraph_index: null,
    start_offset: null,
    end_offset: null,
    page_number: block.page_number,
  });
}

document.addEventListener("mouseup", event => {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) return;
  const text = selection.toString();
  if (!text) return;
  const range = selection.getRangeAt(0);
  const target = range.startContainer.parentElement?.closest(".reader-block");
  if (!target) return;
  const existing = document.querySelector(".selection-bubble");
  if (existing) existing.remove();
  const bubble = document.createElement("button");
  bubble.className = "selection-bubble";
  bubble.textContent = "+ Marquer cette sélection";
  bubble.style.left = `${event.clientX}px`;
  bubble.style.top = `${event.clientY}px`;
  bubble.onclick = () => {
    const instruction = prompt("Consigne pour cette sélection", "Décrire cette sélection");
    if (!instruction) return;
    const paragraphIndex = Number(target.dataset.paragraphIndex);
    const preRange = document.createRange();
    preRange.selectNodeContents(target);
    preRange.setEnd(range.startContainer, range.startOffset);
    const startOffset = preRange.toString().length;
    const endOffset = startOffset + range.toString().length;
    bubble.remove();
    addMarker({
      placeholder_id: crypto.randomUUID(),
      section_path: "",
      user_instruction: instruction,
      original_hint: instruction,
      raw_tag: text,
      location_type: "paragraph",
      mode: "selection",
      paragraph_index: Number.isNaN(paragraphIndex) ? null : paragraphIndex,
      start_offset: startOffset,
      end_offset: endOffset,
      table_coords: null,
      page_number: null,
    });
  };
  document.body.append(bubble);
});

async function loadDemo() {
  const response = await fetch("/api/sessions/demo", { method: "POST" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  applySessionPayload(await response.json());
  document.getElementById("generate").disabled = false;
  document.getElementById("export-template").disabled = false;
  save();
  render();
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
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  applySessionPayload(await response.json());
  document.getElementById("generate").disabled = false;
  document.getElementById("export-template").disabled = false;
  save();
  render();
}

async function regenerateMarker(marker) {
  const response = await fetch(`/api/sessions/${state.sessionId}/regenerate-marker`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ marker, provider: "ollama", model: "llama3.1" }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const replacement = await response.json();
  state.replacements[replacement.placeholder_id] = replacement.proposed_replacement;
  save();
  render();
}

async function exportFinal() {
  const replacements = Object.entries(state.replacements).map(([placeholder_id, proposed_replacement]) => ({
    placeholder_id, proposed_replacement,
  }));
  const response = await fetch(`/api/sessions/${state.sessionId}/export-final`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markers: state.markers, replacements, highlight: true }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const result = await response.json();
  const link = document.createElement("a");
  link.href = result.document_url || result.docx_url;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
}

async function exportTemplate() {
  const response = await fetch(`/api/sessions/${state.sessionId}/export-template`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markers: state.markers }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const result = await response.json();
  const link = document.createElement("a");
  link.href = result.document_url;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
}

async function generate() {
  const response = await fetch(`/api/sessions/${state.sessionId}/generate-stream`, { method: "POST" });
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const messages = buffer.split("\n\n");
    buffer = messages.pop();
    for (const message of messages.filter(Boolean)) {
      const event = JSON.parse(message.replace(/^data: /, ""));
      if (event.type === "started") {
        document.getElementById("bar").max = event.total_batches;
      } else if (event.type === "batch_completed") {
        completed += event.replacements.length;
        event.replacements.forEach(item => {
          state.replacements[item.placeholder_id] = item.proposed_replacement;
        });
        document.getElementById("bar").value = event.batch_index;
        document.getElementById("progress").textContent =
          `Lot ${event.batch_index}/${event.total_batches} terminé — ${completed}/${state.markers.length} zones complétées`;
        save();
        render();
      } else if (event.type === "batch_failed") {
        throw new Error(event.error);
      }
    }
  }
  document.getElementById("progress").textContent = "Génération terminée";
}

document.getElementById("demo").onclick = loadDemo;
document.getElementById("upload").onclick = uploadDocument;
document.getElementById("generate").onclick = generate;
document.getElementById("export-template").onclick = exportTemplate;
