(() => {
  // SSE parser shared by metadata flows.
  const parseEventStream = async (response, onEvent) => {
    const reader = response.body?.getReader();
    if (!reader) {
      const fallbackText = await response.text();
      if (fallbackText && onEvent) {
        onEvent("message", { status: fallbackText });
      }
      return;
    }
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r/g, "");
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      parts.forEach((block) => {
        const lines = block.split("\n").filter((line) => line.trim().length > 0);
        let eventName = "message";
        const dataLines = [];
        lines.forEach((line) => {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
            return;
          }
          if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
          }
        });
        const payloadText = dataLines.join("\n").trim();
        let payload = {};
        if (payloadText) {
          try {
            payload = JSON.parse(payloadText);
          } catch (error) {
            payload = { status: "Malformed event payload." };
            eventName = "error";
          }
        }
        if (onEvent) {
          onEvent(eventName, payload);
        }
      });
    }
    if (buffer.trim() && onEvent) {
      onEvent("message", { status: buffer.trim() });
    }
  };

  const createLogRenderer = (logElement) => {
    const entries = new Map();
    const reset = () => {
      if (logElement) {
        logElement.innerHTML = "";
      }
      entries.clear();
    };
    const scrollToBottom = () => {
      if (!logElement) return;
      requestAnimationFrame(() => {
        logElement.scrollTop = logElement.scrollHeight;
      });
    };
    const render = (eventType, payload) => {
      if (!logElement) return;
      const stepId = payload.step_id || payload.action || eventType;
      let entry = entries.get(stepId);
      if (!entry) {
        entry = document.createElement("div");
        entry.className = "metadata-ai-log-entry";
        const header = document.createElement("div");
        header.className = "metadata-ai-log-header";
        const title = document.createElement("span");
        title.className = "metadata-ai-log-title";
        title.textContent = payload.action || payload.status || eventType;
        header.appendChild(title);
        entry.appendChild(header);
        const reasoningEl = document.createElement("div");
        reasoningEl.className = "metadata-ai-log-reasoning";
        entry.appendChild(reasoningEl);
        const outputWrap = document.createElement("div");
        outputWrap.className = "metadata-ai-log-outputs";
        entry.appendChild(outputWrap);
        logElement.appendChild(entry);
        entries.set(stepId, entry);
      }
      const reasoningEl = entry.querySelector(".metadata-ai-log-reasoning");
      const outputWrap = entry.querySelector(".metadata-ai-log-outputs");
      if (reasoningEl) {
        const text = payload.reasoning ? `Reasoning: ${payload.reasoning}` : "";
        reasoningEl.textContent = text;
        reasoningEl.toggleAttribute("hidden", !text);
      }
      if (outputWrap) {
        if (eventType === "begin") {
          outputWrap.innerHTML = "";
        } else if (eventType === "result") {
          outputWrap.innerHTML = "";
          if (payload.description) {
            const line = document.createElement("div");
            line.className = "metadata-ai-log-output-line";
            line.textContent = payload.description;
            outputWrap.appendChild(line);
          }
          if (payload.value) {
            const line = document.createElement("div");
            line.className = "metadata-ai-log-output-line";
            line.textContent = payload.value;
            outputWrap.appendChild(line);
          }
        }
      }
      scrollToBottom();
    };
    const appendLine = (text) => {
      if (!logElement) return;
      const entry = document.createElement("div");
      entry.className = "metadata-ai-log-entry";
      const output = document.createElement("div");
      output.className = "metadata-ai-log-output-line";
      output.textContent = text;
      entry.appendChild(output);
      logElement.appendChild(entry);
      scrollToBottom();
    };
    return { reset, render, appendLine };
  };

  // Search provider metadata for a given book.
  const searchMetadata = async ({ bookId, title, author, signal }) => {
    const response = await fetch(`/books/${bookId}/metadata/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, author }),
      signal,
    });
    if (!response.ok) {
      throw new Error("Search failed.");
    }
    return response.json();
  };

  // Pick the highest confidence result (fallback to first).
  const selectBestResult = (results) => {
    if (!Array.isArray(results) || results.length === 0) return null;
    let best = results[0];
    let bestScore = typeof best.overall_confidence === "number" ? best.overall_confidence : -1;
    results.forEach((result) => {
      const score = typeof result.overall_confidence === "number" ? result.overall_confidence : -1;
      if (score > bestScore) {
        bestScore = score;
        best = result;
      }
    });
    return best;
  };

  // Prepare tags/description for review using the provider result payload.
  const prepareMetadata = async ({ bookId, result, signal }) => {
    const response = await fetch(`/books/${bookId}/metadata/prepare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        result_id: result.result_id,
        title: result.title,
        author: result.author,
        categories: result.categories || [],
        description: result.description || "",
        source: result.source || "google_books",
      }),
      signal,
    });
    if (!response.ok) {
      throw new Error("Failed to prepare metadata.");
    }
    return response.json();
  };

  // Run AI cleanup stream and return aggregated tags + description.
  const runAiCleanStream = async ({ bookId, description, onEvent, signal }) => {
    const response = await fetch(`/books/${bookId}/metadata/ai_clean/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description }),
      signal,
    });
    if (!response.ok) {
      throw new Error("AI clean failed.");
    }
    const tags = new Set();
    let cleanedDescription = description || "";
    await parseEventStream(response, (eventName, payload) => {
      if (payload.description) {
        cleanedDescription = String(payload.description);
      }
      if (Array.isArray(payload.tags)) {
        payload.tags.forEach((tag) => {
          const cleaned = String(tag).trim();
          if (cleaned) tags.add(cleaned);
        });
      }
      if (payload.value) {
        const cleaned = String(payload.value).trim();
        if (cleaned) tags.add(cleaned);
      }
      if (onEvent) {
        onEvent(eventName, payload);
      }
    });
    return { description: cleanedDescription, tags: Array.from(tags) };
  };

  const runAiCleanupFlow = async ({
    bookId,
    description,
    logRenderer,
    setStatus,
    onDescription,
    onTags,
    onDone,
    onError,
    descWrap,
    applyButton,
    spinner,
  }) => {
    const raw = description || "";
    if (setStatus) setStatus("Running AI cleanup...");
    if (descWrap) descWrap.classList.add("is-loading");
    if (applyButton) applyButton.disabled = true;
    if (spinner) spinner.removeAttribute("hidden");
    if (logRenderer) logRenderer.reset();
    try {
      await runAiCleanStream({
        bookId,
        description: raw,
        onEvent: (eventName, payload) => {
          if (logRenderer && (eventName === "begin" || eventName === "result")) {
            logRenderer.render(eventName, payload);
          }
          if (payload.description && onDescription) {
            onDescription(String(payload.description));
          }
          if (payload.tags && onTags) {
            onTags(payload.tags);
          }
          if (eventName === "error" && payload.detail) {
            if (logRenderer) {
              logRenderer.render(eventName, { ...payload, reasoning: payload.detail });
            }
            if (onError) onError(payload.detail);
            if (spinner) spinner.setAttribute("hidden", "");
          }
          if (eventName === "done") {
            if (setStatus) setStatus("AI updates ready for review.");
            if (spinner) spinner.setAttribute("hidden", "");
            if (onDone) onDone();
          }
        },
      });
    } catch (error) {
      if (setStatus) setStatus("Unable to run AI cleanup.");
      if (logRenderer) logRenderer.appendLine("AI request failed.");
      if (spinner) spinner.setAttribute("hidden", "");
    }
  };

  // Apply tags and description to a book record.
  const applyMetadata = async ({
    bookId,
    tags,
    description,
    source,
    rawDescription,
    descriptionRewritten,
    signal,
  }) => {
    const response = await fetch(`/books/${bookId}/metadata/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tags,
        description,
        source,
        raw_description: rawDescription,
        description_rewritten: !!descriptionRewritten,
      }),
      signal,
    });
    if (!response.ok) {
      throw new Error("Apply failed.");
    }
    return response.json();
  };

  window.MetadataWorkflow = {
    searchMetadata,
    selectBestResult,
    prepareMetadata,
    runAiCleanStream,
    applyMetadata,
    createLogRenderer,
    runAiCleanupFlow,
  };
})();
