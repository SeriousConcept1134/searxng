# SPDX-License-Identifier: AGPL-3.0-or-later
"""Multi-paging logic for single-engine searches (specifically for videos)."""

import typing as t
import time
import random
from copy import deepcopy

from searx import get_setting

if t.TYPE_CHECKING:
    from searx.search.processors.online import OnlineProcessor, OnlineParams
    from searx.result_types import EngineResults


def get_native_results_per_page(processor: "OnlineProcessor") -> t.Optional[int]:
    """Determine the engine's native results per page."""
    # 1. Check for engine.results_per_page attribute
    # 2. Return None if not found (let the caller decide on a fallback or inference)
    return getattr(processor.engine, "results_per_page", None)


def pre_process_params(processor: "OnlineProcessor", params: "OnlineParams"):
    """
    Adjust params before the first request if multi-paging is active.
    Translates user pageno (based on pref) to engine pageno (based on native capacity).
    """
    user_results_per_page = params.get("results_per_page")
    if not user_results_per_page:
        return

    # Use 10 as a sane fallback for calculating the initial offset if capacity is unknown
    native_results_per_page = get_native_results_per_page(processor) or 10

    if user_results_per_page <= native_results_per_page:
        return

    # User Page 1 (30 results) -> Start 0 -> Native Page 1
    # User Page 2 (30 results) -> Start 30 -> Native Page 4 (30/10 + 1)
    user_pageno = params.get("pageno", 1)
    target_start = (user_pageno - 1) * user_results_per_page

    native_pageno = (target_start // native_results_per_page) + 1

    params["pageno"] = native_pageno
    # We also override results_per_page in the params so the engine
    # uses its native capacity for internal calculations.
    params["results_per_page"] = native_results_per_page


def fetch_multiple_pages(
    processor: "OnlineProcessor",
    query: str,
    params: "OnlineParams",
    initial_results: "EngineResults",
    target_count: int,
) -> "EngineResults":
    """
    Fetch and stitch multiple pages of results until target_count is reached.
    """
    # Helper to count valid results (those with a URL)
    def count_results(results):
        return sum(1 for r in results if "url" in r)

    # Helper to truncate results while preserving non-result items (like suggestions)
    def truncate_results(results, limit):
        truncated = []
        count = 0
        for r in results:
            if "url" in r:
                if count < limit:
                    truncated.append(r)
                    count += 1
            else:
                # Keep suggestions, answers, etc.
                truncated.append(r)
        return truncated

    initial_count = count_results(initial_results)

    # 1. If we already have enough results, truncate and return immediately.
    if initial_count >= target_count:
        return truncate_results(initial_results, target_count)

    # 2. If initial request returned no results, stop.
    if initial_count == 0:
        return initial_results

    # 3. Check engine's explicit capacity.
    native_results_per_page = get_native_results_per_page(processor)

    # 4. If the user's target is within the engine's explicit capacity,
    # we stop here (Bug fix: prevent extra query for 9/10 results).
    if native_results_per_page is not None and target_count <= native_results_per_page:
        return initial_results

    all_results = initial_results
    current_count = initial_count

    def get_engine_data(results):
        for res in reversed(results):
            if "engine_data" in res:
                return res["engine_data"]
        return None

    current_engine_data = get_engine_data(initial_results)
    current_native_pageno = params.get("pageno", 1)

    max_loops = 10
    loops = 0

    while current_count < target_count and loops < max_loops:
        if get_setting('multipaging.speed_limit', True):
            min_delay = get_setting('multipaging.min_delay', 500) / 1000.0
            max_delay = get_setting('multipaging.max_delay', 1000) / 1000.0
            delay = random.uniform(min_delay, max_delay) if max_delay > min_delay else min_delay

            processor.logger.debug("Multipaging: sleeping for %.2fs before fetch", delay)
            time.sleep(delay)

        loops += 1
        current_native_pageno += 1

        sub_params: "OnlineParams" = deepcopy(params)
        sub_params["pageno"] = current_native_pageno
        # If we have an explicit capacity, use it; otherwise fallback to 10 for the sub-query.
        sub_params["results_per_page"] = native_results_per_page or 10

        if current_engine_data:
            sub_params["engine_data"][processor.engine.name] = current_engine_data

        try:
            # Perform a basic search for the next page
            # pylint: disable=protected-access
            new_results = processor._search_basic(query, sub_params)

            if not new_results:
                break

            new_actual_results = [r for r in new_results if "url" in r]
            if not new_actual_results:
                # Inference: Engine returned no more results for this query.
                break

            all_results.extend(new_actual_results)
            current_count += len(new_actual_results)

            if current_count >= target_count:
                break

            # Update engine_data for the next loop
            current_engine_data = get_engine_data(new_results)

        except Exception:  # pylint: disable=broad-except
            processor.logger.error("Multipaging: sub-request failed for engine %s", processor.engine.name)
            break

    # Final truncation to ensure we adhere to the user's preference
    if current_count > target_count:
        return truncate_results(all_results, target_count)

    return all_results
