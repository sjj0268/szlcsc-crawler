# 立创商城数据抓取工具 (szlcsc-crawler)

一个用于抓取 [立创商城](https://www.szlcsc.com/) 电子元器件型号数据的 Python 工具，支持 Web GUI 界面，无需安装 tkinter。

## 功能

- 自动抓取立创商城所有分类下的电子元器件型号数据
- 支持浏览器 Web GUI（Flask），双击即用
- 提供完整版和 8 分钟试用版
- 输出 CSV 和 JSON 两种格式
- 数据保存到桌面 `szlcsc_data` 目录

## 抓取字段

| 字段 | 说明 |
|------|------|
| model | 型号 |
| brand | 品牌 |
| package | 封装 |
| category | 类目 |
| code | 编号 |
| description | 描述 |
| stock | 库存 |
| price | 价格梯度 |
| detail_url | 详情链接 |

## 环境要求

- Windows 系统
- Chrome 或 Edge 浏览器（用于 Playwright 渲染）
- Python 3.10+（开发/打包用）

## 安装依赖

```bash
pip install requests beautifulsoup4 lxml playwright flask
playwright install chromium
```

## 使用方式

### 1. 直接运行 Python

```bash
python szlcsc_gui.py
```

运行后自动打开浏览器访问 `http://localhost:5678`

### 2. 打包成 EXE

```bash
pip install pyinstaller

# 完整版
python -m PyInstaller --onefile --name szlcsc_crawler \
  --hidden-import=playwright --hidden-import=requests \
  --hidden-import=bs4 --hidden-import=lxml --hidden-import=flask \
  --hidden-import=jinja2 --hidden-import=markupsafe \
  --hidden-import=itsdangerous --hidden-import=click \
  szlcsc_gui.py

# 试用版（8分钟倒计时）
python -m PyInstaller --onefile --name szlcsc_crawler_trial \
  --hidden-import=playwright --hidden-import=requests \
  --hidden-import=bs4 --hidden-import=lxml --hidden-import=flask \
  --hidden-import=jinja2 --hidden-import=markupsafe \
  --hidden-import=itsdangerous --hidden-import=click \
  szlcsc_gui_trial.py
```

打包后的 EXE 在 `dist/` 目录下，可直接发给他人使用（无需安装 Python）。

## 文件说明

| 文件 | 说明 |
|------|------|
| `szlcsc_gui.py` | 完整版源码（无时间限制） |
| `szlcsc_gui_trial.py` | 试用版源码（8分钟倒计时） |
| `szlcsc_对话记录.md` | 项目开发记录 |

## 技术栈

- **Playwright** - 浏览器自动化，渲染动态页面
- **BeautifulSoup4 + lxml** - HTML 解析
- **Flask** - Web GUI 服务
- **PyInstaller** - 打包成独立 EXE

## 免责声明

本工具仅供学习和研究使用。请遵守立创商城的使用条款，合理控制抓取频率，不要对目标网站造成过大压力。

## License

MIT
