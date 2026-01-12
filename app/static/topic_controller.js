(() => {
  const normalizeText = (value) => value.toLowerCase().trim();

  const initTopicSelector = (input) => {
    const form = input.closest("form");
    const container = input.closest(".rec-group-topics") || form || document;
    const suggest = container.querySelector("[data-topic-suggest]");
    const badges = form ? form.querySelector("[data-topic-badges]") : null;
    const addButton = container.querySelector("[data-topic-add]");
    let activeIndex = -1;

    const clearActive = () => {
      if (!suggest) return;
      suggest.querySelectorAll(".topic-suggest-item").forEach((item) => {
        item.classList.remove("is-active");
      });
      activeIndex = -1;
    };

    const visibleItems = () => {
      if (!suggest) return [];
      return Array.from(suggest.querySelectorAll(".topic-suggest-item:not([hidden])"));
    };

    const openSuggest = () => {
      if (suggest) {
        suggest.removeAttribute("hidden");
      }
    };

    const closeSuggest = () => {
      if (suggest) {
        suggest.setAttribute("hidden", "");
      }
      clearActive();
    };

    const filterSuggestions = () => {
      if (!input || !suggest) return;
      const query = normalizeText(input.value);
      let visible = 0;
      suggest.querySelectorAll(".topic-suggest-item").forEach((item) => {
        const label = item.dataset.topicLabel || "";
        const matches = !query || normalizeText(label).includes(query);
        item.toggleAttribute("hidden", !matches);
        if (matches) {
          visible += 1;
        }
      });
      clearActive();
      if (visible > 0) {
        openSuggest();
      } else {
        closeSuggest();
      }
    };

    const emitChange = () => {
      if (form) {
        form.dispatchEvent(new CustomEvent("topicchange", { bubbles: true }));
      }
    };

    const addBadge = (topicId, label) => {
      if (!badges || !topicId) return;
      if (badges.querySelector(`[data-topic-id='${topicId}']`)) {
        return;
      }
      const pill = document.createElement("div");
      pill.className = "tag-pill";
      pill.dataset.topicId = topicId;

      const text = document.createElement("span");
      text.textContent = label;

      const remove = document.createElement("button");
      remove.className = "tag-remove";
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove topic ${label}`);
      remove.textContent = "x";
      remove.addEventListener("click", () => {
        pill.remove();
        emitChange();
      });

      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "topic_id";
      hidden.value = topicId;

      pill.appendChild(text);
      pill.appendChild(remove);
      pill.appendChild(hidden);
      badges.appendChild(pill);
      emitChange();
    };

    if (badges) {
      badges.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        if (!target.classList.contains("tag-remove")) return;
        const pill = target.closest(".tag-pill");
        if (!pill) return;
        pill.remove();
        emitChange();
      });
    }

    const selectItem = (item) => {
      if (!item) return;
      const label = item.dataset.topicLabel || "";
      const id = item.dataset.topicId || "";
      if (badges) {
        addBadge(id, label);
      } else if (form && input) {
        input.value = label;
        form.submit();
      }
      if (input) {
        input.value = "";
        input.focus();
      }
      closeSuggest();
    };

    input.addEventListener("focus", filterSuggestions);
    input.addEventListener("input", filterSuggestions);
    input.addEventListener("keydown", (event) => {
      if (!suggest) return;
      const items = visibleItems();
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!items.length) return;
        if (event.key === "ArrowDown") {
          activeIndex = (activeIndex + 1) % items.length;
        } else {
          activeIndex = (activeIndex - 1 + items.length) % items.length;
        }
        items.forEach((item) => item.classList.remove("is-active"));
        const current = items[activeIndex];
        current.classList.add("is-active");
        current.scrollIntoView({ block: "nearest" });
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const active = suggest.querySelector(".topic-suggest-item.is-active");
        const fallback = items[0];
        if (active || fallback) {
          selectItem(active || fallback);
        } else if (form) {
          form.submit();
        }
      }
      if (event.key === "Escape") {
        closeSuggest();
      }
    });

    if (suggest) {
      suggest.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        if (!target.dataset.topicLabel) return;
        selectItem(target);
      });
    }

    if (addButton) {
      addButton.addEventListener("click", () => {
        if (!input || !suggest) return;
        const query = normalizeText(input.value);
        if (!query) return;
        const match = Array.from(suggest.querySelectorAll(".topic-suggest-item")).find((item) => {
          const label = item.dataset.topicLabel || "";
          return normalizeText(label) === query;
        });
        if (match) {
          selectItem(match);
        }
      });
    }

    document.addEventListener("click", (event) => {
      if (!suggest || !input) return;
      const target = event.target;
      if (target === input || container.contains(target)) {
        return;
      }
      closeSuggest();
    });
  };

  const inputs = document.querySelectorAll("[data-topic-input]");
  inputs.forEach((input) => {
    const container = input.closest(".rec-group-topics") || input.closest("form");
    if (!container) return;
    if (!container.querySelector("[data-topic-suggest]")) return;
    initTopicSelector(input);
  });
})();
