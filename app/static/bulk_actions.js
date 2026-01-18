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
      let cancelRequested = false;
      let activeJobId = null;
      let eventSource = null;
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
        bulkMetadataCancel.onclick = async () => {
          if (!activeJobId) return;
          cancelRequested = true;
          bulkMetadataCancel.disabled = true;
          bulkMetadataStatus.textContent = "Cancelling...";
          try {
            await fetch(`/bulk-actions/metadata/jobs/${activeJobId}`, { method: "DELETE" });
          } catch (error) {
            // Ignore cancel errors; status poll will reflect outcome.
          }
        };
      }
      try {
        const response = await fetch("/bulk-actions/metadata/jobs", { method: "POST" });
        if (!response.ok) {
          throw new Error("Failed to start job.");
        }
        const payload = await response.json();
        activeJobId = payload.job_id;
        const totalBooks = payload.total_books || 0;
        bulkMetadataStatus.textContent = "Queued.";
        if (logRenderer) {
          logRenderer.appendLine(`Job ${activeJobId} queued.`);
        }
        bulkMetadataStatus.textContent = "Running...";
        eventSource = new EventSource(`/bulk-actions/metadata/jobs/${activeJobId}/stream`);
        const updateProgress = (details) => {
          const processed = Number(details.processed || 0);
          if (totalBooks > 0 && processed > 0) {
            bulkMetadataStatus.textContent = `Processing ${processed} of ${totalBooks}`;
          }
        };
        eventSource.addEventListener("book_completed", (event) => {
          if (!logRenderer) return;
          try {
            const payload = JSON.parse(event.data);
            const details = payload.payload || {};
            updateProgress(details);
            const selected = details.selected || {};
            const title = details.title || "Untitled";
            const author = details.author || "Unknown author";
            const picked = selected.title ? ` -> ${selected.title}` : "";
            logRenderer.appendLine(`Completed ${title} by ${author}${picked}`);
          } catch (error) {
            logRenderer.appendLine("Completed a book.");
          }
        });
        eventSource.addEventListener("book_failed", (event) => {
          if (!logRenderer) return;
          try {
            const payload = JSON.parse(event.data);
            const details = payload.payload || {};
            updateProgress(details);
            const title = details.title || "Untitled";
            const author = details.author || "Unknown author";
            const errorText = details.error ? ` (${details.error})` : "";
            logRenderer.appendLine(`Failed ${title} by ${author}${errorText}`);
          } catch (error) {
            logRenderer.appendLine("Failed a book.");
          }
        });
        eventSource.addEventListener("done", (event) => {
          let finalStatus = "completed";
          try {
            const payload = JSON.parse(event.data);
            finalStatus = payload.status || "completed";
          } catch (error) {
            finalStatus = "completed";
          }
          if (finalStatus === "completed") {
            bulkMetadataStatus.textContent = "Complete.";
          } else if (finalStatus === "failed") {
            bulkMetadataStatus.textContent = "Failed. Check server logs.";
          } else if (finalStatus === "cancelled") {
            bulkMetadataStatus.textContent = "Cancelled.";
          }
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          if (metadataAiSpinner) {
            metadataAiSpinner.setAttribute("hidden", "");
          }
          if (metadataAiContinue) {
            metadataAiContinue.removeAttribute("hidden");
          }
          if (bulkMetadataCancel) {
            bulkMetadataCancel.disabled = true;
          }
          bulkMetadataButton.disabled = false;
        });
        eventSource.onerror = () => {
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }
          bulkMetadataStatus.textContent = "Stream disconnected.";
          if (logRenderer) {
            logRenderer.appendLine("Bulk metadata stream disconnected.");
          }
          if (metadataAiSpinner) {
            metadataAiSpinner.setAttribute("hidden", "");
          }
          if (metadataAiContinue) {
            metadataAiContinue.removeAttribute("hidden");
          }
          bulkMetadataButton.disabled = false;
          if (bulkMetadataCancel) {
            bulkMetadataCancel.disabled = true;
          }
        };
      } catch (error) {
        if (!cancelRequested) {
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
        bulkMetadataButton.disabled = false;
        if (bulkMetadataCancel) {
          bulkMetadataCancel.disabled = true;
        }
      } finally {
        if (bulkMetadataStatus.textContent === "Starting...") {
          bulkMetadataButton.disabled = false;
          if (bulkMetadataCancel) {
            bulkMetadataCancel.disabled = true;
          }
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
