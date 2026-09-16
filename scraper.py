"""Scrape Azur Lane ship paintings from the Azur Lane Wiki (azurlane.koumakan.jp).

Instead of driving a browser, this uses the wiki's MediaWiki API: a few queries list
every ship gallery, one request per changed gallery returns its rendered page, and
the original paintings are downloaded straight from the image server in parallel.

Every painting variant of every skin is saved (Default, Without BG, Censored, ...).
Images that already exist in the output folder are skipped, so re-running the
scraper only downloads new skins.
"""
import argparse
import hashlib
import json
import os
import string
import sys
import threading
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import quote, unquote, urljoin

import requests
from lxml import html
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_URL = 'https://azurlane.koumakan.jp/w/api.php'
GALLERY_SUFFIX = '/Gallery'
IMAGE_BASE_URL = 'https://azurlane.netojuu.com/images/'
# The wiki sits behind Anubis bot protection, which challenges browser-like user
# agents ("Mozilla/..."). A descriptive non-browser user agent is let through.
USER_AGENT = 'AzurLanePaintingScraper/2.0 (+https://github.com/hhdqirui/AzurLane_painting_scraper)'
# The wiki temporarily drops connections from clients that send too many requests,
# so API calls use little concurrency; images come from a separate server.
API_WORKERS = 3
API_BATCH_SIZE = 50
MANIFEST_NAME = 'manifest.json'
MANIFEST_VERSION = 1
MANIFEST_SAVE_INTERVAL = 25
DOWNLOAD_ATTEMPTS = 2
# this many failed requests in a row almost always means the wiki is blocking us
MAX_FAILURES_IN_A_ROW = 10

PUNCTUATION_TABLE = str.maketrans('', '', string.punctuation)
WINDOWS_ILLEGAL_TABLE = str.maketrans('', '', '<>:"/\\|?*')

_thread_local = threading.local()
stop_event = threading.Event()


class Cancelled(Exception):
    """Raised in worker threads after the user pressed Ctrl+C."""


class TooManyFailures(Exception):
    """Raised when so many requests fail in a row that continuing is pointless."""


def get_session():
    """Return a per-thread requests session that retries transient errors."""
    session = getattr(_thread_local, 'session', None)
    if session is None:
        session = requests.Session()
        session.headers['User-Agent'] = USER_AGENT
        # 520-524 are Cloudflare errors for when the image server behind it does not respond
        retry = Retry(total=3, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504, 520, 521, 522, 523, 524),
                      allowed_methods=('GET',), respect_retry_after_header=True)
        session.mount('https://', HTTPAdapter(max_retries=retry))
        _thread_local.session = session
    return session


def api_get(**params):
    params.update(format='json', formatversion='2')
    res = get_session().get(API_URL, params=params, timeout=(10, 30))
    res.raise_for_status()
    try:
        return res.json()
    except ValueError:
        raise RuntimeError('wiki API did not return JSON (blocked by bot protection?)') from None


def fetch_ship_names():
    """Return every ship that has a gallery page on the wiki.

    The wiki's `ships` table misses a few ships that do have skins, so the list of
    `<Ship>/Gallery` pages is used instead. Redirects are left out, otherwise ships
    renamed on the wiki would be downloaded twice.
    """
    names = []
    params = {}
    while True:
        data = api_get(action='query', list='allpages', apnamespace=0, aplimit=500,
                       apfilterredir='nonredirects', **params)
        if 'error' in data:
            raise RuntimeError('ship list query failed: {}'.format(data['error'].get('info')))
        names += [page['title'][:-len(GALLERY_SUFFIX)] for page in data['query']['allpages']
                  if page['title'].endswith(GALLERY_SUFFIX)]
        if 'continue' not in data:
            break
        params = data['continue']
    return sorted(names)


def has_class(cls):
    return 'contains(concat(" ", normalize-space(@class), " "), " {} ")'.format(cls)


def panel_label(panel):
    """Return the title of the tab that shows the given tabber panel."""
    tabber = panel.xpath('ancestor::div[{}][1]'.format(has_class('tabber')))[0]
    tabs = tabber.xpath('./header//a[{}]'.format(has_class('tabber__tab')))
    for tab in tabs:
        if tab.get('aria-controls') == panel.get('id'):
            return tab.text_content().strip()
    panels = tabber.xpath('./section/article[{}]'.format(has_class('tabber__panel')))
    index = panels.index(panel)
    return tabs[index].text_content().strip() if index < len(tabs) else None


