#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
立创商城爬虫 - Web GUI版本（无需tkinter）
双击运行后自动打开浏览器访问 http://localhost:5678
"""

import os
import sys
import json
import time
import csv
import re
import subprocess
import webbrowser
import threading
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

try:
    from flask import Flask, jsonify, request as flask_request, send_file
except ImportError:
    print("正在安装 flask ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "-q"])
    from flask import Flask, jsonify, request as flask_request, send_file


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

CATALOG_URL = "https://www.szlcsc.com/catalog.html"
REQUEST_TIMEOUT = 60
WEB_PORT = 5678


def normalize_url(url: str) -> str:
    if not url:
        return url
    parsed = urlparse(url)
    q = parse_qs(parsed.query, keep_blank_values=True)
    for k in ("spm", "lcsc_vid", "fromZone"):
        q.pop(k, None)
    new_query = urlencode({k: v[0] if len(v) == 1 else v for k, v in q.items()}, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def fetch_with_requests(url: str) -> str:
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
        if 200 <= resp.status_code < 400 and len(resp.text) > 2000:
            return resp.text
    except Exception as e:
        print(f"  [requests] failed: {e}", file=sys.stderr)
    return ""


def get_desktop_path() -> str:
    if sys.platform == "win32":
        return os.path.join(os.path.expanduser("~"), "Desktop")
    elif sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Desktop")
    else:
        return os.path.join(os.path.expanduser("~"), "Desktop")


class SZLCSCCrawler:
    def __init__(self, delay: float = 2.0, pages_per_cat: int = 5, headless: bool = True):
        self.delay = delay
        self.pages_per_cat = pages_per_cat
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._context = None
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def _launch_with_channel(self, channel: str):
        return self._playwright.chromium.launch(
            headless=self.headless,
            channel=channel,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

    def _launch_bundled(self):
        return self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

    def __enter__(self) -> "SZLCSCCrawler":
        self._playwright = sync_playwright().start()
        self._browser = None
        launch_errors = []

        try:
            self._browser = self._launch_with_channel("chrome")
            print("[OK] 使用系统 Chrome 浏览器")
        except Exception as e:
            launch_errors.append(f"Chrome: {e}")

        if self._browser is None:
            try:
                self._browser = self._launch_with_channel("msedge")
                print("[OK] 使用系统 Edge 浏览器")
            except Exception as e:
                launch_errors.append(f"Edge: {e}")

        if self._browser is None:
            try:
                self._browser = self._launch_bundled()
                print("[OK] 使用 Playwright 自带 Chromium")
            except Exception as e:
                launch_errors.append(f"Chromium: {e}")

        if self._browser is None:
            raise RuntimeError(
                "无法启动浏览器。\n请确认你的电脑已安装 Chrome 或 Edge 浏览器。\n"
                "启动失败详情: " + "; ".join(launch_errors)
            )

        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=DEFAULT_HEADERS["User-Agent"],
            locale="zh-CN",
            accept_downloads=False,
        )
        self._context.set_default_timeout(REQUEST_TIMEOUT * 1000)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def fetch_categories(self) -> List[Dict]:
        print(f"[*] 获取分类列表: {CATALOG_URL}")
        html = fetch_with_requests(CATALOG_URL)
        if not html:
            raise RuntimeError("无法获取 catalog 页")
        soup = BeautifulSoup(html, "lxml")

        cats: List[Dict] = []
        pat = re.compile(r"(.+?)[（(]\s*([\d,]+)\s*[)）]")

        tmp: List[Dict] = []
        seen_urls = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "list.szlcsc.com/catalog/" not in href:
                continue
            m_path = re.search(r"/catalog/(\d+)\.html", href)
            if not m_path:
                continue
            text = a.get_text(" ", strip=True)
            m = pat.search(text)
            if not m:
                continue
            name = m.group(1).strip()
            name = re.sub(r"[\s（(）)]+$", "", name)
            count_str = m.group(2).replace(",", "")
            try:
                count = int(count_str)
            except ValueError:
                continue
            url = urljoin(CATALOG_URL, href)
            url = normalize_url(url)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            tmp.append({"name": name, "count": count, "url": url})

        tmp.sort(key=lambda x: x["count"], reverse=True)
        print(f"[+] 共获取 {len(tmp)} 个分类")
        return tmp

    def _render_page(self, url: str, wait_ms: int = 2500) -> str:
        page = self._context.new_page()
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
            except PWTimeout:
                pass
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(wait_ms / 1000.0)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PWTimeout:
                pass
            html = page.content()
            return html
        finally:
            try:
                page.close()
            except Exception:
                pass
        return ""

    @staticmethod
    def parse_product_list(html: str, category_name: str) -> List[Dict]:
        products: List[Dict] = []
        if not html:
            return products
        soup = BeautifulSoup(html, "lxml")

        BLACKLIST = {
            "爆款", "立推", "热卖", "新品", "推荐", "现货", "收藏", "对比",
            "数据手册", "加入购物", "下单最高", "运费", "SMT补贴", "查看", "全部",
            "嘉立库存", "供应商", "样品", "价格梯度", "含", "含税",
            "库存", "交期", "近30天最低价", "30天", "最低价",
            "登录", "注册", "购物车", "搜索",
        }

        anchors = []
        for a in soup.find_all("a", href=True):
            if "item.szlcsc.com" not in a["href"]:
                continue
            txt = a.get_text(" ", strip=True)
            if not txt or len(txt) > 120:
                continue
            if txt in BLACKLIST:
                continue
            if any(k in txt for k in BLACKLIST):
                continue
            if not any(c.isdigit() or c.isalpha() for c in txt):
                continue
            anchors.append(a)

        blocks = []
        for a in anchors:
            parent = a.find_parent(["tr", "li", "section", "div"], attrs={"class": True})
            if parent is None:
                parent = a.parent
            blocks.append((a, parent))

        seen: set = set()
        for a, block in blocks:
            bid = id(block)
            if bid in seen:
                continue
            seen.add(bid)
            try:
                info = SZLCSCCrawler._extract_one(block, a, category_name)
                if info and info.get("model"):
                    products.append(info)
            except Exception as e:
                print(f"  [!] 解析错误: {e}", file=sys.stderr)
        return products

    @staticmethod
    def _extract_one(block, model_a, category_name) -> Dict:
        text_block = block.get_text("\n", strip=True)

        model = model_a.get_text(" ", strip=True) or ""
        model = re.sub(r"\s+", " ", model).strip()
        detail_url = urljoin(CATALOG_URL, model_a["href"]) if model_a and model_a.has_attr("href") else ""
        detail_url = normalize_url(detail_url)

        brand = ""
        brand_a = block.find("a", href=lambda h: h and "list.szlcsc.com/brand/" in h)
        if brand_a:
            brand = brand_a.get_text(" ", strip=True)
        if not brand:
            m = re.search(r"品牌[：:\s]*([^\n]+)", text_block)
            if m:
                brand = m.group(1).strip()[:80]

        package = ""
        category = category_name
        code = ""
        description = ""
        stock = ""
        price = ""

        m = re.search(r"封装[：:\s]*([^\n]+)", text_block)
        if m:
            package = m.group(1).strip()[:80]
        m = re.search(r"类目[：:\s]*([^\n]+)", text_block)
        if m:
            category = m.group(1).strip()[:80]
        m = re.search(r"编号[：:\s]*([^\n]+)", text_block)
        if m:
            code = m.group(1).strip()[:40]
        m = re.search(r"描述[：:\s]*([^\n]+)", text_block)
        if m:
            description = m.group(1).strip()[:200]

        price_lines = []
        for ln in text_block.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            if "￥" in ln and re.search(r"\d+\s*[+￥]", ln):
                price_lines.append(ln)
        if price_lines:
            price = " | ".join(price_lines[:6])

        m = re.search(r"现货[：:\s]*([^\n|￥]+)", text_block)
        if m:
            stock = m.group(1).strip()[:80]
        if not stock:
            m = re.search(r"([\dK+万,]{2,})\s*(?:现货|库存|个/|个|盘)", text_block)
            if m:
                stock = m.group(1).strip()

        return {
            "model": model,
            "brand": brand,
            "package": package,
            "category": category,
            "code": code,
            "description": description,
            "stock": stock,
            "price": price,
            "detail_url": detail_url,
        }

    @staticmethod
    def get_next_page_url(html: str, current_url: str) -> str:
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        candidates = []
        for a in soup.find_all("a", href=True):
            txt = a.get_text(" ", strip=True)
            if not txt:
                continue
            if "下一页" in txt or "下一页" == txt or txt in ("next", "»", ">"):
                candidates.append(a["href"])
        if not candidates:
            return ""
        href = candidates[0]
        if not href.startswith("http"):
            href = urljoin(current_url, href)
        return normalize_url(href)

    def crawl(self, categories: List[Dict], output_dir: Path, progress_callback=None) -> Dict:
        csv_path = output_dir / "szlcsc_models.csv"
        json_path = output_dir / "szlcsc_models.json"

        fields = [
            "model", "brand", "package", "category", "code",
            "description", "stock", "price", "detail_url",
        ]

        with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_fp:
            writer = csv.DictWriter(csv_fp, fieldnames=fields)
            writer.writeheader()

            all_products: List[Dict] = []
            total = 0
            total_categories = len(categories)

            for idx, cat in enumerate(categories, 1):
                if self._stop_flag:
                    break

                print(f"\n[{idx}/{total_categories}] {cat['name']} (约{cat['count']}个) -> {cat['url']}")
                if progress_callback:
                    progress_callback(idx, total_categories, cat['name'], 0)

                page_url = cat["url"]
                page_count = 0
                prev_urls = set()
                while page_url and page_count < self.pages_per_cat:
                    if self._stop_flag:
                        break
                    if page_url in prev_urls:
                        break
                    prev_urls.add(page_url)
                    page_count += 1
                    print(f"  - page {page_count}: {page_url}")
                    if progress_callback:
                        progress_callback(idx, total_categories, cat['name'], page_count)

                    html = self._render_page(page_url)
                    items = self.parse_product_list(html, cat["name"])
                    print(f"    抓取到 {len(items)} 个型号")
                    for item in items:
                        writer.writerow(item)
                        all_products.append(item)
                        total += 1
                    next_url = self.get_next_page_url(html, page_url)
                    if not next_url or next_url == page_url:
                        break
                    page_url = next_url
                    time.sleep(self.delay)

        with json_path.open("w", encoding="utf-8") as jf:
            json.dump(all_products, jf, ensure_ascii=False, indent=2)

        print(f"\n[OK] 共抓取 {total} 条型号数据")
        print(f"    CSV:  {csv_path}")
        print(f"    JSON: {json_path}")
        return {"csv": str(csv_path), "json": str(json_path), "total": total}


# ========== Web GUI (Flask) ==========

# 全局状态
crawl_state = {
    "status": "idle",       # idle / running / done / error / stopped
    "phase": "就绪",
    "progress": 0,
    "total_items": 0,
    "message": "点击「开始抓取」按钮进行操作",
    "crawler": None,
}

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>立创商城数据抓取工具</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .container {
    background: #fff;
    border-radius: 16px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    padding: 40px;
    width: 560px;
    max-width: 95vw;
  }
  h1 {
    text-align: center;
    color: #333;
    font-size: 24px;
    margin-bottom: 6px;
  }
  .subtitle {
    text-align: center;
    color: #999;
    font-size: 13px;
    margin-bottom: 24px;
  }
  .info-box {
    background: #f7f8fc;
    border: 1px solid #e8ecf1;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 20px;
  }
  .info-box p {
    color: #555;
    font-size: 13px;
    line-height: 1.8;
  }
  .progress-section {
    margin-bottom: 20px;
  }
  .progress-section .label {
    font-size: 14px;
    color: #333;
    margin-bottom: 8px;
    font-weight: 600;
  }
  .progress-section .status {
    font-size: 12px;
    color: #888;
    margin-top: 6px;
  }
  .progress-bar-bg {
    background: #e8ecf1;
    border-radius: 8px;
    height: 12px;
    overflow: hidden;
  }
  .progress-bar-fill {
    background: linear-gradient(90deg, #667eea, #764ba2);
    height: 100%;
    border-radius: 8px;
    transition: width 0.3s ease;
    width: 0%;
  }
  .btn-group {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .btn {
    padding: 10px 22px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    color: #fff;
  }
  .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
  .btn:active { transform: translateY(0); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; box-shadow: none; }
  .btn-start { background: linear-gradient(135deg, #667eea, #764ba2); }
  .btn-stop { background: linear-gradient(135deg, #f093fb, #f5576c); }
  .btn-open { background: linear-gradient(135deg, #4facfe, #00f2fe); }
  .btn-dir { background: linear-gradient(135deg, #43e97b, #38f9d7); color: #333; }
  .log-box {
    margin-top: 20px;
    background: #1e1e2e;
    border-radius: 10px;
    padding: 14px 18px;
    max-height: 200px;
    overflow-y: auto;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    color: #a6e3a1;
    display: none;
  }
  .log-box.show { display: block; }
</style>
</head>
<body>
<div class="container">
  <h1>立创商城数据抓取工具</h1>
  <p class="subtitle">自动抓取 szlcsc.com 网站的型号数据</p>

  <div class="info-box">
    <p>网站：szlcsc.com（立创商城）</p>
    <p>数据：型号、品牌、封装、类目、编号、价格、库存</p>
  </div>

  <div class="progress-section">
    <div class="label" id="phaseLabel">就绪</div>
    <div class="progress-bar-bg">
      <div class="progress-bar-fill" id="progressBar"></div>
    </div>
    <div class="status" id="statusText">点击「开始抓取」按钮进行操作</div>
  </div>

  <div class="btn-group">
    <button class="btn btn-start" id="btnStart" onclick="startCrawl()">开始抓取</button>
    <button class="btn btn-stop" id="btnStop" onclick="stopCrawl()" disabled>停止</button>
    <button class="btn btn-open" onclick="window.open('https://www.szlcsc.com/catalog.html')">打开网站</button>
    <button class="btn btn-dir" onclick="openDir()">打开保存目录</button>
  </div>

  <div class="log-box" id="logBox"></div>
</div>

<script>
let pollTimer = null;

function startCrawl() {
  fetch('/api/start', {method:'POST'}).then(r=>r.json()).then(d=>{
    if(d.error){ alert(d.error); return; }
    document.getElementById('btnStart').disabled = true;
    document.getElementById('btnStop').disabled = false;
    document.getElementById('logBox').classList.add('show');
    pollTimer = setInterval(pollStatus, 1000);
  });
}

function stopCrawl() {
  fetch('/api/stop', {method:'POST'});
  document.getElementById('btnStop').disabled = true;
}

function openDir() {
  fetch('/api/open-dir', {method:'POST'});
}

function pollStatus() {
  fetch('/api/status').then(r=>r.json()).then(d=>{
    document.getElementById('phaseLabel').textContent = d.phase || '';
    document.getElementById('progressBar').style.width = d.progress + '%';
    document.getElementById('statusText').textContent = d.message || '';

    if(d.log && d.log.length > 0) {
      const box = document.getElementById('logBox');
      box.textContent = d.log;
      box.scrollTop = box.scrollHeight;
    }

    if(d.status === 'done' || d.status === 'error' || d.status === 'stopped') {
      clearInterval(pollTimer);
      document.getElementById('btnStart').disabled = false;
      document.getElementById('btnStop').disabled = true;
      if(d.status === 'done') {
        alert('抓取完成！共 ' + d.total_items + ' 条数据\n\n保存到桌面 szlcsc_data 目录');
      } else if(d.status === 'error') {
        alert('抓取出错：' + d.message);
      } else {
        alert('抓取已停止，部分数据已保存');
      }
    }
  });
}
</script>
</body>
</html>"""


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return HTML_PAGE

    @app.route("/api/status")
    def api_status():
        return jsonify({
            "status": crawl_state["status"],
            "phase": crawl_state["phase"],
            "progress": crawl_state["progress"],
            "total_items": crawl_state["total_items"],
            "message": crawl_state["message"],
            "log": crawl_state.get("log", ""),
        })

    @app.route("/api/start", methods=["POST"])
    def api_start():
        if crawl_state["status"] == "running":
            return jsonify({"error": "正在抓取中，请先停止"})
        crawl_state["status"] = "running"
        crawl_state["phase"] = "正在初始化..."
        crawl_state["progress"] = 0
        crawl_state["total_items"] = 0
        crawl_state["message"] = "正在启动浏览器..."
        crawl_state["log"] = ""

        def run():
            desktop = get_desktop_path()
            output_dir = os.path.join(desktop, "szlcsc_data")
            os.makedirs(output_dir, exist_ok=True)
            log_lines = []

            def log(msg):
                print(msg)
                log_lines.append(msg)
                crawl_state["log"] = "\n".join(log_lines[-50:])

            try:
                log("[*] 正在获取分类列表...")
                crawl_state["phase"] = "正在获取分类列表..."
                crawl_state["message"] = "连接 szlcsc.com ..."

                with SZLCSCCrawler(delay=2.0, pages_per_cat=5, headless=True) as crawler:
                    crawl_state["crawler"] = crawler
                    cats = crawler.fetch_categories()
                    log(f"[+] 获取到 {len(cats)} 个分类")

                    if not cats:
                        crawl_state["status"] = "error"
                        crawl_state["message"] = "无法获取分类列表，请检查网络"
                        return

                    def progress_callback(idx, total, cat_name, page):
                        pct = int(idx / total * 100)
                        crawl_state["progress"] = pct
                        crawl_state["phase"] = f"正在抓取：{cat_name} ({idx}/{total})"
                        crawl_state["message"] = f"第 {page} 页"

                    crawl_state["phase"] = "开始抓取型号数据..."
                    crawl_state["message"] = f"共 {len(cats)} 个分类"

                    result = crawler.crawl(cats, Path(output_dir), progress_callback)

                    if crawler._stop_flag:
                        crawl_state["status"] = "stopped"
                        crawl_state["phase"] = "已停止"
                        crawl_state["message"] = "抓取已停止"
                        log("[*] 用户停止了抓取")
                    else:
                        crawl_state["status"] = "done"
                        crawl_state["progress"] = 100
                        crawl_state["phase"] = "抓取完成"
                        crawl_state["total_items"] = result["total"]
                        crawl_state["message"] = f"共抓取 {result['total']} 条数据"
                        log(f"[OK] 完成！共 {result['total']} 条")

            except Exception as e:
                log(f"[ERROR] {e}")
                crawl_state["status"] = "error"
                crawl_state["phase"] = "抓取失败"
                crawl_state["message"] = str(e)
            finally:
                crawl_state["crawler"] = None

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return jsonify({"ok": True})

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        c = crawl_state.get("crawler")
        if c:
            c.stop()
        crawl_state["message"] = "正在停止..."
        return jsonify({"ok": True})

    @app.route("/api/open-dir", methods=["POST"])
    def api_open_dir():
        desktop = get_desktop_path()
        output_dir = os.path.join(desktop, "szlcsc_data")
        if os.path.exists(output_dir):
            subprocess.Popen(f'explorer "{output_dir}"')
        else:
            return jsonify({"error": f"目录不存在: {output_dir}"})
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    app = create_app()
    url = f"http://localhost:{WEB_PORT}"
    print(f"\n{'='*50}")
    print(f"  立创商城数据抓取工具")
    print(f"  请在浏览器中访问: {url}")
    print(f"  按 Ctrl+C 停止服务")
    print(f"{'='*50}\n")

    # 自动打开浏览器
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=WEB_PORT, debug=False, threaded=True)
