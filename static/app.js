function initCodeStudio() {
const form = document.getElementById("studio-form");
if (!form || form.dataset.codeStudioInitialized === "true") {
  return;
}
form.dataset.codeStudioInitialized = "true";
const previewTrigger = document.getElementById("preview-trigger");
const code = document.getElementById("code");
const language = document.getElementById("language");
const title = document.getElementById("title");
const theme = document.getElementById("theme_name");
const aspectRatio = document.getElementById("aspect_ratio");
const backgroundStyle = document.getElementById("background_style");
const gradientName = document.getElementById("gradient_name");
const canvasPadding = document.getElementById("canvas_padding");
const canvasHelp = document.getElementById("canvas-help");
const languageIcon = document.getElementById("language-icon");
const languageValue = document.getElementById("language-value");
const themeValue = document.getElementById("theme-value");
const sampleSelect = document.getElementById("sample_name");
const statusPill = document.getElementById("preview-status");
const languageCatalog = JSON.parse(document.getElementById("language-catalog").textContent);
const samples = JSON.parse(document.getElementById("sample-data").textContent);

let refreshTimer = null;
let codeEditor = null;
let highlightTimer = null;
let highlightRequest = null;
let highlightVersion = 0;
let syntaxMarks = [];
const tokenStyles = document.createElement('style');
form.appendChild(tokenStyles);
const customSelects = new Map();

window.cleanupCodeStudio = () => {
  window.clearTimeout(refreshTimer);
  refreshTimer = null;
  window.clearTimeout(highlightTimer);
  highlightRequest?.abort();
  window.removeEventListener('message', receivePlayback);
};
const languageLabels = Object.fromEntries(
  Object.entries(languageCatalog).map(([languageKey, config]) => [languageKey, config.label || languageKey]),
);
const languageBadges = Object.fromEntries(
  Object.entries(languageCatalog).map(([languageKey, config]) => [languageKey, config.icon || "json.svg"]),
);
const languageExtensions = Object.fromEntries(
  Object.entries(languageCatalog).map(([languageKey, config]) => [languageKey, config.extension || languageKey]),
);
const codeMirrorModes = Object.fromEntries(
  Object.entries(languageCatalog).map(([languageKey, config]) => [languageKey, config.codemirror_mode || "text/plain"]),
);

function fileExtension(sampleLanguage) {
  return languageExtensions[sampleLanguage] || sampleLanguage;
}

function updateHeroControls() {
  const currentLanguage = language.value;
  languageValue.textContent = languageLabels[currentLanguage] || currentLanguage;
  languageIcon.src = `/static/icons/${languageBadges[currentLanguage] || "json.svg"}`;
  languageIcon.alt = `${languageValue.textContent} icon`;
  languageIcon.parentElement.dataset.language = currentLanguage;
  themeValue.textContent = theme.value;
  syncCustomSelect(language);
  syncCustomSelect(theme);
  syncCustomSelect(sampleSelect);
  syncCodeEditorMode();
  updateCanvasControls();
}

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
      ? "Display mode exports the editor flush at 700x300, so canvas gradients are ignored."
      : gradientEnabled
        ? "Gradient canvas adds a padded social-style backdrop behind the editor card."
        : "Switch to Gradient to wrap the editor in a social-style export canvas.";
  }
}

function codeEditorMode() {
  return codeMirrorModes[language.value] || "javascript";
}

function syncCodeEditorMode() {
  if (!codeEditor) {
    return;
  }

  // Disable CodeMirror's unrelated theme palette; Shiki marks own every token.
  codeEditor.setOption("mode", null);
}

function setCodeEditorValue(value) {
  if (!codeEditor) {
    code.value = value;
    return;
  }

  if (codeEditor.getValue() !== value) {
    codeEditor.setValue(value);
  }
}

