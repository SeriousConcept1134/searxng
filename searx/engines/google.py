# SPDX-License-Identifier: AGPL-3.0-or-later
"""This is the implementation of the Google WEB engine.  Some of this
implementations (manly the :py:obj:`get_google_info`) are shared by other
engines:

- :ref:`google images engine`
- :ref:`google news engine`
- :ref:`google videos engine`
- :ref:`google scholar engine`
- :ref:`google autocomplete`

"""

import random
import re
import string
import time
import typing as t
import json
from urllib.parse import unquote, urlencode

import babel
import babel.core
import babel.languages
from lxml import html

from searx.enginelib.traits import EngineTraits
from searx.exceptions import SearxEngineCaptchaException
from searx.locales import get_official_locales, language_tag, region_tag
from searx.result_types import EngineResults
from searx.utils import (
    eval_xpath,
    eval_xpath_getindex,
    eval_xpath_list,
    extract_text,
    gen_gsa_useragent,
)
from searx.utils import get_embeded_stream_url
from searx import logger

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

about = {
    "website": "https://www.google.com",
    "wikidata_id": "Q9366",
    "official_api_documentation": "https://developers.google.com/custom-search/",
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}

# engine dependent config
categories = ["general", "web"]
paging = True
max_page = 50
"""`Google max 50 pages`_

.. _Google max 50 pages: https://github.com/searxng/searxng/issues/2982
"""
time_range_support = True
safesearch = True

time_range_dict = {"day": "d", "week": "w", "month": "m", "year": "y"}

# Filter results. 0: None, 1: Moderate, 2: Strict
filter_mapping = {0: "off", 1: "medium", 2: "high"}

# specific xpath variables
# ------------------------

# Suggestions are links placed in a *card-section*, we extract only the text
# from the links not the links itself.
suggestion_xpath = '//div[contains(@class, "gGQDvd iIWm4b")]//a'

_arcid_range = string.ascii_letters + string.digits + "_-"
_arcid_random: tuple[str, int] | None = None


def ui_async(start: int) -> str:
    """Format of the response from UI's async request.

    - ``arc_id:<...>,use_ac:true,_fmt:prog``

    The arc_id is random generated every hour.
    """
    global _arcid_random  # pylint: disable=global-statement
    use_ac = "use_ac:true"
    # _fmt:html returns a HTTP 500 when user search for celebrities like
    # '!google natasha allegri' or '!google chris evans'
    _fmt = "_fmt:prog"

    # create a new random arc_id every hour
    if not _arcid_random or (int(time.time()) - _arcid_random[1]) > 3600:
        _arcid_random = ("".join(random.choices(_arcid_range, k=23)), int(time.time()))
    arc_id = f"arc_id:srp_{_arcid_random[0]}_1{start:02}"
    return ",".join([arc_id, use_ac, _fmt])


# traits
traits = None


