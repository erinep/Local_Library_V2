(() => { 
    const searchModal = document.querySelector("[data-modal-id='search-books']");
    if (! searchModal) return;

    const searchButton = document.querySelector("[data-search-books]");
    const statusLine = document.querySelector("[data-search-status]");
    const resultsList = document.querySelector("[data-search-results]");
    const tagsList = document.querySelector("[data-search-tags]");
    const applyTagsButton = searchModal.querySelector("[data-apply-tags]");
    let currentTags = [];


    const clearResults = () => {
        resultsList.innerHTML = "";
        tagsList.innerHTML = "";
    };

    const setStatus = (text) => {
        statusLine.textContent = text;
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


})();