function initCodeEditor() {
  if (!window.CodeMirror || !code) {
    return;
  }

  codeEditor = CodeMirror.fromTextArea(code, {
    mode: null,
    theme: "textmate",
    lineNumbers: true,
    lineWrapping: false,
    indentUnit: 2,
    tabSize: 2,
    viewportMargin: Infinity,
  });
  codeEditor.getInputField().setAttribute('aria-label', 'Source code');

  codeEditor.on("change", () => {
    syntaxMarks.forEach(mark => mark.clear());
    syntaxMarks = [];
    const nextValue = codeEditor.getValue();
    if (code.value !== nextValue) {
      code.value = nextValue;
      code.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
}

function customSelectLabel(select, value) {
  if (select === language) {
    return languageLabels[value] || value;
  }

  const option = Array.from(select.options).find((item) => item.value === value);
  return option ? option.textContent : value;
}

function customSelectIcon(select, value) {
  if (select === language) {
    const label = customSelectLabel(select, value);
    return `<img class="h-6 w-6 object-contain" src="/static/icons/${languageBadges[value] || "json.svg"}" alt="${label} icon">`;
  }

  if (select === theme) {
    return '<span class="grid h-6 w-6 place-items-center rounded bg-slate-900 text-[10px] font-bold text-white" aria-hidden="true">fn</span>';
  }

  const sampleLanguage = samples[value]?.language || "json";
  const sampleLabel = languageLabels[sampleLanguage] || sampleLanguage;
  return `<img class="h-6 w-6 object-contain" src="/static/icons/${languageBadges[sampleLanguage] || "json.svg"}" alt="${sampleLabel} icon">`;
}

function closeCustomSelect(wrapper) {
  const customSelect = customSelects.get(wrapper.dataset.customSelect);
  if (!customSelect) {
    return;
  }

  customSelect.menu.classList.add("hidden");
  customSelect.trigger.setAttribute("aria-expanded", "false");
}

function closeOtherCustomSelects(activeWrapper) {
  customSelects.forEach(({ wrapper }) => {
    if (wrapper !== activeWrapper) {
      closeCustomSelect(wrapper);
    }
  });
}

function openCustomSelect(wrapper) {
  const customSelect = customSelects.get(wrapper.dataset.customSelect);
  if (!customSelect) {
    return;
  }

  closeOtherCustomSelects(wrapper);
  customSelect.menu.classList.remove("hidden");
  customSelect.trigger.setAttribute("aria-expanded", "true");
  syncCustomSelect(customSelect.select);
}

function toggleCustomSelect(wrapper) {
  const customSelect = customSelects.get(wrapper.dataset.customSelect);
  if (!customSelect) {
    return;
  }

  if (customSelect.menu.classList.contains("hidden")) {
    openCustomSelect(wrapper);
  } else {
    closeCustomSelect(wrapper);
  }
}

function syncCustomSelect(select) {
  const customSelect = customSelects.get(select.id);
  if (!customSelect) {
    return;
  }

  const selectedValue = select.value;
  const valueElement = customSelect.trigger.querySelector("[data-select-value]");
  if (valueElement) {
    valueElement.textContent = customSelectLabel(select, selectedValue);
  }

  const iconElement = customSelect.trigger.querySelector("[data-select-icon]");
  if (iconElement) {
    iconElement.innerHTML = customSelectIcon(select, selectedValue);
  }

  customSelect.options.forEach((optionButton) => {
    const isSelected = optionButton.dataset.value === selectedValue;
    optionButton.setAttribute("aria-selected", String(isSelected));
    optionButton.classList.toggle("bg-slate-50", isSelected);
    optionButton.classList.toggle("font-bold", isSelected);
  });
}

function setCustomSelectValue(select, value) {
  if (select.value === value) {
    syncCustomSelect(select);
    return;
  }

  select.value = value;
  syncCustomSelect(select);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function initCustomSelect(select) {
  const wrapper = document.querySelector(`[data-custom-select="${select.id}"]`);
  if (!wrapper) {
    return;
  }

  const trigger = wrapper.querySelector("[data-select-trigger]");
  const menu = wrapper.querySelector("[data-select-menu]");
  const valueElement = trigger.querySelector(`#${select.id === "sample_name" ? "sample" : select.id === "theme_name" ? "theme" : "language"}-value`);
  if (valueElement) {
    valueElement.dataset.selectValue = "";
  }

  menu.innerHTML = "";
  const optionButtons = Array.from(select.options).map((option, index) => {
    const optionButton = document.createElement("button");
    optionButton.type = "button";
    optionButton.id = `${select.id}-custom-option-${index}`;
    optionButton.dataset.value = option.value;
    optionButton.className = "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-800 transition hover:bg-slate-50 focus:bg-slate-50 focus:outline-none";
    optionButton.setAttribute("role", "option");
    optionButton.innerHTML = `
      ${customSelectIcon(select, option.value)}
      <span class="flex-1 whitespace-nowrap">${customSelectLabel(select, option.value)}</span>
    `;
    optionButton.addEventListener("click", () => {
      setCustomSelectValue(select, option.value);
      closeCustomSelect(wrapper);
      trigger.focus();
    });
    menu.appendChild(optionButton);
    return optionButton;
  });

  customSelects.set(select.id, { wrapper, trigger, menu, select, options: optionButtons });

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleCustomSelect(wrapper);
  });
  trigger.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggleCustomSelect(wrapper);
    } else if (event.key === "Escape") {
      closeCustomSelect(wrapper);
    }
  });
  menu.addEventListener("click", (event) => event.stopPropagation());
  menu.addEventListener('keydown', event => {
    const current = optionButtons.indexOf(document.activeElement);
    if (event.key === 'Escape') { closeCustomSelect(wrapper); trigger.focus(); }
    else if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
      event.preventDefault();
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? optionButtons.length-1 :
        (current + (event.key === 'ArrowDown' ? 1 : -1) + optionButtons.length) % optionButtons.length;
      optionButtons[index].focus();
    }
  });
  trigger.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); openCustomSelect(wrapper);
      optionButtons[Math.max(0,select.selectedIndex)].focus();
    }
  });

  syncCustomSelect(select);
}

