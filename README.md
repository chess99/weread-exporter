# 微信读书导出工具

一个实验性的微信读书网页端导出工具，用于把当前账号在网页阅读器里可见的书籍内容导出为 Markdown。

它只采集登录账号本来就能阅读的内容，不绕过登录、购买、会员、试读或平台限制。

## 思路来源

本项目的技术路线参考了 [lbq110/weread-exporter](https://github.com/lbq110/weread-exporter)：通过 Playwright 打开微信读书网页阅读器，捕获页面实际渲染出的文字和图片，再重建为 Markdown。

我们选择重新实现，而不是直接 fork，主要差异是：

- 更重视断点和可恢复性：逐页写入 checkpoint，不靠已生成章节文件猜进度。
- 更重视结构正确性：记录目录、章节序号、页面指纹和最终可达性，避免重复采集和章节错位。
- 更明确最终产物：完整导出后生成一本合并 Markdown，同时保留 `pages/` 和 `chapters/` 供检查。
- 更透明地处理异常：如果某些目录项无法独立到达，会记录在 `manifest.json` 的 `skippedCatalog` 和 `catalogReachability` 中。

目录中的阅读进度和书签提示会被清理。合并稿支持同一页内的篇、章标题及跨行标题；旧断点恢复产生的重复绘制只保留一份，原始 `pages/` 检查点继续留存。左右页归属按采集时的实际布局判断，避免首屏布局尚未完成时文字交错。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 命令

```powershell
weread-export export <reader-url-or-book-id>
weread-export resume <book-id>
weread-export inspect <book-id>
weread-export clean-locks
```

常用参数：

- `--profile <path>`：浏览器登录态目录，默认 `data/browser-profile`。
- `--output <path>`：导出根目录，默认 `output`。
- `--headless`：无界面运行浏览器；默认会显示浏览器，方便扫码登录和观察。
- `--max-pages <n>`：限制本次最多采集页数，适合调试。
- `--overwrite`：删除这本书已有导出后重新开始。

## 输出

每本书写入 `output/<book-id>/`：

- `manifest.json`：书籍元数据、目录、状态、断点摘要和目录可达性。
- `pages/*.json`：逐页采集检查点。
- `chapters/*.md`：按章节重建出的 Markdown。
- `<title>.md`：全书合并 Markdown，只在完整导出后生成。

## 注意事项

首次运行可能需要在弹出的 Chromium 窗口里扫码登录微信读书。登录态会保存在 `--profile` 指定的目录里。

如果浏览器异常退出后 profile 被占用，可以运行：

```powershell
weread-export clean-locks
```

当前版本优先保证可恢复性和可检查性，只导出 Markdown；epub、pdf、图片本地化下载可以后续再加。
