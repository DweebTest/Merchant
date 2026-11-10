// Small page behaviours, kept out of the HTML so the Content-Security-Policy
// can forbid inline scripts.
(function () {
  // On phones, start the knowledge base filters folded so results show first.
  const panel = document.getElementById("filter-panel");
  if (panel && window.matchMedia("(max-width: 760px)").matches) panel.removeAttribute("open");

  // <form data-confirm="Are you sure?">: ask before submitting.
  document.addEventListener("submit", (event) => {
    const message = event.target.dataset && event.target.dataset.confirm;
    if (message && !window.confirm(message)) event.preventDefault();
  });

  // <input data-clears="from to">: changing this field empties those fields in the same form.
  document.addEventListener("change", (event) => {
    const el = event.target;
    if (!el.dataset || !el.dataset.clears || !el.form) return;
    for (const name of el.dataset.clears.split(/\s+/)) {
      const other = el.form.elements[name];
      if (other) other.value = "";
    }
  });
})();
