#!/usr/bin/env python3
"""
HiAnime Resolver - Standalone Version
Returns JSON with stream URL and headers
"""

import re
import json
import time
import urllib.request
import urllib.error
import ssl
from urllib.parse import urlencode
from bs4 import BeautifulSoup

MEGAPLAY_BASE = 'https://megaplay.buzz'
VIDWISH_BASE = 'https://vidwish.live'
MEGACLOUD_BASE = 'https://megacloud.bloggy.click'

TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Connection': 'keep-alive',
}


class HiAnimeResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _fetch_url(self, url, headers=None, timeout=15, method='GET', data=None):
        merged = HEADERS.copy()
        if headers:
            merged.update(headers)
        headers = merged
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

    def _fetch_text(self, url, headers=None):
        success, content, error = self._fetch_url(url, headers=headers)
        if not success:
            return None
        return content

    def _fetch_json(self, url, headers=None):
        success, content, error = self._fetch_url(url, headers=headers)
        if not success:
            return None
        try:
            return json.loads(content)
        except Exception:
            return None

    def _get_imdb_id(self, tmdb_id, media_type):
        url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
        data = self._fetch_json(url)
        if data:
            return data.get('imdb_id')
        return None

    def _get_tmdb_show_title(self, tmdb_id, media_type):
        url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}?api_key={TMDB_API_KEY}"
        data = self._fetch_json(url)
        if data:
            return data.get('name') or data.get('title') or data.get('original_title')
        return None

    def _resolve_mapping(self, imdb_id, season, episode):
        url = f"https://id-mapping-api-malid.hf.space/api/resolve?id={imdb_id}&s={season}&e={episode}"
        data = self._fetch_json(url)
        if data and not data.get('error'):
            return data
        return None

    def _search_mal_id(self, title, media_type):
        search_type = 'movie' if media_type == 'movie' else 'tv'
        url = f"https://api.jikan.moe/v4/anime?q={urlencode({'': title})[1:]}&type={search_type}&limit=1"
        time.sleep(0.5)
        data = self._fetch_json(url)
        if data and data.get('data') and len(data['data']) > 0:
            return data['data'][0].get('mal_id')
        return None

    def _extract_sources(self, api_url, referer, origin, server_name, anime_title, episode_num, stream_type):
        headers = {
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': referer,
            'Origin': origin,
            'User-Agent': HEADERS['User-Agent'],
        }
        data = self._fetch_json(api_url, headers=headers)
        if not data:
            return []

        file = None
        if isinstance(data.get('sources'), dict):
            file = data['sources'].get('file')
        elif isinstance(data.get('sources'), list):
            file = data['sources'][0].get('file') if data['sources'] else None

        if not file:
            return []

        stream = {
            'url': file,
            'quality': 'Auto',
            'type': 'hls',
            'headers': {
                'User-Agent': HEADERS['User-Agent'],
                'Referer': f'{origin}/',
                'Origin': origin,
            },
            'server': f'HiAnime [{server_name}] ({stream_type.upper()})',
        }

        tracks = data.get('tracks', [])
        if tracks:
            subtitles = []
            for t in tracks:
                if t.get('file') and t.get('kind') == 'captions':
                    subtitles.append({
                        'url': t['file'],
                        'name': t.get('label', 'English'),
                        'language': t.get('label', 'en')[:3].lower() if t.get('label') else 'en',
                    })
            if subtitles:
                stream['subtitles'] = subtitles

        return [stream]

    def _scrape_type(self, mal_id, episode, stream_type, anime_title):
        streams = []
        mega_url = f"{MEGAPLAY_BASE}/stream/mal/{mal_id}/{episode}/{stream_type}"

        html = self._fetch_text(mega_url, headers={'Referer': mega_url})
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        player = soup.select_one('div.fix-area#megaplay-player')
        if not player:
            return []

        data_id = player.get('data-id')
        real_id = player.get('data-realid')

        extractions = []

        if data_id:
            api_url = f"{MEGAPLAY_BASE}/stream/getSources?id={data_id}&id={data_id}"
            extractions.append(
                self._extract_sources(api_url, mega_url, MEGAPLAY_BASE, 'MegaPlay', anime_title, episode, stream_type)
            )

        if real_id:
            vid_page = f"{VIDWISH_BASE}/stream/s-2/{real_id}/{stream_type}"
            try:
                vid_html = self._fetch_text(vid_page, headers={'Referer': mega_url})
                if vid_html:
                    v_soup = BeautifulSoup(vid_html, 'html.parser')
                    v_player = v_soup.select_one('div.fix-area#megaplay-player')
                    if v_player:
                        v_data_id = v_player.get('data-id')
                        if v_data_id:
                            api_url = f"{VIDWISH_BASE}/stream/getSources?id={v_data_id}&id={v_data_id}"
                            extractions.append(
                                self._extract_sources(api_url, vid_page, VIDWISH_BASE, 'Vidwish', anime_title, episode, stream_type)
                            )
            except Exception:
                pass

        if real_id:
            mc_page = f"{MEGACLOUD_BASE}/stream/s-3/{real_id}/{stream_type}"
            try:
                mc_html = self._fetch_text(mc_page, headers={'Referer': mega_url})
                if mc_html:
                    m_soup = BeautifulSoup(mc_html, 'html.parser')
                    m_player = m_soup.select_one('div.fix-area#megaplay-player')
                    if m_player:
                        m_data_id = m_player.get('data-id')
                        if m_data_id:
                            api_url = f"{MEGACLOUD_BASE}/stream/getSources?id={m_data_id}&id={m_data_id}"
                            extractions.append(
                                self._extract_sources(api_url, mc_page, MEGACLOUD_BASE, 'MegaCloud', anime_title, episode, stream_type)
                            )
            except Exception:
                pass

        for result in extractions:
            streams.extend(result)

        return streams

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        self.log("=" * 80)
        self.log(f"HiAnime Resolver Started - {media_type} ID: {url_or_id}")

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
            show_title = self._get_tmdb_show_title(tmdb_id, media_type) or ('' if media_type == 'movie' else 'Anime')
            if not show_title:
                return json.dumps({'status': 'error', 'message': 'Could not get show title from TMDB'})

            self.log(f"Show Title: {show_title}")

            imdb_id = self._get_imdb_id(tmdb_id, media_type)
            if not imdb_id:
                return json.dumps({'status': 'error', 'message': 'Could not get IMDb ID from TMDB'})

            self.log(f"IMDb ID: {imdb_id}")

            s = 1 if media_type == 'movie' else season
            e = 1 if media_type == 'movie' else episode

            mal_id = None
            mapped_ep = e

            if media_type == 'movie':
                mal_id = self._search_mal_id(show_title, 'movie')
                mapped_ep = 1

            if not mal_id and media_type != 'movie':
                if s is None or e is None:
                    return json.dumps({'status': 'error', 'message': 'Season and episode are required for TV shows.'})
                mapping = self._resolve_mapping(imdb_id, s, e)
                if mapping and mapping.get('mal_id'):
                    mal_id = mapping['mal_id']
                    mapped_ep = mapping.get('mal_episode', e)

            if not mal_id:
                return json.dumps({'status': 'error', 'message': 'Could not resolve MAL ID'})

            self.log(f"MAL ID: {mal_id}, Mapped Episode: {mapped_ep}")

            all_streams = []
            for stype in ('sub', 'dub'):
                self.log(f"Scraping {stype}...")
                try:
                    result = self._scrape_type(mal_id, mapped_ep, stype, show_title)
                    all_streams.extend(result)
                    self.log(f"  -> Found {len(result)} {stype} stream(s)")
                except Exception as e:
                    self.log(f"  -> {stype} failed: {e}", "WARNING")

            seen = set()
            unique_streams = []
            for s in all_streams:
                if s['url'] not in seen:
                    seen.add(s['url'])
                    unique_streams.append(s)

            if not unique_streams:
                return json.dumps({'status': 'error', 'message': 'No playable streams found'})

            response = {
                'status': 'success',
                'tmdb_id': tmdb_id,
                'playable_urls': unique_streams,
            }

            self.log("=" * 80)
            self.log("RESOLUTION COMPLETE")
            self.log(f"Found {len(unique_streams)} playable sources")
            return json.dumps(response, indent=2)

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return json.dumps({'status': 'error', 'message': str(e)})


def main():
    import argparse

    parser = argparse.ArgumentParser(description='HiAnime Resolver')
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = HiAnimeResolver(debug=args.debug)
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
