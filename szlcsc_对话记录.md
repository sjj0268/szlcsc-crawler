# 立创商城数据爬虫 - 对话总结

---

## 一、项目目标

抓取 `https://www.szlcsc.com/`（立创商城）上的**电子元器件型号数据**，包括：型号、品牌、封装、类目、编号、价格、库存、详情链接。

---

## 二、已生成的文件

| 文件 | 路径 | 用途 |
|------|------|------|
| szlcsc_crawler.py | /workspace/szlcsc_crawler.py | 原版命令行爬虫（含分类发现、翻页、CSV/JSON 输出） |
| szlcsc_gui.py | /workspace/szlcsc_gui.py | **GUI 版**（含 tkinter 界面、可点击"开始抓取"、自动保存到桌面） |

核心设计：Playwright 渲染动态页面 → BeautifulSoup 解析 DOM → CSV/JSON 输出。

---

## 三、浏览器启动策略（近期重要改动）

原先用 Playwright 自带的 Chromium（需要额外下载浏览器目录，不方便分发）。

现在改为**自动回退策略**，按此顺序尝试：

1. **系统 Chrome**（`channel="chrome"`）→ 优先
2. **系统 Edge**（`channel="msedge"`）→ Win10/11 自带，兜底
3. **Playwright 自带 Chromium** → 纯开发环境兜底

好处：**打包成 EXE 后不需要附带浏览器目录**，用户电脑有 Chrome/Edge 即可运行。

---

## 四、打包成 EXE 的操作步骤（在 Windows 本地执行）

### 准备

把 `szlcsc_gui.py` 放在：`D:\Program Files\MaGa\001\szlcsc_gui.py`

### 在 CMD 中依次执行

**关键注意**：路径含空格必须加**英文双引号**；用 `python -m` 代替裸命令避免 PATH 问题。

```bat
:: 1. 进入代码目录
cd /d "D:\Program Files\MaGa\001"

:: 2. 确认 Python 可用
python --version

:: 3. 安装依赖（用 python -m pip，避免 PATH 缺失）
python -m pip install pyinstaller requests beautifulsoup4 lxml playwright

:: 4. 打包 EXE
python -m PyInstaller --onefile --name szlcsc_crawler ^
  --hidden-import=playwright --hidden-import=requests ^
  --hidden-import=bs4 --hidden-import=lxml szlcsc_gui.py
```

### 产物位置

```
D:\Program Files\MaGa\001\dist\szlcsc_crawler.exe   ← 双击运行
```

运行后数据保存到桌面 `szlcsc_data\` 目录：
- `szlcsc_models.csv`（Excel 可直接打开）
- `szlcsc_models.json`

---

## 五、遇到的问题与解决方案

| 问题 | 原因 | 解决 |
|------|------|------|
| `'pip' 不是内部或外部命令` | Python Scripts 目录未加入系统 PATH | 用 `python -m pip install ...` 代替裸 `pip` |
| `'pyinstaller' 不是内部或外部命令` | 同上 | 用 `python -m PyInstaller ...` 代替 |
| `'D:\Program' 不是内部或外部命令` | 路径含空格但没加引号 | 写成 `cd /d "D:\Program Files\MaGa\001"` |
| `D：`（中文冒号）报错 | 输入时误用了中文标点 | 切英文输入法打 `D:` |
| szlcsc_gui.py 被当成路径一部分 | `cd` 不能定位到文件，应定位目录 | `cd /d "D:\Program Files\MaGa\001"` 即可 |
| Playwright 找不到浏览器 | 想让它用系统浏览器 | 已在代码中加入 `channel="chrome"` / `channel="msedge"` 自动回退 |

---

## 六、下一步操作

1. 在本机 CMD 中跑 `python --version`，确认 Python 可用
2. 跑 `python -m pip install pyinstaller requests beautifulsoup4 lxml playwright` 装依赖
3. 跑 `python -m PyInstaller ...` 打包（完整命令见上方第四节）
4. 到 `dist\szlcsc_crawler.exe` 双击测试
