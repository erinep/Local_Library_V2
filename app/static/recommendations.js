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
        const checked = group.querySelector("input[type='checkbox']:checked");
        isActive = !!checked;
      }
      group.toggleAttribute("data-active", isActive);
    });
  };

  recForm.addEventListener("change", updateGroupHighlights);
  recForm.addEventListener("topicchange", updateGroupHighlights);
  updateGroupHighlights();
})();
