#!/usr/bin/env python3
"""Preflight de fuentes candidatas para Task 0."""
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse
import json

CANDIDATES = [
    ("stripe", "Stripe changelog", "https://stripe.com/blog/changelog"),
    ("stripe-docs", "Stripe docs changelog", "https://docs.stripe.com/changelog"),
    ("aws", "AWS What's New", "https://aws.amazon.com/about-aws/whats-new/feed/"),
    ("supabase", "Supabase changelog RSS", "https://supabase.com/changelog/rss.xml"),
    ("sentry", "Sentry changelog", "https://sentry.io/changelog/feed.xml"),
    ("cloudflare", "Cloudflare changelog", "https://developers.cloudflare.com/changelog/rss/index.xml"),
    ("github", "GitHub changelog", "https://github.blog/changelog/feed/"),
    ("twilio", "Twilio changelog", "https://twilio.com/en-us/changelog.feed.xml"),
    ("gcp", "Google Cloud release notes", "https://docs.cloud.google.com/feeds/gcp-release-notes.xml"),
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

results = []
for slug, name, url in CANDIDATES:
    print(f"Testing {slug}: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "vigia/0.1 (+https://github.com/Diegohhl1/vigia)"})
        with urllib.request.urlopen(req, timeout=15) as response:
            final_url = response.geturl()
            code = response.status
            content_type = response.headers.get("Content-Type", "unknown")
            body = response.read()
            size = len(body)

            # Detectar formato
            fmt = "UNKNOWN"
            if "xml" in content_type.lower() or "rss" in content_type.lower() or "atom" in content_type.lower():
                if b"<rss" in body[:500] or b"<feed" in body[:500]:
                    fmt = "RSS/Atom"
            elif "html" in content_type.lower():
                fmt = "HTML"
            elif "json" in content_type.lower():
                fmt = "JSON"

            robots = check_robots(url)

            results.append({
                "slug": slug,
                "name": name,
                "url": url,
                "final_url": final_url,
                "code": code,
                "content_type": content_type,
                "size": size,
                "format": fmt,
                "robots": robots,
                "body_preview": body[:200].decode('utf-8', errors='ignore'),
                "status": "OK" if code == 200 and robots != "DENY" else "FAIL"
            })

    except Exception as e:
        results.append({
            "slug": slug,
            "name": name,
            "url": url,
            "final_url": url,
            "code": 0,
            "content_type": "ERROR",
            "size": 0,
            "format": "ERROR",
            "robots": "N/A",
            "body_preview": str(e),
            "status": "ERROR"
        })

print("\n=== RESULTS ===")
print(json.dumps(results, indent=2))
