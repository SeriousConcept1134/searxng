.. SPDX-License-Identifier: AGPL-3.0-or-later

.. _metasearch engine: https://en.wikipedia.org/wiki/Metasearch_engine
.. _Installation guide: https://docs.searxng.org/admin/installation.html
.. _Configuration guide: https://docs.searxng.org/admin/settings/index.html
.. _CONTRIBUTING: https://github.com/searxng/searxng/blob/master/CONTRIBUTING.rst
.. _LICENSE: https://github.com/searxng/searxng/blob/master/LICENSE

.. figure:: https://raw.githubusercontent.com/searxng/searxng/master/client/simple/src/brand/searxng.svg
   :target: https://searxng.org
   :alt: SearXNG
   :width: 512px

|organization| |documentation| |license| |commits| |translated|

.. |organization| image:: https://img.shields.io/badge/organization-3050ff?style=flat-square&logo=searxng&logoColor=fff&cacheSeconds=86400
   :target: https://github.com/searxng
   :alt: Organization

.. |documentation| image:: https://img.shields.io/badge/documentation-3050ff?style=flat-square&logo=readthedocs&logoColor=fff&cacheSeconds=86400
   :target: https://docs.searxng.org
   :alt: Documentation

.. |license| image:: https://img.shields.io/github/license/searxng/searxng?style=flat-square&label=license&color=3050ff&cacheSeconds=86400
   :target: https://github.com/searxng/searxng/blob/master/LICENSE
   :alt: License

.. |commits| image:: https://img.shields.io/github/commit-activity/y/searxng/searxng/master?style=flat-square&label=commits&color=3050ff&cacheSeconds=3600
   :target: https://github.com/searxng/searxng/commits/master/
   :alt: Commits

.. |translated| image:: https://img.shields.io/weblate/progress/searxng?server=https%3A%2F%2Ftranslate.codeberg.org&style=flat-square&label=translated&color=3050ff&cacheSeconds=86400
   :target: https://translate.codeberg.org/projects/searxng/
   :alt: Translated

----

SearXNG is a free, privacy-respecting `metasearch engine`_ — users are never tracked or profiled.

About This Fork
===============

While SearXNG is an excellent privacy-focused meta-search engine, its stock UI can feel spartan.
This fork builds on that solid foundation with a modernized interface, quality-of-life improvements,
and targeted bug fixes — without compromising the core privacy guarantees.

It's a work in progress (though fully functional). I originally built it for personal use,
but made it public for anyone who may find it useful.

**Goals:**

- Stay current with upstream ``master`` at all times
- Layer in meaningful UI/UX improvements incrementally
- Fix bugs faster where possible


What's New
==========

✨ New UI/UX features
---------------------

🌓 Dynamic Theme Switcher
^^^^^^^^^^^^^^^^^^^^^^^^^

A toggle accessible from any page lets you switch between light and dark modes on the fly.

- **Intelligent switching**: automatically detects whether you prefer *Dark* or *Black* (OLED) mode and
  alternates between that and light, rather than always falling back to a generic dark theme.
- Uses ``window.matchMedia`` for native system-level sync.
- Persists your preference via ``simple_style`` and ``preferred_dark_style`` cookies.

🖼️ Video Search: Grid View & Dynamic Resizer
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Brings the image-search grid experience to video results.

- **Grid view toggle**: switch between list and grid layouts at any time.
- **Live resizer**: a real-time slider controls how many results appear per row.
- **Cleaner layout**: consistent vertical spacing and a logical result order
  (URL → Engines → Thumbnail → Title → Content → Metadata), maintained via CSS variables
  (``--video-size``) and Flexbox ``order`` rules regardless of thumbnail size.

🎥 Ability to set Results Per Page (Video Search)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Set the number of video results shown per page: from 10 up to 50.

Under the hood, a transparent "stitching" mechanism fetches and merges multiple pages from
underlying engines that have fixed pagination limits. For example, Google Videos is capped at
10 results per page. Requesting 30 results with ``!gov <query>`` would normally yield only 10;
the stitching layer calls the engine multiple times with offset pages and merges the results
seamlessly before presenting them to you.

Implemented via ``multipaging.py`` and a ``pre_process_params`` stage that translates user-facing
page numbers into the correct native engine offsets (e.g., User Page 2 @ 30/page → Native Page 4 @ 10/page).

----

📺 Video Preview Improvements
------------------------------

🔇 Universal Autoplay Suppression
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Strengthened protections against unwanted autoplay across all supported video engines
(YouTube, Dailymotion, BitChute, and others).

- Standardized ``autoplay=0`` URL parameters site-wide.
- Applied modern iframe Permissions Policy (``autoplay 'none'``) as a secondary enforcement layer.

🚀 Interaction-Based Lazy Loading
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Video previews no longer load in the background. Iframes are initialized with an empty ``src``;
the actual URL is stored in a ``data-src`` attribute and only applied when you explicitly click
**Show Video**. This eliminates background tracking, reduces page load times, and closes the gap
where autoplay suppression alone was insufficient.

🛑 Playback Kill Switch
^^^^^^^^^^^^^^^^^^^^^^^^

Clicking **Hide Video** now immediately resets the iframe ``src`` to an empty string, forcing
the browser to unload the external media player entirely. Previously, hidden videos could
continue streaming or transferring data in the background.

----

🛠️ Engine & UI Fixes
---------------------

Google Engine
^^^^^^^^^^^^^

- **Google Videos description parsing**: Fixed the issue where Google Videos was returning malformed or
  missing snippets. The extraction logic was modernized to support new ``ITZIwc``, ``p4wth``,
  ``fzUZNc``, and ``data-sncf`` containers, including a fallback to ``aria-label`` attributes for
  certain layout variants.
- **Description parsing (General)**: modernized snippet extraction to support ``ITZIwc``, ``p4wth``,
  ``fzUZNc``, and ``data-sncf`` containers, resolving malformed or missing descriptions
  in Google results.
- **Duplicate results**: tightened result targeting using high-precision XPaths
  (``jsname="pKB8Bc"``, ``WVV5ke"``) and explicit filtering of top-level ``MjjYud`` wrappers.
- **Thumbnail reliability**: enhanced ``parse_data_images`` to extract JSON-mapped image data
  from modern ``google.ldi`` and ``google.pim`` structures, with logic to prefer high-resolution
  images and exclude favicons and UI chrome.

General UI/UX
^^^^^^^^^^^^^

- **Category highlighting**: fixed a bug where categories (e.g., *Videos*) would not highlight
  when triggered via a bang shortcut (``!yt``, ``!gov``, etc.). Resolved via ``triggered_categories``
  logic that correctly infers the active category from the bang used.
- **Pagination layout**: corrected grid-view pagination where *Previous* / *Next* buttons were
  pushed to the screen edges; they are now centered and correctly sequenced.
- **YouTube "Error 153"**: resolved a common inline playback failure for embedded YouTube videos
  by applying the appropriate ``allow`` and ``referrer`` iframe policies.


Setup
=====

To install SearXNG, follow the `Installation guide`_.

To configure SearXNG, see the `Configuration guide`_.

Additional how-to guides are available in the `admin documentation <https://docs.searxng.org/admin/index.html>`_.

Community
=========

Questions and discussion:

- Matrix: `#searxng:matrix.org <https://matrix.to/#/#searxng:matrix.org>`_

Contributing
============

Contributions are welcome — see CONTRIBUTING_ for details.

License
=======

Licensed under the GNU Affero General Public License v3.0 or later. See LICENSE_ for the full text.
