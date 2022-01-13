# 碧蓝航线立绘爬虫
用Python写的爬虫。爬虫用到了Selenium。从 [https://azurlane.koumakan.jp](https://azurlane.koumakan.jp) 爬取立绘。

爬取立绘不包括没有背景，censored，没有舰装和别的地区（EN, TW) 的立绘。这是为了只爬取每个皮肤tab的第一个皮肤。

这个爬虫可能不会爬取所有的立绘因为还没有测试，也还没有handle `TimeoutException`，所以遇到`TimeoutException`要手动重新跑一遍爬虫。在重新跑之前要重设`cnt`这个变量，这个变量是指现在在爬取第几个舰娘，这个可以在 console 找到。

## 怎么跑
`python scraper.py`

## 技术栈
- Python
- Selenium

## 欢迎使用与提交PR

[English](https://github.com/hhdqirui/AzurLane_painting_scraper)