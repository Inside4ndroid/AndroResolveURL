#!/usr/bin/env python3
"""
Supreme Provider â€“ Fetches debrid-resolved torrent streams from sup-nyp1.onrender.com.
Requires debrid API keys passed via command line.
"""

import json
import sys
import base64
import urllib.request
import urllib.error
import ssl

sys.stdout.reconfigure(encoding='utf-8')

SOURCE = "supreme"
BASE_URL = "https://sup-nyp1.onrender.com"

TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"


def fetch_url(url, headers=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req_headers = {'User-Agent': 'Mozilla/5.0'}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    return resp.read().decode('utf-8', errors='replace')


def fetch_json(url):
    return json.loads(fetch_url(url))


def get_imdb_id(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
    data = fetch_json(url)
    return data.get('imdb_id')


def parse_quality(resolution):
    r = str(resolution).lower()
    if '2160' in r or r == '4k':
        return '2160p'
    if '1080' in r:
        return '1080p'
    if '720' in r:
        return '720p'
    if '480' in r:
        return '480p'
    return 'Unknown'


def get_data(tmdb_id=None, media_type='movie', season=None, episode=None,
             alldebrid=None, premiumize=None, torbox=None, realdebrid=None):
    if not tmdb_id:
        return {'source': SOURCE, 'error': 'tmdb_id required'}

    debrids = []
    if alldebrid:
        debrids.append({'id': 'alldebrid', 'key': alldebrid})
    if premiumize:
        debrids.append({'id': 'premiumize', 'key': premiumize})
    if torbox:
        debrids.append({'id': 'torbox', 'key': torbox})
    if realdebrid:
        debrids.append({'id': 'realdebrid', 'key': realdebrid})

    if not debrids:
        return {'source': SOURCE, 'error': 'At least one debrid API key required (--alldebrid, --premiumize, --torbox, --realdebrid)'}

    config = {
        'providers': [
            'yts', 'eztv', 'tpb', 'tgx', '1337x', 'nyaa', 'solidtorrents',
            'rutor', 'kickass', 'magnetdl', 'torrentio', 'knaben', 'therarbg',
            'limetorrents', 'bitsearch', 'bt4g', 'torlock', 'torrentdownloads',
            'idope', 'zooqle', 'torrentz2', 'torrentfunk', 'btdig',
            'torrentsdb', 'rutracker', 'animetosho', 'subsplease', 'torrentscsv',
        ],
        'maxQuality': '4k',
        'sizeFilter': True,
        'maxSizeBytes': 0,
        'minSizeBytes': 536870912,
        'minSeeders': 0,
        'sortOrder': 'quality',
        'prioritize': 'size_asc',
        'dedupe': True,
        'excludeCam': True,
        'audioLanguage': 'all',
        'maxResults': 50,
        'codecs': [],
        'debrids': debrids,
    }

    config_b64 = base64.urlsafe_b64encode(json.dumps(config).encode()).decode()

    imdb_id = get_imdb_id(tmdb_id, media_type)
    if not imdb_id:
        return {'source': SOURCE, 'error': f'Could not resolve IMDB ID for tmdbId={tmdb_id}'}

    if media_type == 'tv' and season is not None and episode is not None:
        path = f"stream/series/{imdb_id}:{season}:{episode}.json"
    else:
        path = f"stream/movie/{imdb_id}.json"

    url = f"{BASE_URL}/{config_b64}/{path}"
    try:
        text = fetch_url(url)
    except urllib.error.HTTPError as e:
        return {'source': SOURCE, 'error': f"HTTP {e.code}"}

    data = json.loads(text)
    raw_streams = data.get('streams', [])

    torrents = []
    for s in raw_streams:
        info_hash = s.get('infoHash')
        if not info_hash:
            continue

        quality_data = s.get('quality', {})
        resolution = quality_data.get('resolution', '')
        quality = parse_quality(resolution)

        seeders = s.get('seeders', 0)
        size_bytes = s.get('sizeBytes')
        provider = s.get('providerName', s.get('providerId', ''))
        tracker = s.get('tracker', '')

        torrents.append({
            'name': f"SUPREME - {quality}",
            'quality': quality,
            'infoHash': info_hash,
            'seeders': seeders,
            'size': size_bytes,
            'magnet': f"magnet:?xt=urn:btih:{info_hash}",
            'fileIdx': s.get('fileIdx', 0),
            'provider': provider,
            'tracker': tracker,
            'sources': s.get('sources', []),
            'hdr': quality_data.get('hdr', []),
            'audio': quality_data.get('audio', []),
            'encode': quality_data.get('encode', ''),
        })

    torrents.sort(key=lambda x: (x['seeders'], x['quality']), reverse=True)
    torrents = torrents[:30]

    return {
        'source': SOURCE,
        'imdb_id': imdb_id,
        'total': len(torrents),
        'torrents': torrents,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Supreme Provider')
    parser.add_argument('tmdb_id', help='TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie')
    parser.add_argument('--season', type=int)
    parser.add_argument('--episode', type=int)
    parser.add_argument('--alldebrid', help='AllDebrid API key')
    parser.add_argument('--premiumize', help='Premiumize API key')
    parser.add_argument('--torbox', help='TorBox API key')
    parser.add_argument('--realdebrid', help='RealDebrid API key')
    args = parser.parse_args()

    try:
        result = get_data(args.tmdb_id, args.type, args.season, args.episode,
                          args.alldebrid, args.premiumize, args.torbox, args.realdebrid)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'source': SOURCE, 'error': str(e)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
