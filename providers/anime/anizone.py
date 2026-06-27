#!/usr/bin/env python3
"""
AniZone Resolver - Standalone Version
Returns JSON with stream URL and headers
"""

import re
import json
import time
import urllib.request
import urllib.error
import ssl
from urllib.parse import urlencode, urljoin
from bs4 import BeautifulSoup

BASE_URL = "https://anizone.to"

TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://anizone.to/',
}


class AniZoneResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _fetch_url(self, url, headers=None, timeout=15, method='GET', data=None):
        if headers is None:
            headers = HEADERS.copy()
        if data:
            data = urlencode(data).encode('utf-8')
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=timeout) as resp:
                content = resp.read().decode('utf-8', errors='replace')
            return True, content, None
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8', errors='replace')[:500] if e.code != 304 else ''
            return False, None, f"HTTP {e.code}: {e.reason} {error_body}"
        except urllib.error.URLError as e:
            return False, None, f"URL Error: {e.reason}"
        except Exception as e:
            return False, None, str(e)

    def _fetch_text(self, path, headers=None):
        url = path if path.startswith('http') else urljoin(BASE_URL, path)
        success, content, error = self._fetch_url(url, headers=headers)
        if not success:
            self.log(f"Fetch failed: {error}", "ERROR")
            return None
        return content

    def _get_tmdb_title(self, tmdb_id, media_type):
        url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}?api_key={TMDB_API_KEY}"
        success, content, error = self._fetch_url(url)
        if not success:
            return None
        try:
            data = json.loads(content)
            return data.get('title') or data.get('original_title') or data.get('name')
        except Exception:
            return None

    def _get_imdb_id(self, tmdb_id, media_type):
        url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
        success, content, error = self._fetch_url(url)
        if not success:
            return None
        try:
            data = json.loads(content)
            return data.get('imdb_id')
        except Exception:
            return None

    def _resolve_mapping(self, imdb_id, season, episode):
        url = f"https://id-mapping-api-malid.hf.space/api/resolve?id={imdb_id}&s={season}&e={episode}"
        success, content, error = self._fetch_url(url)
        if not success:
            return None
        try:
            data = json.loads(content)
            return data
        except Exception:
            return None

    def _get_mal_title(self, mal_id):
        url = f"https://api.jikan.moe/v4/anime/{mal_id}"
        time.sleep(0.5)
        success, content, error = self._fetch_url(url)
        if not success:
            return None
        try:
            data = json.loads(content)
            return data.get('data', {}).get('title')
        except Exception:
            return None

    def _normalize(self, s):
        return re.sub(r'[^a-z0-9]', '', s.lower()).strip()

    def _extract_card_info(self, soup, el):
        a = el.find('a', href=re.compile(r'/anime/'))
        if not a:
            return None
        href = a.get('href', '')
        parts = href.rstrip('/').split('/')
        slug = parts[-1] if parts[-1] else parts[-2]

        x_data = el.get('x-data', '')
        titles = set()

        m = re.search(r"window\.getTitle\(this\.anmTitles,\s*'([^']+)'\)", x_data)
        if m:
            titles.add(m.group(1))

        m = re.search(r"JSON\.parse\('([^']+)'\)", x_data)
        if m:
            try:
                json_str = m.group(1)
                json_str = json_str.replace('\\\\', '\\')
                json_str = re.sub(r'\\u([0-9a-fA-F]{4})', lambda x: chr(int(x.group(1), 16)), json_str)
                json_str = json_str.replace("\\'", "'")
                parsed = json.loads(json_str)
                for v in parsed.values():
                    if v:
                        titles.add(v)
            except Exception:
                pass

        return {'slug': slug, 'titles': list(titles)}

    def _get_season_regexes(self, season):
        if season == 1:
            return {
                'must_not': [
                    re.compile(r'season\s*[2-9]', re.I),
                    re.compile(r'[\s\-][iI]{2,}'),
                    re.compile(r'\s+[2-9]nd\b'),
                    re.compile(r'\s+[2-9]rd\b'),
                    re.compile(r'\s+[2-9]th\b'),
                    re.compile(r'\s+ii\b'),
                    re.compile(r'\s+iii\b'),
                    re.compile(r'\s+iv\b'),
                    re.compile(r'\s+v\b'),
                ]
            }
        patterns = []
        if season == 2:
            patterns.extend([re.compile(r'season\s*2', re.I), re.compile(r'2nd\s*season', re.I), re.compile(r'[\s\-]ii\b', re.I), re.compile(r'\b2\b')])
        elif season == 3:
            patterns.extend([re.compile(r'season\s*3', re.I), re.compile(r'3rd\s*season', re.I), re.compile(r'[\s\-]iii\b', re.I), re.compile(r'\b3\b')])
        elif season == 4:
            patterns.extend([re.compile(r'season\s*4', re.I), re.compile(r'4th\s*season', re.I), re.compile(r'[\s\-]iv\b', re.I), re.compile(r'\b4\b')])
        else:
            patterns.extend([re.compile(f'season\\s*{season}', re.I), re.compile(f'\\b{season}\\b')])
        return {'must': patterns}

    def _match_card(self, cards, jikan_title, base_title, season):
        norm_jikan = self._normalize(jikan_title)
        norm_jikan_no_sub = self._normalize(jikan_title.split(':')[0])
        norm_base = self._normalize(base_title)

        for card in cards:
            for title in card['titles']:
                norm_t = self._normalize(title)
                norm_t_no_sub = self._normalize(title.split(':')[0])
                if norm_t == norm_jikan or norm_t_no_sub == norm_jikan_no_sub:
                    return card['slug']

        season_rules = self._get_season_regexes(season)
        for card in cards:
            matches_base = any(norm_base in self._normalize(t) for t in card['titles'])
            if not matches_base:
                continue
            if season == 1:
                has_other = any(r.test(t) for t in card['titles'] for r in season_rules['must_not'])
                if not has_other:
                    return card['slug']
            else:
                if any(r.test(t) for t in card['titles'] for r in season_rules['must']):
                    return card['slug']

        return None

    def _match_movie_card(self, cards, target_title):
        norm_target = self._normalize(target_title)
        for card in cards:
            for title in card['titles']:
                if self._normalize(title) == norm_target:
                    return card['slug']
        for card in cards:
            for title in card['titles']:
                norm_t = self._normalize(title)
                if norm_target in norm_t or norm_t in norm_target:
                    return card['slug']
        return cards[0]['slug'] if cards else None

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        self.log("=" * 80)
        self.log(f"AniZone Resolver Started - {media_type} ID: {url_or_id}")

        if url_or_id.startswith('http'):
            match = re.search(r'/(?:movie|tv)/(\d+)', url_or_id)
            if match:
                tmdb_id = match.group(1)
                if '/tv/' in url_or_id:
                    media_type = 'tv'
                    se_match = re.search(r'/tv/\d+/(\d+)/(\d+)', url_or_id)
                    if se_match:
                        season = int(se_match.group(1))
                        episode = int(se_match.group(2))
            else:
                return json.dumps({'status': 'error', 'message': 'Could not extract TMDB ID from URL'})
        else:
            tmdb_id = url_or_id

        self.log(f"TMDB ID: {tmdb_id}")
        self.log(f"Content Type: {'TV Show' if media_type == 'tv' else 'Movie'}")
        if media_type == 'tv':
            self.log(f"Season: {season}, Episode: {episode}")

        try:
            anime_title = None
            mapped_ep = episode if media_type == 'tv' else 1
            mapping = None

            if media_type == 'tv':
                if season is None or episode is None:
                    return json.dumps({'status': 'error', 'message': 'Season and episode are required for TV shows.'})
                imdb_id = self._get_imdb_id(tmdb_id, media_type)
                if not imdb_id:
                    return json.dumps({'status': 'error', 'message': 'Could not get IMDb ID from TMDB'})
                self.log(f"IMDb ID: {imdb_id}")
                mapping = self._resolve_mapping(imdb_id, season, episode)
                if not mapping or not mapping.get('mal_id'):
                    return json.dumps({'status': 'error', 'message': 'Could not resolve MAL mapping'})
                mapped_ep = mapping.get('mal_episode', episode)
                anime_title = self._get_mal_title(mapping['mal_id'])
            else:
                anime_title = self._get_tmdb_title(tmdb_id, 'movie')
                mapped_ep = 1

            if not anime_title:
                return json.dumps({'status': 'error', 'message': 'Could not determine anime title'})

            self.log(f"Anime Title: {anime_title}")

            search_query = anime_title
            if media_type == 'tv' and mapping:
                search_query = mapping.get('anime_title', anime_title.split(':')[0].strip())
            else:
                search_query = anime_title.split(':')[0].strip()

            html = self._fetch_text(f"/anime?search={urlencode({'': search_query})[1:]}")
            if not html:
                return json.dumps({'status': 'error', 'message': 'Search request failed'})

            soup = BeautifulSoup(html, 'html.parser')
            cards = []
            for el in soup.select('[x-data*="anmTitles"]'):
                info = self._extract_card_info(soup, el)
                if info:
                    cards.append(info)

            if not cards:
                for el in soup.select('[x-data*="anmTitles"]'):
                    info = self._extract_card_info(soup, el)
                    if info:
                        cards.append(info)

            anime_slug = None
            if cards:
                if media_type == 'tv':
                    base = (mapping and mapping.get('anime_title')) or anime_title
                    anime_slug = self._match_card(cards, anime_title, base, season)
                else:
                    anime_slug = self._match_movie_card(cards, anime_title)

            if not anime_slug:
                for a in soup.select('main a'):
                    href = a.get('href', '')
                    if href and ('https://anizone.to/anime/' in href or href.startswith('/anime/')):
                        parts = href.rstrip('/').split('/')
                        anime_slug = parts[-1] if parts[-1] else parts[-2]
                        if anime_slug:
                            break

            if not anime_slug:
                return json.dumps({'status': 'error', 'message': 'Could not find anime on AniZone'})

            self.log(f"Anime Slug: {anime_slug}")

            ep_html = self._fetch_text(f"/anime/{anime_slug}/{mapped_ep}")
            if not ep_html:
                return json.dumps({'status': 'error', 'message': 'Episode page request failed'})

            ep_soup = BeautifulSoup(ep_html, 'html.parser')

            master_url = None
            mp = ep_soup.find('media-player')
            if mp:
                master_url = mp.get('src')

            if not master_url:
                m = re.search(r'https://[^"\']+/master\.m3u8', ep_html)
                if m:
                    master_url = m.group(0)

            if not master_url:
                return json.dumps({'status': 'error', 'message': 'No stream URL found'})

            subtitles = []
            for track in ep_soup.select('track'):
                src = track.get('src')
                kind = track.get('kind', '')
                if src and (kind in ('subtitles', 'captions') or src.endswith('.ass') or src.endswith('.vtt')):
                    subtitles.append({
                        'url': src,
                        'name': track.get('label', 'English'),
                        'language': track.get('srclang', 'en'),
                    })

            format_type = "Sub"
            for btn in ep_soup.select('button'):
                text = btn.get_text()
                if 'Audio:' in text:
                    has_jp = 'Japanese' in text
                    has_en = 'English' in text
                    if has_en and not has_jp:
                        format_type = "Dub"
                    elif has_en and has_jp:
                        format_type = "Sub & Dub"

            if format_type == "Sub":
                for btn in ep_soup.select('button[wire\\:click^="setVideo"]'):
                    text = btn.get_text()
                    has_jp = 'Japanese' in text
                    has_en = 'English' in text
                    if has_en and not has_jp:
                        format_type = "Dub"
                    elif has_en and has_jp:
                        format_type = "Sub & Dub"

            playable_urls = [{
                'url': master_url,
                'quality': 'Multi',
                'type': 'hls',
                'headers': HEADERS.copy(),
                'server': 'AniZone',
                'format': format_type,
                'subtitles': subtitles,
            }]

            response = {
                'status': 'success',
                'tmdb_id': tmdb_id,
                'playable_urls': playable_urls,
            }

            self.log("=" * 80)
            self.log("RESOLUTION COMPLETE")
            self.log(f"Found {len(playable_urls)} playable sources")
            return json.dumps(response, indent=2)

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return json.dumps({'status': 'error', 'message': str(e)})


def main():
    import argparse

    parser = argparse.ArgumentParser(description='AniZone Resolver')
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = AniZoneResolver(debug=args.debug)
    result_json = resolver.resolve(
        args.url_or_id,
        media_type=args.type,
        season=args.season,
        episode=args.episode
    )

    if args.pretty:
        try:
            data = json.loads(result_json)
            print(json.dumps(data, indent=2))
        except Exception:
            print(result_json)
    else:
        print(result_json)


if __name__ == "__main__":
    main()