function initCustomSelects() {
  [language, theme, sampleSelect].forEach(initCustomSelect);
  form.addEventListener("click", () => {
    customSelects.forEach(({ wrapper }) => closeCustomSelect(wrapper));
  });
}

function schedulePreview(delay = 450) {
  window.clearTimeout(refreshTimer);
  statusPill.textContent = "Editing";
  scheduleHighlight();
  refreshTimer = window.setTimeout(() => {
    statusPill.textContent = "Rendering";
    htmx.trigger(previewTrigger, "refreshPreview");
  }, delay);
}

function scheduleHighlight() {
  const version = ++highlightVersion;
  clearTimeout(highlightTimer);
  highlightRequest?.abort();
  highlightTimer = setTimeout(async () => {
    const controller = new AbortController();
    highlightRequest = controller;
    try {
      const response = await fetch('/highlight', { method: 'POST', body: new FormData(form), signal: controller.signal });
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      if (version !== highlightVersion || !codeEditor) return;
      const styles = new Map();
      codeEditor.operation(() => {
        syntaxMarks.forEach(mark => mark.clear()); syntaxMarks = [];
        data.lines.forEach((tokens, line) => {
          let ch = 0;
          for (const token of tokens) {
            const start = ch; ch += token.content.length;
            if (!token.content) continue;
            const key = `${token.color}:${token.fontStyle}`;
            if (!styles.has(key)) styles.set(key, { name: `shiki-${styles.size}`, token });
            syntaxMarks.push(codeEditor.markText({line, ch:start}, {line, ch}, { className: styles.get(key).name }));
          }
        });
      });
      tokenStyles.textContent = [...styles.values()].map(({name,token}) =>
        `#editor .${name}{color:${token.color};font-style:${token.fontStyle&1?'italic':'normal'};font-weight:${token.fontStyle&2?'700':'400'};text-decoration:${token.fontStyle&4?'underline':'none'}}`).join('\n');
      const wrapper = codeEditor.getWrapperElement();
      wrapper.style.setProperty('--source-bg', data.background);
      wrapper.style.setProperty('--source-fg', data.foreground);
      wrapper.style.setProperty('--source-muted', data.colors['editorLineNumber.foreground'] || data.foreground);
      document.getElementById('syntax-engine').textContent = `${languageLabels[data.language] || data.language} · ${data.theme} · TextMate`;
    } catch(error) {
      if (error.name !== 'AbortError' && version === highlightVersion) statusPill.textContent = error.message || 'Highlighting unavailable';
    }
  }, 200);
}

