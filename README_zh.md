# 碧蓝航线立绘爬虫
用 Python 写的爬虫，从 [碧蓝航线 Wiki](https://azurlane.koumakan.jp) 下载舰娘立绘。

爬虫会下载**每个舰娘每个皮肤的所有立绘版本**：默认、没有背景（Without BG）、和谐（Censored）、和谐且没有背景（Censored Without BG），以及皮肤立绘里的其他版本。Q版、头像、横幅和背景图不会下载。

## 原理
爬虫不使用浏览器，而是直接调用 Wiki 的 MediaWiki API：
1. 几次查询获取 Wiki 上所有舰娘的图库页面。
2. 一次批量查询检查哪些舰娘的图库页面自上次运行后有改动，只重新读取有改动的 `<舰娘>/Gallery` 页面。
3. 从 Wiki 的图片服务器并行下载原图。

扫描全部 901 个舰娘大约需要 80 秒；如果没有改动，重新运行只需几秒。之后的下载时间只取决于新图片的数量。

## 只下载新图片
输出文件夹里已存在的图片会被跳过，所以重新运行爬虫只会下载新皮肤。爬虫会生成 `images/manifest.json`，记录已下载的文件和图库缓存，即使 Wiki 以后修改了皮肤名称，已下载的图片仍然能被识别。

每张图片会先写入 `.part` 文件，下载完成后才重命名。可以随时按 Ctrl+C 停止爬虫，重新运行就会从中断的地方继续。

## 文件名
- 皮肤的主立绘：`<舰娘>_<皮肤>.png`，例如 `Akagi_Wedding.png`
- 其他版本：`<舰娘>_<皮肤>_<版本>.png`，例如 `Akagi_Precipice of Sweetness_Without BG.png`

皮肤名称中的标点符号会被去掉。

## 怎么跑
```
pip install -r requirements.txt
python scraper.py
```

参数：

| 参数 | 说明 |
| --- | --- |
| `--ships NAME ...` | 只爬取这些舰娘，例如 `--ships Akagi "Émile Bertin"` |
| `--dry-run` | 只列出将要下载的图片，不下载 |
| `--workers N` | 同时下载的图片数量（默认 4）。不要设太高：请求太多时 Wiki 会暂时屏蔽你的网络 |
| `--out DIR` | 保存图片的文件夹（默认是脚本旁边的 `images/`） |
| `--force` | 重新读取所有图库，并重新下载已存在的图片 |

如果有下载失败（例如网络错误），会在最后列出，重新运行爬虫即可重试。如果连续很多请求失败，爬虫会自动停止：这通常是 Wiki 暂时限制了你的网络，等一段时间（可能要几个小时）再运行。

## 技术栈
- Python
- requests
- lxml

## 欢迎使用与提交PR

[English](https://github.com/hhdqirui/AzurLane_painting_scraper)
