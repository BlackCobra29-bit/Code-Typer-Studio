const form = document.getElementById("terminal-form");
const previewTrigger = document.getElementById("terminal-preview-trigger");
const preview = document.getElementById("terminal-preview");
const restart = document.getElementById("restart-terminal");
const speed = document.getElementById("word-speed");
const speedValue = document.getElementById("speed-value");

let refreshTimer = null;

function refreshPreview() {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => {
    htmx.trigger(previewTrigger, "refreshPreview");
  }, 220);
}

form.addEventListener("input", (event) => {
  if (event.target === speed) {
    speedValue.textContent = `${speed.value} ms`;
  }
  refreshPreview();
});

form.addEventListener("change", refreshPreview);

restart.addEventListener("click", () => {
  const frame = preview.querySelector("iframe");
  frame?.contentWindow?.postMessage("terminal:restart", "*");
});
