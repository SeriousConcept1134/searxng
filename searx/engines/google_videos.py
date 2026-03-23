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


# =26;[3,"dimg_ZNMiZPCqE4apxc8P3a2tuAQ_137"]a87;data:image/jpeg;base64,/9j/4AAQSkZJRgABA
# ...6T+9Nl4cnD+gr9OK8I56/tX3l86nWYw//2Q==26;
RE_DATA_IMAGE = re.compile(r'"(dimg_[^"]*)"[^;]*;(data:image[^;]*;[^;]*);?')

# Regex to find title and description pairs in scripts: ["Title","Description",...
RE_SCRIPT_DESCRIPTION = re.compile(r'\["([^"\[\]]{5,})","([^"\[\]]{10,})"')


def parse_data_images(text: str):
    data_image_map = {}

    for img_id, data_image in RE_DATA_IMAGE.findall(text):
        end_pos = data_image.rfind("=")
        if end_pos > 0:
            data_image = data_image[: end_pos + 1]
        data_image_map[img_id] = data_image
    return data_image_map


def extract_descriptions(text: str):
    """Extract descriptions from script tags using regex."""
    descriptions = {}
    for match in RE_SCRIPT_DESCRIPTION.finditer(text):
        title, desc = match.groups()
        try:
            # Basic manual unescape for common ones
            desc = desc.replace('\\u0026', '&').replace('\\"', '"').replace('\\n', ' ')
            descriptions[title] = desc
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
    return params


def response(resp):
    """Get response from google's search request"""
    detect_google_sorry(resp)

    results = []
    data_image_map = parse_data_images(resp.text)
    script_descriptions = extract_descriptions(resp.text)
    dom = html.fromstring(resp.text)

    # In this layout, each result is typically a div containing:
    # 1. Thumbnail: div.kSFuOd
    # 2. Link/Title: a.rIRoqf containing div.rp5hob
    # 3. Metadata: div.WRu9Cd
    
    # We find all title containers as anchors for results
    title_containers = eval_xpath_list(dom, '//div[@class="rp5hob"]')

    for title_div in title_containers:
        # Find the link container (parent or self)
        link_node = eval_xpath_getindex(title_div, 'ancestor-or-self::a[@class="rIRoqf"]', 0, default=None)
        if link_node is None:
            continue

        url = link_node.get("href")
        if url and url.startswith('/url?q='):
            url = unquote(url[7:].split('&sa=U')[0])

        title = extract_text(title_div)
        if not title:
            continue

        # Content (Description) from script map
        content = script_descriptions.get(title, "")

        # Find metadata and thumbnail by looking at siblings/parent of the link container
        # Usually they are within a common parent
        common_parent = link_node.getparent()
        
        # Metadata
        metadata_text = None
        metadata_div = eval_xpath_getindex(common_parent, './/div[contains(@class, "WRu9Cd")]', 0, default=None)
        if metadata_div is not None:
            metadata_text = extract_text(metadata_div)

        # Thumbnail
        thumbnail = None
        # Look for div.kSFuOd within common parent or preceding sibling
        thumb_container = eval_xpath_getindex(common_parent, './/div[contains(@class, "kSFuOd")]', 0, default=None)
        if thumb_container is None:
            # Fallback to preceding sibling search if not nested
            thumb_container = eval_xpath_getindex(link_node, 'preceding-sibling::div[contains(@class, "kSFuOd")]', 0, default=None)

        if thumb_container is not None:
            img_node = eval_xpath_getindex(thumb_container, './/img', 0, default=None)
            if img_node is not None:
                thumbnail = img_node.get("data-src") or img_node.get("src")
                if thumbnail and thumbnail.startswith("data:image"):
                    img_id = img_node.get("id")
                    if img_id and img_id in data_image_map:
                        thumbnail = data_image_map[img_id]

        # Duration
        duration = extract_text(
            eval_xpath_getindex(common_parent, './/span[contains(@class, "k1U36b")]', 0, default=None), allow_none=True
        )

        video_id = None
        if url and 'youtube.com' in url:
            parsed_url = urlparse(url)
            video_id = parse_qs(parsed_url.query).get('v', [None])[0]
        elif url and 'youtu.be' in url:
            video_id = urlparse(url).path.split('/')[-1]

        if not thumbnail and video_id:
            thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

        # Handle video embed URL
        embed_url = None
        if video_id:
            embed_url = get_embeded_stream_url(f"https://www.youtube.com/watch?v={video_id}")
        elif url:
            embed_url = get_embeded_stream_url(url)

        # Only append results with valid title and url
        if title and url:
            results.append(
                {
                    'url': url,
                    'title': title,
                    'content': content or '',
                    'author': metadata_text,
                    'thumbnail': thumbnail,
                    'length': duration,
                    'iframe_src': embed_url,
                    'template': 'videos.html',
                }
            )

    # parse suggestion
    for suggestion in eval_xpath_list(dom, suggestion_xpath):
        results.append({'suggestion': extract_text(suggestion)})

    return results
