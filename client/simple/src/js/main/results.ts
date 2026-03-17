// SPDX-License-Identifier: AGPL-3.0-or-later

import "../../../node_modules/swiped-events/src/swiped-events.js";
import { listen, mutable, settings } from "../toolkit.ts";
import { assertElement } from "../util/assertElement.ts";

let imgTimeoutID: number;

const imageLoader = (resultElement: HTMLElement): void => {
  if (imgTimeoutID) clearTimeout(imgTimeoutID);

  const imgElement = resultElement.querySelector<HTMLImageElement>(".result-images-source img");
  if (!imgElement) return;

  // use thumbnail until full image loads
  const thumbnail = resultElement.querySelector<HTMLImageElement>(".image_thumbnail");
  if (thumbnail) {
    if (thumbnail.src === `${settings.theme_static_path}/img/img_load_error.svg`) return;

    imgElement.onerror = (): void => {
      imgElement.src = thumbnail.src;
    };

    imgElement.src = thumbnail.src;
  }

  const imgSource = imgElement.getAttribute("data-src");
  if (!imgSource) return;

  // unsafe nodejs specific, cast to https://developer.mozilla.org/en-US/docs/Web/API/Window/setTimeout#return_value
  // https://github.com/searxng/searxng/pull/5073#discussion_r2265767231
  imgTimeoutID = setTimeout(() => {
    imgElement.src = imgSource;
    imgElement.removeAttribute("data-src");
  }, 1000) as unknown as number;
};

const imageThumbnails: NodeListOf<HTMLImageElement> =
  document.querySelectorAll<HTMLImageElement>("#urls img.image_thumbnail");
for (const thumbnail of imageThumbnails) {
  if (thumbnail.complete && thumbnail.naturalWidth === 0) {
    thumbnail.src = `${settings.theme_static_path}/img/img_load_error.svg`;
  }

  thumbnail.onerror = (): void => {
    thumbnail.src = `${settings.theme_static_path}/img/img_load_error.svg`;
  };
}

const copyUrlButton: HTMLButtonElement | null =
  document.querySelector<HTMLButtonElement>("#search_url button#copy_url");
copyUrlButton?.style.setProperty("display", "block");

mutable.selectImage = (resultElement: HTMLElement): void => {
  // add a class that can be evaluated in the CSS and indicates that the
  // detail view is open
  const resultsElement = document.getElementById("results");
  resultsElement?.classList.add("image-detail-open");

  // add a hash to the browser history so that pressing back doesn't return
  // to the previous page this allows us to dismiss the image details on
  // pressing the back button on mobile devices
  window.location.hash = "#image-viewer";

  mutable.scrollPageToSelected?.();

  // if there is no element given by the caller, stop here
  if (!resultElement) return;

  imageLoader(resultElement);
};

mutable.closeDetail = (): void => {
  const resultsElement = document.getElementById("results");
  resultsElement?.classList.remove("image-detail-open");

  // remove #image-viewer hash from url by navigating back
  if (window.location.hash === "#image-viewer") {
    window.history.back();
  }

  mutable.scrollPageToSelected?.();
};

listen("click", ".btn-collapse", function (this: HTMLElement) {
  const btnLabelCollapsed = this.getAttribute("data-btn-text-collapsed");
  const btnLabelNotCollapsed = this.getAttribute("data-btn-text-not-collapsed");
  const target = this.getAttribute("data-target");

  if (!(target && btnLabelCollapsed && btnLabelNotCollapsed)) return;

  const targetElement = document.querySelector<HTMLElement>(target);
  assertElement(targetElement);

  const isCollapsed = this.classList.contains("collapsed");
  const newLabel = isCollapsed ? btnLabelNotCollapsed : btnLabelCollapsed;
  const oldLabel = isCollapsed ? btnLabelCollapsed : btnLabelNotCollapsed;

  this.innerHTML = this.innerHTML.replace(oldLabel, newLabel);
  this.classList.toggle("collapsed");

  const isNowCollapsed = this.classList.contains("collapsed");
  targetElement.classList.toggle("invisible", isNowCollapsed);

  // Kill switch / Lazy load logic for media-loader
  if (this.classList.contains("media-loader")) {
    const iframeLoad = targetElement.querySelector<HTMLIFrameElement>("iframe");
    if (iframeLoad) {
      if (isNowCollapsed) {
        // Hiding: clear src to stop playback
        iframeLoad.setAttribute("src", "");
      } else {
        // Showing: load from data-src if src is empty
        const currentSrc = iframeLoad.getAttribute("src");
        if (!currentSrc || currentSrc === "") {
          const dataSrc = iframeLoad.getAttribute("data-src");
          if (dataSrc) {
            iframeLoad.setAttribute("src", dataSrc);
          }
        }
      }
    }
  }
});

