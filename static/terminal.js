function initTerminalStudio() {
const form = document.getElementById("terminal-form");
if (!form || form.dataset.terminalStudioInitialized === "true") {
  return;
}
form.dataset.terminalStudioInitialized = "true";
const previewTrigger = document.getElementById("terminal-preview-trigger");
const preview = document.getElementById("terminal-preview");
const restart = document.getElementById("restart-terminal");
const speed = document.getElementById("word-speed");
const speedValue = document.getElementById("speed-value");
const aspectRatio = document.getElementById("terminal-aspect-ratio");
const backgroundStyle = document.getElementById("terminal-background-style");
const gradientName = document.getElementById("terminal-gradient-name");
const canvasPadding = document.getElementById("terminal-canvas-padding");
const canvasHelp = document.getElementById("terminal-canvas-help");

let refreshTimer = null;

window.cleanupTerminalStudio = () => {
  window.clearTimeout(refreshTimer);
  refreshTimer = null;
};

function updateCanvasControls() {
  const isDisplay = aspectRatio?.value === "display";
  const gradientEnabled = backgroundStyle?.value === "gradient";
  if (gradientName) {
    gradientName.disabled = !gradientEnabled || isDisplay;
  }
  if (canvasPadding) {
    canvasPadding.disabled = !gradientEnabled || isDisplay;
  }
  if (canvasHelp) {
    canvasHelp.textContent = isDisplay
      ? "Display mode exports the terminal flush at 700x300, so canvas gradients are ignored."
      : gradientEnabled
        ? "Gradient canvas adds a padded social-style backdrop behind the terminal card."
        : "Switch to Gradient to wrap the terminal in a social-style export canvas.";
  }
}

function syncGradientAspectRatio() {
  if (!aspectRatio || !backgroundStyle) {
    return;
  }
  if (backgroundStyle.value === "gradient" && aspectRatio.value === "display") {
    aspectRatio.value = "16_9";
  }
}

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
  if (event.target === backgroundStyle) {
    syncGradientAspectRatio();
  }
  updateCanvasControls();
  refreshPreview();
});

form.addEventListener("change", () => {
  syncGradientAspectRatio();
  updateCanvasControls();
  refreshPreview();
});

restart.addEventListener("click", () => {
  const frame = preview.querySelector("iframe");
  frame?.contentWindow?.postMessage("terminal:restart", "*");
});

updateCanvasControls();
}

document.addEventListener("htmx:load", initTerminalStudio);
initTerminalStudio();
