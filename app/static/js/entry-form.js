// New entry form: when an existing organization is picked, fill in the details
// from its most recent entry and lock those sections until "Edit" is pressed.
(function () {
  "use strict";
  const form = document.getElementById("entry-form");
  if (!form || !form.dataset.prefillUrl) return;
  const org = document.getElementById("organization");
  const note = document.getElementById("prefill-note");
  const sections = Array.from(form.querySelectorAll(".lockable"));
  const known = new Set(Array.from(document.querySelectorAll("#org-list option")).map(o => o.value.toLowerCase()));
  let lastName = "";
  let autoFilled = false;

  // Each lockable section gets a small bar with an Edit button.
  sections.forEach(section => {
    const bar = document.createElement("div");
    bar.className = "lock-bar";
    bar.hidden = true;
    bar.innerHTML = '<span>From the last entry</span><button type="button" class="link">Edit</button>';
    bar.querySelector("button").addEventListener("click", () => unlock(section, true));
    section.prepend(bar);
  });

  function body(section) {
    return Array.from(section.children).filter(el => !el.classList.contains("lock-bar"));
  }
  function lock(section) {
    section.classList.add("locked");
    body(section).forEach(el => el.setAttribute("inert", ""));
    section.querySelector(".lock-bar").hidden = false;
  }
  function unlock(section, focus) {
    section.classList.remove("locked");
    body(section).forEach(el => el.removeAttribute("inert"));
    section.querySelector(".lock-bar").hidden = true;
    if (focus) {
      const details = section.querySelector("details");
      if (details) details.open = true;
      const first = section.querySelector("input, select, textarea");
      if (first) first.focus();
    }
  }
  const unlockAll = () => sections.forEach(s => unlock(s, false));

  function setChecks(name, ids) {
    form.querySelectorAll(`input[name="${name}"]`).forEach(box => {
      box.checked = ids.includes(Number(box.value));
    });
  }
  function setValue(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value || "";
  }
  function clearAuto() {
    setChecks("clusters", []);
    setChecks("opportunity_types", []);
    ["contact_name", "contact_title", "contact_email", "contact_phone", "college_area", "link_url"]
      .forEach(id => setValue(id, ""));
    autoFilled = false;
  }

  function apply(data) {
    setChecks("clusters", data.clusters);
    setChecks("opportunity_types", data.opportunity_types);
    const c = data.contact || {};
    setValue("contact_name", c.name);
    setValue("contact_title", c.title);
    setValue("contact_email", c.email);
    setValue("contact_phone", c.phone);
    const details = form.querySelector(".contact-box");
    if (details) details.open = Boolean(data.contact);
    setValue("college_area", data.college_area);
    setValue("link_url", data.link_url);
    sections.forEach(lock);
    autoFilled = true;
    note.textContent = `Filled in from the last entry for ${data.organization} (${data.last_entry_label}). ` +
      "Press Edit on any section to change it.";
    note.hidden = false;
  }

  async function lookup() {
    const name = org.value.trim();
    if (name.toLowerCase() === lastName) return;
    lastName = name.toLowerCase();
    let data = { found: false };
    if (name) {
      try {
        const resp = await fetch(`${form.dataset.prefillUrl}?name=${encodeURIComponent(name)}`,
          { headers: { Accept: "application/json" }, credentials: "same-origin" });
        if (resp.ok) data = await resp.json();
      } catch (e) { /* offline or server error: just leave the form as it is */ }
    }
    if (org.value.trim().toLowerCase() !== lastName) return; // the name changed while we waited
    if (data.found && data.has_entry) {
      apply(data);
    } else {
      if (autoFilled) clearAuto();
      unlockAll();
      note.hidden = true;
    }
  }

  org.addEventListener("change", lookup);
  org.addEventListener("blur", lookup);
  // Picking from the suggestion list fills the whole name at once.
  org.addEventListener("input", () => { if (known.has(org.value.trim().toLowerCase())) lookup(); });
})();
