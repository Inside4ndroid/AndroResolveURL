#!/usr/bin/env python3
"""
Parse Tubi M3U playlist to JSON
"""

import re
import json
import sys
import urllib.request
import urllib.error
import ssl

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

URL = "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/tubi_playlist.m3u"
SOURCE = "tubi"


def fetch_m3u(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    return resp.read().decode('utf-8', errors='replace')


def parse_m3u(content):
    channels = []
    lines = content.splitlines()

    extinf_re = re.compile(
        r'#EXTINF:-1\s+(.*?),(.+)'
    )
    param_re = re.compile(r'(\w[\w-]*?)="([^"]*)"')

    for i, line in enumerate(lines):
        line = line.strip()
        m = extinf_re.match(line)
        if m:
            raw_params = m.group(1)
            name = m.group(2).strip()
            params = dict(param_re.findall(raw_params))

            url = ''
            if i + 1 < len(lines):
                url = lines[i + 1].strip()

            channels.append({
                'name': name,
                'tvg_id': params.get('tvg-id', ''),
                'tvg_name': params.get('tvg-name', ''),
                'logo': params.get('tvg-logo', ''),
                'group': params.get('group-title', ''),
                'url': url,
            })

    return channels


def get_data():
    content = fetch_m3u(URL)
    channels = parse_m3u(content)
    return {
        'source': SOURCE,
        'url': URL,
        'total': len(channels),
        'channels': channels,
    }


def main():
    try:
        result = get_data()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'source': SOURCE, 'error': str(e)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
