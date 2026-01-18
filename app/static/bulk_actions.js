(() => {
  const scanButton = document.querySelector("[data-scan]");
  const scanStatus = document.getElementById("scan-status");
  const bulkMetadataButton = document.querySelector("[data-bulk-metadata]");
  const bulkMetadataStatus = document.getElementById("bulk-metadata-status");
  const metadataProcessingModal = document.querySelector("[data-modal-id='metadata-processing']");
  const metadataAiLog = metadataProcessingModal
    ? metadataProcessingModal.querySelector("[data-metadata-ai-log]")
    : null;
  const metadataAiContinue = metadataProcessingModal
    ? metadataProcessingModal.querySelector("[data-metadata-ai-continue]")
    : null;
  const metadataAiSpinner = metadataProcessingModal
    ? metadataProcessingModal.querySelector("[data-metadata-ai-spinner]")
    : null;
  const bulkMetadataCancel = metadataProcessingModal
    ? metadataProcessingModal.querySelector("[data-bulk-metadata-cancel]")
    : null;

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

  const logRenderer = window.MetadataWorkflow
    ? window.MetadataWorkflow.createLogRenderer(metadataAiLog)
    : null;

  const openProcessingModal = () => {
    if (window.ModalController) {
      window.ModalController.open("metadata-processing");
    }
  };

  const closeProcessingModal = () => {
    if (window.ModalController) {
      window.ModalController.close("metadata-processing");
    }
  };

  if (metadataAiContinue) {
    metadataAiContinue.addEventListener("click", () => {
      closeProcessingModal();
    });
  }

  if (bulkMetadataButton && bulkMetadataStatus) {
    bulkMetadataButton.addEventListener("click", async () => {
      bulkMetadataButton.disabled = true;
      bulkMetadataStatus.textContent = "Starting...";
      let cancelled = false;
      const controller = new AbortController();
      if (bulkMetadataCancel) {
        bulkMetadataCancel.disabled = false;
      }
      if (logRenderer) {
        logRenderer.reset();
      }
      if (metadataAiContinue) {
        metadataAiContinue.setAttribute("hidden", "");
      }
      if (metadataAiSpinner) {
        metadataAiSpinner.removeAttribute("hidden");
      }
      openProcessingModal();
      if (bulkMetadataCancel) {
        bulkMetadataCancel.onclick = () => {
          cancelled = true;
          controller.abort();
          bulkMetadataStatus.textContent = "Cancelled.";
          if (logRenderer) {
            logRenderer.appendLine("Cancelled by user.");
          }
          if (metadataAiSpinner) {
            metadataAiSpinner.setAttribute("hidden", "");
          }
          if (metadataAiContinue) {
            metadataAiContinue.removeAttribute("hidden");
          }
        };
      }
      try {
        const response = await fetch("/bulk-actions/metadata/books");
        if (!response.ok) {
          throw new Error("Failed to load books.");
        }
        const books = await response.json();
        for (let index = 0; index < books.length; index += 1) {
          if (cancelled) break;
          const book = books[index];
          bulkMetadataStatus.textContent = `Processing ${index + 1} of ${books.length}`;
          if (logRenderer) {
            logRenderer.appendLine(`Book ${book.id}: ${book.title}`);
          }
          const results = await window.MetadataWorkflow.searchMetadata({
            bookId: book.id,
            title: book.title,
            author: book.author,
            signal: controller.signal,
          });
          if (cancelled) break;
          const best = window.MetadataWorkflow.selectBestResult(results);
          if (!best) {
            if (logRenderer) {
              logRenderer.appendLine("No metadata results.");
            }
            continue;
          }
          const prepared = await window.MetadataWorkflow.prepareMetadata({
            bookId: book.id,
            result: best,
            signal: controller.signal,
          });
          if (cancelled) break;
          const rawDescription = prepared.description || best.description || "";
          const baseTags = Array.isArray(prepared.tags) ? prepared.tags : [];
          const aiResult = await window.MetadataWorkflow.runAiCleanStream({
            bookId: book.id,
            description: rawDescription,
            onEvent: (eventName, payload) => {
              if (!logRenderer) return;
              if (eventName === "begin" || eventName === "result") {
                logRenderer.render(eventName, payload);
              }
              if (eventName === "error" && payload.detail) {
                logRenderer.appendLine(`ERROR ${payload.detail}`);
              }
            },
            signal: controller.signal,
          });
          if (cancelled) break;
          const mergedTags = Array.from(new Set([...baseTags, ...aiResult.tags]));
          const cleanedDescription = aiResult.description || rawDescription || null;
          await window.MetadataWorkflow.applyMetadata({
            bookId: book.id,
            tags: mergedTags,
            description: cleanedDescription,
            source: best.source || "google_books",
            rawDescription,
            descriptionRewritten: cleanedDescription && cleanedDescription !== rawDescription,
            signal: controller.signal,
          });
          if (logRenderer) {
            logRenderer.appendLine("Applied metadata.");
          }
        }
        if (!cancelled) {
          bulkMetadataStatus.textContent = "Complete.";
        }
        if (metadataAiSpinner) {
          metadataAiSpinner.setAttribute("hidden", "");
        }
        if (metadataAiContinue) {
          metadataAiContinue.removeAttribute("hidden");
        }
      } catch (error) {
        if (!cancelled) {
          bulkMetadataStatus.textContent = "Failed. Check server logs.";
          if (logRenderer) {
            logRenderer.appendLine("Bulk metadata failed.");
          }
        }
        if (metadataAiSpinner) {
          metadataAiSpinner.setAttribute("hidden", "");
        }
        if (metadataAiContinue) {
          metadataAiContinue.removeAttribute("hidden");
        }
      } finally {
        bulkMetadataButton.disabled = false;
        if (bulkMetadataCancel) {
          bulkMetadataCancel.disabled = true;
        }
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
