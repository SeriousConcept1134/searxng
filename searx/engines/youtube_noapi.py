# SPDX-License-Identifier: AGPL-3.0-or-later
"""Youtube (Videos)"""

from functools import reduce
from json import loads, dumps
from urllib.parse import quote_plus

from searx.utils import extr

# about
about = {
    "website": 'https://www.youtube.com/',
    "wikidata_id": 'Q866',
    "official_api_documentation": 'https://developers.google.com/youtube/v3/docs/search/list?apix=true',
    "use_official_api": False,
    "require_api_key": False,
    "results": 'HTML',
}

# engine dependent config
categories = ['videos', 'music']
paging = True
language_support = False
time_range_support = True

# search-url
base_url = 'https://www.youtube.com/results'
search_url = base_url + '?search_query={query}&page={page}'
time_range_url = '&sp=EgII{time_range}%253D%253D'
# the key seems to be constant
next_page_url = 'https://www.youtube.com/youtubei/v1/search?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8'
time_range_dict = {'day': 'Ag', 'week': 'Aw', 'month': 'BA', 'year': 'BQ'}

base_youtube_url = 'https://www.youtube.com/watch?v='


# do search-request
def request(query, params):
    params['cookies']['CONSENT'] = "YES+"
    if not params['engine_data'].get('next_page_token'):
        params['url'] = search_url.format(query=quote_plus(query), page=params['pageno'])
        if params['time_range'] in time_range_dict:
            params['url'] += time_range_url.format(time_range=time_range_dict[params['time_range']])
    else:
        params['url'] = next_page_url
        params['method'] = 'POST'
        params['data'] = dumps(
            {
                'context': {"client": {"clientName": "WEB", "clientVersion": "2.20210310.12.01"}},
                'continuation': params['engine_data']['next_page_token'],
            }
        )
        params['headers']['Content-Type'] = 'application/json'

    return params


# get response from search-request
def response(resp):
    if resp.search_params.get('engine_data'):
        return parse_next_page_response(resp.text)
    return parse_first_page_response(resp.text)


def parse_video_renderer(video):
    videoid = video.get('videoId')
    if videoid is None:
        return None

    url = base_youtube_url + videoid
    thumbnail = 'https://i.ytimg.com/vi/' + videoid + '/hqdefault.jpg'
    title = get_text_from_json(video.get('title', {}))

    # Try different description sources
    content = get_text_from_json(video.get('descriptionSnippet', {}))
    if not content and 'detailedMetadataSnippets' in video:
        content = get_text_from_json(video['detailedMetadataSnippets'][0].get('snippetText', {}))

    author = get_text_from_json(video.get('ownerText', {}))
    length = get_text_from_json(video.get('lengthText', {}))

    return {
        'url': url,
        'title': title,
        'content': content,
        'author': author,
        'length': length,
        'template': 'videos.html',
        'iframe_src': 'https://www.youtube-nocookie.com/embed/' + videoid + '?autoplay=0',
        'thumbnail': thumbnail,
    }


def parse_next_page_response(response_text):
    results = []
    result_json = loads(response_text)
    for continuation_item in result_json['onResponseReceivedCommands'][0].get('appendContinuationItemsAction', {}).get(
        'continuationItems', []
    ):
        if 'itemSectionRenderer' in continuation_item:
            for item in continuation_item['itemSectionRenderer'].get('contents', []):
                if 'videoRenderer' in item:
                    res = parse_video_renderer(item['videoRenderer'])
                    if res:
                        results.append(res)
        elif 'continuationItemRenderer' in continuation_item:
            token = (
                continuation_item['continuationItemRenderer']
                .get('continuationEndpoint', {})
                .get('continuationCommand', {})
                .get('token')
            )
            if token:
                results.append({"engine_data": token, "key": "next_page_token"})

    return results


def parse_first_page_response(response_text):
    results = []
    results_data = extr(response_text, 'ytInitialData = ', ';</script>')

    results_json = loads(results_data) if results_data else {}
    sections = (
        results_json.get('contents', {})
        .get('twoColumnSearchResultsRenderer', {})
        .get('primaryContents', {})
        .get('sectionListRenderer', {})
        .get('contents', [])
    )

    for section in sections:
        if "continuationItemRenderer" in section:
            next_page_token = (
                section["continuationItemRenderer"]
                .get("continuationEndpoint", {})
                .get("continuationCommand", {})
                .get("token", "")
            )
            if next_page_token:
                results.append(
                    {
                        "engine_data": next_page_token,
                        "key": "next_page_token",
                    }
                )
        for video_container in section.get('itemSectionRenderer', {}).get('contents', []):
            if 'videoRenderer' in video_container:
                res = parse_video_renderer(video_container['videoRenderer'])
                if res:
                    results.append(res)
            elif 'shelfRenderer' in video_container:
                for shelf_item in (
                    video_container['shelfRenderer'].get('content', {}).get('verticalListRenderer', {}).get('contents', [])
                ):
                    if 'videoRenderer' in shelf_item:
                        res = parse_video_renderer(shelf_item['videoRenderer'])
                        if res:
                            results.append(res)

    return results


def get_text_from_json(element):
    if 'runs' in element:
        return reduce(lambda a, b: a + b.get('text', ''), element.get('runs'), '')
    return element.get('simpleText', '')
