(() => {
  const recForm = document.querySelector(".recommendations-form");
  if (!recForm) return;

  const updateGroupHighlights = () => {
    const groups = recForm.querySelectorAll("[data-rec-group]");
    const topicBadges = recForm.querySelector("[data-topic-badges]");
    groups.forEach((group) => {
      const isTopicGroup = group.hasAttribute("data-rec-topic");
      let isActive = false;
      if (isTopicGroup) {
        isActive = !!(topicBadges && topicBadges.querySelector("input[name='topic_id']"));
      } else {
        const checked = group.querySelector("input[type='checkbox']:checked, input[type='radio']:checked");
        const minSlider = group.querySelector("[data-range-min]");
        const maxSlider = group.querySelector("[data-range-max]");
        const hasRange = minSlider && maxSlider
          ? minSlider.value !== "0" || maxSlider.value !== "1"
          : false;
        isActive = !!checked || hasRange;
      }
      group.toggleAttribute("data-active", isActive);
    });
  };

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  const syncRangeGroup = (group) => {
    const minSlider = group.querySelector("[data-range-min]");
    const maxSlider = group.querySelector("[data-range-max]");
    const minHidden = group.querySelector("[data-range-hidden-min]");
    const maxHidden = group.querySelector("[data-range-hidden-max]");
    const fill = group.querySelector("[data-range-fill]");
    const minDisplay = group.querySelector("[data-range-display='min']");
    const maxDisplay = group.querySelector("[data-range-display='max']");
    if (!minSlider || !maxSlider || !minHidden || !maxHidden || !fill) return;

    const minValue = clamp(parseFloat(minSlider.value), 0, 1);
    const maxValue = clamp(parseFloat(maxSlider.value), 0, 1);
    const start = Math.min(minValue, maxValue);
    const end = Math.max(minValue, maxValue);

    minSlider.value = start;
    maxSlider.value = end;
    const minText = start.toFixed(2).replace(/\.00$/, "");
    const maxText = end.toFixed(2).replace(/\.00$/, "");
    minHidden.value = minText;
    maxHidden.value = maxText;
    if (minDisplay) minDisplay.textContent = minText;
    if (maxDisplay) maxDisplay.textContent = maxText;

    fill.style.setProperty("--range-start", start);
    fill.style.setProperty("--range-end", end);
  };

  const initRangeSliders = () => {
    const groups = recForm.querySelectorAll(".rec-group-range");
    groups.forEach((group) => {
      syncRangeGroup(group);
      group.addEventListener("input", (event) => {
        if (event.target.matches("[data-range-min], [data-range-max]")) {
          syncRangeGroup(group);
          updateGroupHighlights();
        }
      });
    });
  };

  recForm.addEventListener("change", updateGroupHighlights);
  recForm.addEventListener("topicchange", updateGroupHighlights);
  updateGroupHighlights();
  initRangeSliders();
})();
