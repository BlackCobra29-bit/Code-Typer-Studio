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
const languageCatalog = JSON.parse(document.getElementById("language-catalog").textContent);
const samples = JSON.parse(document.getElementById("sample-data").textContent);

let refreshTimer = null;
let codeEditor = null;
const customSelects = new Map();
const modalTriggers = document.querySelectorAll("[data-modal-open]");
const modals = document.querySelectorAll("[data-modal]");
let activeModal = null;
let modalTrigger = null;

function modalFocusableElements(modal) {
  return Array.from(
    modal.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'),
  ).filter((element) => !element.hidden);
}

function openModal(modalId, trigger) {
  const modal = document.getElementById(modalId);
  if (!modal) {
    return;
  }

  activeModal = modal;
  modalTrigger = trigger;
  trigger.closest("details")?.removeAttribute("open");
  modal.classList.remove("hidden");
  modal.classList.add("flex");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("overflow-hidden");

  window.requestAnimationFrame(() => {
    modal.querySelector("[data-modal-backdrop]").classList.remove("opacity-0");
    const panel = modal.querySelector("[data-modal-panel]");
    panel.classList.remove("scale-95", "opacity-0");
    modalFocusableElements(modal)[0]?.focus();
  });
}

function closeModal(modal = activeModal) {
  if (!modal) {
    return;
  }

  modal.querySelector("[data-modal-backdrop]").classList.add("opacity-0");
  modal.querySelector("[data-modal-panel]").classList.add("scale-95", "opacity-0");
  modal.setAttribute("aria-hidden", "true");

  window.setTimeout(() => {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    if (activeModal === modal) {
      activeModal = null;
      document.body.classList.remove("overflow-hidden");
      modalTrigger?.focus();
      modalTrigger = null;
    }
  }, 200);
}

modalTriggers.forEach((trigger) => {
  trigger.addEventListener("click", () => openModal(trigger.dataset.modalOpen, trigger));
});

modals.forEach((modal) => {
  modal.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(modal));
  });
  modal.querySelector("[data-modal-backdrop]").addEventListener("click", () => closeModal(modal));
});

document.addEventListener("keydown", (event) => {
  if (!activeModal) {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeModal();
    return;
  }
  if (event.key !== "Tab") {
    return;
  }

  const focusable = modalFocusableElements(activeModal);
  if (focusable.length === 0) {
    event.preventDefault();
    activeModal.querySelector("[data-modal-panel]").focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});

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
}

function codeEditorMode() {
  return codeMirrorModes[language.value] || "javascript";
}

function syncCodeEditorMode() {
  if (!codeEditor) {
    return;
  }

  codeEditor.setOption("mode", codeEditorMode());
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
    mode: codeEditorMode(),
    theme: "light-studio",
    lineNumbers: true,
    lineWrapping: true,
    indentUnit: 2,
    tabSize: 2,
    viewportMargin: Infinity,
  });

  codeEditor.on("change", () => {
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

  syncCustomSelect(select);
}

function initCustomSelects() {
  [language, theme, sampleSelect].forEach(initCustomSelect);
  document.addEventListener("click", () => {
    customSelects.forEach(({ wrapper }) => closeCustomSelect(wrapper));
  });
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
  setCodeEditorValue(sample.code);
  language.value = sample.language;
  title.value = `${sampleName.toLowerCase().replaceAll(" ", "-")}.${fileExtension(sample.language)}`;
  updateHeroControls();
  schedulePreview(80);
}

document.querySelectorAll("#studio-form input, #studio-form select, #studio-form textarea, [form='studio-form']").forEach((control) => {
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

document.body.addEventListener("htmx:afterSwap", (event) => {
  if (event.detail.target.id === "preview-panel") {
    statusPill.textContent = "Ready";
  }
});

document.body.addEventListener("htmx:responseError", () => {
  statusPill.textContent = "Error";
});

initCustomSelects();
initCodeEditor();
updateHeroControls();