def original_url(thumb_src, wiki_file):
    """Turn a gallery thumbnail URL into the URL of the full-size original."""
    if thumb_src:
        url = urljoin(IMAGE_BASE_URL, thumb_src)
        if '/thumb/' in url:
            # .../images/thumb/5/53/Name.png/468px-Name.png -> .../images/5/53/Name.png
            url = url.replace('/thumb/', '/', 1).rsplit('/', 1)[0]
        return url
    # MediaWiki stores files under md5-based directories
    name = wiki_file.replace(' ', '_')
    digest = hashlib.md5(name.encode('utf-8')).hexdigest()
    return '{}{}/{}/{}'.format(IMAGE_BASE_URL, digest[0], digest[:2], quote(name))


def parse_gallery(page_html):
    """Return (paintings, empty_skins) for a rendered `<Ship>/Gallery` page.

    paintings is a list of dicts (skin, variant, is_main, wiki_file, url), one per
    painting variant of every skin; empty_skins lists skin tabs without paintings.
    """
    doc = html.fromstring(page_html)
    paintings = []
    empty_skins = []
    seen_files = set()
    for skin_div in doc.xpath('//div[{}]'.format(has_class('shipskin'))):
        outer_panel = skin_div.xpath('ancestor::article[{}][1]'.format(has_class('tabber__panel')))
        if outer_panel:
            skin = panel_label(outer_panel[0])
        else:
            header = skin_div.xpath('.//div[{}]'.format(has_class('shipskin-name')))
            skin = header[0].text_content().split(':', 1)[-1].strip() if header else 'Default'

        # Chibi, icons, banner and background live outside `shipskin-image`
        links = skin_div.xpath('.//div[{}]//a[{}]'.format(has_class('shipskin-image'), has_class('mw-file-description')))
        links = [link for link in links if 'File:' in (link.get('href') or '')]
        if not links:
            empty_skins.append(skin)
            continue

        main_stem = os.path.splitext(unquote(links[0].get('href').rsplit('File:', 1)[1]))[0]
        for index, link in enumerate(links):
            wiki_file = unquote(link.get('href').rsplit('File:', 1)[1])
            if wiki_file in seen_files:
                continue
            seen_files.add(wiki_file)

            # variants (Without BG, Censored, ...) are tabs nested inside the skin
            inner_panel = link.xpath('ancestor::article[{}][ancestor::div[{}]][1]'.format(
                has_class('tabber__panel'), has_class('shipskin')))
            variant = panel_label(inner_panel[0]) if inner_panel else None
            if not variant:
                stem = os.path.splitext(wiki_file)[0]
                variant = stem[len(main_stem):] if index and stem.startswith(main_stem) else stem
                variant = variant or 'Default'

            img = link.find('.//img')
            paintings.append({
                'skin': skin,
                'variant': variant,
                'is_main': index == 0,
                'wiki_file': wiki_file,
                'url': original_url(img.get('src') if img is not None else None, wiki_file),
            })
    return paintings, empty_skins


def fetch_gallery_timestamps(ships):
    """Return ({ship: last-changed timestamp}, [ships without a gallery page]).

    Ship names are returned as the wiki spells them, e.g. `akagi` becomes `Akagi`.
    """
    touched = {}
    missing = []
    for start in range(0, len(ships), API_BATCH_SIZE):
        titles = {ship + GALLERY_SUFFIX: ship for ship in ships[start:start + API_BATCH_SIZE]}
        data = api_get(action='query', prop='info', titles='|'.join(titles), redirects='1')
        if 'error' in data:
            raise RuntimeError('gallery timestamp query failed: {}'.format(data['error'].get('info')))
        query = data.get('query', {})
        # the API reports the titles it normalised or followed redirects for
        for step in query.get('normalized', []) + query.get('redirects', []):
            if step['from'] in titles:
                titles[step['to']] = titles.pop(step['from'])
        for page in query.get('pages', []):
            if page['title'] in titles and 'missing' not in page and 'invalid' not in page:
                titles.pop(page['title'])
                ship = page['title'][:-len(GALLERY_SUFFIX)]
                # `touched` also changes when a template used by the page changes
                touched[ship] = page['touched']
        missing.extend(titles.values())
    return touched, missing


def fetch_paintings(ship):
    """Return (paintings, empty_skins) for a ship, or None if it has no gallery page."""
    if stop_event.is_set():
        raise Cancelled
    data = api_get(action='parse', page=ship + GALLERY_SUFFIX, prop='text', redirects='1')
    if 'error' in data:
        if data['error'].get('code') == 'missingtitle':
            return None
        raise RuntimeError(data['error'].get('info'))
    return parse_gallery(data['parse']['text'])


def clean(text, keep_punctuation=False):
    return text.translate(WINDOWS_ILLEGAL_TABLE if keep_punctuation else PUNCTUATION_TABLE).strip()


