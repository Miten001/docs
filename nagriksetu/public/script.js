/*
 * NagrikSetu — Client ES module
 *
 * Detects the current page (Report or Track) and wires the relevant
 * handler. All DOM lookups are defensive so this module can be loaded
 * safely on pages that lack these elements (Home, Dashboard, About).
 *
 * Requirements: 1.8, 1.10, 2.3, 2.5, 2.6
 */

// ------------------------------------------------------------------ //
// Small DOM helpers                                                   //
// ------------------------------------------------------------------ //

/**
 * Safe element lookup by id. Returns null when not present.
 * @param {string} id
 * @returns {HTMLElement | null}
 */
function byId(id) {
  return typeof document !== "undefined" ? document.getElementById(id) : null;
}

/**
 * Human-readable label for a required field, used in validation messages.
 */
const FIELD_LABELS = {
  name: "Your Name",
  category: "Problem Type",
  locationArea: "Location / Area",
  description: "Describe the Problem",
};

/**
 * Map a complaint status to its status-badge variant class.
 * @param {string} status
 * @returns {string}
 */
function statusVariantClass(status) {
  switch ((status || "").trim()) {
    case "Pending":
      return "pending";
    case "In Progress":
      return "status-progress";
    case "Resolved":
      return "resolved";
    default:
      return "";
  }
}

/**
 * Format an ISO 8601 timestamp into a readable date, falling back to
 * the raw value when parsing fails.
 * @param {string} iso
 * @returns {string}
 */
function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Escape a string for safe insertion into HTML.
 * @param {unknown} value
 * @returns {string}
 */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => {
    switch (ch) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#39;";
      default:
        return ch;
    }
  });
}

// ------------------------------------------------------------------ //
// Report page                                                         //
// ------------------------------------------------------------------ //

/**
 * Wire the report form submit handler.
 * @param {HTMLFormElement} form
 */
function initReportPage(form) {
  const messageBox = byId("reportMessage");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await handleReportSubmit(form, messageBox);
  });
}

/**
 * Render a message into the report result area.
 * @param {HTMLElement | null} messageBox
 * @param {string} html
 * @param {"error" | "success"} kind
 */
function renderReportMessage(messageBox, html, kind) {
  if (!messageBox) return;
  messageBox.className = `message ${kind}`;
  messageBox.innerHTML = html;
}

/**
 * Perform client-side validation and submit the complaint.
 * @param {HTMLFormElement} form
 * @param {HTMLElement | null} messageBox
 */
async function handleReportSubmit(form, messageBox) {
  const values = {
    name: (byId("name")?.value ?? "").trim(),
    category: (byId("category")?.value ?? "").trim(),
    locationArea: (byId("locationArea")?.value ?? "").trim(),
    description: (byId("description")?.value ?? "").trim(),
    contact: (byId("contact")?.value ?? "").trim(),
  };

  // Client-side required-field checks (Req 1.10).
  const missing = ["name", "category", "locationArea", "description"].filter(
    (field) => values[field].length === 0
  );

  if (missing.length > 0) {
    const labels = missing.map((field) => FIELD_LABELS[field]);
    const list = labels
      .map((label) => `<li>${escapeHtml(label)}</li>`)
      .join("");
    renderReportMessage(
      messageBox,
      `<p>Please fill in the following required field${
        missing.length > 1 ? "s" : ""
      }:</p><ul class="field-error">${list}</ul>`,
      "error"
    );
    return; // Do not send the request.
  }

  // Build multipart FormData (Req 1.11 — include photo when present).
  const formData = new FormData();
  formData.append("citizenName", values.name);
  formData.append("category", values.category);
  formData.append("locationArea", values.locationArea);
  formData.append("description", values.description);
  if (values.contact) {
    formData.append("contact", values.contact);
  }

  const photoInput = byId("photo");
  const photoFile =
    photoInput && photoInput.files && photoInput.files.length > 0
      ? photoInput.files[0]
      : null;
  if (photoFile) {
    formData.append("photo", photoFile);
  }

  const submitButton = byId("submitComplaint");
  if (submitButton) submitButton.disabled = true;

  try {
    const response = await fetch("/api/complaints", {
      method: "POST",
      body: formData,
    });

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }

    if (response.status === 201) {
      // Success — display the returned Complaint ID prominently (Req 1.8).
      const complaintId = payload.complaintId ?? "";
      renderReportMessage(
        messageBox,
        `<p>Your complaint has been submitted successfully.</p>` +
          `<p>Your Complaint ID is <span class="complaint-id">${escapeHtml(
            complaintId
          )}</span>. Please save it to track your complaint later.</p>`,
        "success"
      );
      form.reset();
    } else if (response.status === 400) {
      // Server-side validation error (Req 1.9 / 1.10).
      let detail = payload.message ? escapeHtml(payload.message) : "";
      if (Array.isArray(payload.missingFields) && payload.missingFields.length > 0) {
        const list = payload.missingFields
          .map((field) => `<li>${escapeHtml(field)}</li>`)
          .join("");
        detail += `<ul class="field-error">${list}</ul>`;
      }
      renderReportMessage(
        messageBox,
        detail || "<p>Please check the form and try again.</p>",
        "error"
      );
    } else {
      renderReportMessage(
        messageBox,
        "<p>Something went wrong while submitting your complaint. Please try again later.</p>",
        "error"
      );
    }
  } catch {
    renderReportMessage(
      messageBox,
      "<p>Unable to submit your complaint. Please check your connection and try again.</p>",
      "error"
    );
  } finally {
    if (submitButton) submitButton.disabled = false;
  }
}

