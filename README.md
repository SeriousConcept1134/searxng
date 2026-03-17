<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

<p align="left">
  <a href="https://searxng.org">
    <img src="https://raw.githubusercontent.com/SeriousConcept1134/searxng-enhanced/refs/heads/dev/searxng_enhanced.png" alt="SearXNG" width="512px">
  </a>
</p>

<p align="left">
  <a href="https://github.com/searxng"><img src="https://img.shields.io/badge/organization-3050ff?style=flat-square&logo=searxng&logoColor=fff&cacheSeconds=86400" alt="Organization"></a>
  <a href="https://docs.searxng.org"><img src="https://img.shields.io/badge/documentation-3050ff?style=flat-square&logo=readthedocs&logoColor=fff&cacheSeconds=86400" alt="Documentation"></a>
  <a href="https://github.com/searxng/searxng/blob/master/LICENSE"><img src="https://img.shields.io/github/license/searxng/searxng?style=flat-square&label=license&color=3050ff&cacheSeconds=86400" alt="License"></a>
  <a href="https://github.com/searxng/searxng/commits/master/"><img src="https://img.shields.io/github/commit-activity/y/searxng/searxng/master?style=flat-square&label=commits&color=3050ff&cacheSeconds=3600" alt="Commits"></a>
  <a href="https://translate.codeberg.org/projects/searxng/"><img src="https://img.shields.io/weblate/progress/searxng?server=https%3A%2F%2Ftranslate.codeberg.org&style=flat-square&label=translated&color=3050ff&cacheSeconds=86400" alt="Translated"></a>
</p>


