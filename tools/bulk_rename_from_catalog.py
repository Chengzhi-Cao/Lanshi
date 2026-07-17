import argparse
import csv
import html
import json
import os
import re
import shutil
import ssl
import urllib.request
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".mpg", ".mpeg"}
BASE_URL = "https://www.silknblood.com/product-category/video-downloads"
CATEGORY_SLUGS = [
    "bluestone-superheroines",
    "sexy-spies",
    "scotland-yard-cold-cases",
    "silk-n-blood-series",
    "superheroine-fans-videos",
    "girl-power-videos",
]

KNOWN_SERIES = [
    "supernova",
    "darkwing",
    "white angel",
    "whiteangel",
    "wondra",
    "dark wondra",
    "darkwondra",
    "catwarrior",
    "catwoman",
    "black bird",
    "blackbird",
    "dark canary",
    "dark widow",
    "teenbat",
    "teenwing",
    "ultrawoman",
    "wonderkick",
    "athena",
    "spider warrior",
    "stellar",
    "amazon",
    "scotland yard",
    "sycc",
    "uksg",
    "sexy spies",
]


def repo_root():
    return Path(__file__).resolve().parents[2]


def tool_root():
    return Path(__file__).resolve().parents[1]


def curl_path():
    found = shutil.which("curl.exe") or shutil.which("curl")
    if not found:
        raise RuntimeError("curl was not found")
    return found


def fetch(url, out_path, refresh=False):
    if out_path.exists() and out_path.stat().st_size > 5000 and not refresh:
        return out_path.read_text("utf-8", errors="ignore")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    context = ssl._create_unverified_context()
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, context=context, timeout=45) as response:
        text = response.read().decode("utf-8", "ignore")
    out_path.write_text(text, "utf-8")
    return text


def max_page_from_html(text):
    nums = [int(n) for n in re.findall(r'aria-label="Page\s+(\d+)"', text)]
    if not nums:
        nums = [int(n) for n in re.findall(r"/page/(\d+)/", text)]
    return max(nums) if nums else 1


def extract_products(text, category):
    products = []
    pattern = re.compile(
        r'<a href="(?P<url>https://www\.silknblood\.com/product/[^"]+)"[^>]*>.*?'
        r'<h2 class="woocommerce-loop-product__title">(?P<title>.*?)</h2>',
        re.S,
    )
    for match in pattern.finditer(text):
        title = html.unescape(re.sub(r"<.*?>", "", match.group("title")))
        title = normalize_spaces(title)
        products.append({"title": title, "url": match.group("url"), "category": category})
    return products


def crawl_catalog(refresh=False, workers=4):
    cache_dir = tool_root() / "title_sources"
    pages = []
    for slug in CATEGORY_SLUGS:
        first_url = f"{BASE_URL}/{slug}/"
        first_path = cache_dir / f"{slug}_page_1.html"
        try:
            first_html = fetch(first_url, first_path, refresh=refresh)
        except Exception as exc:
            print(f"warn: could not fetch {first_url}: {exc}", file=sys.stderr)
            continue
        max_page = max_page_from_html(first_html)
        pages.append((slug, 1, first_url, first_path))
        for page in range(2, max_page + 1):
            pages.append((slug, page, f"{BASE_URL}/{slug}/page/{page}/", cache_dir / f"{slug}_page_{page}.html"))

    products = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, url, path, refresh): (slug, page, url) for slug, page, url, path in pages}
        for future in as_completed(futures):
            slug, page, url = futures[future]
            try:
                text = future.result()
            except Exception as exc:
                print(f"warn: could not fetch {url}: {exc}", file=sys.stderr)
                continue
            products.extend(extract_products(text, slug))

    unique = {}
    for product in products:
        key = product["url"]
        unique[key] = product
    return list(unique.values())


def normalize_spaces(value):
    return re.sub(r"\s+", " ", value).strip()


def strip_original_noise(stem):
    value = stem
    value = re.sub(r"[_+]+", " ", value)
    value = re.sub(r"\b20\d{10,14}\b", " ", value)
    value = re.sub(r"\b2025[-_]\d{2}[-_]\d{2}\s+\d{1,2}[-_]\d{2}[-_]\d{2}\b", " ", value)
    value = re.sub(r"(?i)A{3,}\w*", " ", value)
    value = re.sub(r"\b(good|collected)\b", " ", value, flags=re.I)
    value = normalize_spaces(value)
    return value


def has_aaa_suffix(stem):
    return bool(re.search(r"(?i)A{3,}", stem))


def clean_product_title(title):
    value = html.unescape(title)
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    value = re.sub(r"\s*[–—]\s*", " - ", value)
    value = normalize_spaces(value)

    # Remove catalog-only codes while keeping real series numbers.
    value = re.sub(
        r"^(?:VV|SS)\s*#?\s*\d+[A-Za-z]?(?:\s*-\s*(?:VV|SS)\s*#?\s*\d+[A-Za-z]?)*\s*[-:]\s*",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"^\d+[A-Za-z]?\s*[-:]\s*(?=(?:" + "|".join(re.escape(s) for s in KNOWN_SERIES) + r")\b)", "", value, flags=re.I)

    value = re.sub(r"\s*:\s*", " - ", value)
    value = normalize_spaces(value)
    value = sanitize_filename_stem(value)
    return value