def get_google_info(params: "OnlineParams", eng_traits: EngineTraits) -> dict[str, t.Any]:
    """Composing various (language) properties for the google engines (:ref:`google
    API`).

    This function is called by the various google engines (:ref:`google web
    engine`, :ref:`google images engine`, :ref:`google news engine` and
    :ref:`google videos engine`).

    :param dict param: Request parameters of the engine.  At least
        a ``searxng_locale`` key should be in the dictionary.

    :param eng_traits: Engine's traits fetched from google preferences
        (:py:obj:`searx.enginelib.traits.EngineTraits`)

    :rtype: dict
    :returns:
        Py-Dictionary with the key/value pairs:

        language:
            The language code that is used by google (e.g. ``lang_en`` or
            ``lang_zh-TW``)

        country:
            The country code that is used by google (e.g. ``US`` or ``TW``)

        locale:
            A instance of :py:obj:`babel.core.Locale` build from the
            ``searxng_locale`` value.

        subdomain:
            Google subdomain :py:obj:`google_domains` that fits to the country
            code.

        params:
            Py-Dictionary with additional request arguments (can be passed to
            :py:func:`urllib.parse.urlencode`).

            - ``hl`` parameter: specifies the interface language of user interface.
            - ``lr`` parameter: restricts search results to documents written in
              a particular language.
            - ``cr`` parameter: restricts search results to documents
              originating in a particular country.
            - ``ie`` parameter: sets the character encoding scheme that should
              be used to interpret the query string ('utf8').
            - ``oe`` parameter: sets the character encoding scheme that should
              be used to decode the XML result ('utf8').

        headers:
            Py-Dictionary with additional HTTP headers (can be passed to
            request's headers)

            - ``Accept: '*/*``

    """
    ret_val: dict[str, t.Any] = {
        "language": None, "country": None, "subdomain": None, "params": {},
        "headers": {}, "cookies": {}, "locale": None,
    }

    sxng_locale = params.get("searxng_locale", "all")
    try:
        locale = babel.Locale.parse(sxng_locale, sep="-")
    except babel.core.UnknownLocaleError:
        locale = None

    eng_lang = eng_traits.get_language(sxng_locale, "lang_en")
    lang_code = eng_lang.split("_")[-1]
    country = eng_traits.get_region(sxng_locale, eng_traits.all_locale)

    # Test zh_hans & zh_hant --> in the topmost links in the result list of list
    # TW and HK you should a find wiktionary.org zh_hant link.  In the result
    # list of zh-CN should not be no hant link instead you should find
    # zh.m.wikipedia.org/zh somewhere in the top.

    # '!go 日 :zh-TW' --> https://zh.m.wiktionary.org/zh-hant/%E6%97%A5
    # '!go 日 :zh-CN' --> https://zh.m.wikipedia.org/zh/%E6%97%A5

    ret_val["language"] = eng_lang
    ret_val["country"] = country
    ret_val["locale"] = locale
    ret_val["subdomain"] = eng_traits.custom["supported_domains"].get(country.upper(), "www.google.com")

    # hl parameter:
    #   The hl parameter specifies the interface language (host language) of
    #   your user interface. To improve the performance and the quality of your
    #   search results, you are strongly encouraged to set this parameter
    #   explicitly.
    #   https://developers.google.com/custom-search/docs/xml_results#hlsp
    # The Interface Language:
    #   https://developers.google.com/custom-search/docs/xml_results_appendices#interfaceLanguages

    # https://github.com/searxng/searxng/issues/2515#issuecomment-1607150817
    ret_val["params"]["hl"] = f"{lang_code}-{country}"

    # lr parameter:
    #   The lr (language restrict) parameter restricts search results to
    #   documents written in a particular language.
    #   https://developers.google.com/custom-search/docs/xml_results#lrsp
    #   Language Collection Values:
    #   https://developers.google.com/custom-search/docs/xml_results_appendices#languageCollections
    #
    # To select 'all' languages an empty 'lr' value is used.
    #
    # Different to other google services, Google Scholar supports to select more
    # than one language. The languages are separated by a pipe '|' (logical OR).
    # By example: &lr=lang_zh-TW%7Clang_de selects articles written in
    # traditional chinese OR german language.

    ret_val["params"]["lr"] = eng_lang if sxng_locale != "all" else ""

    # cr parameter:
    #   The cr parameter restricts search results to documents originating in a
    #   particular country.
    #   https://developers.google.com/custom-search/docs/xml_results#crsp

    # specify a region (country) only if a region is given in the selected
    # locale --> https://github.com/searxng/searxng/issues/2672
    ret_val["params"]["cr"] = "country" + country if len(sxng_locale.split("-")) > 1 else ""

    # gl parameter: (mandatory by Google News)
    #   The gl parameter value is a two-letter country code. For WebSearch
    #   results, the gl parameter boosts search results whose country of origin
    #   matches the parameter value. See the Country Codes section for a list of
    #   valid values.
    #   Specifying a gl parameter value in WebSearch requests should improve the
    #   relevance of results. This is particularly true for international
    #   customers and, even more specifically, for customers in English-speaking
    #   countries other than the United States.
    #   https://developers.google.com/custom-search/docs/xml_results#glsp

    # https://github.com/searxng/searxng/issues/2515#issuecomment-1606294635
    # ret_val['params']['gl'] = country

    # ie parameter:
    #   The ie parameter sets the character encoding scheme that should be used
    #   to interpret the query string. The default ie value is latin1.
    #   https://developers.google.com/custom-search/docs/xml_results#iesp

    ret_val["params"]["ie"] = "utf8"

    # oe parameter:
    #   The oe parameter sets the character encoding scheme that should be used
    #   to decode the XML result. The default oe value is latin1.
    #   https://developers.google.com/custom-search/docs/xml_results#oesp

    ret_val["params"]["oe"] = "utf8"

    # num parameter:
    #   The num parameter identifies the number of search results to return.
    #   The default num value is 10, and the maximum value is 20. If you request
    #   more than 20 results, only 20 results will be returned.
    #   https://developers.google.com/custom-search/docs/xml_results#numsp

    # HINT: seems to have no effect (tested in google WEB & Images)
    # ret_val['params']['num'] = 20

    # HTTP headers

    ret_val["headers"]["Accept"] = "*/*"
    ret_val["headers"]["User-Agent"] = gen_gsa_useragent()

    # Cookies

    # - https://github.com/searxng/searxng/pull/1679#issuecomment-1235432746
    # - https://github.com/searxng/searxng/issues/1555
    ret_val["cookies"]["CONSENT"] = "YES+"
    return ret_val