listen("click", "#copy_url", async function (this: HTMLElement) {
  const target = this.parentElement?.querySelector<HTMLPreElement>("pre");
  assertElement(target);

  if (window.isSecureContext) {
    await navigator.clipboard.writeText(target.innerText);
  } else {
    const selection = window.getSelection();
    if (selection) {
      const range = document.createRange();
      range.selectNodeContents(target);
      selection.removeAllRanges();
      selection.addRange(range);
      document.execCommand("copy");
    }
  }

  if (this.dataset.copiedText) {
    this.innerText = this.dataset.copiedText;
  }
});

listen("click", ".result-detail-close", (event: Event) => {
  event.preventDefault();
  mutable.closeDetail?.();
});

listen("click", ".result-detail-previous", (event: Event) => {
  event.preventDefault();
  mutable.selectPrevious?.(false);
});

listen("click", ".result-detail-next", (event: Event) => {
  event.preventDefault();
  mutable.selectNext?.(false);
});

// listen for the back button to be pressed and dismiss the image details when called
window.addEventListener("hashchange", () => {
  if (window.location.hash !== "#image-viewer") {
    mutable.closeDetail?.();
  }
});

const swipeHorizontal: NodeListOf<HTMLElement> = document.querySelectorAll<HTMLElement>(".swipe-horizontal");
for (const element of swipeHorizontal) {
  listen("swiped-left", element, () => {
    mutable.selectNext?.(false);
  });

  listen("swiped-right", element, () => {
    mutable.selectPrevious?.(false);
  });
}

// Snippet splitting and expansion logic
const TRUNCATE_LIMIT = settings.result_truncation_limit ?? 330;
const TOGGLE_SVG = `
<svg width="14" height="8" viewBox="0 0 14 8" xmlns="http://www.w3.org/2000/svg">
  <rect width="14" height="8" rx="1.5" ry="1.5" />
  <circle cx="3.5" cy="4" r="1.1" fill="black" />
  <circle cx="7" cy="4" r="1.1" fill="black" />
  <circle cx="10.5" cy="4" r="1.1" fill="black" />
</svg>`;

const splitSnippet = (element: HTMLElement): void => {
  if (element.querySelector(".btn-toggle-content")) return; // Already processed

  const fullHtml = element.innerHTML;
  if ((element.textContent || "").length <= TRUNCATE_LIMIT) return;

  // We need to find a safe split point in the HTML string that doesn't break tags
  let charCount = 0;
  let splitIndex = -1;
  let inTag = false;

  for (let i = 0; i < fullHtml.length; i++) {
    const char = fullHtml[i];
    if (char === "<") {
      inTag = true;
    } else if (char === ">") {
      inTag = false;
    } else if (!inTag) {
      charCount++;
      if (charCount >= TRUNCATE_LIMIT && splitIndex === -1) {
        // Try to find the next space to avoid cutting words
        const nextSpace = fullHtml.indexOf(" ", i);
        if (nextSpace !== -1 && nextSpace - i < 20) {
          splitIndex = nextSpace;
        } else {
          splitIndex = i;
        }
      }
    }
  }

  if (splitIndex !== -1 && splitIndex < fullHtml.length - 20) {
    const visiblePart = fullHtml.substring(0, splitIndex);
    const hiddenPart = fullHtml.substring(splitIndex);

    element.innerHTML = `${visiblePart}<span class="content-hidden">${hiddenPart}</span><button class="btn-toggle-content" aria-expanded="false">${TOGGLE_SVG}</button>`;
  }
};

const initSnippetSplitting = (): void => {
  if (settings.result_truncation === false) return;
  const snippets = document.querySelectorAll<HTMLElement>(".result .content");
  for (const snippet of snippets) {
    splitSnippet(snippet);
  }
};

// Run immediately as this script is dynamically imported by router.ts
const tryInit = () => {
  initSnippetSplitting();
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", tryInit);
} else {
  tryInit();
}

listen("click", ".btn-toggle-content", function (this: HTMLButtonElement) {
  const parent = this.parentElement;
  if (!parent) return;

  const hiddenSpan = parent.querySelector<HTMLElement>(".content-hidden");
  if (!hiddenSpan) return;

  const isExpanded = this.getAttribute("aria-expanded") === "true";
  if (isExpanded) {
    hiddenSpan.style.display = "none";
    this.setAttribute("aria-expanded", "false");
  } else {
    hiddenSpan.style.display = "inline";
    this.setAttribute("aria-expanded", "true");
  }
});

window.addEventListener(
  "scroll",
  () => {
    const backToTopElement = document.getElementById("backToTop");
    const resultsElement = document.getElementById("results");

    if (backToTopElement && resultsElement) {
      const scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      const isScrolling = scrollTop >= 100;
      resultsElement.classList.toggle("scrolling", isScrolling);
    }
  },
  true
);
