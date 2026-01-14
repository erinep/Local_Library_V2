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
        const metadataClean = metadataReviewModal.querySelector("[data-metadata-clean]");
        const metadataDescWrap = metadataReviewModal.querySelector("[data-metadata-desc-wrap]");
        const metadataBack = metadataReviewModal.querySelector("[data-metadata-back]");
        const metadataCancel = metadataReviewModal.querySelector("[data-metadata-cancel]");
        const metadataLoading = metadataReviewModal.querySelector("[data-metadata-loading]");
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
            if (metadataClean) {
                metadataClean.disabled = false;
                metadataClean.removeAttribute("title");
            }
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
                info.appendChild(year);
                info.appendChild(isbn);
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
                const descriptionValue = metadataDescription?.value || "";
                const hasDescription = descriptionValue.trim().length > 0;
                const choice = hasDescription ? "include" : "none";
                const payload = {
                    tags,
                    description_choice: choice,
                    description: hasDescription ? descriptionValue : null,
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
                if (metadataLoading) {
                    metadataLoading.removeAttribute("hidden");
                }
                if (metadataApply) {
                    metadataApply.disabled = true;
                }
                let cleaned = false;
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
                        cleaned = true;
                    }
                    setMetadataStatus("Description cleaned.");
                } catch (error) {
                    setMetadataStatus("Unable to clean description.");
                } finally {
                    if (metadataDescWrap) {
                        metadataDescWrap.classList.remove("is-loading");
                    }
                    if (metadataLoading) {
                        metadataLoading.setAttribute("hidden", "");
                    }
                    if (metadataApply) {
                        metadataApply.disabled = false;
                    }
                    if (metadataClean && cleaned) {
                        metadataClean.disabled = true;
                        metadataClean.setAttribute(
                            "title",
                            "Already cleaned this session. Reopen metadata to run again."
                        );
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

        if (metadataCancel) {
            metadataCancel.addEventListener("click", () => {
                if (window.ModalController) {
                    window.ModalController.close("metadata-review");
                    window.ModalController.close("fetch-metadata");
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

        if (window.ModalController) {
            const originalOpen = window.ModalController.open?.bind(window.ModalController);
            if (originalOpen) {
                window.ModalController.open = (modalId) => {
                    if (modalId === "metadata-review" && metadataClean) {
                        metadataClean.disabled = false;
                        metadataClean.removeAttribute("title");
                    }
                    return originalOpen(modalId);
                };
            }
        }
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
