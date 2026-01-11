(() => {
  const openModals = new Set();

  const getModal = (id) => document.querySelector(`[data-modal-id="${id}"]`);
  const setBodyLock = (locked) => {
    document.body.style.overflow = locked ? "hidden" : "";
  };

  const open = (id) => {
    const modal = getModal(id);
    if (!modal) return;
    modal.removeAttribute("hidden");
    openModals.add(id);
    setBodyLock(true);
  };

  const close = (id) => {
    const modal = getModal(id);
    if (!modal) return;
    modal.setAttribute("hidden", "");
    openModals.delete(id);
    if (openModals.size === 0) {
      setBodyLock(false);
    }
  };

  const closeAll = () => {
    Array.from(openModals).forEach((id) => close(id));
  };

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented) return;
    const openButton = event.target.closest("[data-modal-open]");
    if (openButton) {
      open(openButton.dataset.modalOpen);
      return;
    }
    const closeButton = event.target.closest("[data-modal-close]");
    if (closeButton) {
      const modal = closeButton.closest("[data-modal-id]");
      if (modal) {
        close(modal.dataset.modalId);
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const lastOpened = Array.from(openModals).pop();
    if (lastOpened) {
      close(lastOpened);
    }
  });

  window.ModalController = { open, close, closeAll };
})();
