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

    # Bulk extraction from google.ldi = {...}
    ldi_match = re.search(r'google\.ldi\s*=\s*({.*?});', text, re.DOTALL)
    if ldi_match:
        try:
            data_image_map.update(json.loads(ldi_match.group(1)))
        except Exception:  # pylint: disable=broad-except
            pass

    # Individual extraction from _setImagesSrc calls (Both patterns)
    for m in re.finditer(r"var ii=\['(dimg_[^']+)'\];var s='([^']+)';", text):
        data_image_map[m.group(1)] = m.group(2)
    for m in re.finditer(r"var s='([^']+)';var ii=\['(dimg_[^']+)'\];", text):
        data_image_map[m.group(2)] = m.group(1)

    # Post-process strings to fix encoding and padding
    for img_id, val in data_image_map.items():
        if isinstance(val, str) and '\\x' in val:
            try:
                data_image_map[img_id] = val.encode('utf-8').decode('unicode-escape')
            except Exception:  # pylint: disable=broad-except
                pass

        if isinstance(val, str) and val.startswith("data:image"):
            end_pos = val.rfind("=")
            if end_pos > 0:
                data_image_map[img_id] = val[: end_pos + 1]

    return data_image_map


def extract_descriptions(text: str):
    """Extract descriptions from script tags using regex."""
    descriptions = {}
    for match in re.finditer(r'\["([^"\[\]]{5,})","([^"\[\]]{10,})"', text):
        title, desc = match.groups()
        try:
            title_decoded = json.loads(f'"{title}"')
            desc_decoded = json.loads(f'"{desc}"').replace('\\n', ' ')
            descriptions[title_decoded] = desc_decoded
        except Exception:  # pylint: disable=broad-except
            descriptions[title] = desc
    return descriptions


def yt_reconstruct_thumbnail(url: str) -> str | None:
    """Reconstruct high-resolution YouTube thumbnail from URL."""
    if 'youtube.com' in url or 'youtu.be' in url:
        yt_id_match = re.search(r'(?:v=|\/live\/|embed\/|youtu\.be\/)([0-9A-Za-z_-]{11})', url)
        if yt_id_match:
            return f"https://img.youtube.com/vi/{yt_id_match.group(1)}/mqdefault.jpg"
    return None


def request(query, params):
    """Google-Video search request"""
    google_info = get_google_info(params, traits)

    # Base parameters
    # Uses udm=7 for the modern GSA layout. While udm=7 and tbm=vid are used
    # together to prevent redirects on residential IPs, this configuration
    # remains sensitive to high-risk proxy IPs (e.g. Cloudflare WARP) which
    # may still trigger 302 redirects.
    query_params = {
        'q': query,
        'tbm': 'vid',
        'filter': '0',
        'source': 'lnms',
        'aep': '1',
        'biw': '400',
        'bih': '700',
        **google_info['params'],
    }

    if params['pageno'] > 1:
        query_params['start'] = (params['pageno'] - 1) * 10

    query_url = 'https://' + google_info['subdomain'] + '/search?' + urlencode(query_params)
    query_url += '&udm=7'

    if params['time_range'] in time_range_dict:
        query_url += '&' + urlencode({'tbs': 'qdr:' + time_range_dict[params['time_range']]})
    if 'safesearch' in params:
        query_url += '&' + urlencode({'safe': filter_mapping[params['safesearch']]})

    params['url'] = query_url
    params['cookies'] = google_info['cookies']
    params['headers'].update(google_info['headers'])

    return params


