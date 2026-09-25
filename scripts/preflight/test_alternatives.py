#!/usr/bin/env python3
"""Buscar alternativas para las fuentes que fallaron."""
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse
import json

# Alternativas a probar
ALTERNATIVES = [
    ("aws-alt1", "AWS What's New (recent)", "https://aws.amazon.com/about-aws/whats-new/recent/feed/"),
    ("aws-alt2", "AWS new feed", "https://aws.amazon.com/new/feed/"),
    ("aws-alt3", "AWS RSS", "https://aws.amazon.com/blogs/aws/feed/"),
    ("supabase-alt1", "Supabase RSS main", "https://supabase.com/rss.xml"),
    ("supabase-alt2", "Supabase blog RSS", "https://supabase.com/blog/rss.xml"),
]

def check_robots(url):
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = f"{base}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        allowed = rp.can_fetch("vigia/0.1", url)
        return "ALLOW" if allowed else "DENY"
    except:
        return "ERROR/NO_FILE"

for slug, name, url in ALTERNATIVES:
    print(f"Testing {slug}: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "vigia/0.1 (+https://github.com/Diegohhl1/vigia)"})
        with urllib.request.urlopen(req, timeout=15) as response:
            code = response.status
            content_type = response.headers.get("Content-Type", "unknown")
            body = response.read()[:500]
            robots = check_robots(url)

            fmt = "UNKNOWN"
            if b"<rss" in body or b"<feed" in body:
                fmt = "RSS/Atom"
            elif b"<html" in body:
                fmt = "HTML"

            print(f"  ✓ {code} | {content_type} | {fmt} | robots={robots}")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
    print()
