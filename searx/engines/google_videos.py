# SPDX-License-Identifier: AGPL-3.0-or-later
"""This is the implementation of the Google Videos engine.

.. admonition:: Content-Security-Policy (CSP)

   This engine needs to allow images from the `data URLs`_ (prefixed with the
   ``data:`` scheme)::

     Header set Content-Security-Policy "img-src 'self' data: ;"

.. _data URLs:
   https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/Data_URIs
"""
import re
import json
from urllib.parse import urlencode, urlparse, parse_qs, unquote
from lxml import html

from searx.utils import (
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
)
from searx.utils import get_embeded_stream_url
from searx import logger

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
results_per_page = 10
max_page = 50
language_support = True
time_range_support = True
safesearch = True

# traits
traits = None


def parse_data_images(text: str):
    """Extract all image ID to URL/Data mapping from the page."""
    data_image_map = {}

    # 1. Bulk extraction from google.ldi = {...} (Mechanism B)
    # This is usually for the bottom half of the results.
    ldi_match = re.search(r'google\.ldi\s*=\s*({.*?});', text, re.DOTALL)
    if ldi_match:
        try:
            # We use json.loads which handles the unicode escaping correctly.
            data_image_map.update(json.loads(ldi_match.group(1)))
        except Exception:  # pylint: disable=broad-except
            pass

    # 2. Individual extraction from _setImagesSrc calls (Mechanism A)
    # This covers both 'var ii=...; var s=...' and 'var s=...; var ii=...' patterns.
    # Pattern 1: var ii=['ID'];var s='DATA';
    for m in re.finditer(r"var ii=\['(dimg_[^']+)'\];var s='([^']+)';", text):
        data_image_map[m.group(1)] = m.group(2)
    # Pattern 2: var s='DATA';var ii=['ID'];
    for m in re.finditer(r"var s='([^']+)';var ii=\['(dimg_[^']+)'\];", text):
        data_image_map[m.group(2)] = m.group(1)

    # 3. Post-process ONLY the strings from regex (Mechanism A) to fix hex escapes.
    # Bulk JSON strings (Mechanism B) are already decoded.
    for img_id, val in data_image_map.items():
        if isinstance(val, str) and '\\x' in val:
            try:
                data_image_map[img_id] = val.encode('utf-8').decode('unicode-escape')
            except Exception:  # pylint: disable=broad-except
                pass
        
        # Standardize padding for base64
        if isinstance(val, str) and val.startswith("data:image"):
            end_pos = val.rfind("=")
            if end_pos > 0:
                data_image_map[img_id] = val[: end_pos + 1]

    return data_image_map


def extract_descriptions(text: str):
    """Extract descriptions from script tags using regex."""
    descriptions = {}
    # We look for ["Title","Description",...
    for match in re.finditer(r'\["([^"\[\]]{5,})","([^"\[\]]{10,})"', text):
        title, desc = match.groups()
        try:
            # json.loads handles unicode escapes like \u0026
            title_decoded = json.loads(f'"{title}"')
            desc_decoded = json.loads(f'"{desc}"').replace('\\n', ' ')
            descriptions[title_decoded] = desc_decoded
        except Exception:  # pylint: disable=broad-except
            descriptions[title] = desc
    return descriptions


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
                'udm': '7',
                'start': start,
                **google_info['params'],
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
    return params


def response(resp):
    """Get response from google's search request"""
    detect_google_sorry(resp)

    results = []
    data_image_map = parse_data_images(resp.text)
    script_descriptions = extract_descriptions(resp.text)
    dom = html.fromstring(resp.text)

    # Result container identified as div[@jsname="pKB8Bc"] (Stable outer anchor)
    result_divs = eval_xpath_list(dom, '//div[@jsname="pKB8Bc"]')

    for result in result_divs:
        # 1. Title extraction (role="heading")
        title_node = eval_xpath_getindex(result, './/*[@role="heading"]', 0, default=None)
        title = extract_text(title_node, allow_none=True)

        if not title:
            continue

        # 2. URL extraction (WVV5ke container or fallback to <a>)
        url = None
        video_data_node = eval_xpath_getindex(result, './/div[contains(@class, "WVV5ke")]', 0, default=None)
        if video_data_node is not None:
            url = video_data_node.get("data-surl") or video_data_node.get("data-curl")
            video_id = video_data_node.get("data-vid")
        else:
            video_id = None

        if not url:
            url = eval_xpath_getindex(result, './/a/@href', 0, default=None)

        if url and url.startswith('/url?q='):
            url = unquote(url[7:].split('&sa=U')[0])

        # 3. Content (Description) from script map
        content = script_descriptions.get(title, "")

        # 4. Metadata (Website, Date)
        metadata_div = eval_xpath_getindex(result, './/div[contains(@class, "WRu9Cd")]', 0, default=None)
        pub_info = None
        if metadata_div is not None:
            pub_info = extract_text(metadata_div)

        # 5. Thumbnail Extraction (Structural Nesting)
        # We look for an <img> descendant of the interaction element (rIRoqf)
        thumbnail = None
        img_node = eval_xpath_getindex(result, './/*[contains(@class, "rIRoqf")]//img', 0, default=None)
        
        if img_node is not None:
            img_id = img_node.get("id")
            # Preference 1: The high-resolution mapping from the page scripts
            if img_id and img_id in data_image_map:
                thumbnail = data_image_map[img_id]
            else:
                # Preference 2: Direct source from DOM (could be base64 or lazy URL)
                thumbnail = img_node.get("src")
                # Handle placeholders
                if (not thumbnail or 'base64,R0lGODlhAQABA' in thumbnail):
                    thumbnail = img_node.get("data-src") or thumbnail

        # Preference 3: YouTube fallback
        if (not thumbnail or 'base64,R0lGODlhAQABA' in thumbnail) and video_id:
            thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

        # Duration
        duration = extract_text(
            eval_xpath_getindex(result, './/span[contains(@class, "k1U36b")]', 0, default=None), allow_none=True
        )

        # Build final result
        if title and url:
            results.append({
                'url': url,
                'title': title,
                'content': content or '',
                'author': pub_info,
                'thumbnail': thumbnail,
                'length': duration,
                'iframe_src': get_embeded_stream_url(url) if url else None,
                'template': 'videos.html',
            })

    # Suggestions
    for suggestion in eval_xpath_list(dom, suggestion_xpath):
        results.append({'suggestion': extract_text(suggestion)})

    return results
