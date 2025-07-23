# SPDX-License-Identifier: AGPL-3.0-or-later
"""This is the implementation of the Google Videos engine.

.. admonition:: Content-Security-Policy (CSP)

   This engine needs to allow images from the `data URLs`_ (prefixed with the
   ``data:`` scheme)::

     Header set Content-Security-Policy "img-src 'self' data: ;"

.. _data URLs:
   https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/Data_URIs
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from urllib.parse import urlencode
from lxml import html

from searx.utils import (
    eval_xpath,
    eval_xpath_list,
    eval_xpath_getindex,
    extract_text,
)

from searx.engines.google import fetch_traits  # pylint: disable=unused-import
from searx.engines.google import (
    get_google_info,
    time_range_dict,
    filter_mapping,
    suggestion_xpath,
    detect_google_sorry,
    ui_async,
    parse_data_images,
)
from searx.enginelib.traits import EngineTraits
from searx.utils import get_embeded_stream_url

if TYPE_CHECKING:
    logger: logging.Logger

logger = logging.getLogger('searx.engines.google_videos')
traits: EngineTraits

# about
about = {
    "website": 'https://www.google.com',
    "wikidata_id": 'Q219885',
    "official_api_documentation": 'https://developers.google.com/custom-search',
    "use_official_api": False,
    "require_api_key": False,
    "results": 'HTML',
}

# engine dependent config
categories = ['videos', 'web']
paging = True
max_page = 50
language_support = True
time_range_support = True
safesearch = True

def request(query, params):
    """Google-Video search request"""
    google_info = get_google_info(params, traits)
    start = (params['pageno'] - 1) * 10

    query_url = (
        'https://'
        + google_info['subdomain']
        + '/search'
        + "?"
        + urlencode(
            {
                'q': query,
                'tbm': "vid",
                'start': start,
                **google_info['params'],
                'asearch': 'arc',
                'async': ui_async(start),
            }
        )
    )

    if params['time_range'] in time_range_dict:
        query_url += '&' + urlencode({'tbs': 'qdr:' + time_range_dict[params['time_range']]})
    if 'safesearch' in params:
        query_url += '&' + urlencode({'safe': filter_mapping[params['safesearch']]})
    params['url'] = query_url

    params['cookies'] = google_info['cookies']
    params['headers'].update(google_info['headers'])
    logger.debug("Constructed query URL: %s", query_url)
    return params

def response(resp):
    """Get response from google's search request"""
    results = []

    detect_google_sorry(resp)
    data_image_map = parse_data_images(resp.text)
    
    # Log data_image_map for debugging
    logger.debug("data_image_map keys: %s", list(data_image_map.keys()))

    # convert the text to dom
    dom = html.fromstring(resp.text)

    # Log all matched result divs
    result_divs = eval_xpath_list(dom, '//div[contains(@class, "MjjYud")]')
    logger.debug("Found %d result divs with XPath '//div[contains(@class, \"MjjYud\")]'",
                 len(result_divs))

    # parse results
    for i, result in enumerate(result_divs):
        logger.debug("Processing result #%d", i + 1)
        title = extract_text(eval_xpath_getindex(result, './/h3[contains(@class, "LC20lb")]', 0, default=None), allow_none=True)
        url = eval_xpath_getindex(result, './/a[@jsname="UWckNb"]/@href', 0, default=None)
        content = extract_text(eval_xpath_getindex(result, './/div[contains(@class, "ITZIwc")]', 0, default=None), allow_none=True)
        pub_info = extract_text(eval_xpath_getindex(result, './/div[contains(@class, "gqF9jc")]', 0, default=None), allow_none=True)
        # Broader XPath to find any <img> element
        thumbnail = eval_xpath_getindex(result, './/img/@src', 0, default=None)
        duration = extract_text(eval_xpath_getindex(result, './/span[contains(@class, "k1U36b")]', 0, default=None), allow_none=True)
        video_id = eval_xpath_getindex(result, './/div[@jscontroller="rTuANe"]/@data-vid', 0, default=None)

        # Log extracted fields
        logger.debug("Result #%d: title=%s, url=%s, video_id=%s, thumbnail=%s",
                     i + 1, title, url, video_id, thumbnail)

        # Handle thumbnail
        if thumbnail and thumbnail.startswith('data:image'):
            img_id = eval_xpath_getindex(result, './/img/@id', 0, default=None)
            logger.debug("Processing thumbnail: img_id=%s, thumbnail=%s", img_id, thumbnail)
            if img_id and img_id in data_image_map:
                thumbnail = data_image_map[img_id]
                logger.debug("Matched thumbnail for img_id=%s: %s", img_id, thumbnail[:50] + "..." if thumbnail else None)
            else:
                logger.debug("No match for img_id=%s in data_image_map", img_id)
                thumbnail = None
        # Attempt YouTube fallback even if thumbnail is None
        if not thumbnail and (video_id or (url and 'youtube.com' in url)):
            if video_id:
                thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                logger.debug("Using YouTube fallback thumbnail (video_id): %s", thumbnail)
            elif url:
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(url)
                video_id_from_url = parse_qs(parsed_url.query).get('v', [None])[0]
                if video_id_from_url:
                    thumbnail = f"https://img.youtube.com/vi/{video_id_from_url}/hqdefault.jpg"
                    logger.debug("Using YouTube fallback thumbnail (url): %s", thumbnail)
                else:
                    logger.debug("No video_id found for YouTube URL, thumbnail remains None")

        # Handle video embed URL
        embed_url = None
        if video_id:
            embed_url = get_embeded_stream_url(f"https://www.youtube.com/watch?v={video_id}")
            logger.debug("Generated embed_url from video_id: %s", embed_url)
        elif url:
            embed_url = get_embeded_stream_url(url)
            logger.debug("Generated embed_url from url: %s", embed_url)

        # Only append results with valid title and url
        if title and url:
            results.append({
                'url': url,
                'title': title,
                'content': content or '',
                'author': pub_info or '',
                'thumbnail': thumbnail or '',
                'length': duration or '',
                'iframe_src': embed_url or '',
                'template': 'videos.html',
            })
            logger.debug("Added result #%d to results", i + 1)
        else:
            logger.debug("Skipped result #%d: missing title or url", i + 1)

    # parse suggestion
    for suggestion in eval_xpath_list(dom, suggestion_xpath):
        results.append({'suggestion': extract_text(suggestion)})

    logger.debug("Returning %d results", len(results))
    return results
