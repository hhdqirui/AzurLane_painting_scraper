# AzurLane Painting Scraper
This is a scraper written in Python that downloads ship paintings from the [Azur Lane Wiki](https://azurlane.koumakan.jp).

It downloads **every painting variant of every skin of every ship**: Default, Without BG, Censored, Censored Without BG and any other variant shown in a skin's painting viewer. Chibis, icons, banners and backgrounds are not downloaded.

## How it works
The scraper does not use a browser. It talks to the wiki's MediaWiki API directly:
1. A few queries list every ship gallery page on the wiki.
2. One batched query checks which ship galleries changed since the last run. Only those `<Ship>/Gallery` pages are read again.
3. Full-size original images are downloaded from the wiki's image server in parallel.

A full scan of all 901 ships takes about 80 seconds, and a re-run with nothing changed takes a few seconds. After that, the download time depends only on how many images are new.

## Only new images are downloaded
Images that already exist in the output folder are skipped, so re-running the scraper only downloads new skins. The scraper keeps `images/manifest.json`, which records downloaded files and cached gallery data. Images stay recognised even if the wiki renames a skin later.

Each image is first written to a `.part` file and renamed only when it is complete. You can stop the scraper at any time (Ctrl+C) and run it again to continue where it left off.

## File names
- Main painting of a skin: `<Ship>_<Skin>.png`, e.g. `Akagi_Wedding.png`
- Other variants: `<Ship>_<Skin>_<Variant>.png`, e.g. `Akagi_Precipice of Sweetness_Without BG.png`

Punctuation is removed from skin names.

## How to run
```
pip install -r requirements.txt
python scraper.py
```

Options:

| Option | Description |
| --- | --- |
| `--ships NAME ...` | Only scrape these ships, e.g. `--ships Akagi "Émile Bertin"` |
| `--dry-run` | List the images that would be downloaded without downloading them |
| `--workers N` | Number of parallel image downloads (default: 4). Keep it low: the wiki temporarily blocks networks that send too many requests |
| `--out DIR` | Folder to save images to (default: `images/` next to the script) |
| `--force` | Read every gallery again and re-download images that already exist |

If some downloads fail (e.g. network errors), they are listed at the end. Run the scraper again to retry them. If many requests fail in a row, the scraper stops: the wiki is probably limiting your network, so wait a while (possibly hours) before running it again.

## Tech stack
- Python
- requests
- lxml

## Welcome to contribute!
You are welcome to submit PRs and post in issue tracker.

[中文](https://github.com/hhdqirui/AzurLane_painting_scraper/blob/master/README_zh.md)
