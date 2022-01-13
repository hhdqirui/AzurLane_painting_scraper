# AzurLane Painting Scraper
This is a scraper written in python using Selenium to scrape the painting from [https://azurlane.koumakan.jp]().

Scraping does not include paintings that are Chibi, without background, cencored, without rigging and in other regions (such as EN, TW). This is to ensure only the first (or default) painting in each skin tab is scraped.

This scraper may not scrape all the target skins as it is not tested yet. It also does not handle `TimeoutException` (to be added in the future), so need to manually restart the scraper and set the `cnt` variable to the current ship. This variable refers to which ship you are currently scraping. This number can be found at the console.

## How to run
`python scraper.py`

## Tech stack
- Python
- Selenium

## Welcome to contribute!
You are welcome to submit PRs and post in issue tracker.

[中文]()