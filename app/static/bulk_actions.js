(() => {
  const scanButton = document.querySelector("[data-scan]");
  const scanStatus = document.getElementById("scan-status");

  if (scanButton && scanStatus) {
    scanButton.addEventListener("click", async () => {
      scanButton.disabled = true;
      scanStatus.textContent = "Scanning...";
      try {
        const response = await fetch("/scan", { method: "POST" });
        if (!response.ok) {
          throw new Error(`Scan failed: ${response.status}`);
        }
        const result = await response.json();
        scanStatus.textContent = `Indexed ${result.indexed} files at ${result.scanned_at}`;
      } catch (error) {
        scanStatus.textContent = "Scan failed. Check server logs.";
      } finally {
        scanButton.disabled = false;
      }
    });
  }

  const cleanTagsButton = document.querySelector("[data-clean-tags]");
  const cleanTagsStatus = document.getElementById("clean-tags-status");
  const clearTagsButton = document.querySelector("[data-clear-tags]");
  const clearTagsStatus = document.getElementById("clear-tags-status");
  const clearDatabaseButton = document.querySelector("[data-clear-database]");
  const clearDatabaseStatus = document.getElementById("clear-database-status");

  if (cleanTagsButton && cleanTagsStatus) {
    cleanTagsButton.addEventListener("click", async () => {
      cleanTagsButton.disabled = true;
      cleanTagsStatus.textContent = "Cleaning...";
      try {
        const response = await fetch("/bulk-actions/cleanup-tags", { method: "POST" });
        if (!response.ok) {
          throw new Error("Cleanup failed.");
        }
        const result = await response.json();
        cleanTagsStatus.textContent = `Removed ${result.removed} unused tags.`;
      } catch (error) {
        cleanTagsStatus.textContent = "Cleanup failed. Check server logs.";
      } finally {
        cleanTagsButton.disabled = false;
      }
    });
  }


  if (clearTagsButton && clearTagsStatus) {
    clearTagsButton.addEventListener("click", async () => {
      const confirmed = window.confirm("Delete all tags and book-tag links?");
      if (!confirmed) return;
      clearTagsButton.disabled = true;
      clearTagsStatus.textContent = "Clearing...";
      try {
        const response = await fetch("/bulk-actions/clear-tags", { method: "POST" });
        if (!response.ok) {
          throw new Error("Clear failed.");
        }
        const result = await response.json();
        clearTagsStatus.textContent =
          `Removed ${result.removed_tags} tags and ${result.removed_links} links.`;
      } catch (error) {
        clearTagsStatus.textContent = "Clear failed. Check server logs.";
      } finally {
        clearTagsButton.disabled = false;
      }
    });
  }

  if (clearDatabaseButton && clearDatabaseStatus) {
    clearDatabaseButton.addEventListener("click", async () => {
      const confirmed = window.confirm(
        "Clear the entire database? This removes all books, tags, and activity logs."
      );
      if (!confirmed) return;
      clearDatabaseButton.disabled = true;
      clearDatabaseStatus.textContent = "Clearing...";
      try {
        const response = await fetch("/bulk-actions/clear-database", { method: "POST" });
        if (!response.ok) {
          throw new Error("Clear failed.");
        }
        clearDatabaseStatus.textContent = "Database cleared.";
      } catch (error) {
        clearDatabaseStatus.textContent = "Clear failed. Check server logs.";
      } finally {
        clearDatabaseButton.disabled = false;
      }
    });
  }
})();
