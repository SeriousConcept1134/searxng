# Upstream Merge History (SearXNG Dev Branch)

This document tracks the handling of upstream commits from `searxng/searxng` (master) into this enhanced fork's `dev` branch.

**Date of Analysis**: 2026-03-23
**Status**: 11 commits analyzed. 8 merged (5 with manual conflict resolution), 3 skipped.

---

## 1. Merged Commits (Clean)

The following commits were identified as cleanly mergeable and were cherry-picked directly.

| Upstream Hash | Local Hash | Description |
| :--- | :--- | :--- |
| `6c7e9c197` | `90050d4a4` | [upd] github-actions: Bump actions/cache from 5.0.3 to 5.0.4 |
| `8ad72872b" | `7f3bd3154` | [upd] github-actions: Bump github/codeql-action from 4.32.6 to 4.33.0 |
| `c589b56d6` | `b79e11eb5` | [upd] web-client (simple): Bump the minor group |

---

## 2. Merged Commits (Conflict Resolution)

The following commits required manual intervention to preserve fork-specific enhancements.

### [feat] Autocomplete focus/blur (`5ab3ef774`)
*   **Local Hash**: `643a01d40`
*   **Resolution**: 
    *   **Preserved**: `form?.requestSubmit()` from our fork to ensure category synchronization (e.g., staying in Videos category) remains functional.
    *   **Adopted**: Focus/Blur logic (auto-open/close) and Escape key support from upstream.
    *   **Rejected**: Upstream's `form?.submit()` which bypasses custom listeners.

### [enh] Rework bing engine (`6521190bb`)
*   **Local Hash**: `df1b998cf`
*   **Resolution**:
    *   **Adopted**: Upstream's new shared locale logic (`mkt` parameter and header-based market settings) and updated XPath selectors for Web, News, and Video results.
    *   **Preserved**: Fork-specific sanitization in `bing_images.py` (PUA character removal) and the Zero-Width Space hack (`\u200B`) which prevents descriptions from being stripped when they match titles.

### [upd] Bump vite in /client/simple (`3810dc9d1`)
*   **Local Hash**: `398501bc4`
*   **Resolution**:
    *   **Manual Update**: Manually updated `package.json` to version `8.0.0` and regenerated `package-lock.json`.
    *   **Asset Rebuild**: Cleaned `searx/static/themes/simple/` and ran `./manage themes.all` to generate fresh assets. This was necessary because upstream's pre-built assets conflict with our custom UI source code.

### [fix] google: switch to using "Google App" for Android useragent (`2c1ce3b`)
*   **Local Hash**: `9738511ac`
*   **Resolution**:
    *   **Adopted**: Resolved all conflicts in `google.py` in favor of the upstream commit's version to maintain compatibility with the new Android User Agent layout.

### [fix] google engine - don't set __Secure-ENID in the HTTP header (`c4f51aa`)
*   **Local Hash**: `181b30824`
*   **Resolution**:
    *   **Manual Application**: The header was surgically removed from our refactored `google.py` implementation.
    *   **Adopted**: Upstream's optimization to remove the redundant `__Secure-ENID` header, as the Android GSA parsing logic only requires the User-Agent.

---

## 3. Skipped Commits

The following commits were skipped because the fork contains superior or incompatible implementations.

| Upstream Hash | Description | Reasoning |
| :--- | :--- | :--- |
| `2bb8ac17c` | [fix] Youtube referrerpolicy | Fork has a more robust implementation for video player embedding and policy. |
| `4c4ed4b19` | [fix] google engine thumbnails | Fork has enhanced thumbnail extraction and multi-paging logic that supersedes this. |
| `2bf5f00e7` | [build] /static | Upstream pre-built static assets are based on master; we generate our own based on fork changes. |
