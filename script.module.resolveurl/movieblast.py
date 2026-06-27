#!/usr/bin/env python3
"""
MovieBlast Resolver - Standalone Version
Supports both movies and TV shows.
Returns JSON with stream URL and headers.
Based on MovieBlast provider (index.js, utils.js, constants.js)
Requires: pycryptodome (pip install pycryptodome), requests
"""

import re
import json
import time
import base64
import hmac
import hashlib
import urllib.parse
import requests

try:
    from Crypto.Hash import HMAC, SHA256
except ImportError:
    raise ImportError("Please install pycryptodome: pip install pycryptodome")

__version__ = "1.0.0"

# Constants from constants.js
BASE_URL = "https://app.cloud-mb.xyz"
TOKEN = "jdvhhjv255vghhghdhvfch2565656jhdcghfdf"
APP_ID = "com.movieblast"
SIGN_SECRET = "GJ8reydarI7Jqat9rvbAJKNQ9gY4DoEQF2H5nfuI1gi"
TMDB_API_KEY = "439c478a771f35c05022f9feabcca01c"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

HEADERS = {
    "user-agent": "okhttp/5.0.0-alpha.6",
    "x-request-x": APP_ID
}

SEARCH_HEADERS = {
    **HEADERS,
    "hash256": "86dc03244adddb3cbedbf0ae36074a736ee293a64774b18e82a6244eafd0df30",
    "packagename": APP_ID
}


class MovieBlastResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _fetch_url(self, url, headers=None, timeout=20):
        """Make HTTP GET request."""
        if headers is None:
            headers = HEADERS.copy()
        try:
            resp = self.session.get(url, headers=headers, timeout=timeout)
            if resp.status_code >= 400:
                return False, None, f"HTTP Error {resp.status_code}: {resp.text[:100]}"
            return True, resp.json(), None
        except Exception as e:
            return False, None, str(e)

    def _generate_signed_url(self, url_str):
        """Generate signed URL with HMAC-SHA256 signature."""
        try:
            parsed = urllib.parse.urlparse(url_str)
            path = parsed.path
            timestamp = str(int(time.time()))
            # HMAC-SHA256
            message = path + timestamp
            signature = hmac.new(
                SIGN_SECRET.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            encoded_sig = base64.b64encode(signature).decode('utf-8')
            # URL-encode the signature
            encoded_sig = urllib.parse.quote(encoded_sig)
            return f"{url_str}?verify={timestamp}-{encoded_sig}"
        except Exception as e:
            self.log(f"Error generating signed URL: {e}", "ERROR")
            return url_str

    def _match_quality(self, server_str):
        """Map server string to quality label."""
        if not server_str:
            return "Unknown"
        v = server_str.lower()
        if "2160" in v or "4k" in v:
            return "4K"
        if "1440" in v:
            return "2K"
        if "1080" in v:
            return "1080p"
        if "720" in v:
            return "720p"
        if "480" in v:
            return "480p"
        if "360" in v:
            return "360p"
        return "Unknown"

    def _normalize_title(self, title):
        """Normalize title for matching."""
        if not title:
            return ""
        title = title.lower()
        # Remove common words
        title = re.sub(r'\b(the|a|an)\b', '', title)
        # Replace separators
        title = re.sub(r'[:_\-]', ' ', title)
        # Remove non-word chars
        title = re.sub(r'[^\w\s]', '', title)
        # Collapse spaces
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    def _calculate_similarity(self, title1, title2):
        """Jaccard similarity of normalized titles."""
        norm1 = self._normalize_title(title1)
        norm2 = self._normalize_title(title2)
        if norm1 == norm2:
            return 1.0
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0

    def _find_best_match(self, media_info, search_results):
        """Find best match from search results."""
        if not search_results:
            return None
        best_score = 0.0
        best_match = None
        for result in search_results:
            score = self._calculate_similarity(media_info['title'], result.get('name', ''))
            # Year bonus
            if media_info.get('year') and result.get('release_date'):
                result_year = result['release_date'].split('-')[0]
                if result_year.isdigit() and int(result_year) == media_info['year']:
                    score += 0.2
            if score > best_score and score > 0.4:
                best_score = score
                best_match = result
        return best_match

    def _get_tmdb_details(self, tmdb_id, media_type):
        """Fetch TMDB title and year."""
        endpoint = "tv" if media_type == "tv" else "movie"
        url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}"
        try:
            resp = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            if resp.status_code != 200:
                self.log(f"TMDB API error: {resp.status_code}", "ERROR")
                return None
            data = resp.json()
            title = data.get('name') if media_type == 'tv' else data.get('title')
            release_date = data.get('first_air_date') if media_type == 'tv' else data.get('release_date')
            year = int(release_date.split('-')[0]) if release_date else None
            return {'title': title, 'year': year}
        except Exception as e:
            self.log(f"TMDB fetch error: {e}", "ERROR")
            return None

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        """Main resolve method."""
        self.log("=" * 80)
        self.log(f"MovieBlast Resolver Started - {media_type} ID: {url_or_id}")

        # Extract TMDB ID from URL if needed
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
                return json.dumps({
                    'status': 'error',
                    'message': 'Could not extract TMDB ID from URL'
                })
        else:
            tmdb_id = url_or_id

        self.log(f"TMDB ID: {tmdb_id}")
        self.log(f"Content Type: {'TV Show' if media_type == 'tv' else 'Movie'}")
        if media_type == 'tv':
            self.log(f"Season: {season}, Episode: {episode}")

        try:
            # 1. Get TMDB details
            media_info = self._get_tmdb_details(tmdb_id, media_type)
            if not media_info:
                raise Exception("Failed to get TMDB details")
            self.log(f"TMDB Info: {media_info['title']} ({media_info.get('year', 'N/A')})")

            # 2. Search
            safe_query = urllib.parse.quote(media_info['title'])
            search_url = f"{BASE_URL}/api/search/{safe_query}/{TOKEN}"
            self.log(f"Search URL: {search_url}")
            success, search_data, err = self._fetch_url(search_url, headers=SEARCH_HEADERS)
            if not success:
                raise Exception(f"Search failed: {err}")

            search_results = search_data.get('search', [])
            self.log(f"Search results: {len(search_results)}")
            if self.debug:
                for r in search_results:
                    self.log(f"  {r.get('name')} ({r.get('release_date', '')})", "DEBUG")

            # 3. Find best match
            match = self._find_best_match(media_info, search_results)
            if not match:
                raise Exception("No confident match found")
            internal_id = match.get('id')
            is_series = 'serie' in match.get('type', '').lower() or media_type == 'tv'
            self.log(f"Match: {match.get('name')} (ID: {internal_id}, Series: {is_series})")

            # 4. Get details
            detail_path = "series/show" if is_series else "media/detail"
            detail_url = f"{BASE_URL}/api/{detail_path}/{internal_id}/{TOKEN}"
            self.log(f"Detail URL: {detail_url}")
            success, detail_data, err = self._fetch_url(detail_url)
            if not success:
                raise Exception(f"Detail fetch failed: {err}")

            target_videos = []
            if is_series:
                seasons = detail_data.get('seasons', [])
                if season is None or episode is None:
                    raise Exception("Season and episode required for TV shows")
                target_season = None
                for s in seasons:
                    if s.get('season_number') == season:
                        target_season = s
                        break
                if not target_season:
                    raise Exception(f"Season {season} not found")
                episodes = target_season.get('episodes', [])
                target_episode = None
                for ep in episodes:
                    if ep.get('episode_number') == episode:
                        target_episode = ep
                        break
                if not target_episode:
                    raise Exception(f"Episode {episode} not found")
                target_videos = target_episode.get('videos', [])
            else:
                target_videos = detail_data.get('videos', [])

            if not target_videos:
                raise Exception("No video links found")

            # 5. Generate signed URLs and build streams
            playable_urls = []
            for vid in target_videos:
                raw_url = vid.get('link')
                if not raw_url:
                    continue
                if not raw_url.startswith('http'):
                    raw_url = 'https://' + raw_url
                signed_url = self._generate_signed_url(raw_url)
                quality = self._match_quality(vid.get('server', ''))
                headers = {
                    "Accept-Encoding": "identity",
                    "Connection": "Keep-Alive",
                    "Icy-MetaData": "1",
                    "Referer": "MovieBlast",
                    "User-Agent": "MovieBlast",
                    "x-request-x": APP_ID
                }
                # Determine type from URL
                if '.m3u8' in signed_url.lower():
                    stream_type = 'hls'
                elif '.mpd' in signed_url.lower():
                    stream_type = 'dash'
                elif '.mp4' in signed_url.lower() or '.mkv' in signed_url.lower():
                    stream_type = 'mp4'
                else:
                    stream_type = 'hls'

                playable_urls.append({
                    'url': signed_url,
                    'quality': quality,
                    'type': stream_type,
                    'headers': headers,
                    'server': vid.get('server', 'MovieBlast'),
                    'lang': vid.get('lang', 'EN'),
                })

            if not playable_urls:
                return json.dumps({
                    'status': 'error',
                    'message': 'No playable sources found'
                })

            response = {
                'status': 'success',
                'tmdb_id': tmdb_id,
                'playable_urls': playable_urls
            }

            self.log("=" * 80)
            self.log("RESOLUTION COMPLETE")
            self.log(f"Found {len(playable_urls)} playable sources")
            return json.dumps(response, indent=2)

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return json.dumps({
                'status': 'error',
                'message': str(e)
            })


def main():
    import argparse

    parser = argparse.ArgumentParser(description='MovieBlast Resolver')
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = MovieBlastResolver(debug=args.debug)
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
        except:
            print(result_json)
    else:
        print(result_json)


if __name__ == "__main__":
    main()