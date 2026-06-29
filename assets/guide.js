const tabButtons = document.querySelectorAll("[data-tab-target]");
const tabPanels = document.querySelectorAll("[data-tab-panel]");
const mediaButtons = document.querySelectorAll("[data-zoom-src]");
const modal = document.getElementById("imageModal");
const modalImage = document.getElementById("imageModalImage");
const modalTitle = document.getElementById("imageModalTitle");
const modalClose = document.getElementById("imageModalClose");

function setActiveTab(target) {
  tabButtons.forEach((button) => {
    const active = button.dataset.tabTarget === target;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });

  tabPanels.forEach((panel) => {
    panel.hidden = panel.dataset.tabPanel !== target;
  });
}

function closeModal() {
  if (!modal) return;
  modal.classList.remove("show");
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  modalImage.removeAttribute("src");
  modalImage.alt = "";
}

function openModal(src, title, alt) {
  if (!modal) return;
  modalImage.src = src;
  modalImage.alt = alt || title || "教程截图";
  modalTitle.textContent = title || "教程截图";
  modal.classList.add("show");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => setActiveTab(button.dataset.tabTarget));
});

mediaButtons.forEach((button) => {
  button.addEventListener("click", () => {
    openModal(button.dataset.zoomSrc, button.dataset.zoomTitle, button.dataset.zoomAlt);
  });
});

if (modalClose) {
  modalClose.addEventListener("click", closeModal);
}

if (modal) {
  modal.addEventListener("click", (event) => {
    if (event.target.hasAttribute("data-modal-close")) {
      closeModal();
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeModal();
  }
});

if (tabButtons.length) {
  setActiveTab(tabButtons[0].dataset.tabTarget);
}
