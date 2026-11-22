# 师生指南 H5 阅读版

正文来自[师生使用指南](../开题手记-设计思路与师生使用指南.md)。从仓库根目录运行 `python -B docs/h5/build.py`，在浏览器打开生成的 `docs/开题手记.html`。页面内嵌样式、脚本、图解和三张隔离演示截图，可以离线阅读。

安装 Playwright（`npm ci`）和 Google Chrome 后，运行 `node docs/h5/capture.cjs` 可从临时演示库更新截图。重建阅读版后，依次运行 `node docs/h5/verify.cjs`、`node docs/h5/verify-fit.cjs` 和 `node docs/h5/verify-reading.cjs` 检查布局与交互。
