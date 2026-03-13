# SPDX-License-Identifier: AGPL-3.0-or-later
"""Multi-paging logic for single-engine searches (specifically for videos)."""

import typing as t
from copy import deepcopy

if t.TYPE_CHECKING:
    from searx.search.processors.online import OnlineProcessor, OnlineParams
    from searx.result_types import EngineResults


def fetch_multiple_pages(
    processor: "OnlineProcessor",
    query: str,
    params: "OnlineParams",
    initial_results: "EngineResults",
) -> "EngineResults":
    """
    Fetch and stitch multiple pages of results if a single engine search is performed
    and the user requested more results than the engine's native capacity.
    """
    results_per_page = params.get("results_per_page")
    if not results_per_page:
        return initial_results

    # Determine native results per page
    # 1. Check for engine.results_per_page attribute
    # 2. Otherwise, count actual results in initial_results
    # 3. Fallback to 10 if nothing found
    native_results_per_page = getattr(processor.engine, "results_per_page", None)
    if native_results_per_page is None:
        native_results_per_page = sum(1 for r in initial_results if "url" in r)
        if native_results_per_page == 0:
            native_results_per_page = 10

    # If the engine already returned enough results, or if it doesn't return any, stop.
    current_count = sum(1 for r in initial_results if "url" in r)
    if current_count >= results_per_page or current_count == 0:
        return initial_results

    # Suggestions and other metadata should probably only be taken from the first page
    # so we'll append only 'url' results from subsequent pages.
    all_results = initial_results

    # Extract engine_data from the last result of the initial results if present
    def get_engine_data(results):
        for res in reversed(results):
            if "engine_data" in res:
                return res["engine_data"]
        return None

    current_engine_data = get_engine_data(initial_results)
    
    # Calculate the current page offset in terms of native pages
    # e.g. if user is on page 1, and results_per_page=30, and native is 10.
    # Page 1 (user) starts at offset 0.
    # We want to fetch native pages 2 and 3 (offsets 10 and 20).
    user_pageno = params.get("pageno", 1)
    
    # Cap the number of loops to avoid infinite loops
    max_loops = 10
    loops = 0

    while current_count < results_per_page and loops < max_loops:
        loops += 1
        
        # In the loop, we want to fetch the "next" native page.
        # We calculate the target offset:
        # target_offset = (user_pageno - 1) * results_per_page + current_count
        # Then we find the corresponding "native pageno":
        # native_pageno = (target_offset // native_results_per_page) + 1
        
        target_offset = (user_pageno - 1) * results_per_page + current_count
        native_pageno = (target_offset // native_results_per_page) + 1
        
        sub_params: "OnlineParams" = deepcopy(params)
        sub_params["pageno"] = native_pageno
        # We set results_per_page to the native capacity so the engine's request() 
        # calculates the offset correctly for small pages.
        sub_params["results_per_page"] = native_results_per_page
        
        # If the engine supports engine_data (continuation tokens), pass it.
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
                
            # Filter out suggestions and other non-result items to avoid duplicates/noise
            all_results.extend(new_actual_results)
            current_count += len(new_actual_results)
            
            # Update engine_data for the next loop
            current_engine_data = get_engine_data(new_results)
            
        except Exception: # pylint: disable=broad-except
            # If a sub-request fails, we just stop and return what we have
            processor.logger.error("Multipaging: sub-request failed for engine %s", processor.engine.name)
            break

    return all_results
