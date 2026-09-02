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
  if (!modal) return;

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
  if (!modal) return;

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
  if (!activeModal) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeModal();
    return;
  }
  if (event.key !== "Tab") return;

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

const pageTitles = {
  "/": "Coduxum",
  "/code-typer": "Code Typer — Coduxum",
  "/code-diff": "Code Diff — Coduxum",
  "/code-scroll": "Code Scroll — Coduxum",
  "/terminal": "Terminal Simulator — Coduxum",
};

function normalizedPagePath(pathname = window.location.pathname) {
  const cleanPath = pathname.replace(/\/+$/, "");
  return cleanPath || "/";
}

function updateActiveNavigation(pathname = window.location.pathname) {
  const currentPath = normalizedPagePath(pathname);
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    const linkPath = normalizedPagePath(new URL(link.href, window.location.origin).pathname);
    const isActive = linkPath === currentPath;
    link.classList.toggle("text-blue-600", isActive);
    link.classList.toggle("font-bold", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function updatePageTitle(responseText = "") {
  if (responseText) {
    const responseDocument = new DOMParser().parseFromString(responseText, "text/html");
    const responseTitle = responseDocument.querySelector("title")?.textContent?.trim();
    if (responseTitle) {
      document.title = responseTitle;
      return;
    }
  }
  document.title = pageTitles[normalizedPagePath()] || "Coduxum";
}

if (window.htmx) {
  htmx.config.globalViewTransitions = true;
  htmx.config.historyCacheSize = 10;
  htmx.config.scrollIntoViewOnBoost = false;
}

document.body.addEventListener("htmx:beforeRequest", (event) => {
  if (event.detail.target?.id !== "page-content") return;
  document.getElementById("page-content")?.setAttribute("aria-busy", "true");
  document.querySelector("header details[open]")?.removeAttribute("open");
});

document.body.addEventListener("htmx:beforeSwap", (event) => {
  if (event.detail.target?.id !== "page-content" || event.detail.shouldSwap === false) return;
  window.cleanupCodeStudio?.();
  window.cleanupCodeDiffStudio?.();
  window.cleanupTerminalStudio?.();
});

document.body.addEventListener("htmx:afterSwap", (event) => {
  if (event.detail.target?.id !== "page-content") return;

  const pageContent = document.getElementById("page-content");
  pageContent?.removeAttribute("aria-busy");
  updatePageTitle(event.detail.xhr?.responseText || "");
  const requestedPath = event.detail.requestConfig?.path;
  const activePath = requestedPath
    ? new URL(requestedPath, window.location.origin).pathname
    : window.location.pathname;
  updateActiveNavigation(activePath);

  const pageHeading = pageContent?.querySelector("h1");
  if (pageHeading) {
    pageHeading.setAttribute("tabindex", "-1");
    pageHeading.focus({ preventScroll: true });
  }
});

document.body.addEventListener("htmx:responseError", (event) => {
  if (event.detail.target?.id !== "page-content") return;
  document.getElementById("page-content")?.removeAttribute("aria-busy");
});

document.body.addEventListener("htmx:historyRestore", () => {
  updatePageTitle();
  updateActiveNavigation();
  window.initCodeStudio?.();
  window.initCodeDiffStudio?.();
  window.initTerminalStudio?.();
});

updateActiveNavigation();