function playback(action, extra = {}) {
  document.querySelector('#preview-panel iframe')?.contentWindow.postMessage({type:'typing:command', action, ...extra}, '*');
}
function receivePlayback(event) {
  if (event.source !== document.querySelector('#preview-panel iframe')?.contentWindow || event.data?.type !== 'typing:state') return;
  const state = event.data;
  const button = document.getElementById('preview-play');
  button.textContent = state.playing ? 'Pause' : 'Play';
  button.setAttribute('aria-label', state.playing ? 'Pause animation' : 'Play animation');
  document.getElementById('preview-scrubber').value = String(state.time/state.duration*1000);
  document.getElementById('preview-time').textContent = `${(state.time/1000).toFixed(1)} / ${(state.duration/1000).toFixed(1)}s`;
}
window.addEventListener('message', receivePlayback);
document.getElementById('preview-play').addEventListener('click', () => playback('toggle'));
document.getElementById('preview-restart').addEventListener('click', () => playback('restart'));
document.getElementById('replay-action').addEventListener('click', () => playback('restart'));
const previewScrubber = document.getElementById('preview-scrubber');
function scrubPreview(value) {
  previewScrubber.value = String(Math.max(0, Math.min(1000, value)));
  playback('seek', { progress: Number(previewScrubber.value)/1000 });
}
previewScrubber.addEventListener('input', event => scrubPreview(Number(event.target.value)));
previewScrubber.addEventListener('keydown', event => {
  const current = Number(previewScrubber.value);
  const values = {Home:0, End:1000, ArrowLeft:current-10, ArrowRight:current+10, ArrowDown:current-10, ArrowUp:current+10};
  if (event.key in values) { event.preventDefault(); scrubPreview(values[event.key]); }
});
previewScrubber.addEventListener('click', event => {
  if (!event.detail) return;
  const bounds = previewScrubber.getBoundingClientRect();
  scrubPreview((event.clientX-bounds.left)/bounds.width*1000);
});

function fitPreview() {
  const ratios = { display:[700,300], '16_9':[1280,720], '9_16':[720,1280], '1_1':[1080,1080], '4_5':[1080,1350], '4_3':[1024,768] };
  const [w,h] = ratios[aspectRatio.value] || ratios['16_9'];
  const panel = document.getElementById('preview-panel');
  panel.style.aspectRatio = `${w}/${h}`;
  document.querySelector('.studio-preview-wrap').style.maxWidth = `${Math.min(920, 580*w/h)}px`;
}
aspectRatio.addEventListener('change', fitPreview);

form.addEventListener('submit', async event => {
  const button = event.submitter;
  if (!button?.formAction.includes('/download/')) return;
  event.preventDefault();
  const label = button.textContent;
  const buttons = [...form.querySelectorAll('button[type="submit"]')];
  buttons.forEach(item => item.disabled = true);
  button.textContent = 'Rendering…'; statusPill.textContent = 'Rendering export…';
  try {
    const response = await fetch(button.formAction, {method:'POST', body:new FormData(form)});
    if (!response.ok) throw new Error(await response.text());
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] || 'code-animation';
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    statusPill.textContent = 'Export ready';
  } catch(error) { statusPill.textContent = error.message || 'Export failed'; }
  finally { buttons.forEach(item => item.disabled = false); button.textContent = label; }
});

function loadSample(sampleName) {
  const sample = samples[sampleName];
  if (!sample) {
    return;
  }

  code.value = sample.code;
  setCodeEditorValue(sample.code);
  language.value = sample.language;
  title.value = `${sampleName.toLowerCase().replaceAll(" ", "-")}.${fileExtension(sample.language)}`;
  updateHeroControls();
  schedulePreview(80);
}

form.querySelectorAll("input, select, textarea, [form='studio-form']").forEach((control) => {
  if (control.closest('.studio-transport')) return;
  control.addEventListener("input", () => {
    updateHeroControls();
    schedulePreview(control === code ? 650 : 300);
  });
  control.addEventListener("change", () => {
    updateHeroControls();
    schedulePreview(120);
  });
});

sampleSelect.addEventListener("change", () => loadSample(sampleSelect.value));

form.addEventListener("htmx:afterSwap", (event) => {
  if (event.detail.target.id === "preview-panel") {
    statusPill.textContent = "Ready";
  }
});

form.addEventListener("htmx:responseError", (event) => {
  statusPill.textContent = event.detail.xhr?.responseText || "Preview could not be rendered";
});

initCustomSelects();
initCodeEditor();
updateHeroControls();
fitPreview();
scheduleHighlight();

}

document.addEventListener("htmx:load", initCodeStudio);
initCodeStudio();