def local_filename(ship, painting, keep_punctuation=False):
    """`Ship_Skin.png` for the main painting (same as older versions), `Ship_Skin_Variant.png` otherwise."""
    parts = [ship.translate(WINDOWS_ILLEGAL_TABLE).strip(' .'), clean(painting['skin'], keep_punctuation)]
    if not painting['is_main']:
        parts.append(clean(painting['variant'], keep_punctuation))
    ext = os.path.splitext(painting['wiki_file'])[1].lower() or '.png'
    return '_'.join(parts) + ext


def existing_filename(ship, painting, filename, existing):
    """Return the name this painting already has in the output folder, if any.

    Older versions of the scraper kept the punctuation in skin names, so
    `Akatsuki_Santa's Lost Helper!.png` counts as already downloaded too.
    """
    candidates = [filename, local_filename(ship, painting, keep_punctuation=True)]
    for candidate in candidates:
        if normalize(candidate) in existing:
            return candidate
    return None


def normalize(filename):
    # Windows file systems are case-insensitive, and names may differ in unicode form
    return unicodedata.normalize('NFC', filename).casefold()


def download(task, out_dir):
    """Download one painting to the output folder and return its size in bytes."""
    path = os.path.join(out_dir, task['filename'])
    part_path = path + '.part'
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        if stop_event.is_set():
            raise Cancelled
        try:
            size = 0
            with get_session().get(task['url'], stream=True, timeout=(10, 30)) as res:
                res.raise_for_status()
                if not res.headers.get('Content-Type', '').startswith('image/'):
                    raise RuntimeError('unexpected content type {!r}'.format(res.headers.get('Content-Type')))
                expected = int(res.headers.get('Content-Length', 0)) if 'Content-Encoding' not in res.headers else 0
                with open(part_path, 'wb') as file:
                    for chunk in res.iter_content(chunk_size=1 << 16):
                        if stop_event.is_set():
                            raise Cancelled
                        file.write(chunk)
                        size += len(chunk)
            if expected and size != expected:
                raise IOError('incomplete download ({}/{} bytes)'.format(size, expected))
            # write to a temporary name first so an interrupted run never leaves a
            # truncated image that later runs would mistake for a finished one
            os.replace(part_path, path)
            return size
        except (requests.RequestException, IOError):
            if attempt == DOWNLOAD_ATTEMPTS:
                raise
        finally:
            if os.path.exists(part_path):
                os.remove(part_path)


def run_parallel(func, items, workers, on_done):
    """Run func over items in a thread pool, calling on_done(count, item, future) as each finishes."""
    count = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(func, item): item for item in items}
        try:
            while pending:
                # poll with a timeout so Ctrl+C is handled promptly on every platform
                done, _ = wait(pending, timeout=1, return_when=FIRST_COMPLETED)
                for future in done:
                    count += 1
                    on_done(count, pending.pop(future), future)
        except BaseException:
            stop_event.set()
            pool.shutdown(cancel_futures=True)
            raise


def load_manifest(path):
    """Load the manifest: downloaded files and a cache of parsed galleries."""
    try:
        with open(path, encoding='utf-8') as file:
            manifest = json.load(file)
    except FileNotFoundError:
        manifest = {}
    manifest.setdefault('files', {})
    if manifest.get('version') != MANIFEST_VERSION:
        # cached galleries from another scraper version may have been parsed differently
        manifest['galleries'] = {}
        manifest['version'] = MANIFEST_VERSION
    return manifest


def save_manifest(path, manifest):
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as file:
        json.dump(manifest, file, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp_path, path)


def parse_args():
    parser = argparse.ArgumentParser(description='Download Azur Lane ship paintings from the Azur Lane Wiki.')
    parser.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images'),
                        help='folder to save images to (default: images/ next to this script)')
    parser.add_argument('--workers', type=int, default=4, help='number of parallel image downloads (default: 4)')
    parser.add_argument('--ships', nargs='+', metavar='NAME', help='only scrape these ships, e.g. --ships Akagi "Emile Bertin"')
    parser.add_argument('--dry-run', action='store_true', help='list the images that would be downloaded without downloading')
    parser.add_argument('--force', action='store_true', help='re-read every gallery and download images again even if they already exist')
    return parser.parse_args()


