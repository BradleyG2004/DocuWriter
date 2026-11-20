const state = {
  activeFolder: "targets",
  activeMarker: "2",
  documents: {
    context: [{ name: "Spécifications" }],
    targets: [{ name: "Document 1" }, { name: "Document 2" }, { name: "Document 3" }],
    completed: [],
    trash: [],
  },
  markerNotes: {
    "1": "Lorem ipsum dolor sit amet.",
    "2": "Lorem ipsum dolor sit amet.",
    "3": "",
    "4": "",
    "n": "",
  },
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function setActiveMarker(markerId) {
  state.activeMarker = String(markerId);
  $$(".marker-row").forEach((row) => row.classList.toggle("selected",
    row.dataset.marker === state.activeMarker));
  $$(".hatch-zone").forEach((zone) => {
    zone.classList.toggle("active", zone.dataset.marker === state.activeMarker);
  });
  $("#comment-input").value = state.markerNotes[state.activeMarker] || "";
  positionArrow();
}

function positionArrow() {
  const active = $(`.marker-row[data-marker="${state.activeMarker}"]`);
  const arrow = $("#comment-arrow");
  if (!active || !arrow) return;
  const from = active.getBoundingClientRect();
  const bubble = $("#comment-bubble").getBoundingClientRect();
  const side = $("#comment-side").getBoundingClientRect();
  const startY = from.top + from.height / 2;
  const endY = bubble.top + bubble.height * 0.48;
  const relativeY = startY - side.top - 19;
  arrow.style.top = `${relativeY}px`;
  arrow.style.left = "-58px";
  arrow.style.width = "86px";
  arrow.querySelectorAll("path").forEach((path, index) => {
    if (index === 0) path.setAttribute("d", "M3 24 C24 25, 44 34, 79 10");
  });
}

function setActiveFolder(folder) {
  state.activeFolder = folder;
  $$(".folder-nav").forEach((nav) => {
    nav.classList.toggle("active", nav.dataset.folder === folder);
  });
  const pile = $("#document-pile");
  pile.dataset.folder = folder;
  const count = state.documents[folder]?.length || 0;
  if (folder === "context") {
    pile.style.filter = "saturate(0.7)";
  } else {
    pile.style.filter = "";
  }
  if (!count) {
    $("#active-sheet").style.opacity = "0.25";
  } else {
    $("#active-sheet").style.opacity = "1";
  }
}

function completeCurrentDocument() {
  const targets = state.documents.targets;
  if (!targets.length) {
    const button = $("#complete-button");
    button.textContent = "Complété";
    setTimeout(() => button.textContent = "Compléter", 900);
    return;
  }
  targets.shift();
  state.documents.completed.push({ name: "Document complété" });
  setActiveFolder("completed");
  setTimeout(() => setActiveFolder("targets"), 700);
  const button = $("#complete-button");
  button.textContent = "Complété";
  setTimeout(() => button.textContent = "Compléter", 900);
  if (!targets.length) $("#active-sheet").style.opacity = "0.25";
}

$$(".marker-row").forEach((row) => {
  row.addEventListener("click", () => setActiveMarker(row.dataset.marker));
});

$$(".hatch-zone").forEach((zone) => {
  zone.addEventListener("click", () => setActiveMarker(zone.dataset.marker));
});

$("#expand-markers").addEventListener("click", (event) => {
  const expanded = $("#expanded-markers");
  const willOpen = expanded.hidden;
  expanded.hidden = !willOpen;
  event.currentTarget.setAttribute("aria-expanded", String(willOpen));
  $$(".expanded-markers .marker-row").forEach((row) => {
    row.addEventListener("click", () => setActiveMarker(row.dataset.marker), { once: true });
  });
  positionArrow();
});

$("#comment-input").addEventListener("input", (event) => {
  state.markerNotes[state.activeMarker] = event.target.value;
});

$$(".folder-nav").forEach((nav) => {
  nav.addEventListener("click", () => setActiveFolder(nav.dataset.folder));
});

$$(".sheet-back").forEach((sheet) => {
  sheet.addEventListener("click", () => {
    sheet.classList.add("to-front");
    sheet.remove();
  });
});

$("#complete-button").addEventListener("click", completeCurrentDocument);

window.addEventListener("resize", positionArrow);
window.addEventListener("load", () => setActiveMarker("2"));