SearXNG is a free, privacy-respecting [metasearch engine](https://en.wikipedia.org/wiki/Metasearch_engine) — users are never tracked or profiled.

## About This Fork

While SearXNG is an excellent privacy-focused meta-search engine, its stock UI can feel spartan.
This fork builds on that solid foundation with a modernized interface, quality-of-life improvements,
and targeted bug fixes — without compromising the core privacy guarantees.

**Goals:**

- Stay current with upstream `master` as much as possible
- Layer in meaningful UI/UX improvements incrementally
- Adhere to the project's development guidelines and existing workflows
- Adhere to the project's privacy centered philosophy
- Fix bugs faster/better than upstream `master` where possible


## What's New

<details>
<summary>🌓 <b>1. Dynamic Dark/Light theme toggle</b></summary>

- Ability to switch between light/dark theme styles on demand from any location
- Changes are applied dynamically without requiring a page reload
- Intelligent switching: automatically detects whether you prefer Dark or Black (OLED) mode and alternates between that and light, rather than always falling back to a generic dark theme.
><video src="https://github.com/user-attachments/assets/fca6b5e4-edcd-471f-a02d-87a68987fafc" controls></video>
</details>

<details>
<summary>🎥 <b>2. Video Search</b></summary>

- <b>\[feat\] Video Grid:</b> New grid layout for video search results (can be toggled on/off dynamically)
- <b>\[feat\] Video Grid Size:</b> A dynamic size slider allowing to change the video grid size on the fly
><video src="https://github.com/user-attachments/assets/70e6e4f7-1282-41b2-8d2b-4f42edaa556c" controls></video>
- <b>\[feat\] Results-per-page dropdown:</b> Added a dropdown menu for setting desired results per page, ranging from 10 up to 50.
><video src="https://github.com/user-attachments/assets/00c855b2-ff74-438a-b2df-059ed2429765" controls></video>
- <b>\[feat\] Under the hood:</b> a transparent "stitching" mechanism fetches and merges multiple pages if using a single engine which has fixed pagination limits. For example, Google Videos is capped at 10 results per page. Requesting 30 results with !gov <query> would normally yield only 10; the stitching layer calls the engine multiple times with offset pages and merges the results seamlessly before presenting them to you.
- <b>\[feat\] Lazy Loading:</b> Added lazy loading to video preview embeds which no longer load in the background (or worse - start autoplaying without ever clicking on "show video"). Instead video embeds are loaded on demand only once the "show video" button is clicked, and completely unload once "hide video" is clicked.
- <b>\[fix\]</b> Resolved "Error 153" for YouTube video embeds when clicking on "show video".
- <b>\[ui\]</b> Various UI layout optimizations and improvements.
</details>

<details>
<summary><b>🖼️ 3. Image Search</b></summary>

- <b>\[feat\] Image Grid Size:</b> Implemented a dynamic size slider to resize the image grid on the fly (same as video grid)
- <b>\[feat\] Results-per-page dropdown:</b> Added a dropdown menu for setting desired results per page, from 25 up to 200 (tracked separately from the videos section).
- <b>\[ui\]</b> Added rounded corner to all image results for a more modern look
- <b>\[ui\]</b> Added a subtle dropshadow effect when hovering over image results (similar to Google images)
- <b>\[ui\]</b> Reduced the size of the side panel (no longer takes up 50% of the screen), and added corner rounding, margins, and a dropshadow for a modern hover style effect
</details>

<details>
<summary>✨ <b>4. Quality of Life</b></summary>

- <b>\[feat\] Intelligent Bang Purging:</b> Using a bang to perform a search using a specific engine/category (e.g. `!yt!`, `!news`) no longer locks you in that category. You are now able to switch search categories on the fly for the same query, and the bang automatically gets purged. Only bangs defined in SearXNG get purged (so `!yt` will get purged while `!important` won't).
- <b>\[ui\] Prevent Autoplay:</b> Strengthened protections against unwanted autoplay across all supported video engines (YouTube, Dailymotion, BitChute, and others).
- <b>\[ui\] Dynamic preferences save:</b> Added a visual confirmation message when saving settings. Instead of redirecting to the homepage, the "Save" button now triggers an asynchronous update and displays a "Settings saved" notification with a green checkmark that smoothly fades away.
</details>

<details>
<summary>🧹 <b>5. General UI/UX</b></summary>

- <b>\[ui\] Thumbnail size:</b> Increased search results thumbnail sizes across all relevant categories (e.g. General, News etc.), for a more modern look, while limiting max. height to maintain proportions for square thumbnails.
- <b>\[feat\] Results Truncation:</b> Cleaned up the appeareance of search results by truncating really long result descriptions returned by some engines (sometimes a whole paragraph is returned). The truncated part gets hidden and a small button is added allowing to unhide/hide it. The feature can be turned on/off from the preferences (default is on), and the truncation character threshold is configurable as well (default is 330).
- <b>\[fix\] Category highlighting:</b> Fixed a bug where categories (e.g., `Videos`) would not highlight when triggered via a bang shortcut (`!yt`, `!gov`, etc.). Resolved via `triggered_categories` logic that correctly infers the active category from the bang used.
- <b>\[ui\] Pagination layout:</b> Corrected grid-view pagination where Previous / Next buttons were pushed to the screen edges; they are now centered and correctly sequenced.
- <b>\[fix\] Filters redirection:</b> Fixed a bug where changing an option in the search filters (e.g. Safe Search, Language etc.) would always reload back into the "General" category. The current search category is now preserved after the page reloads.
- <b>\[fix\] Keywords highlighting:</b> Fixed a bug where no additonal CSS was applied to keywords, preventing proper highlighting. It now works as intended across all search categories.
- <b>\[feat\] Dynamic highlighting switch:</b> Turns highlighting into a feature that can be toggled on/off dynamically from any search category.
- <b>\[fix\] Invisible dropdown arrows:</b> Light colors are now correctly used for dropdown menu icons (which were previously invisible) when using the "Black" theme style.
</details>

<details>
<summary>🛠️ <b>6. Engine Fixes</b></summary>

- <b>\[fix\] Google News:</b> Updated parsing logic to resolve zero returned results issue. And an additional separate issue where thumbnails were not loading correctly alongside the results.
- <b>\[fix\] Google Videos:</b> Updated parsing logic to resolve zero returned results issue. Also fixed an additonal parsing issue where the result descriptions were missing.
- <b>\[fix\] Google (main):</b> Fixed parsing issues that caused missing results and incorrect extraction of elements like title, description, or thumbnails.
- <b>\[fix\] Google (all):</b> Enhanced the parsing logic to prevent a duplicate results issue in some edge cases.
- <b>\[fix\] YouTube videos:</b> Restored missing video descriptions in results.
- <b>\[fix\] Wikicommons Engine:</b> Fixed an issue where video and audio results from Wikimedia Commons were missing thumbnails.
- <b>\[fix\] Bing Images:</b> Added logic to filter out unsupported special characters returned in image descriptions
</details>

All features and fixes were maticulously planned, executed, fully tested and confirmed working before commiting. Code additions follow the project guidelines and workflows in an effort to maintain a clean development process.



## Setup

Recommended and fastest way is using Docker (or Podman):

- Via Docker `run`:
```
docker run --name searxng-enhanced -d \
  -p 8080:8080 \
  -v searxng-config:/etc/searxng \
  -v searxng-data:/var/cache/searxng \
  ghcr.io/seriousconcept1134/searxng-enhanced:latest
```

- Via Docker `compose` (in your `docker-compose.yaml` configuration) set `image` to:
```
services:
  searxng:
    image: ghcr.io/seriousconcept1134/searxng-enhanced:latest
  ...
```

Official Documentation:

To install SearXNG, follow the [Installation guide](https://docs.searxng.org/admin/installation.html).

To configure SearXNG, see the [Configuration guide](https://docs.searxng.org/admin/settings/index.html).

Additional how-to guides are available in the [admin documentation](https://docs.searxng.org/admin/index.html).

## Community

Questions and discussion:

- Matrix: [#searxng:matrix.org](https://matrix.to/#/#searxng:matrix.org)

## Contributing

Contributions are welcome — see [CONTRIBUTING](https://github.com/searxng/searxng/blob/master/CONTRIBUTING.rst) for details.

## License

Licensed under the GNU Affero General Public License v3.0 or later. See [LICENSE](https://github.com/searxng/searxng/blob/master/LICENSE) for the full text.
