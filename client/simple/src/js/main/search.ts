// SPDX-License-Identifier: AGPL-3.0-or-later

import { listen, settings } from "../toolkit.ts";
import { getElement } from "../util/getElement.ts";

const searchForm: HTMLFormElement = getElement<HTMLFormElement>("search");
const searchInput: HTMLInputElement = getElement<HTMLInputElement>("q");
const searchReset: HTMLButtonElement = getElement<HTMLButtonElement>("clear_search");

const isMobile: boolean = window.matchMedia("(max-width: 50em)").matches;
const isResultsPage: boolean = document.querySelector("main")?.id === "main_results";

const categoryButtons: HTMLButtonElement[] = Array.from(
  document.querySelectorAll<HTMLButtonElement>("#categories_container button.category")
);

const validBangs: Set<string> = new Set((settings as any).bangs || []);

const purgeBangs = (query: string): string => {
  if (!query) return "";
  return query
    .split(/\s+/)
    .filter((token) => {
      // Always strip external bangs (starts with !!)
      if (token.startsWith("!!")) return false;

      // Strip internal bangs if they match a known engine/category
      if (token.startsWith("!")) {
        const bang = token.slice(1).toLowerCase();
        // Normalize underscores/dashes to match backend variants
        if (validBangs.has(bang) || validBangs.has(bang.replace(/[-_]/g, " "))) return false;
      }

      return true;
    })
    .join(" ")
    .trim();
};

if (searchInput.value.length === 0) {
  searchReset.classList.add("empty");
}

// focus search input on large screens
if (!(isMobile || isResultsPage)) {
  searchInput.focus();
}

// On mobile, move cursor to the end of the input on focus
if (isMobile) {
  listen("focus", searchInput, () => {
    // Defer cursor move until the next frame to prevent a visual jump
    requestAnimationFrame(() => {
      const end = searchInput.value.length;
      searchInput.setSelectionRange(end, end);
      searchInput.scrollLeft = searchInput.scrollWidth;
    });
  });
}

listen("input", searchInput, () => {
  searchReset.classList.toggle("empty", searchInput.value.length === 0);
});

listen("click", searchReset, (event: MouseEvent) => {
  event.preventDefault();
  searchInput.value = "";
  searchInput.focus();
  searchReset.classList.add("empty");
});

for (const button of categoryButtons) {
  // Use mousedown to ensure the value is updated BEFORE the click/submit fires
  listen("mousedown", button, (event: MouseEvent) => {
    if (event.shiftKey) return;

    // Purge bangs immediately on the input element
    searchInput.value = purgeBangs(searchInput.value);
  });

  listen("click", button, (event: MouseEvent) => {
    if (event.shiftKey) {
      event.preventDefault();
      button.classList.toggle("selected");
      return;
    }

    // deselect all other categories
    for (const categoryButton of categoryButtons) {
      categoryButton.classList.toggle("selected", categoryButton === button);
    }
  });
}

if (document.querySelector("div.search_filters")) {
  const safesearchElement = document.getElementById("safesearch");
  if (safesearchElement) {
    listen("change", safesearchElement, () => searchForm.requestSubmit());
  }

  const timeRangeElement = document.getElementById("time_range");
  if (timeRangeElement) {
    listen("change", timeRangeElement, () => searchForm.requestSubmit());
  }

  const languageElement = document.getElementById("language");
  if (languageElement) {
    listen("change", languageElement, () => searchForm.requestSubmit());
  }
}

// override searchForm submit event
listen("submit", searchForm, (event: Event) => {
  event.preventDefault();

  if (categoryButtons.length > 0) {
    const searchCategories = getElement<HTMLInputElement>("selected-categories");
    searchCategories.value = categoryButtons
      .filter((button) => button.classList.contains("selected"))
      .map((button) => button.name.replace("category_", ""))
      .join(",");
  }

  searchForm.submit();
});