// ------------------------------------------------------------------ //
// Track page                                                          //
// ------------------------------------------------------------------ //

/**
 * Wire the track form submit handler.
 * @param {HTMLFormElement} form
 */
function initTrackPage(form) {
  const statusText = byId("statusText");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await handleTrackSubmit(statusText);
  });
}

/**
 * Render plain text (safe) into the track status area.
 * @param {HTMLElement | null} statusText
 * @param {string} html
 */
function renderStatusText(statusText, html) {
  if (!statusText) return;
  statusText.innerHTML = html;
}

/**
 * Look up a complaint by its Complaint ID and render the result.
 * @param {HTMLElement | null} statusText
 */
async function handleTrackSubmit(statusText) {
  const input = byId("complaintId");
  const rawId = input?.value ?? "";
  const id = rawId.trim();

  // Guard against empty / whitespace-only IDs (Req 2.6) — send no request.
  if (id.length === 0) {
    renderStatusText(
      statusText,
      "Please enter a Complaint ID to look up its status."
    );
    return;
  }

  const trackButton = byId("trackButton");
  if (trackButton) trackButton.disabled = true;

  renderStatusText(statusText, "Looking up your complaint…");

  try {
    const response = await fetch(
      `/api/complaints/${encodeURIComponent(id)}`,
      { method: "GET" }
    );

    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }

    if (response.status === 200) {
      renderComplaintDetails(statusText, payload);
    } else if (response.status === 404) {
      // Not found (Req 2.5).
      renderStatusText(
        statusText,
        escapeHtml(
          payload.message ||
            "No complaint matches the entered Complaint ID."
        )
      );
    } else {
      renderStatusText(
        statusText,
        "Something went wrong while looking up your complaint. Please try again later."
      );
    }
  } catch {
    renderStatusText(
      statusText,
      "Unable to look up your complaint. Please check your connection and try again."
    );
  } finally {
    if (trackButton) trackButton.disabled = false;
  }
}

/**
 * Render the complaint details (Req 2.3): status badge, category,
 * location area, description, and creation date.
 * @param {HTMLElement | null} statusText
 * @param {Record<string, unknown>} complaint
 */
function renderComplaintDetails(statusText, complaint) {
  if (!statusText) return;

  const status = String(complaint.status ?? "");
  const variant = statusVariantClass(status);
  const badgeClass = variant ? `status-badge ${variant}` : "status-badge";

  const parts = [];
  parts.push(
    `<span class="complaint-id">${escapeHtml(
      complaint.complaintId ?? ""
    )}</span>`
  );
  parts.push(
    `<span class="${badgeClass}">${escapeHtml(status || "Unknown")}</span>`
  );

  const rows = [];
  rows.push(
    `<dt>Category</dt><dd>${escapeHtml(complaint.category ?? "")}</dd>`
  );
  rows.push(
    `<dt>Location / Area</dt><dd>${escapeHtml(
      complaint.locationArea ?? ""
    )}</dd>`
  );
  rows.push(
    `<dt>Description</dt><dd>${escapeHtml(complaint.description ?? "")}</dd>`
  );
  rows.push(
    `<dt>Reported On</dt><dd>${escapeHtml(
      formatDate(complaint.createdAt)
    )}</dd>`
  );

  statusText.innerHTML =
    `<span>${parts.join(" ")}</span>` +
    `<dl>${rows.join("")}</dl>`;
}

// ------------------------------------------------------------------ //
// Page detection / bootstrap                                          //
// ------------------------------------------------------------------ //

/**
 * Detect the current page by the presence of its form and wire the
 * matching handler. Safe to call on pages that have neither form.
 */
function init() {
  const reportForm = byId("reportForm");
  if (reportForm) {
    initReportPage(reportForm);
  }

  const trackForm = byId("trackForm");
  if (trackForm) {
    initTrackPage(trackForm);
  }
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
}

export {
  init,
  handleReportSubmit,
  handleTrackSubmit,
  statusVariantClass,
  formatDate,
};
