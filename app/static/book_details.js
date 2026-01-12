(() => { 
    const searchModal = document.querySelector("[data-modal-id='search-books']");
    const searchButton = document.querySelector("[data-search-books]");
    if (!searchModal || !searchButton) return;
    const descriptionButton = document.querySelector("[data-generate-description]");
    const clearDescriptionButton = document.querySelector("[data-clear-description]");
    const descriptionBox = document.querySelector("[data-description-text]");
    const descriptionStatus = document.querySelector("[data-description-status]");
    const descriptionConfirm = document.querySelector("[data-description-confirm]");
    const descriptionPreview = document.querySelector("[data-description-preview]");
    const descriptionAccept = document.querySelector("[data-description-accept]");
    const descriptionReject = document.querySelector("[data-description-reject]");
    const statusLine = document.querySelector("[data-search-status]");
    const resultsList = document.querySelector("[data-search-results]");
    const tagsList = document.querySelector("[data-search-tags]");
    const searchParams = document.querySelector("[data-search-params]");
    const applyTagsButton = searchModal.querySelector("[data-apply-tags]");
    let currentTags = [];


    const clearResults = () => {
        resultsList.innerHTML = "";
        tagsList.innerHTML = "";
    };

    const setStatus = (text) => {
        statusLine.textContent = text;
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
        const title = searchButton?.getAttribute("data-title") || "";
        const author = searchButton?.getAttribute("data-author") || "";
        const parts = [];
        if (title) parts.push(`Title: ${title}`);
        if (author) parts.push(`Author: ${author}`);
        return parts.length ? parts.join(" | ") : "Title: Unknown title | Author: Unknown author";
    };

    const showDescriptionConfirm = (text) => {
        if (!descriptionConfirm || !descriptionPreview) return;
        descriptionPreview.textContent = text;
        descriptionConfirm.removeAttribute("hidden");
    };

    const clearDescriptionConfirm = () => {
        if (!descriptionConfirm || !descriptionPreview) return;
        descriptionPreview.textContent = "";
        descriptionConfirm.setAttribute("hidden", "");
    };

    const renderTags = (tags) => {
        tagsList.innerHTML = "";
        currentTags = tags.map((tag) => tag.tag_text).filter(Boolean);
        applyTagsButton.disabled = currentTags.length === 0;
        if (!tags.length) {
        tagsList.innerHTML = '<p class="note">No tags returned.</p>';
        return;
        }
        tags.forEach((tag) => {
        const pill = document.createElement("div");
        pill.className = "tag-pill";
        const label = document.createElement("span");
        label.textContent = tag.tag_text;
        pill.appendChild(label);
        tagsList.appendChild(pill);
        });
    };

    const handleTagClick = async (resultId, button) => {
        button.disabled = true;
        button.textContent = "Loading...";
        try {
        const response = await fetch(`/search/${encodeURIComponent(resultId)}/tags`);
        if (!response.ok) {
            throw new Error("Failed to load tags.");
        }
        const tags = await response.json();
        renderTags(tags);
        } catch (error) {
        tagsList.innerHTML = '<p class="note">Unable to load tags.</p>';
        } finally {
        button.disabled = false;
        button.textContent = "Get tags";
        }
    };

    const renderResults = (results) => {
        clearResults();
        if (!results.length) {
        setStatus("No results found.");
        return;
        }
        setStatus("");
        results.forEach((result) => {
        const item = document.createElement("div");
        item.className = "list-item";

        const info = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = result.title || "Untitled";
        const author = document.createElement("div");
        author.className = "note";
        author.textContent = result.author || "Unknown author";
        info.appendChild(title);
        info.appendChild(author);

        const actions = document.createElement("div");
        const tagsButton = document.createElement("button");
        tagsButton.className = "btn btn-outline btn-small";
        tagsButton.type = "button";
        tagsButton.textContent = "Get tags";
        tagsButton.addEventListener("click", () => handleTagClick(result.result_id, tagsButton));
        actions.appendChild(tagsButton);

        item.appendChild(info);
        item.appendChild(actions);
        resultsList.appendChild(item);
        });
    };


    applyTagsButton.addEventListener("click", async () => {
        if (!currentTags.length) {
        return;
        }
        applyTagsButton.disabled = true;
        applyTagsButton.textContent = "Adding...";
        const bookId = searchButton.getAttribute("data-book-id");
        const formData = new FormData();
        formData.set("tags", currentTags.join(", "));
        try {
        const response = await fetch(`/books/${bookId}/tags`, {
            method: "POST",
            body: formData,
        });
        if (!response.ok) {
            throw new Error("Failed to add tags.");
        }
        window.location.reload();
        return;
        } catch (error) {
        setStatus("Unable to add tags.");
        } finally {
        applyTagsButton.textContent = "Add tags to book";
        applyTagsButton.disabled = currentTags.length === 0;
        }
    });

    const runSearch = async () => {
        const title = searchButton.getAttribute("data-title") || "";
        const author = searchButton.getAttribute("data-author") || "";
        const params = new URLSearchParams();
        if (title) {
        params.set("title", title);
        }
        if (author) {
        params.set("author", author);
        }
        if (searchParams) {
        const parts = [];
        if (title) parts.push(`Title: ${title}`);
        if (author) parts.push(`Author: ${author}`);
        searchParams.textContent = parts.length ? `Search params: ${parts.join(" | ")}` : "";
        }
        setStatus("Loading results...");
        try {
        const response = await fetch(`/search?${params.toString()}`);
        if (!response.ok) {
            throw new Error("Search failed.");
        }
        const results = await response.json();
        renderResults(results);
        } catch (error) {
        clearResults();
        setStatus("Unable to load search results.");
        }
    };

    searchButton.addEventListener("click", () => {
        runSearch();
    });

    if (descriptionButton) {
        descriptionButton.addEventListener("click", async () => {
        const bookId = descriptionButton.getAttribute("data-book-id");
        if (!bookId || !descriptionBox) return;
        descriptionButton.disabled = true;
        descriptionButton.textContent = "Generating...";
        setDescriptionStatus(`Generating description using prompt: ${getDescriptionPrompt()}`);
        try {
            const response = await fetch(`/books/${bookId}/description/generate`, {
            method: "POST",
            });
            if (!response.ok) {
            throw new Error("Failed to generate description.");
            }
            const payload = await response.json();
            const text = payload.description;
            if (text && String(text).toLowerCase() !== "null") {
                showDescriptionConfirm(text);
                setDescriptionStatus("Description generated. Review the draft below and accept or reject.");
            } else {
                clearDescriptionConfirm();
                setDescriptionStatus(
                    "No confident match could be generated by the model. Try again or adjust title/author."
                );
            }
        } catch (error) {
            setDescriptionStatus("Unable to generate description. The LLM service may be unavailable.");
        } finally {
            descriptionButton.textContent = "Generate description";
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
            if (!bookId || !descriptionPreview || !descriptionBox) return;
            const text = descriptionPreview.textContent || "";
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
                    throw new Error("Failed to save description.");
                }
                descriptionBox.textContent = text;
                clearDescriptionConfirm();
                setDescriptionStatus("Description saved.");
                if (clearDescriptionButton) {
                    clearDescriptionButton.disabled = false;
                }
            } catch (error) {
                setDescriptionStatus("Unable to save description. Please try again.");
            } finally {
                descriptionAccept.disabled = false;
                descriptionReject?.removeAttribute("disabled");
            }
        });
    }

    if (clearDescriptionButton) {
        clearDescriptionButton.addEventListener("click", async () => {
            const bookId = clearDescriptionButton.getAttribute("data-book-id");
            if (!bookId || !descriptionBox) return;
            clearDescriptionButton.disabled = true;
            setDescriptionStatus("Clearing the saved description...");
            try {
                const response = await fetch(`/books/${bookId}/description`, {
                    method: "DELETE",
                });
                if (!response.ok) {
                    throw new Error("Failed to clear description.");
                }
                descriptionBox.innerHTML = '<p class="note">No description yet.</p>';
                clearDescriptionConfirm();
                setDescriptionStatus("Description cleared.");
            } catch (error) {
                setDescriptionStatus("Unable to clear description. Please try again.");
                clearDescriptionButton.disabled = false;
                return;
            }
            clearDescriptionButton.disabled = true;
        });
    }

})();