def detect_google_sorry(resp):
    if resp.url.host == "sorry.google.com" or resp.url.path.startswith("/sorry"):
        raise SearxEngineCaptchaException()


def request(query: str, params: "OnlineParams") -> None:
    """Google search request"""
    start = (params["pageno"] - 1) * 10
    google_info = get_google_info(params, traits)

    query_url = (
        "https://" + google_info["subdomain"] + "/search?" + urlencode({
            "q": query, **google_info["params"], "filter": "0", "start": start,
            "source": "lnms", "aep": "1",
            "biw": "400", "bih": "700",
        })
    )

    if params["time_range"] in time_range_dict:
        query_url += "&" + urlencode({"tbs": "qdr:" + time_range_dict[params["time_range"]]})
    if params["safesearch"]:
        query_url += "&" + urlencode({"safe": filter_mapping[params["safesearch"]]})
    
    params["url"] = query_url
    params["cookies"] = google_info["cookies"]
    params["headers"].update(google_info["headers"])


def parse_data_images(text: str):
    """Extract all image mapping from the page."""
    data_image_map = {}
    
    # 1. Broad JSON mapping search (ldi, pim, etc.)
    for match in re.finditer(r'google\.[a-z]+\s*=\s*({.*?});', text, re.DOTALL):
        try:
            data_image_map.update(json.loads(match.group(1)))
        except: pass

    # 2. Extract assignments like s='data:...'; ii=['dimg_...'];
    for m in re.finditer(r"s='(data:[^']+|https?://[^']+)';\s*(?:var\s+)?ii=\['([^']+)'\];", text):
        data_image_map[m.group(2)] = m.group(1)
    for m in re.finditer(r"(?:var\s+)?ii=\['([^']+)'\];\s*s='(data:[^']+|https?://[^']+)';", text):
        data_image_map[m.group(1)] = m.group(2)
        
    # 3. Modern GSA explicit calls
    for m in re.finditer(r"_setImageSrc\('([^']+)'\s*,\s*'([^']+)'\)", text):
        data_image_map[m.group(1)] = m.group(2)
    # Aggressive _setImagesSrc(ii,s) handler
    for m in re.finditer(r"ii=\['([^']+)'\];\s*_setImagesSrc\(ii,s\);", text):
        s_match = list(re.finditer(r"s='([^']+)'", text[:m.start()]))
        if s_match: data_image_map[m.group(1)] = s_match[-1].group(1)

    # 4. Global variable mapping (var s='...'; var ii=['...'])
    for m in re.finditer(r"var s='([^']+)';\s*var ii=\['([^']+)'\];", text):
        data_image_map[m.group(2)] = m.group(1)
    for m in re.finditer(r"var ii=\['([^']+)'\];\s*var s='([^']+)';", text):
        data_image_map[m.group(1)] = m.group(2)

    # 5. Extract all dimg_ IDs and their data from any script text
    for m in re.finditer(r'["\'](dimg_[^"\']+)["\']\s*:\s*["\'](data:[^"\']+|https?://[^"\']+)["\']', text):
        data_image_map[m.group(1)] = m.group(2)

    # Final Cleanup
    for img_id, val in data_image_map.items():
        if not isinstance(val, str): continue
        if '\\x' in val:
            try: val = val.encode('utf-8').decode('unicode-escape')
            except: pass
        val = val.replace('\\/', '/').replace('\\u003d', '=').replace('\\u0026', '&')
        val = val.rstrip('\\')
        data_image_map[img_id] = val
    return data_image_map


