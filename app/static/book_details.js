(() => { 
    const clearDescriptionButton = document.querySelector("[data-clear-description]");
    const descriptionBox = document.querySelector("[data-description-text]");
    const descriptionStatus = document.querySelector("[data-description-status]");
    const topicInput = document.querySelector("[data-topic-input]");
    const topicSuggest = document.querySelector("[data-topic-suggest]");
    const topicForm = document.querySelector("[data-topic-form]");
    const setStatus = (text) => {
        if (!descriptionStatus) return;
        descriptionStatus.textContent = text;
        if (text) {
            descriptionStatus.removeAttribute("hidden");
        } else {
            descriptionStatus.setAttribute("hidden", "");
        }
    };
    const setDescriptionStatus = (text) => {
        if (!descriptionStatus) return;
        descriptionStatus.textContent = text;
        if (text) {
            descriptionStatus.removeAttribute("hidden");
        } else {
            descriptionStatus.setAttribute("hidden", "");
        }
    };

    const readResponseDetail = async (response) => {
        try {
            const payload = await response.json();
            if (payload && typeof payload.detail === "string") {
                return payload.detail;
            }
        } catch (error) {
            // Ignore invalid JSON responses.
        }
        return "";
    };

    const normalizeText = (value) => value.toLowerCase().trim();

    const filterTopicSuggestions = () => {
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
        if (visible > 0) {
            topicSuggest.removeAttribute("hidden");
        } else {
            topicSuggest.setAttribute("hidden", "");
        }
    };

    const submitTopic = (label) => {
        if (!topicInput || !topicForm || !label) return;
        topicInput.value = label;
        topicForm.submit();
    };

    if (topicInput) {
        topicInput.addEventListener("focus", filterTopicSuggestions);
        topicInput.addEventListener("input", filterTopicSuggestions);
    }

    if (topicSuggest) {
        topicSuggest.addEventListener("click", (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }
            if (!target.dataset.topicLabel) {
                return;
            }
            submitTopic(target.dataset.topicLabel);
        });
    }

    document.addEventListener("click", (event) => {
        if (!topicSuggest || !topicInput) return;
        const target = event.target;
        if (target === topicInput || topicSuggest.contains(target)) {
            return;
        }
        topicSuggest.setAttribute("hidden", "");
    });

    if (clearDescriptionButton) {
        clearDescriptionButton.addEventListener("click", async () => {
            const confirmClear = window.confirm(
                "This will delete the description for this book. Continue?"
            );
            if (!confirmClear) {
                return;
            }
            const bookId = clearDescriptionButton.getAttribute("data-book-id");
            if (!bookId || !descriptionBox) return;
            clearDescriptionButton.disabled = true;
            setDescriptionStatus("Clearing the saved description...");
            try {
                const response = await fetch(`/books/${bookId}/description`, {
                    method: "DELETE",
                });
                if (!response.ok) {
                    const detail = await readResponseDetail(response);
                    throw new Error(detail || "Failed to clear description.");
                }
                descriptionBox.innerHTML = '<p class="note">No description yet.</p>';
                setDescriptionStatus("Result: description cleared.");
            } catch (error) {
                setDescriptionStatus(`Clear failed: ${error.message}`);
                clearDescriptionButton.disabled = false;
                return;
            }
            clearDescriptionButton.disabled = true;
        });
    }

    const metadataModal = document.querySelector("[data-modal-id='fetch-metadata']");
    const metadataReviewModal = document.querySelector("[data-modal-id='metadata-review']");
    const metadataProcessingModal = document.querySelector("[data-modal-id='metadata-processing']");
    if (metadataModal && metadataReviewModal && window.MetadataWorkflow) {
        const {
            searchMetadata,
            prepareMetadata,
            runAiCleanupFlow,
            applyMetadata,
            createLogRenderer,
        } = window.MetadataWorkflow;
        const metadataStatus = metadataModal.querySelector("[data-metadata-status]");
        const metadataTitle = metadataModal.querySelector("[data-metadata-title]");
        const metadataAuthor = metadataModal.querySelector("[data-metadata-author]");
        const metadataSearch = metadataModal.querySelector("[data-metadata-search]");
        const metadataResults = metadataModal.querySelector("[data-metadata-results]");
        const metadataTags = metadataReviewModal.querySelector("[data-metadata-tags]");
        const metadataDescription = metadataReviewModal.querySelector("[data-metadata-description]");
        const metadataApply = metadataReviewModal.querySelector("[data-metadata-apply]");
        const metadataDescWrap = metadataReviewModal.querySelector("[data-metadata-desc-wrap]");
        const metadataBack = metadataReviewModal.querySelector("[data-metadata-back]");
        const metadataCancel = metadataReviewModal.querySelector("[data-metadata-cancel]");
        const metadataAiLog = metadataProcessingModal
            ? metadataProcessingModal.querySelector("[data-metadata-ai-log]")
            : null;
        const metadataAiSpinner = metadataProcessingModal
            ? metadataProcessingModal.querySelector("[data-metadata-ai-spinner]")
            : null;
        const logRenderer = createLogRenderer(metadataAiLog);

        let activeResult = null;
        let originalDescription = "";
        let rewrittenDescription = "";
        let activeSource = "google_books";
        let activeBookId = "";

        const setMetadataStatus = (text) => {
            if (!metadataStatus) return;
            metadataStatus.textContent = text;
        };

        const resetMetadataView = () => {
            if (metadataResults) metadataResults.innerHTML = "";
            if (metadataTags) metadataTags.innerHTML = "";
            if (metadataDescription) metadataDescription.value = "";
            originalDescription = "";
            rewrittenDescription = "";
            activeResult = null;
            activeSource = "google_books";
            if (logRenderer) {
                logRenderer.reset();
            }
        };

        const openProcessingModal = () => {
            if (window.ModalController) {
                window.ModalController.open("metadata-processing");
            }
        };

        const openReviewModal = () => {
            if (window.ModalController) {
                window.ModalController.close("metadata-processing");
                window.ModalController.open("metadata-review");
            }
            if (metadataDescWrap) {
                metadataDescWrap.classList.remove("is-loading");
            }
            if (metadataApply) {
                metadataApply.disabled = false;
            }
        };

        const applyTags = (tags) => {
            const list = Array.isArray(tags) ? tags : [];
            if (!list.length || !metadataTags) return;
            const existing = new Set(
                Array.from(metadataTags.querySelectorAll("input[type='checkbox']"))
                    .map((input) => input.value)
            );
            list.forEach((tag) => {
                const cleaned = String(tag).trim();
                if (!cleaned || existing.has(cleaned)) return;
                existing.add(cleaned);
                const pill = document.createElement("label");
                pill.className = "tag-pill tag-pill-proposed";
                const checkbox = document.createElement("input");
                checkbox.type = "checkbox";
                checkbox.checked = true;
                checkbox.value = cleaned;
                const text = document.createElement("span");
                text.textContent = cleaned;
                pill.appendChild(checkbox);
                pill.appendChild(text);
                metadataTags.appendChild(pill);
            });
        };

        const renderResults = (results) => {
            if (!metadataResults) return;
            metadataResults.innerHTML = "";
            if (!results.length) {
                metadataResults.innerHTML = '<p class="note">No results found.</p>';
                return;
            }
            const scored = results
                .map((result, index) => ({ result, index }))
                .filter((entry) => typeof entry.result.overall_confidence === "number");
            const maxConfidence = scored.length
                ? Math.max(...scored.map((entry) => entry.result.overall_confidence))
                : null;
            results.forEach((result) => {
                const item = document.createElement("div");
                item.className = "list-item";
                if (maxConfidence !== null && result.overall_confidence === maxConfidence) {
                    item.classList.add("list-item-best");
                }
                const info = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = result.title || "Untitled";
                const author = document.createElement("div");
                author.className = "note";
                author.textContent = result.author || "Unknown author";
                const confidence = document.createElement("div");
                confidence.className = "note";
                const confidenceText = typeof result.overall_confidence === "number"
                    ? result.overall_confidence.toFixed(2)
                    : "n/a";
                const identityText = typeof result.identity_score === "number"
                    ? result.identity_score.toFixed(2)
                    : "n/a";
                const descScoreText = typeof result.desc_score === "number"
                    ? result.desc_score.toFixed(2)
                    : "n/a";
                confidence.textContent = `OverallConfidence: ${confidenceText} | Identity: ${identityText} | Desc score: ${descScoreText}`;
                const year = document.createElement("div");
                year.className = "note";
                year.textContent = result.published_year ? `Year: ${result.published_year}` : "Year: n/a";
                const isbn = document.createElement("div");
                isbn.className = "note";
                const isbnParts = [];
                if (result.isbn13) {
                    isbnParts.push(`ISBN-13: ${result.isbn13}`);
                }
                if (result.isbn10) {
                    isbnParts.push(`ISBN-10: ${result.isbn10}`);
                }
                isbn.textContent = isbnParts.length ? isbnParts.join(" | ") : "ISBN: n/a";
                const categories = document.createElement("div");
                categories.className = "note";
                const categoryList = result.categories?.length ? result.categories : [];
                const topics = categoryList
                    .flatMap((entry) => String(entry).replace(">", "/").split("/"))
                    .map((part) => part.trim())
                    .filter((part) => part.length > 0);
                const seen = new Set();
                const uniqueTopics = topics.filter((topic) => {
                    const key = topic.toLowerCase();
                    if (seen.has(key)) {
                        return false;
                    }
                    seen.add(key);
                    return true;
                });
                categories.textContent = uniqueTopics.length
                    ? `Topics: ${uniqueTopics.join(", ")}`
                    : "Topics: none";
                const desc = document.createElement("div");
                desc.className = "note";
                desc.textContent = result.description
                    ? `Description: ${result.description.slice(0, 180)}${result.description.length > 180 ? "..." : ""}`
                    : "Description: none";
                info.appendChild(title);
                info.appendChild(author);
                info.appendChild(confidence);
                info.appendChild(year);
                info.appendChild(isbn);
                info.appendChild(categories);
                info.appendChild(desc);

                const actions = document.createElement("div");
                const selectButton = document.createElement("button");
                selectButton.className = "btn btn-outline btn-small";
                selectButton.type = "button";
                selectButton.textContent = "Select";
                selectButton.addEventListener("click", async () => {
                    activeResult = result;
                    activeSource = result.source || "google_books";
                    setMetadataStatus("Preparing metadata for review...");
                    if (window.ModalController) {
                        window.ModalController.close("fetch-metadata");
                        openProcessingModal();
                    }
                    const payload = await prepareMetadata({
                        bookId: activeBookId,
                        result: {
                            ...activeResult,
                            source: activeSource,
                        },
                    }).catch(() => null);
                    if (!payload) {
                        setMetadataStatus("Unable to prepare metadata for review.");
                        return;
                    }
                    if (metadataTags) {
                        metadataTags.innerHTML = "";
                        (payload.tags || []).forEach((tag) => {
                            const pill = document.createElement("label");
                            pill.className = "tag-pill tag-pill-proposed";
                            const checkbox = document.createElement("input");
                            checkbox.type = "checkbox";
                            checkbox.checked = true;
                            checkbox.value = tag;
                            const text = document.createElement("span");
                            text.textContent = tag;
                            pill.appendChild(checkbox);
                            pill.appendChild(text);
                            metadataTags.appendChild(pill);
                        });
                    }
                    originalDescription = payload.description || activeResult.description || "";
                    rewrittenDescription = "";
                    if (metadataDescription) {
                        metadataDescription.value = originalDescription;
                    }
                    setMetadataStatus("Metadata ready for review.");
                    const raw = metadataDescription?.value.trim() || originalDescription || "";
                    await runAiCleanupFlow({
                        bookId: activeBookId,
                        description: raw,
                        logRenderer,
                        setStatus: setMetadataStatus,
                        onDescription: (text) => {
                            rewrittenDescription = text;
                            metadataDescription.value = text;
                        },
                        onTags: applyTags,
                        onDone: openReviewModal,
                        onError: () => {
                            setMetadataStatus("AI cleanup failed.");
                        },
                        descWrap: metadataDescWrap,
                        applyButton: metadataApply,
                        spinner: metadataAiSpinner,
                    });
                });
                actions.appendChild(selectButton);

                item.appendChild(info);
                item.appendChild(actions);
                metadataResults.appendChild(item);
            });
        };

        if (metadataSearch) {
            metadataSearch.addEventListener("click", async () => {
                if (!metadataTitle || !metadataAuthor) return;
                resetMetadataView();
                const titleValue = metadataTitle.value.trim();
                const authorValue = metadataAuthor.value.trim();
                setMetadataStatus("Searching external metadata...");
                try {
                    const results = await searchMetadata({
                        bookId: activeBookId,
                        title: titleValue,
                        author: authorValue,
                    });
                    renderResults(results);
                    setMetadataStatus("Select a result to prepare metadata.");
                } catch (error) {
                    setMetadataStatus("Unable to search metadata provider.");
                }
            });
        }

        if (metadataApply) {
            metadataApply.addEventListener("click", async () => {
                if (!activeBookId) return;
                const tags = metadataTags
                    ? Array.from(metadataTags.querySelectorAll("input[type='checkbox']:checked"))
                        .map((input) => input.value)
                    : [];
                const descriptionValue = metadataDescription?.value || "";
                const rawDescription = originalDescription?.trim() || "";
                const payload = {
                    tags,
                    description: descriptionValue.trim().length ? descriptionValue : null,
                    source: activeSource,
                    description_rewritten: !!rewrittenDescription && descriptionValue === rewrittenDescription,
                    raw_description: rawDescription.length ? rawDescription : null,
                };
                setMetadataStatus("Applying metadata...");
                try {
                    await applyMetadata({
                        bookId: activeBookId,
                        tags: payload.tags,
                        description: payload.description,
                        source: payload.source,
                        rawDescription: payload.raw_description,
                        descriptionRewritten: payload.description_rewritten,
                    });
                    if (window.ModalController) {
                        window.ModalController.close("metadata-review");
                        window.ModalController.close("fetch-metadata");
                    }
                    window.location.reload();
                } catch (error) {
                    setMetadataStatus("Unable to apply metadata.");
                }
            });
        }

        if (metadataBack) {
            metadataBack.addEventListener("click", () => {
                if (window.ModalController) {
                    window.ModalController.close("metadata-review");
                    window.ModalController.open("fetch-metadata");
                }
            });
        }

        if (metadataCancel) {
            metadataCancel.addEventListener("click", () => {
                if (window.ModalController) {
                    window.ModalController.close("metadata-review");
                    window.ModalController.close("fetch-metadata");
                }
            });
        }

        document.addEventListener("click", (event) => {
            const trigger = event.target.closest("[data-modal-open='fetch-metadata']");
            if (!trigger) return;
            activeBookId = trigger.getAttribute("data-metadata-book-id") || "";
            const titleValue = trigger.getAttribute("data-metadata-title") || "";
            const authorValue = trigger.getAttribute("data-metadata-author") || "";
            if (metadataTitle) metadataTitle.value = titleValue;
            if (metadataAuthor) metadataAuthor.value = authorValue;
            resetMetadataView();
            setMetadataStatus("Ready to search.");
        });
    }

    const copyButtons = document.querySelectorAll("[data-copy-path]");
    copyButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            const path = button.getAttribute("data-file-path") || "";
            if (!path) return;
            try {
                if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(path);
                    button.textContent = "Copied";
                    setTimeout(() => {
                        button.textContent = "Copy path";
                    }, 1200);
                }
            } catch (error) {
                // Clipboard access may be blocked; ignore silently.
            }
        });
    });

})();
