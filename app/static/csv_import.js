(() => {
  const csvModal = document.querySelector("[data-modal-id='csv-import']");
  if (!csvModal) return;

  const csvCloseButtons = csvModal.querySelectorAll("[data-modal-close]");
  const csvFileInput = csvModal.querySelector("[data-csv-file]");
  const csvStatus = csvModal.querySelector("[data-csv-status]");
  const csvColumnsSection = csvModal.querySelector("[data-csv-columns]");
  const csvBookIdSelect = csvModal.querySelector("[data-csv-book-id]");
  const csvTagColumns = csvModal.querySelector("[data-csv-tag-columns]");
  const csvValidateButton = csvModal.querySelector("[data-csv-validate]");
  const csvImportSubmit = csvModal.querySelector("[data-csv-import-submit]");
  const csvValidation = csvModal.querySelector("[data-csv-validation]");
  const csvAllowedNamespaces = (csvModal.dataset.namespaces || "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);

  if (!csvAllowedNamespaces.includes("topic")) {
    csvAllowedNamespaces.push("topic");
  }

  let csvHeaders = [];
  let csvFile = null;
  let csvValidated = false;

  const csvCloseModal = () => {
    if (window.ModalController) {
      window.ModalController.close("csv-import");
    }
    if (csvFileInput) csvFileInput.value = "";
    csvResetMapping();
    csvSetStatus("Select a CSV file to begin.");
  };

  const csvSetStatus = (text) => {
    if (csvStatus) csvStatus.textContent = text;
  };

  const csvSetValidation = (text) => {
    if (csvValidation) csvValidation.textContent = text;
  };

  const csvParseLine = (line) => {
    const values = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i += 1) {
      const char = line[i];
      if (char === '"') {
        if (inQuotes && line[i + 1] === '"') {
          current += '"';
          i += 1;
        } else {
          inQuotes = !inQuotes;
        }
        continue;
      }
      if (char === "," && !inQuotes) {
        values.push(current.trim());
        current = "";
        continue;
      }
      current += char;
    }
    values.push(current.trim());
    return values.filter((value) => value.length > 0);
  };

  const csvResetMapping = () => {
    csvHeaders = [];
    csvValidated = false;
    if (csvValidation) csvValidation.textContent = "";
    if (csvImportSubmit) csvImportSubmit.disabled = true;
    if (csvColumnsSection) csvColumnsSection.setAttribute("hidden", "");
    if (csvBookIdSelect) csvBookIdSelect.innerHTML = "";
    if (csvTagColumns) csvTagColumns.innerHTML = "";
  };

  const csvPopulateColumns = (headers) => {
    if (!csvBookIdSelect || !csvTagColumns || !csvColumnsSection) return;
    csvBookIdSelect.innerHTML = "";
    csvTagColumns.innerHTML = "";
    headers.forEach((header) => {
      const option = document.createElement("option");
      option.value = header;
      option.textContent = header;
      csvBookIdSelect.appendChild(option);

      const label = document.createElement("label");
      label.className = "list-item";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = header;
      const text = document.createElement("span");
      text.textContent = header;
      label.appendChild(checkbox);
      label.appendChild(text);
      csvTagColumns.appendChild(label);
    });
    const idIndex = headers.findIndex((header) => header.toLowerCase() === "id");
    if (idIndex >= 0) {
      csvBookIdSelect.value = headers[idIndex];
    }
    csvColumnsSection.removeAttribute("hidden");
  };

  const csvLoadHeaders = (file) => {
    csvResetMapping();
    if (!file) {
      csvSetStatus("Select a CSV file to begin.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const firstLine = text.replace(/^\uFEFF/, "").split(/\r?\n/)[0] || "";
      const headers = csvParseLine(firstLine);
      if (!headers.length) {
        csvSetStatus("Unable to read CSV headers.");
        return;
      }
      csvHeaders = headers;
      csvPopulateColumns(headers);
      csvSetStatus("Select columns and validate the namespaces.");
    };
    reader.onerror = () => {
      csvSetStatus("Unable to read CSV file.");
    };
    reader.readAsText(file);
  };

  const csvGetSelectedTags = () => {
    if (!csvTagColumns) return [];
    const selected = Array.from(
      csvTagColumns.querySelectorAll("input[type='checkbox']:checked")
    ).map((input) => input.value);
    const bookIdColumn = csvBookIdSelect ? csvBookIdSelect.value : "";
    return selected.filter((value) => value !== bookIdColumn);
  };

  const csvValidateSelection = () => {
    if (!csvBookIdSelect) return false;
    const bookIdColumn = csvBookIdSelect.value;
    const selectedTags = csvGetSelectedTags();
    if (!bookIdColumn) {
      csvSetValidation("Select a book ID column.");
      return false;
    }
    if (!selectedTags.length) {
      csvSetValidation("Select at least one tag column.");
      return false;
    }
    const allowedLookup = new Set(csvAllowedNamespaces.map((entry) => entry.toLowerCase()));
    const invalid = selectedTags.filter(
      (tag) => allowedLookup.size && !allowedLookup.has(tag.toLowerCase())
    );
    if (invalid.length) {
      csvSetValidation(`Unknown namespaces: ${invalid.join(", ")}.`);
      return false;
    }
    csvValidated = true;
    csvSetValidation("Looks good. Ready to import.");
    if (csvImportSubmit) csvImportSubmit.disabled = false;
    return true;
  };

  if (csvFileInput) {
    csvFileInput.addEventListener("change", (event) => {
      const file = event.target.files ? event.target.files[0] : null;
      csvFile = file;
      csvLoadHeaders(file);
    });
  }

  if (csvValidateButton) {
    csvValidateButton.addEventListener("click", () => {
      csvValidateSelection();
    });
  }

  if (csvImportSubmit) {
    csvImportSubmit.addEventListener("click", async () => {
      if (!csvFile) {
        csvSetValidation("Select a CSV file first.");
        return;
      }
      if (!csvValidated && !csvValidateSelection()) {
        return;
      }
      const bookIdColumn = csvBookIdSelect ? csvBookIdSelect.value : "";
      const selectedTags = csvGetSelectedTags();
      const formData = new FormData();
      formData.set("file", csvFile);
      formData.set("book_id_column", bookIdColumn);
      formData.set("tag_columns", JSON.stringify(selectedTags));
      if (csvImportSubmit) csvImportSubmit.disabled = true;
      csvSetStatus("Importing tags...");
      csvSetValidation("");
      try {
        const response = await fetch("/batch-actions/import-tags", {
          method: "POST",
          body: formData,
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.detail || "Import failed.");
        }
        csvSetStatus("Import complete.");
        csvSetValidation(
          `Books updated: ${result.books_updated}. Tags added: ${result.tags_added}.`
        );
      } catch (error) {
        csvSetStatus("Import failed.");
        csvSetValidation(error.message || "Unable to import tags.");
      } finally {
        if (csvImportSubmit) csvImportSubmit.disabled = false;
      }
    });
  }

  csvCloseButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      csvCloseModal();
    });
  });
})();