def extract_descriptions(text: str):
    """Extract descriptions from script tags."""
    descriptions = {}
    for match in re.finditer(r'\["([^"\[\]]{5,})","([^"\[\]]{10,})"', text):
        title, desc = match.groups()
        try:
            title_decoded = json.loads(f'"{title}"')
            desc_decoded = json.loads(f'"{desc}"').replace('\\n', ' ')
            descriptions[title_decoded] = desc_decoded
        except: descriptions[title] = desc
    return descriptions


def parse_layout_1(dom, text, data_image_map, script_descriptions):
    """Parser for Layout 1 (Modern Android Layout)"""
    results = []
    seen_results = set() # Store (url, template)
    
    # 1. Videos (STABLE VERSION PRESERVED)
    v_candidates = dom.xpath('//div[contains(@class, "WVV5ke")] | //div[contains(@class, "xT1K2d") and .//a[contains(@href, "youtube.com") or contains(@href, "vimeo.com")]]')
    if not v_candidates:
        v_candidates = dom.xpath('//div[@role="heading" and contains(text(), "Video")]/following-sibling::div//a[contains(@href, "youtube.com")]/ancestor::div[1]')

    for v in v_candidates:
        title = v.get('data-title') or extract_text(v.xpath('.//*[@role="heading"]'))
        url = v.get('data-surl') or v.get('data-curl') or extract_text(v.xpath('.//a[contains(@href, "youtube.com") or contains(@href, "vimeo.com")]/@href'))
        if url and url.startswith('/url?q='): url = unquote(url[7:].split('&sa=U')[0])
        
        template = 'videos.html'
        if title and url and (url, template) not in seen_results:
            content = extract_text(v.xpath('.//div[contains(@class, "vqseUe") or contains(@class, "vwPXuf")]')) or script_descriptions.get(title, "")
            
            img_node = eval_xpath_getindex(v, './/img', 0, default=None)
            img_id = img_node.get("id") if img_node is not None else None
            thumbnail = data_image_map.get(img_id)
            if not thumbnail and img_id:
                for k, val in data_image_map.items():
                    if k.endswith(img_id): thumbnail = val; break
            
            if (not thumbnail) and v.get('data-vid'):
                thumbnail = f"https://img.youtube.com/vi/{v.get('data-vid')}/hqdefault.jpg"
            
            duration = extract_text(v.xpath('.//div[contains(@class, "c8rnLc")]//span'))
            if not duration:
                aria = extract_text(v.xpath('.//@aria-label'))
                d_match = re.search(r'(\d+:\d+)', aria)
                if d_match: duration = d_match.group(1)

            res = {'url': url, 'title': title, 'content': content, 'thumbnail': thumbnail, 'template': template}
            if duration: res['length'] = duration
            
            if 'youtube.com' in url or 'youtu.be' in url:
                vid_match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', url)
                if vid_match: res['iframe_src'] = f"https://www.youtube.com/embed/{vid_match.group(1)}"

            results.append(res)
            seen_results.add((url, template))

    # 2. Reddit (Only first with description)
    for r in dom.xpath('//div[contains(@class, "yD2vYc")]'):
        if r.xpath('./ancestor::div[contains(@class, "WVV5ke") or contains(@class, "xT1K2d")]'):
            continue
            
        content = extract_text(r.xpath('.//div[contains(@class, "vqseUe")]'))
        if content:
            title = extract_text(r.xpath('.//*[@role="heading"]'))
            url = extract_text(r.xpath('.//a/@href'))
            if url and url.startswith('/url?q='): url = unquote(url[7:].split('&sa=U')[0])
            template = None
            if title and url and (url, template) not in seen_results:
                img_node = eval_xpath_getindex(r, './/img', 0, default=None)
                img_id = img_node.get("id") if img_node is not None else None
                thumbnail = data_image_map.get(img_id)
                if not thumbnail and img_id:
                    for k, val in data_image_map.items():
                        if k.endswith(img_id): thumbnail = val; break
                results.append({'url': url, 'title': title, 'content': content, 'thumbnail': thumbnail})
                seen_results.add((url, template))
                break

    # 3. Merriam-Webster
    for mw in dom.xpath('//div[contains(@class, "b8PhZd")]'):
        headings = mw.xpath('.//*[@role="heading"]')
        if headings:
            title = extract_text(headings[0])
            url = extract_text(mw.xpath('.//a/@href'))
            if url and url.startswith('/url?q='): url = unquote(url[7:].split('&sa=U')[0])
            template = None
            if title and url and (url, template) not in seen_results:
                content = extract_text(mw.xpath('.//div[contains(@class, "VwiC3b") or contains(@class, "yXK7lf")]'))
                results.append({'url': url, 'title': title, 'content': content})
                seen_results.add((url, template))

    # 4. Standard Web Results (IMAGES WIDGET REMOVED)
    for sw in dom.xpath('//div[contains(@class, "N54PNb")] | //div[contains(@class, "kb0PBd")]'):
        if sw.xpath('./ancestor::div[contains(@class, "WVV5ke") or contains(@class, "yD2vYc") or contains(@class, "b8PhZd") or @data-attrid="images universal" or contains(@class, "xT1K2d")]'):
            continue
            
        headings = sw.xpath('.//*[@role="heading"]')
        if not headings: continue
        title = extract_text(headings[0])
        if title in ["AI Overview", "People also ask", "Places", "Videos", "Images", "People also search for", "Web results"]:
            continue
            
        links = sw.xpath('./ancestor::a/@href') or sw.xpath('.//a/@href')
        if not links: continue
        url = links[0]
        if url.startswith('/url?q='): url = unquote(url[7:].split('&sa=U')[0])
        if 'google.com/' in url and '/search' in url: continue
        
        template = None
        if (url, template) in seen_results: continue

        content = script_descriptions.get(title, "")
        if not content:
            desc_node = sw.xpath('.//div[contains(@class, "VwiC3b") or contains(@class, "yXK7lf")]')
            content = extract_text(desc_node[0]) if desc_node else ""
        
        img_node = eval_xpath_getindex(sw, './/img', 0, default=None)
        img_id = img_node.get("id") if img_node is not None else None
        thumbnail = data_image_map.get(img_id)
        if not thumbnail and img_id:
            for k, val in data_image_map.items():
                if k.endswith(img_id): thumbnail = val; break
        results.append({'url': url, 'title': title, 'content': content, 'thumbnail': thumbnail})
        seen_results.add((url, template))

    return results


