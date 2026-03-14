# SPDX-License-Identifier: AGPL-3.0-or-later
"""Multi-paging logic for single-engine searches (specifically for videos)."""

import typing as t
from copy import deepcopy

if t.TYPE_CHECKING:
    from searx.search.processors.online import OnlineProcessor, OnlineParams
    from searx.result_types import EngineResults


def get_native_results_per_page(processor: "OnlineProcessor") -> int:
    """Determine the engine's native results per page."""
    # 1. Check for engine.results_per_page attribute
    # 2. Fallback to 10 if nothing found (standard for most engines)
    return getattr(processor.engine, "results_per_page", 10)


def pre_process_params(processor: "OnlineProcessor", params: "OnlineParams"):
    """
    Adjust params before the first request if multi-paging is active.
    Translates user pageno (based on pref) to engine pageno (based on native capacity).
    """
    user_results_per_page = params.get("results_per_page")
    if not user_results_per_page:
        return

    native_results_per_page = get_native_results_per_page(processor)
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
    native_results_per_page = get_native_results_per_page(processor)
    
    current_count = sum(1 for r in initial_results if "url" in r)
    if current_count >= target_count or current_count == 0:
        return initial_results

    all_results = initial_results

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
        loops += 1
        current_native_pageno += 1
        
        sub_params: "OnlineParams" = deepcopy(params)
        sub_params["pageno"] = current_native_pageno
        sub_params["results_per_page"] = native_results_per_page
        
        if current_engine_data:
            sub_params["engine_data"][processor.engine.name] = current_engine_data
            
        try:
            # Perform a basic search for the next page
            new_results = processor._search_basic(query, sub_params)
            
            if not new_results:
                break
                
            new_actual_results = [r for r in new_results if "url" in r]
            if not new_actual_results:
                break
                
            all_results.extend(new_actual_results)
            current_count += len(new_actual_results)
            
            # Update engine_data for the next loop
            current_engine_data = get_engine_data(new_results)
            
        except Exception: # pylint: disable=broad-except
            processor.logger.error("Multipaging: sub-request failed for engine %s", processor.engine.name)
            break

    return all_results
