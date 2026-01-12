(() => { 
    const descriptionButton = document.querySelector("[data-clean-description]");
    const clearDescriptionButton = document.querySelector("[data-clear-description]");
    const descriptionBox = document.querySelector("[data-description-text]");
    const descriptionStatus = document.querySelector("[data-description-status]");
    const descriptionActions = document.querySelector("[data-description-actions]");
    const descriptionConfirm = document.querySelector("[data-description-confirm]");
    const descriptionAccept = document.querySelector("[data-description-accept]");
    const descriptionReject = document.querySelector("[data-description-reject]");
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

    const getDescriptionPrompt = () => {
        const title = descriptionButton?.getAttribute("data-title") || "";
        const author = descriptionButton?.getAttribute("data-author") || "";
        const parts = [];
        if (title) parts.push(`Title: ${title}`);
        if (author) parts.push(`Author: ${author}`);
        return parts.length ? parts.join(" | ") : "Title: Unknown title | Author: Unknown author";
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

    let originalDescriptionHtml = null;

    const showDescriptionConfirm = (text) => {
        if (!descriptionConfirm || !descriptionBox) return;
        if (originalDescriptionHtml === null) {
            originalDescriptionHtml = descriptionBox.innerHTML;
        }
        descriptionBox.textContent = text;
        descriptionBox.classList.add("is-proposed");
        descriptionConfirm.removeAttribute("hidden");
    };

    const clearDescriptionConfirm = (restore = true) => {
        if (!descriptionConfirm || !descriptionBox) return;
        if (restore && originalDescriptionHtml !== null) {
            descriptionBox.innerHTML = originalDescriptionHtml;
        }
        if (!restore) {
            originalDescriptionHtml = descriptionBox.innerHTML;
        }
        descriptionBox.classList.remove("is-proposed");
        descriptionConfirm.setAttribute("hidden", "");
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

    const getTitle = () => descriptionButton?.getAttribute("data-title") || "";
    const getAuthor = () => descriptionButton?.getAttribute("data-author") || "";

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

    if (descriptionButton) {
        descriptionButton.addEventListener("click", async () => {
        const bookId = descriptionButton.getAttribute("data-book-id");
        if (!bookId || !descriptionBox) return;
        const currentText = descriptionBox.textContent?.trim() || "";
        if (!currentText) {
            setDescriptionStatus("No description to clean.");
            return;
        }
        descriptionButton.disabled = true;
        descriptionActions?.classList.add("is-loading");
        setDescriptionStatus(`Cleaning description. Message sent: ${getDescriptionPrompt()}`);
        try {
            const response = await fetch(`/books/${bookId}/metadata/clean`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    title: getTitle(),
                    author: getAuthor(),
                    description: descriptionBox.textContent || "",
                }),
            });
            if (!response.ok) {
            const detail = await readResponseDetail(response);
            throw new Error(detail || "Failed to clean description.");
            }
            const payload = await response.json();
            const text = payload.description;
            if (text && String(text).toLowerCase() !== "null") {
                showDescriptionConfirm(text);
                setDescriptionStatus(
                    `Result: description cleaned (${text.length} chars). Review the draft below and accept or reject.`
                );
            } else {
                clearDescriptionConfirm();
                setDescriptionStatus(
                    "Result: no description returned. The provider could not clean this description."
                );
            }
        } catch (error) {
            setDescriptionStatus(`Description clean failed: ${error.message}`);
        } finally {
            descriptionActions?.classList.remove("is-loading");
            descriptionButton.disabled = false;
        }
        });
    }

    if (descriptionReject) {
        descriptionReject.addEventListener("click", () => {
            clearDescriptionConfirm();
        });
    }

    if (descriptionAccept) {
        descriptionAccept.addEventListener("click", async () => {
            const bookId = descriptionButton?.getAttribute("data-book-id");
            if (!bookId || !descriptionBox) return;
            const text = descriptionBox.textContent || "";
            if (!text) return;
            descriptionAccept.disabled = true;
            descriptionReject?.setAttribute("disabled", "");
            setDescriptionStatus("Saving accepted description to the library...");
            try {
                const response = await fetch(`/books/${bookId}/description`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ description: text }),
                });
                if (!response.ok) {
                    const detail = await readResponseDetail(response);
                    throw new Error(detail || "Failed to save description.");
                }
                descriptionBox.textContent = text;
                clearDescriptionConfirm(false);
                setDescriptionStatus("Result: description saved.");
                if (clearDescriptionButton) {
                    clearDescriptionButton.disabled = false;
                }
            } catch (error) {
                setDescriptionStatus(`Save failed: ${error.message}`);
            } finally {
                descriptionAccept.disabled = false;
                descriptionReject?.removeAttribute("disabled");
            }
        });
    }

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
                clearDescriptionConfirm(false);
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
    if (metadataModal && metadataReviewModal) {
        const metadataStatus = metadataModal.querySelector("[data-metadata-status]");
        const metadataTitle = metadataModal.querySelector("[data-metadata-title]");
        const metadataAuthor = metadataModal.querySelector("[data-metadata-author]");
        const metadataSearch = metadataModal.querySelector("[data-metadata-search]");
        const metadataResults = metadataModal.querySelector("[data-metadata-results]");
        const metadataReview = metadataReviewModal.querySelector("[data-metadata-review]");
        const metadataTags = metadataReviewModal.querySelector("[data-metadata-tags]");
        const metadataDescription = metadataReviewModal.querySelector("[data-metadata-description]");
        const metadataApply = metadataReviewModal.querySelector("[data-metadata-apply]");
        const metadataChoiceInputs = metadataReviewModal.querySelectorAll("[data-metadata-desc-choice]");
        const metadataClean = metadataReviewModal.querySelector("[data-metadata-clean]");
        const metadataDescWrap = metadataReviewModal.querySelector("[data-metadata-desc-wrap]");
        const metadataBack = metadataReviewModal.querySelector("[data-metadata-back]");
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
            metadataChoiceInputs.forEach((input) => {
                input.checked = input.value === "include";
            });
        };

        const renderResults = (results) => {
            if (!metadataResults) return;
            metadataResults.innerHTML = "";
            if (!results.length) {
                metadataResults.innerHTML = '<p class="note">No results found.</p>';
                return;
            }
            results.forEach((result) => {
                const item = document.createElement("div");
                item.className = "list-item";
                const info = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = result.title || "Untitled";
                const author = document.createElement("div");
                author.className = "note";
                author.textContent = result.author || "Unknown author";
                const year = document.createElement("div");
                year.className = "note";
                year.textContent = result.published_year ? `Year: ${result.published_year}` : "Year: n/a";
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
                info.appendChild(year);
                info.appendChild(categories);
                info.appendChild(desc);

                const actions = document.createElement("div");
                const selectButton = document.createElement("button");
                selectButton.className = "btn btn-outline btn-small";
                selectButton.type = "button";
                selectButton.textContent = "Select";
                selectButton.addEventListener("click", () => {
                    activeResult = result;
                    activeSource = result.source || "google_books";
                    setMetadataStatus("Preparing metadata for review...");
                    if (window.ModalController) {
                        window.ModalController.open("metadata-review");
                        window.ModalController.close("fetch-metadata");
                    }
                    prepareMetadata();
                });
                actions.appendChild(selectButton);

                item.appendChild(info);
                item.appendChild(actions);
                metadataResults.appendChild(item);
            });
        };

        const prepareMetadata = async () => {
            if (!activeResult || !activeBookId) return;
            try {
                const response = await fetch(`/books/${activeBookId}/metadata/prepare`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        result_id: activeResult.result_id,
                        title: activeResult.title,
                        author: activeResult.author,
                        categories: activeResult.categories || [],
                        description: activeResult.description || "",
                        source: activeSource,
                    }),
                });
                if (!response.ok) {
                    throw new Error("Failed to prepare metadata.");
                }
                const payload = await response.json();
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
            } catch (error) {
                setMetadataStatus("Unable to prepare metadata for review.");
            }
        };

        metadataChoiceInputs.forEach((input) => {
            input.addEventListener("change", () => {
                if (!metadataDescription) return;
                if (input.value === "include") {
                    metadataDescription.value = rewrittenDescription || originalDescription;
                } else {
                    metadataDescription.value = "";
                }
            });
        });

        if (metadataSearch) {
            metadataSearch.addEventListener("click", async () => {
                if (!metadataTitle || !metadataAuthor) return;
                resetMetadataView();
                const titleValue = metadataTitle.value.trim();
                const authorValue = metadataAuthor.value.trim();
                setMetadataStatus("Searching external metadata...");
                try {
                    const response = await fetch(`/books/${activeBookId}/metadata/search`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ title: titleValue, author: authorValue }),
                    });
                    if (!response.ok) {
                        throw new Error("Search failed.");
                    }
                    const results = await response.json();
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
                const choice = Array.from(metadataChoiceInputs).find((input) => input.checked)?.value || "none";
                const descriptionValue = metadataDescription?.value || "";
                const payload = {
                    tags,
                    description_choice: choice,
                    description: choice === "none" ? null : descriptionValue,
                    source: activeSource,
                    description_rewritten: !!rewrittenDescription && descriptionValue === rewrittenDescription,
                };
                setMetadataStatus("Applying metadata...");
                try {
                    const response = await fetch(`/books/${activeBookId}/metadata/apply`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                    });
                    if (!response.ok) {
                        throw new Error("Apply failed.");
                    }
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

        if (metadataClean) {
            metadataClean.addEventListener("click", async () => {
                if (!metadataDescription || !activeBookId) return;
                const raw = metadataDescription.value.trim() || originalDescription || "";
                setMetadataStatus("Cleaning description...");
                if (metadataDescWrap) {
                    metadataDescWrap.classList.add("is-loading");
                }
                if (metadataApply) {
                    metadataApply.disabled = true;
                }
                try {
                    const response = await fetch(`/books/${activeBookId}/metadata/clean`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            title: metadataTitle?.value || "",
                            author: metadataAuthor?.value || "",
                            description: raw,
                        }),
                    });
                    if (!response.ok) {
                        throw new Error("Clean failed.");
                    }
                    const payload = await response.json();
                if (payload.description) {
                    rewrittenDescription = payload.description;
                    if (metadataDescription) {
                        metadataDescription.value = payload.description;
                    }
                    metadataChoiceInputs.forEach((input) => {
                        input.checked = input.value === "include";
                    });
                    }
                    setMetadataStatus("Description cleaned.");
                } catch (error) {
                    setMetadataStatus("Unable to clean description.");
                } finally {
                    if (metadataDescWrap) {
                        metadataDescWrap.classList.remove("is-loading");
                    }
                    if (metadataApply) {
                        metadataApply.disabled = false;
                    }
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

        metadataReviewModal.addEventListener("click", (event) => {
            const closeButton = event.target.closest("[data-modal-close]");
            if (!closeButton) return;
            if (window.ModalController) {
                window.ModalController.close("metadata-review");
                window.ModalController.close("fetch-metadata");
            }
        });

        metadataModal.addEventListener("click", (event) => {
            const closeButton = event.target.closest("[data-modal-close]");
            if (!closeButton) return;
            if (window.ModalController) {
                window.ModalController.close("metadata-review");
            }
        });

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
