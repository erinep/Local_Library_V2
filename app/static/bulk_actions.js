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

  const bulkTagsButton = document.querySelector("[data-bulk-tags]");
  const bulkModal = document.querySelector("[data-modal-id='bulk-tags']");
  const bulkCloseButtons = bulkModal ? bulkModal.querySelectorAll("[data-modal-close]") : [];
  const bulkStopButton = bulkModal ? bulkModal.querySelector("[data-bulk-stop]") : null;
  const bulkStatus = bulkModal ? bulkModal.querySelector("[data-bulk-status]") : null;
  const bulkTitle = bulkModal ? bulkModal.querySelector("[data-bulk-title]") : null;
  const bulkAuthor = bulkModal ? bulkModal.querySelector("[data-bulk-author]") : null;
  const bulkSearchParams = bulkModal ? bulkModal.querySelector("[data-bulk-search-params]") : null;
  const bulkCurrentTags = bulkModal ? bulkModal.querySelector("[data-bulk-current-tags]") : null;
  const bulkResults = bulkModal ? bulkModal.querySelector("[data-bulk-results]") : null;
  const bulkTagsPreview = bulkModal ? bulkModal.querySelector("[data-bulk-tags]") : null;
  const bulkSearchButton = bulkModal ? bulkModal.querySelector("[data-bulk-search]") : null;
  const bulkSkipButton = bulkModal ? bulkModal.querySelector("[data-bulk-skip]") : null;
  const bulkAddButton = bulkModal ? bulkModal.querySelector("[data-bulk-add]") : null;
  const cleanTagsButton = document.querySelector("[data-clean-tags]");
  const cleanTagsStatus = document.getElementById("clean-tags-status");
  const normalizeAuthorsButton = document.querySelector("[data-normalize-authors]");
  const normalizeAuthorsStatus = document.getElementById("normalize-authors-status");
  const normalizeTitlesButton = document.querySelector("[data-normalize-titles]");
  const normalizeTitlesStatus = document.getElementById("normalize-titles-status");
  const clearTagsButton = document.querySelector("[data-clear-tags]");
  const clearTagsStatus = document.getElementById("clear-tags-status");
  const clearDatabaseButton = document.querySelector("[data-clear-database]");
  const clearDatabaseStatus = document.getElementById("clear-database-status");

  let bulkBooks = [];
  let bulkIndex = 0;
  let bulkSelectedResultId = null;
  let bulkSelectedTags = [];
  let bulkStopped = false;
  let bulkRunning = false;

  const bulkOpenModal = () => {
    if (window.ModalController) {
      window.ModalController.open("bulk-tags");
    }
  };

  const bulkCloseModal = () => {
    if (window.ModalController) {
      window.ModalController.close("bulk-tags");
    }
  };

  const bulkClearResults = () => {
    if (bulkResults) {
      bulkResults.innerHTML = "";
    }
    if (bulkTagsPreview) {
      bulkTagsPreview.innerHTML = "";
    }
    bulkSelectedResultId = null;
    bulkSelectedTags = [];
    if (bulkAddButton) bulkAddButton.disabled = true;
  };

  const bulkSetStatus = (text) => {
    if (bulkStatus) bulkStatus.textContent = text;
  };

  const bulkRenderCurrentTags = (tags) => {
    if (!bulkCurrentTags) return;
    bulkCurrentTags.innerHTML = "";
    if (!tags || tags.length === 0) {
      bulkCurrentTags.innerHTML = '<p class="note">No tags yet.</p>';
      return;
    }
    tags.forEach((tag) => {
      const pill = document.createElement("div");
      pill.className = "tag-pill";
      const label = document.createElement("span");
      label.textContent = tag;
      pill.appendChild(label);
      bulkCurrentTags.appendChild(pill);
    });
  };

  const bulkUpdateSelectedTags = () => {
    if (!bulkTagsPreview) {
      return;
    }
    const selected = Array.from(
      bulkTagsPreview.querySelectorAll("input[type='checkbox']:checked")
    ).map((input) => input.value);
    bulkSelectedTags = selected;
    if (bulkAddButton) bulkAddButton.disabled = bulkSelectedTags.length === 0;
  };

  const bulkRenderTags = (tags) => {
    if (!bulkTagsPreview) return;
    bulkTagsPreview.innerHTML = "";
    if (!tags.length) {
      bulkTagsPreview.innerHTML = '<p class="note">No tags returned.</p>';
      return;
    }
    tags.forEach((tag) => {
      const wrapper = document.createElement("label");
      wrapper.className = "tag-pill tag-pill-proposed";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = tag.tag_text;
      checkbox.checked = true;
      checkbox.addEventListener("change", bulkUpdateSelectedTags);
      const label = document.createElement("span");
      label.textContent = tag.tag_text;
      wrapper.appendChild(checkbox);
      wrapper.appendChild(label);
      bulkTagsPreview.appendChild(wrapper);
    });
    bulkUpdateSelectedTags();
  };

  const bulkRenderResults = (results) => {
    if (!bulkResults) return;
    bulkResults.innerHTML = "";
    if (!results.length) {
      bulkSetStatus("No results found. Search again or skip.");
      return;
    }
    bulkSetStatus("Select a result to fetch tags.");
    results.forEach((result) => {
      const item = document.createElement("div");
      item.className = "list-item";
      item.dataset.resultId = result.result_id;

      const info = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = result.title || "Untitled";
      const author = document.createElement("div");
      author.className = "note";
      author.textContent = result.author || "Unknown author";
      info.appendChild(title);
      info.appendChild(author);

      const actions = document.createElement("div");
      const selectButton = document.createElement("button");
      selectButton.className = "btn btn-outline btn-small";
      selectButton.type = "button";
      selectButton.textContent = "Select";
      selectButton.addEventListener("click", () => {
        bulkSelectedResultId = result.result_id;
        const items = bulkResults.querySelectorAll(".list-item");
        items.forEach((node) => node.classList.remove("is-selected"));
        item.classList.add("is-selected");
        bulkSetStatus("Selected. Fetching tags...");
        bulkGetTags();
      });
      actions.appendChild(selectButton);

      item.appendChild(info);
      item.appendChild(actions);
      bulkResults.appendChild(item);
    });
  };

  const bulkShowBook = () => {
    if (bulkIndex >= bulkBooks.length) {
      bulkSetStatus("All books processed.");
      bulkClearResults();
      return;
    }
    const book = bulkBooks[bulkIndex];
    if (bulkTitle) bulkTitle.textContent = book.title || "Untitled";
    if (bulkAuthor) bulkAuthor.textContent = book.author || "Unknown author";
    if (bulkSearchParams) {
      const title = book.normalized_title || book.title || "";
      const author = book.normalized_author || book.author || "";
      const parts = [];
      if (title) parts.push(`Title: ${title}`);
      if (author) parts.push(`Author: ${author}`);
      bulkSearchParams.textContent = parts.length ? `Search params: ${parts.join(" | ")}` : "";
    }
    bulkRenderCurrentTags(book.tags);
    bulkClearResults();
    bulkSetStatus("Search tags or skip this book.");
  };

  const bulkLoadBooks = async () => {
    bulkSetStatus("Loading books...");
    try {
      const response = await fetch("/bulk-actions/books");
      if (!response.ok) {
        throw new Error("Failed to load books.");
      }
      bulkBooks = await response.json();
      bulkIndex = 0;
      bulkStopped = false;
      if (!bulkBooks.length) {
        bulkSetStatus("No books found.");
        return;
      }
      bulkShowBook();
    } catch (error) {
      bulkSetStatus("Unable to load books.");
    }
  };

  const bulkSearchForBook = async (book) => {
    if (!book) return [];
    if (!book.title && !book.author && !book.normalized_title && !book.normalized_author) {
      bulkSetStatus("Missing title and author. Skip this book.");
      return [];
    }
    bulkSetStatus("Searching Google Books...");
    try {
      const params = new URLSearchParams();
      const title = book.normalized_title || book.title;
      const author = book.normalized_author || book.author;
      if (title) params.set("title", title);
      if (author) params.set("author", author);
      const response = await fetch(`/search?${params.toString()}`);
      if (!response.ok) {
        throw new Error("Search failed.");
      }
      const results = await response.json();
      bulkRenderResults(results);
      return results;
    } catch (error) {
      bulkSetStatus("Search failed. Try again or skip.");
      return [];
    }
  };

  const bulkGetTags = async () => {
    if (!bulkSelectedResultId) {
      bulkSetStatus("Select a result first.");
      return [];
    }
    bulkSetStatus("Loading tags...");
    try {
      const response = await fetch(`/search/${encodeURIComponent(bulkSelectedResultId)}/tags`);
      if (!response.ok) {
        throw new Error("Tags failed.");
      }
      const tags = await response.json();
      bulkRenderTags(tags);
      bulkSetStatus("Select tags, then add to book.");
      return tags;
    } catch (error) {
      bulkSetStatus("Unable to load tags.");
      return [];
    }
  };

  const bulkAddTagsToBook = async (bookId, tags) => {
    if (!tags.length) {
      bulkSetStatus("No tags to add.");
      return false;
    }
    bulkSetStatus("Adding tags...");
    const formData = new FormData();
    formData.set("tags", tags.join(", "));
    try {
      const response = await fetch(`/books/${bookId}/tags`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error("Add tags failed.");
      }
      return true;
    } catch (error) {
      bulkSetStatus("Unable to add tags.");
      return false;
    }
  };

  const bulkAddTags = async () => {
    const book = bulkBooks[bulkIndex];
    if (!book || !bulkSelectedTags.length) {
      bulkSetStatus("No tags to add.");
      return;
    }
    if (bulkAddButton) bulkAddButton.disabled = true;
    const added = await bulkAddTagsToBook(book.book_id, bulkSelectedTags);
    if (added) {
      bulkIndex += 1;
      bulkAdvanceLoop();
    }
  };

  const bulkAdvanceLoop = async () => {
    if (bulkRunning) return;
    bulkRunning = true;
    while (bulkIndex < bulkBooks.length) {
      if (bulkStopped) break;
      const book = bulkBooks[bulkIndex];
      if (book.tags && book.tags.length > 0) {
        bulkIndex += 1;
        continue;
      }
      bulkShowBook();
      const results = await bulkSearchForBook(book);
      if (bulkStopped) break;
      if (!results.length) {
        bulkSetStatus("No results found. Moving to next book...");
        bulkIndex += 1;
        continue;
      }
      bulkSetStatus("Select a result to fetch tags.");
      bulkRunning = false;
      return;
    }
    bulkRunning = false;
    if (!bulkStopped) {
      bulkSetStatus("Bulk tagging complete.");
      bulkClearResults();
      try {
        await fetch("/bulk-actions/complete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: "completed", processed: bulkIndex, total: bulkBooks.length }),
        });
      } catch (error) {
        // Ignore logging errors for completion.
      }
    }
  };

  const bulkSkipBook = () => {
    bulkIndex += 1;
    bulkAdvanceLoop();
  };

  const bulkStop = () => {
    bulkStopped = true;
    bulkRunning = false;
    try {
      fetch("/bulk-actions/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "stopped", processed: bulkIndex, total: bulkBooks.length }),
      });
    } catch (error) {
      // Ignore logging errors for stop.
    }
    bulkCloseModal();
  };

  if (bulkTagsButton && bulkModal) {
    bulkTagsButton.addEventListener("click", () => {
      bulkOpenModal();
      bulkLoadBooks().then(() => {
        if (!bulkStopped) {
          bulkAdvanceLoop();
        }
      });
    });
  }

  if (bulkSearchButton) {
    bulkSearchButton.addEventListener("click", async () => {
      await bulkSearchForBook(bulkBooks[bulkIndex]);
    });
  }

  if (bulkSkipButton) {
    bulkSkipButton.addEventListener("click", bulkSkipBook);
  }

  if (bulkAddButton) {
    bulkAddButton.addEventListener("click", bulkAddTags);
  }

  if (bulkStopButton) {
    bulkStopButton.addEventListener("click", bulkStop);
  }

  bulkCloseButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      bulkCloseModal();
    });
  });

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

  if (normalizeAuthorsButton && normalizeAuthorsStatus) {
    normalizeAuthorsButton.addEventListener("click", async () => {
      normalizeAuthorsButton.disabled = true;
      normalizeAuthorsStatus.textContent = "Normalizing...";
      try {
        const response = await fetch("/bulk-actions/normalize-authors", { method: "POST" });
        if (!response.ok) {
          throw new Error("Normalize failed.");
        }
        const result = await response.json();
        normalizeAuthorsStatus.textContent = `Normalized ${result.normalized} authors.`;
      } catch (error) {
        normalizeAuthorsStatus.textContent = "Normalize failed. Check server logs.";
      } finally {
        normalizeAuthorsButton.disabled = false;
      }
    });
  }

  if (normalizeTitlesButton && normalizeTitlesStatus) {
    normalizeTitlesButton.addEventListener("click", async () => {
      normalizeTitlesButton.disabled = true;
      normalizeTitlesStatus.textContent = "Normalizing...";
      try {
        const response = await fetch("/bulk-actions/normalize-titles", { method: "POST" });
        if (!response.ok) {
          throw new Error("Normalize failed.");
        }
        const result = await response.json();
        normalizeTitlesStatus.textContent = `Normalized ${result.normalized} titles.`;
      } catch (error) {
        normalizeTitlesStatus.textContent = "Normalize failed. Check server logs.";
      } finally {
        normalizeTitlesButton.disabled = false;
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
