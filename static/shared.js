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
