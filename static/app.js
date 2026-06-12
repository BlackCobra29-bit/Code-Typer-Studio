const form = document.getElementById("studio-form");
const previewTrigger = document.getElementById("preview-trigger");
const code = document.getElementById("code");
const language = document.getElementById("language");
const title = document.getElementById("title");
const theme = document.getElementById("theme_name");
const languageIcon = document.getElementById("language-icon");
const languageValue = document.getElementById("language-value");
const themeValue = document.getElementById("theme-value");
const sampleSelect = document.getElementById("sample_name");
const statusPill = document.getElementById("preview-status");
const aspectRatio = document.getElementById("aspect_ratio");
const widthInput = document.getElementById("width");
const heightInput = document.getElementById("height");
const aspectRatioPresets = JSON.parse(document.getElementById("aspect-ratio-data").textContent);
const samples = JSON.parse(document.getElementById("sample-data").textContent);

let refreshTimer = null;
const aspectRatioByValue = Object.fromEntries(aspectRatioPresets.map((preset) => [preset.value, preset]));

const languageLabels = {
  bash: "Bash",
  cpp: "C++",
  csharp: "C#",
  css: "CSS",
  go: "Go",
  html: "HTML",
  java: "Java",
  javascript: "JavaScript",
  json: "JSON",
  jsx: "JSX",
  kotlin: "Kotlin",
  php: "PHP",
  python: "Python",
  ruby: "Ruby",
  rust: "Rust",
  sql: "SQL",
  swift: "Swift",
  tsx: "TSX",
  typescript: "TypeScript",
  yaml: "YAML",
};

const languageBadges = {
  bash: "bash.svg",
  cpp: "cplusplus.svg",
  csharp: "csharp.svg",
  css: "css.svg",
  go: "go.svg",
  html: "html.svg",
  java: "java.svg",
  javascript: "javascript.svg",
  json: "json.svg",
  jsx: "react.svg",
  kotlin: "kotlin.svg",
  php: "php.svg",
  python: "python.svg",
  ruby: "ruby.svg",
  rust: "rust.svg",
  sql: "postgresql.svg",
  swift: "swift.svg",
  tsx: "react.svg",
  typescript: "typescript.svg",
  yaml: "yaml.svg",
};

function fileExtension(sampleLanguage) {
  const extensions = {
    bash: "sh",
    cpp: "cpp",
    csharp: "cs",
    css: "css",
    go: "go",
    html: "html",
    java: "java",
    javascript: "js",
    json: "json",
    jsx: "jsx",
    kotlin: "kt",
    php: "php",
    python: "py",
    ruby: "rb",
    rust: "rs",
    sql: "sql",
    swift: "swift",
    tsx: "tsx",
    typescript: "ts",
    yaml: "yaml",
  };

  return extensions[sampleLanguage] || sampleLanguage;
}

function updateHeroControls() {
  const currentLanguage = language.value;
  languageValue.textContent = languageLabels[currentLanguage] || currentLanguage;
  languageIcon.src = `/static/icons/${languageBadges[currentLanguage] || "json.svg"}`;
  languageIcon.alt = `${languageValue.textContent} icon`;
  languageIcon.parentElement.dataset.language = currentLanguage;
  themeValue.textContent = theme.value;
}

function applyAspectRatioPreset() {
  const preset = aspectRatioByValue[aspectRatio.value];
  if (!preset || preset.value === "custom") {
    return;
  }

  widthInput.value = preset.width;
  heightInput.value = preset.height;
}

function updateAspectRatioFromPixels() {
  const width = Number(widthInput.value);
  const height = Number(heightInput.value);
  const matchingPreset = aspectRatioPresets.find((preset) => {
    return preset.value !== "custom" && Number(preset.width) === width && Number(preset.height) === height;
  });

  aspectRatio.value = matchingPreset ? matchingPreset.value : "custom";
}

function schedulePreview(delay = 450) {
  window.clearTimeout(refreshTimer);
  statusPill.textContent = "Editing";
  refreshTimer = window.setTimeout(() => {
    statusPill.textContent = "Rendering";
    htmx.trigger(previewTrigger, "refreshPreview");
  }, delay);
}

function loadSample(sampleName) {
  const sample = samples[sampleName];
  if (!sample) {
    return;
  }

  code.value = sample.code;
  language.value = sample.language;
  title.value = `${sampleName.toLowerCase().replaceAll(" ", "-")}.${fileExtension(sample.language)}`;
  updateHeroControls();
  schedulePreview(80);
}

document.querySelectorAll("#studio-form input, #studio-form select, #studio-form textarea, [form='studio-form']").forEach((control) => {
  control.addEventListener("input", () => {
    if (control === widthInput || control === heightInput) {
      updateAspectRatioFromPixels();
    }
    updateHeroControls();
    schedulePreview(control === code ? 650 : 300);
  });
  control.addEventListener("change", () => {
    if (control === aspectRatio) {
      applyAspectRatioPreset();
    } else if (control === widthInput || control === heightInput) {
      updateAspectRatioFromPixels();
    }
    updateHeroControls();
    schedulePreview(120);
  });
});

sampleSelect.addEventListener("change", () => loadSample(sampleSelect.value));

document.body.addEventListener("htmx:afterSwap", (event) => {
  if (event.detail.target.id === "preview-panel") {
    statusPill.textContent = "Ready";
  }
});

document.body.addEventListener("htmx:responseError", () => {
  statusPill.textContent = "Error";
});

updateHeroControls();
