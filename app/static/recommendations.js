(() => {
  const recForm = document.querySelector(".recommendations-form");
  const topicInput = document.querySelector("[data-topic-input]");
  const topicAddButton = document.querySelector("[data-topic-add]");
  const topicBadges = document.querySelector("[data-topic-badges]");
  const topicSuggest = document.querySelector("[data-topic-suggest]");
  let activeSuggestIndex = -1;

  const addTopicBadge = (topicId, label) => {
    if (!topicBadges) return;
    if (topicBadges.querySelector(`[data-topic-id='${topicId}']`)) {
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
      updateGroupHighlights();
    });

    const input = document.createElement("input");
    input.type = "hidden";
    input.name = "topic_id";
    input.value = topicId;

    pill.appendChild(text);
    pill.appendChild(remove);
    pill.appendChild(input);
    topicBadges.appendChild(pill);
  };

  const normalizeText = (value) => value.toLowerCase().trim();

  const handleAddTopic = (topicId, label) => {
    if (!topicId || !label) {
      return;
    }
    addTopicBadge(topicId, label);
    updateGroupHighlights();
    if (topicInput) {
      topicInput.value = "";
    }
    if (topicSuggest) {
      topicSuggest.setAttribute("hidden", "");
    }
  };

  const filterSuggestions = () => {
    if (!topicInput || !topicSuggest) return;
    const query = normalizeText(topicInput.value);
    const items = topicSuggest.querySelectorAll(".topic-suggest-item");
    let visible = 0;
    items.forEach((item) => {
      const label = item.dataset.topicLabel || "";
      const matches = !query || normalizeText(label).includes(query);
      item.toggleAttribute("hidden", !matches);
      if (matches) {
        visible += 1;
      }
    });
    activeSuggestIndex = -1;
    items.forEach((item) => item.classList.remove("is-active"));
    if (visible > 0) {
      topicSuggest.removeAttribute("hidden");
    } else {
      topicSuggest.setAttribute("hidden", "");
    }
  };

  const updateGroupHighlights = () => {
    if (!recForm) return;
    const groups = recForm.querySelectorAll("[data-rec-group]");
    groups.forEach((group) => {
      const isTopicGroup = group.hasAttribute("data-rec-topic");
      let isActive = false;
      if (isTopicGroup) {
        isActive = !!(topicBadges && topicBadges.querySelector("input[name='topic_id']"));
      } else {
        const checked = group.querySelector("input[type='checkbox']:checked");
        isActive = !!checked;
      }
      group.toggleAttribute("data-active", isActive);
    });
  };

  if (recForm) {
    recForm.addEventListener("change", () => {
      updateGroupHighlights();
    });
    updateGroupHighlights();
  }

  if (topicInput) {
    topicInput.addEventListener("focus", filterSuggestions);
    topicInput.addEventListener("input", filterSuggestions);
    topicInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        const active = topicSuggest?.querySelector(".topic-suggest-item.is-active");
        const fallback = topicSuggest?.querySelector(".topic-suggest-item:not([hidden])");
        const chosen = active || fallback;
        if (chosen) {
          handleAddTopic(chosen.dataset.topicId, chosen.dataset.topicLabel || "");
        }
        return;
      }
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!topicSuggest) return;
        const items = Array.from(topicSuggest.querySelectorAll(".topic-suggest-item:not([hidden])"));
        if (!items.length) return;
        if (event.key === "ArrowDown") {
          activeSuggestIndex = (activeSuggestIndex + 1) % items.length;
        } else {
          activeSuggestIndex = (activeSuggestIndex - 1 + items.length) % items.length;
        }
        items.forEach((item) => item.classList.remove("is-active"));
        const current = items[activeSuggestIndex];
        current.classList.add("is-active");
        current.scrollIntoView({ block: "nearest" });
      }
    });
  }

  if (topicSuggest) {
    topicSuggest.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (!target.dataset.topicId) {
        return;
      }
      handleAddTopic(target.dataset.topicId, target.dataset.topicLabel || "");
    });
  }

  if (topicAddButton) {
    topicAddButton.addEventListener("click", () => {
      if (!topicInput || !topicSuggest) return;
      const query = normalizeText(topicInput.value);
      if (!query) return;
      const match = Array.from(topicSuggest.querySelectorAll(".topic-suggest-item")).find((item) => {
        const label = item.dataset.topicLabel || "";
        return normalizeText(label) === query;
      });
      if (match) {
        handleAddTopic(match.dataset.topicId, match.dataset.topicLabel || "");
      }
    });
  }

  document.addEventListener("click", (event) => {
    if (!topicSuggest) return;
    if (!topicInput) return;
    const target = event.target;
    if (target === topicInput || topicSuggest.contains(target)) {
      return;
    }
    topicSuggest.setAttribute("hidden", "");
  });
})();
