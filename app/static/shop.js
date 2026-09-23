/*
 * The "Added to cart" dialog on the product page.
 *
 * After "Add to cart" the page comes back with the dialog in its markup,
 * hidden. This script opens it: the rest of the page becomes inert, focus
 * moves to the dialog's first control, and Tab and Shift+Tab go round its
 * controls. Escape and "Continue shopping" close it and put focus back on the
 * button that opened it. It is shown once: a reload or coming Back to the page
 * does not show it again.
 */
(function () {
  "use strict";

  const dialog = document.querySelector("[data-dialog]");
  if (!dialog) {
    return;
  }
  const backdrop = dialog.parentElement;
  const opener = document.getElementById(dialog.dataset.opener);
  const rest = Array.from(document.body.children).filter((element) => element !== backdrop);

  function controls() {
    return Array.from(dialog.querySelectorAll("a[href], button:not([disabled])"));
  }

  function open() {
    backdrop.hidden = false;
    rest.forEach((element) => {
      element.inert = true;
    });
    document.addEventListener("keydown", onKeydown);
    // The dialog has now been shown: drop `?added=1` from the address, so that
    // neither a reload nor coming Back to this page opens it a second time.
    history.replaceState(null, "", window.location.pathname);
    controls()[0].focus();
  }

  function close() {
    document.removeEventListener("keydown", onKeydown);
    rest.forEach((element) => {
      element.inert = false;
    });
    backdrop.hidden = true;
    if (opener) {
      opener.focus();
    }
  }

  function onKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    const items = controls();
    const first = items[0];
    const last = items[items.length - 1];
    const inside = dialog.contains(document.activeElement);
    if (event.shiftKey && (!inside || document.activeElement === first)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (!inside || document.activeElement === last)) {
      event.preventDefault();
      first.focus();
    }
  }

  dialog.querySelectorAll("[data-dialog-close]").forEach((control) => {
    control.addEventListener("click", close);
  });

  // A browser with a back/forward cache brings the page back exactly as it was
  // left: after "Go to cart" and Back, with the dialog still open. It has been
  // seen by then, so close it.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted && !backdrop.hidden) {
      close();
    }
  });

  open();
})();