def parse_layout_1(dom, text, data_image_map, script_descriptions):
    """Parser for Layout 1 (Modern Android App Layout)"""
    results = []
    # Identified by jsname="pKB8Bc" containers
    result_divs = eval_xpath_list(dom, '//div[@jsname="pKB8Bc"]')

    for result in result_divs:
        title_node = eval_xpath_getindex(result, './/*[@role="heading"]', 0, default=None)
        title = extract_text(title_node, allow_none=True)
        if not title:
            continue

        video_data_node = eval_xpath_getindex(result, './/div[contains(@class, "WVV5ke")]', 0, default=None)
        url = None
        video_id = None
        if video_data_node is not None:
            url = video_data_node.get("data-surl") or video_data_node.get("data-curl")
            video_id = video_data_node.get("data-vid")

        if not url:
            url = eval_xpath_getindex(result, './/a/@href', 0, default=None)
        if url and url.startswith('/url?q='):
            url = unquote(url[7:].split('&sa=U')[0])

        content = script_descriptions.get(title, "")

        # Metadata parsing (Split Author and Date)
        metadata_div = eval_xpath_getindex(result, './/div[contains(@class, "WRu9Cd")]', 0, default=None)
        pub_info = extract_text(metadata_div) if metadata_div is not None else ""

        author = None
        metadata = []
        if pub_info:
            # Matches strings like "YouTube · Ginger Cat1 month ago"
            # or "YouTube · The Dodo2 days ago"
            m = re.match(r'(.*?·\s*.*?)(\d+\s+\w+\s+ago|\d+\s+\w+\s+\d{4})', pub_info)
            if m:
                author, date_str = m.groups()
                author = author.rstrip(' ·').strip()
                metadata.append(date_str)
            else:
                author = pub_info

        thumbnail = yt_reconstruct_thumbnail(url) if url else None
        if not thumbnail:
            img_node = eval_xpath_getindex(result, './/*[contains(@class, "rIRoqf")]//img', 0, default=None)
            if img_node is not None:
                img_id = img_node.get("id")
                if img_id and img_id in data_image_map:
                    thumbnail = data_image_map[img_id]
                else:
                    thumbnail = img_node.get("src")
                    if not thumbnail or 'base64,R0lGODlhAQABA' in thumbnail:
                        thumbnail = img_node.get("data-src") or thumbnail

        if (not thumbnail or 'base64,R0lGODlhAQABA' in thumbnail) and video_id:
            thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

        duration = extract_text(
            eval_xpath_getindex(result, './/span[contains(@class, "k1U36b")]', 0, default=None), allow_none=True
        )

        if title and url:
            results.append(
                {
                    'url': url,
                    'title': title,
                    'content': content or '',
                    'author': author,
                    'thumbnail': thumbnail,
                    'length': duration,
                    'iframe_src': get_embeded_stream_url(url) if url else None,
                    'template': 'videos.html',
                    'metadata': " | ".join(metadata) if metadata else None,
                }
            )
    return results


def parse_layout_2(dom, text, data_image_map, script_descriptions):
    """Parser for Layout 2 (KFKAWI / Heirloom Android Layout)"""
    results = []
    # Identified by Gx5Zad containers
    result_divs = eval_xpath_list(dom, '//div[contains(@class, "Gx5Zad")]')

    for result in result_divs:
        # 1. Title (typically in <h3>)
        title_node = eval_xpath_getindex(result, './/h3', 0, default=None)
        title = extract_text(title_node, allow_none=True)
        if not title:
            continue

        # 2. URL
        url = eval_xpath_getindex(result, './/a/@href', 0, default=None)
        if url and url.startswith('/url?q='):
            url = unquote(url[7:].split('&sa=U')[0])

        # 3. Content (Description)
        content = script_descriptions.get(title, "")
        if not content:
            # Fallback to description div
            desc_nodes = result.xpath('.//div[contains(@class, "kCrYT")]/div/div[string-length(text()) > 10]')
            if desc_nodes:
                content = extract_text(desc_nodes[0])

        # 4. Metadata (Duration, Posted)
        duration = None
        metadata = []
        metadata_text = extract_text(result)

        dur_match = re.search(r'Duration:\s*(\d+:\d+)', metadata_text)
        if dur_match:
            duration = dur_match.group(1)

        # Capture date as generic metadata
        post_match = re.search(r'Posted:\s*([^<]+)', metadata_text)
        if post_match:
            date_str = post_match.group(1).split('\n')[0].strip()
            metadata.append(date_str)

        # 5. Thumbnail
        thumbnail = yt_reconstruct_thumbnail(url) if url else None
        if not thumbnail:
            img_node = eval_xpath_getindex(result, './/img', 0, default=None)
            if img_node is not None:
                img_id = img_node.get("id")
                if img_id and img_id in data_image_map:
                    thumbnail = data_image_map[img_id]
                else:
                    thumbnail = img_node.get("src")
                    if not thumbnail or 'base64,R0lGODlhAQABA' in thumbnail:
                        thumbnail = img_node.get("data-src") or thumbnail

        if title and url:
            results.append(
                {
                    'url': url,
                    'title': title,
                    'content': content or '',
                    'author': None,  # Layout 2 doesn't provide author
                    'thumbnail': thumbnail,
                    'length': duration,
                    'iframe_src': get_embeded_stream_url(url) if url else None,
                    'template': 'videos.html',
                    'metadata': " | ".join(metadata) if metadata else None,
                }
            )
    return results


def response(resp):
    """Get response from google's search request"""
    detect_google_sorry(resp)

    data_image_map = parse_data_images(resp.text)
    script_descriptions = extract_descriptions(resp.text)
    dom = html.fromstring(resp.text)

    # Layout Fingerprinting
    if eval_xpath_list(dom, '//div[@jsname="pKB8Bc"]'):
        results = parse_layout_1(dom, resp.text, data_image_map, script_descriptions)
    elif eval_xpath_list(dom, '//div[contains(@class, "Gx5Zad")]'):
        results = parse_layout_2(dom, resp.text, data_image_map, script_descriptions)
    else:
        # Fallback
        results = parse_layout_1(dom, resp.text, data_image_map, script_descriptions)

    # Suggestions
    for suggestion in eval_xpath_list(dom, suggestion_xpath):
        results.append({'suggestion': extract_text(suggestion)})

    return results