def sanitize_filename_stem(stem):
    value = stem.replace("/", " ").replace("\\", " ")
    value = re.sub(r'[<>:"|?*]', " - ", value)
    value = re.sub(r"\s+-\s+-\s+", " - ", value)
    value = normalize_spaces(value).strip(" .-_")
    return value or "Untitled"


def canonical(value):
    value = html.unescape(value).lower()
    value = strip_original_noise(value)
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = normalize_spaces(value)
    return value


def token_score(a, b):
    at = set(a.split())
    bt = set(b.split())
    if not at or not bt:
        return 0.0
    inter = len(at & bt)
    return (2 * inter) / (len(at) + len(bt))


def series_hint(stem):
    text = canonical(stem)
    for series in KNOWN_SERIES:
        if canonical(series) in text:
            return canonical(series)
    return ""


def score_match(file_stem, product):
    left = canonical(file_stem)
    candidates = [product["canonical_clean"], product["canonical_raw"]]
    best = 0.0
    for right in candidates:
        ratio = SequenceMatcher(None, left, right).ratio()
        ts = token_score(left, right)
        contains = min(len(left), len(right)) / max(len(left), len(right)) if left and right and (left in right or right in left) else 0.0
        best = max(best, ratio, ts, contains)
    hint = series_hint(file_stem)
    if hint and hint not in product["canonical_clean"] and hint not in product["canonical_raw"]:
        best -= 0.15
    if "peril" in left and "peril" not in product["canonical_clean"] and "peril" not in product["canonical_raw"]:
        best -= 0.10
    return max(0.0, min(1.0, best))


def build_product_index(products):
    indexed = []
    for product in products:
        clean = clean_product_title(product["title"])
        product = dict(product)
        product["cleanTitle"] = clean
        product["canonical_clean"] = canonical(clean)
        product["canonical_raw"] = canonical(product["title"])
        indexed.append(product)
    return indexed


def unique_target(path, target_stem, aaa):
    suffix = "AAA" if aaa and not re.search(r"(?i)A{3}$", target_stem) else ""
    base = sanitize_filename_stem(target_stem + suffix)
    candidate = path.with_name(base + path.suffix)
    if candidate.name == path.name:
        return candidate
    if not candidate.exists():
        return candidate
    return None


def find_plan(video_dir, products):
    indexed = build_product_index(products)
    rows = []
    for path in sorted(video_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTS:
            continue
        stem_for_match = strip_original_noise(path.stem)
        scored = sorted(((score_match(stem_for_match, product), product) for product in indexed), key=lambda item: item[0], reverse=True)
        best_score, best = scored[0] if scored else (0, None)
        second_score = scored[1][0] if len(scored) > 1 else 0
        reason = ""
        target = ""
        source_title = ""
        status = "skip"
        if not best or best_score < 0.86:
            reason = "no high-confidence title match"
        elif second_score >= best_score - 0.035:
            reason = "ambiguous title match"
        else:
            aaa = has_aaa_suffix(path.stem)
            target_path = unique_target(path, best["cleanTitle"], aaa)
            source_title = best["title"]
            if target_path is None:
                reason = "target exists"
            elif target_path.name == path.name:
                reason = "already named"
                status = "keep"
                target = target_path.name
            else:
                status = "rename"
                target = target_path.name
        rows.append(
            {
                "status": status,
                "current": path.name,
                "target": target,
                "score": f"{best_score:.3f}",
                "secondScore": f"{second_score:.3f}",
                "sourceTitle": source_title,
                "reason": reason,
            }
        )
    return rows


def write_reports(rows, products):
    reports = tool_root() / "rename_reports"
    reports.mkdir(parents=True, exist_ok=True)
    with (reports / "title_catalog.json").open("w", encoding="utf-8") as file:
        json.dump(products, file, ensure_ascii=False, indent=2)
    with (reports / "bulk_rename_plan.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["status", "current", "target", "score", "secondScore", "sourceTitle", "reason"])
        writer.writeheader()
        writer.writerows(rows)
    return reports


def execute_plan(video_dir, rows):
    renamed = []
    for row in rows:
        if row["status"] != "rename":
            continue
        src = video_dir / row["current"]
        dst = video_dir / row["target"]
        if not src.exists() or dst.exists():
            row["status"] = "skip"
            row["reason"] = "source missing or target exists at execution"
            continue
        src.rename(dst)
        renamed.append((src.name, dst.name))
    return renamed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="refresh cached source pages")
    parser.add_argument("--execute", action="store_true", help="perform renames")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    root = repo_root()
    products = crawl_catalog(refresh=args.refresh, workers=args.workers)
    rows = find_plan(root, products)
    reports = write_reports(rows, products)
    renamed = execute_plan(root, rows) if args.execute else []
    if args.execute:
        write_reports(rows, products)

    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"products={len(products)} videos={len(rows)} counts={counts}")
    print(f"report={reports / 'bulk_rename_plan.csv'}")
    if args.execute:
        print(f"renamed={len(renamed)}")


if __name__ == "__main__":
    main()