def main():
    args = parse_args()
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    manifest = load_manifest(manifest_path)
    files, galleries = manifest['files'], manifest['galleries']

    ships = args.ships or fetch_ship_names()
    touched, no_gallery = fetch_gallery_timestamps(ships)
    # only galleries edited since the last run need to be read again
    changed = [ship for ship in touched if args.force or galleries.get(ship, {}).get('touched') != touched[ship]]
    print('{} ships, {} galleries changed since the last run'.format(len(ships), len(changed)))

    # Phase 1: find every painting of every skin
    failures = []
    failures_in_a_row = 0

    def record_failure(message):
        nonlocal failures_in_a_row
        failures.append(message)
        failures_in_a_row += 1
        if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
            raise TooManyFailures

    def record_success():
        nonlocal failures_in_a_row
        failures_in_a_row = 0

    def on_gallery(count, ship, future):
        try:
            result = future.result()
            if result is None:
                raise RuntimeError('gallery page disappeared')
        except Exception as e:
            print('[{}/{}] {}: FAILED to read gallery: {}'.format(count, len(changed), ship, e))
            record_failure('{} (gallery): {}'.format(ship, e))
            return
        record_success()
        paintings, empty_skins = result
        galleries[ship] = {'touched': touched[ship], 'paintings': paintings}
        skins = len({p['skin'] for p in paintings})
        print('[{}/{}] {}: {} skins, {} images'.format(count, len(changed), ship, skins, len(paintings)))
        for skin in empty_skins:
            print('    warning: skin "{}" has no images'.format(skin))

    try:
        run_parallel(fetch_paintings, changed, API_WORKERS, on_gallery)
    finally:
        # keep the galleries read so far, even when interrupted
        save_manifest(manifest_path, manifest)
    # a gallery that failed to load falls back to its cached version, if any
    paintings_by_ship = {ship: galleries[ship]['paintings'] for ship in touched if ship in galleries}

    # Phase 2: work out which images are new
    existing = {normalize(name) for name in os.listdir(out_dir)}
    tasks = []
    present = 0
    for ship in sorted(paintings_by_ship):
        used_names = set()
        for painting in paintings_by_ship[ship]:
            filename = local_filename(ship, painting)
            stem, ext = os.path.splitext(filename)
            suffix = 2
            while normalize(filename) in used_names:
                filename = '{}_{}{}'.format(stem, suffix, ext)
                suffix += 1
            used_names.add(normalize(filename))

            key = '{}|{}'.format(ship, painting['wiki_file'])
            if not args.force:
                # a manifest entry keeps a file recognised even if the wiki renames the skin later
                already = files[key] if key in files and normalize(files[key]) in existing else None
                already = already or existing_filename(ship, painting, filename, existing)
                if already:
                    files[key] = already
                    present += 1
                    continue
            tasks.append(dict(painting, ship=ship, filename=filename, key=key))

    total_images = sum(len(p) for p in paintings_by_ship.values())
    total_skins = sum(len({p['skin'] for p in paintings}) for paintings in paintings_by_ship.values())
    print('\nFound {} skins and {} images: {} already downloaded, {} new'.format(
        total_skins, total_images, present, len(tasks)))

    if args.dry_run:
        for task in tasks:
            print('  would download {}  <-  {}'.format(task['filename'], task['url']))
        print_summary(len(ships), no_gallery, failures)
        return 1 if failures else 0

    # Phase 3: download the new images
    downloaded = []

    def on_download(count, task, future):
        try:
            size = future.result()
        except Exception as e:
            print('[{}/{}] FAILED {}: {}'.format(count, len(tasks), task['filename'], e))
            record_failure('{}: {}'.format(task['filename'], e))
            return
        record_success()
        files[task['key']] = task['filename']
        downloaded.append(size)
        print('[{}/{}] Saved {} ({:.1f} MB)'.format(count, len(tasks), task['filename'], size / 1e6))
        if len(downloaded) % MANIFEST_SAVE_INTERVAL == 0:
            save_manifest(manifest_path, manifest)

    try:
        run_parallel(lambda task: download(task, out_dir), tasks, args.workers, on_download)
    finally:
        save_manifest(manifest_path, manifest)

    print('\nDownloaded {} images ({:.1f} MB)'.format(len(downloaded), sum(downloaded) / 1e6))
    print_summary(len(ships), no_gallery, failures)
    return 1 if failures else 0


def print_summary(ship_count, no_gallery, failures):
    print('Scanned {} ships'.format(ship_count))
    if no_gallery:
        print('Ships without a gallery page ({}): {}'.format(len(no_gallery), ', '.join(sorted(no_gallery))))
    if failures:
        print('{} failures (re-run the scraper to retry):'.format(len(failures)))
        for failure in failures:
            print('  ' + failure)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nInterrupted. Finished downloads are kept; re-run to continue.')
        sys.exit(130)
    except TooManyFailures:
        print('\nStopped after {} failed requests in a row. The wiki is probably limiting requests from '
              'your network; wait a while (this can take hours) and run the scraper again. '
              'Finished downloads are kept.'.format(MAX_FAILURES_IN_A_ROW))
        sys.exit(1)