def response(resp: "SXNG_Response"):
    """Get response from google's search request"""
    detect_google_sorry(resp)
    data_image_map = parse_data_images(resp.text)
    script_descriptions = extract_descriptions(resp.text)
    dom = html.fromstring(resp.text)

    results = EngineResults()
    for s in dom.xpath('//a[@data-l1]'):
        l1, l2 = s.get("data-l1"), s.get("data-l2")
        text = f"{l1} {l2}" if l2 else l1
        if text and not any(r.get('suggestion') == text for r in results):
            results.append({'suggestion': text})

    results.extend(parse_layout_1(dom, resp.text, data_image_map, script_descriptions))
    return results


def fetch_traits(engine_traits: EngineTraits, add_domains: bool = True):
    """Fetch languages from Google."""
    # pylint: disable=import-outside-toplevel, too-many-branches

    from searx.network import get  # see https://github.com/searxng/searxng/issues/762

    engine_traits.custom["supported_domains"] = {}

    resp = get("https://www.google.com/preferences", timeout=5)
    if not resp.ok:
        raise RuntimeError("Response from Google preferences is not OK.")

    dom = html.fromstring(resp.text.replace('<?xml version="1.0" encoding="UTF-8"?>', ""))

    # supported language codes

    lang_map = {"no": "nb"}
    for x in eval_xpath_list(dom, "//select[@name='hl']/option"):
        eng_lang = x.get("value")
        try:
            locale = babel.Locale.parse(lang_map.get(eng_lang, eng_lang), sep="-")
        except babel.UnknownLocaleError:
            print("INFO:  google UI language %s (%s) is unknown by babel" % (eng_lang, x.text.split("(")[0].strip()))
            continue
        sxng_lang = language_tag(locale)

        conflict = engine_traits.languages.get(sxng_lang)
        if conflict:
            if conflict != eng_lang:
                print("CONFLICT: babel %s --> %s, %s" % (sxng_lang, conflict, eng_lang))
            continue
        engine_traits.languages[sxng_lang] = "lang_" + eng_lang

    # alias languages
    engine_traits.languages["zh"] = "lang_zh-CN"

    # supported region codes

    for x in eval_xpath_list(dom, "//select[@name='gl']/option"):
        eng_country = x.get("value")

        if eng_country in skip_countries:
            continue
        if eng_country == "ZZ":
            engine_traits.all_locale = "ZZ"
            continue

        sxng_locales = get_official_locales(eng_country, engine_traits.languages.keys(), regional=True)

        if not sxng_locales:
            print("ERROR: can't map from google country %s (%s) to a babel region." % (x.get("data-name"), eng_country))
            continue

        for sxng_locale in sxng_locales:
            engine_traits.regions[region_tag(sxng_locale)] = eng_country

    # alias regions
    engine_traits.regions["zh-CN"] = "HK"

    # supported domains

    if add_domains:
        resp = get("https://www.google.com/supported_domains", timeout=5)
        if not resp.ok:
            raise RuntimeError("Response from Google supported domains is not OK.")

        for domain in resp.text.split():
            domain = domain.strip()
            if not domain or domain in [
                ".google.com",
            ]:
                continue
            region = domain.split(".")[-1].upper()
            engine_traits.custom["supported_domains"][region] = "www" + domain
            if region == "HK":
                # There is no google.cn, we use .com.hk for zh-CN
                engine_traits.custom["supported_domains"]["CN"] = "www" + domain


skip_countries = [
    # official language of google-country not in google-languages
    "AL",  # Albanien (sq)
    "AZ",  # Aserbaidschan  (az)
    "BD",  # Bangladesch (bn)
    "BN",  # Brunei Darussalam (ms)
    "BT",  # Bhutan (dz)
    "ET",  # Äthiopien (am)
    "GE",  # Georgien (ka, os)
    "GL",  # Grönland (kl)
    "KH",  # Kambodscha (km)
    "LA",  # Laos (lo)
    "LK",  # Sri Lanka (si, ta)
    "ME",  # Montenegro (sr)
    "MK",  # Nordmazedonien (mk, sq)
    "MM",  # Myanmar (my)
    "MN",  # Mongolei (mn)
    "MV",  # Malediven (dv) // dv_MV is unknown by babel
    "MY",  # Malaysia (ms)
    "NP",  # Nepal (ne)
    "TJ",  # Tadschikistan (tg)
    "TM",  # Turkmenistan (tk)
    "UZ",  # Usbekistan (uz)
]
