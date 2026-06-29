const mediaButtons = Array.from(document.querySelectorAll("[data-zoom-src]"));
const modal = document.getElementById("imageModal");
const modalImage = document.getElementById("imageModalImage");
const modalTitle = document.getElementById("imageModalTitle");
const modalClose = document.getElementById("imageModalClose");
const modalPrev = document.getElementById("imageModalPrev");
const modalNext = document.getElementById("imageModalNext");
const revealNodes = document.querySelectorAll(".reveal-on-scroll");
const spyNodes = document.querySelectorAll("[data-spy]");
const tocLinks = document.querySelectorAll(".toc-panel a");
const progressBar = document.getElementById("scrollProgressBar");

let activeMediaIndex = -1;

function openModalByIndex(index) {
  if (!modal || !modalImage || !mediaButtons[index]) return;

  const button = mediaButtons[index];
  activeMediaIndex = index;
  modalImage.src = button.dataset.zoomSrc;
  modalImage.alt = button.dataset.zoomAlt || button.dataset.zoomTitle || "教程截图";
  modalTitle.textContent = button.dataset.zoomTitle || "教程截图";
  modal.classList.add("show");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeModal() {
  if (!modal || !modalImage) return;

  modal.classList.remove("show");
  modal.setAttribute("aria-hidden", "true");
  modalImage.removeAttribute("src");
  modalImage.alt = "";
  document.body.classList.remove("modal-open");
  activeMediaIndex = -1;
}

function moveModal(step) {
  if (activeMediaIndex < 0 || !mediaButtons.length) return;

  const nextIndex = (activeMediaIndex + step + mediaButtons.length) % mediaButtons.length;
  openModalByIndex(nextIndex);
}

function setActiveTocLink(id) {
  tocLinks.forEach((link) => {
    link.classList.toggle("active", link.getAttribute("href") === `#${id}`);
  });
}

function updateScrollProgress() {
  if (!progressBar) return;

  const root = document.documentElement;
  const maxScroll = root.scrollHeight - window.innerHeight;
  const ratio = maxScroll > 0 ? window.scrollY / maxScroll : 0;
  progressBar.style.width = `${Math.min(Math.max(ratio, 0), 1) * 100}%`;
}

mediaButtons.forEach((button, index) => {
  button.addEventListener("click", () => {
    openModalByIndex(index);
  });
});

if (modalClose) {
  modalClose.addEventListener("click", closeModal);
}

if (modalPrev) {
  modalPrev.addEventListener("click", () => moveModal(-1));
}

if (modalNext) {
  modalNext.addEventListener("click", () => moveModal(1));
}

if (modal) {
  modal.addEventListener("click", (event) => {
    if (event.target.hasAttribute("data-modal-close")) {
      closeModal();
    }
  });
}

document.addEventListener("keydown", (event) => {
  if (!modal || !modal.classList.contains("show")) {
    if (event.key === "Escape") closeModal();
    return;
  }

  if (event.key === "Escape") {
    closeModal();
  } else if (event.key === "ArrowLeft") {
    moveModal(-1);
  } else if (event.key === "ArrowRight") {
    moveModal(1);
  }
});

if (revealNodes.length) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.14 }
  );

  revealNodes.forEach((node) => revealObserver.observe(node));
}

if (spyNodes.length) {
  const spyObserver = new IntersectionObserver(
    (entries) => {
      const visibleEntries = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);

      if (visibleEntries[0]) {
        setActiveTocLink(visibleEntries[0].target.id);
      }
    },
    {
      threshold: [0.2, 0.4, 0.65],
      rootMargin: "-18% 0px -45% 0px",
    }
  );

  spyNodes.forEach((node) => spyObserver.observe(node));
  setActiveTocLink(spyNodes[0].id);
}

window.addEventListener("scroll", updateScrollProgress, { passive: true });
window.addEventListener("resize", updateScrollProgress);
updateScrollProgress();
