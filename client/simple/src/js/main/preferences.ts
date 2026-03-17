// SPDX-License-Identifier: AGPL-3.0-or-later

import { listen } from "../toolkit.ts";

listen("submit", "#save-preferences", async function (this: HTMLFormElement, event: Event) {
  event.preventDefault();

  const confirmation = document.getElementById("save-confirmation");
  if (!confirmation) return;

  // Clear any existing animation state
  confirmation.classList.remove("fade-out");
  confirmation.classList.remove("invisible");

  try {
    const formData = new FormData(this);
    const response = await fetch(this.action, {
      method: "POST",
      body: formData,
      headers: {
        "X-Requested-With": "XMLHttpRequest"
      }
    });

    if (response.ok) {
      // Show confirmation
      confirmation.classList.remove("invisible");
      
      // Start fade out after 1 second
      setTimeout(() => {
        confirmation.classList.add("fade-out");
        // Hide completely after fade animation (1s)
        setTimeout(() => {
          confirmation.classList.add("invisible");
        }, 1000);
      }, 1000);
    } else {
      console.error("Failed to save preferences");
    }
  } catch (error) {
    console.error("Error saving preferences:", error);
  }
});

// Dynamic UI for preferences
const truncationCheckbox = document.getElementById("result_truncation");
const truncationLimitFieldset = document.getElementById("result_truncation_limit_fieldset");

if (truncationCheckbox && truncationLimitFieldset) {
  listen("change", truncationCheckbox, () => {
    truncationLimitFieldset.hidden = !(truncationCheckbox as HTMLInputElement).checked;
  });
}

