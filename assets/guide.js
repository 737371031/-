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
const anchorLinks = document.querySelectorAll('a[href^="#"]');

let activeMediaIndex = -1;
let isAnchorScrolling = false;
let anchorScrollTimer = 0;

function normalizeHash(hash) {
  if (!hash || hash === "#") return "";
  return hash.startsWith("#") ? hash : `#${hash}`;
}

function getAnchorOffset() {
  const pageHeader = document.querySelector(".page-header");
  const headerHeight = pageHeader?.getBoundingClientRect().height || 0;

  return Math.ceil(headerHeight + 18);
}

function scrollToAnchor(hash, shouldPushState = true) {
  const normalizedHash = normalizeHash(hash);
  const id = decodeURIComponent(normalizedHash.replace(/^#/, ""));
  const target = id ? document.getElementById(id) : null;
  if (!target) return;

  const alignTarget = () => {
    const offset = getAnchorOffset();
    const top = target.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top: Math.max(top, 0), behavior: "auto" });
    updateScrollProgress();
  };

  isAnchorScrolling = true;
  window.clearTimeout(anchorScrollTimer);
  setActiveTocLink(id);
  alignTarget();

  if (shouldPushState) {
    history.pushState(null, "", normalizedHash);
  }

  requestAnimationFrame(() => {
    alignTarget();
    anchorScrollTimer = window.setTimeout(() => {
      alignTarget();
      isAnchorScrolling = false;
    }, 180);
  });
}

function settleAnchorScroll(hash, shouldPushState = true) {
  const normalizedHash = normalizeHash(hash);
  if (!normalizedHash) return;

  scrollToAnchor(normalizedHash, shouldPushState);

  [90, 280, 700].forEach((delay) => {
    window.setTimeout(() => {
      if (window.location.hash === normalizedHash) {
        scrollToAnchor(normalizedHash, false);
      }
    }, delay);
  });
}

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

anchorLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    const hash = link.getAttribute("href");
    if (!hash || hash === "#") return;

    event.preventDefault();
    settleAnchorScroll(hash);
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

if (revealNodes.length && "IntersectionObserver" in window) {
  document.documentElement.classList.add("reveal-motion");
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
  window.setTimeout(() => {
    revealNodes.forEach((node) => node.classList.add("is-visible"));
  }, 900);
} else {
  revealNodes.forEach((node) => node.classList.add("is-visible"));
}

if (spyNodes.length && "IntersectionObserver" in window) {
  const spyObserver = new IntersectionObserver(
    (entries) => {
      const visibleEntries = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);

      if (visibleEntries[0]) {
        if (isAnchorScrolling) return;
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
window.addEventListener("hashchange", () => {
  if (window.location.hash) {
    settleAnchorScroll(window.location.hash, false);
  }
});

window.addEventListener("load", () => {
  if (window.location.hash) {
    settleAnchorScroll(window.location.hash, false);
  }
});

updateScrollProgress();

if (window.location.hash) {
  window.setTimeout(() => settleAnchorScroll(window.location.hash, false), 80);
}
