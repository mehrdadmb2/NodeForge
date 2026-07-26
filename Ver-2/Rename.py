#!/usr/bin/env python3
"""
V2Ray / Xray Config Renamer Pro v2.0
تمامی حقوق محفوظ است — نسخه تک‌فایلی

قابلیت‌ها:
- پشتیبانی از تمام پروتکل‌های رایج (VMess, VLESS, Trojan, Shadowsocks, Hysteria, TUIC, و غیره)
- دریافت لینک از فایل، کلیپ‌بورد، Drag & Drop و URL اشتراک
- تغییر نام هوشمند با پیشوند، شماره، تاریخ و پرچم کشور
- کش موقعیت جغرافیایی + درخواست‌های همزمان (Multi-thread)
- حذف کانفیگ‌های تکراری، فیلتر بر اساس پروتکل و جستجوی پیشرفته
- مرتب‌سازی خروجی (بر اساس نام، کشور، پروتکل)
- پیش‌نمایش تغییرات قبل از اعمال نهایی
- نمایش درصد پیشرفت، زمان تقریبی باقی‌مانده و سرعت پردازش
- قابلیت توقف، از سرگیری و لغو عملیات
- ذخیره و بازیابی تنظیمات در config.json
- خروجی به فرمت‌های TXT, CSV, JSON
- رابط کاربری مدرن با ttkbootstrap و پشتیبانی از چند تم
- لاگ‌گیری و مدیریت خطاها
"""

import base64
import json
import re
import threading
import time
import queue
import os
import sys
import csv
import io
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, scrolledtext, StringVar, IntVar, BooleanVar, TclError, simpledialog
from tkinter import ttk as tk_ttk
from urllib.parse import quote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import Style

# کتابخانه‌های اختیاری با پیام راهنما در صورت عدم وجود
try:
    import httpx
except ImportError:
    httpx = None
try:
    import dns.resolver
except ImportError:
    dns = None

# تلاش برای بارگذاری tkinterdnd2 برای قابلیت Drag & Drop
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES   # وارد کردن DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    DND_FILES = None

# ----------------------------------------------------------------------
# تنظیمات اولیه
# ----------------------------------------------------------------------
APP_NAME = "V2Ray Config Renamer Pro"
VERSION = "2.0.1"
CONFIG_FILE = "config.json"
LOG_DIR = "logs"
CACHE_FILE = "geo_cache.json"

# رنگ‌های ثابت
PRIMARY = "#0d6efd"
SUCCESS = "#198754"
DANGER = "#dc3545"
WARNING = "#ffc107"
INFO = "#0dcaf0"

# ----------------------------------------------------------------------
# مدل‌های داده
# ----------------------------------------------------------------------
@dataclass
class ConfigLine:
    """نگهداری اطلاعات یک کانفیگ"""
    original: str
    index: int = 0
    protocol: str = ""
    host: str = ""
    name: str = ""
    renamed: str = ""
    country: str = ""      # کد ISO
    flag: str = ""         # ایموجی پرچم
    status: str = "success"  # success, failed, duplicate
    error_msg: str = ""

# ----------------------------------------------------------------------
# ابزارهای کمکی
# ----------------------------------------------------------------------
def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)

def log_message(message: str):
    """ثبت پیام در فایل لاگ روزانه"""
    ensure_dir(LOG_DIR)
    log_file = Path(LOG_DIR) / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

# ----------------------------------------------------------------------
# مدیریت تنظیمات
# ----------------------------------------------------------------------
class AppSettings:
    """بارگذاری و ذخیره تنظیمات برنامه"""
    DEFAULTS = {
        "prefix": "Node-",
        "start_num": 0,
        "timestamp_enabled": False,
        "timestamp_format": "%Y%m%d_%H%M%S",
        "flag_enabled": False,
        "theme": "darkly",
        "language": "fa",
        "max_threads": 20,
        "remove_duplicates": True,
        "sort_by": "none",   # none, name, country, protocol
        "filter_protocol": ""
    }

    def __init__(self):
        self.data = self.DEFAULTS.copy()
        self.load()

    def load(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                self.data.update(saved)
        except:
            pass

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            log_message(f"Error saving config: {e}")

    def get(self, key):
        return self.data.get(key, self.DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

# ----------------------------------------------------------------------
# کش موقعیت جغرافیایی
# ----------------------------------------------------------------------
class GeoCache:
    """کش برای ذخیره اطلاعات کشور بر اساس هاست"""
    def __init__(self):
        self.cache: Dict[str, Tuple[str, str]] = {}  # host -> (country_code, flag)
        self.load()

    def load(self):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                self.cache = json.load(f)
        except:
            self.cache = {}

    def save(self):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            log_message(f"Error saving geo cache: {e}")

    def get(self, host: str) -> Optional[Tuple[str, str]]:
        return self.cache.get(host)

    def set(self, host: str, country_code: str, flag: str):
        self.cache[host] = (country_code, flag)
        self.save()

# ----------------------------------------------------------------------
# استخراج و تغییر نام لینک‌ها
# ----------------------------------------------------------------------
class ProtocolBase:
    """کلاس پایه برای پروتکل‌ها"""
    def rename(self, link: str, new_name: str) -> Optional[str]:
        raise NotImplementedError

class VMess(ProtocolBase):
    def rename(self, link: str, new_name: str) -> Optional[str]:
        try:
            b64 = link[len("vmess://"):].strip().lstrip("/")
            missing = len(b64) % 4
            if missing:
                b64 += "=" * (4 - missing)
            decoded = base64.b64decode(b64).decode("utf-8")
            config = json.loads(decoded)
            config["ps"] = new_name
            new_json = json.dumps(config, separators=(",", ":"), ensure_ascii=False)
            new_b64 = base64.b64encode(new_json.encode("utf-8")).decode("utf-8")
            return "vmess://" + new_b64
        except Exception as e:
            log_message(f"VMess rename error: {e}")
            return None

class URIProtocol(ProtocolBase):
    """برای vless, trojan, hysteria, tuic, socks, http و غیره"""
    def rename(self, link: str, new_name: str) -> Optional[str]:
        try:
            if "#" in link:
                base = link[:link.index("#")]
            else:
                base = link
            encoded = quote(new_name, safe="")
            return base + "#" + encoded
        except Exception as e:
            log_message(f"URI rename error: {e}")
            return None

class Shadowsocks(ProtocolBase):
    def rename(self, link: str, new_name: str) -> Optional[str]:
        try:
            if "#" in link:
                base = link[:link.index("#")]
                return base + "#" + quote(new_name, safe="")
            else:
                return link + "#" + quote(new_name, safe="")
        except Exception as e:
            log_message(f"SS rename error: {e}")
            return None

def protocol_factory(link: str) -> ProtocolBase:
    low = link.lower()
    if low.startswith("vmess://"):
        return VMess()
    if low.startswith("ss://"):
        return Shadowsocks()
    if any(low.startswith(p) for p in [
        "vless://", "trojan://", "hysteria2://", "hysteria://",
        "tuic://", "socks://", "http://", "https://", "ssh://",
        "wireguard://", "reality://", "grpc://", "quic://"
    ]):
        return URIProtocol()
    return URIProtocol()  # fallback

def extract_host(link: str) -> str:
    """استخراج هاست از لینک (IP یا دامنه)"""
    link = link.strip()
    if link.startswith("vmess://"):
        try:
            b64 = link[len("vmess://"):].strip().lstrip("/")
            missing = len(b64) % 4
            if missing:
                b64 += "=" * (4 - missing)
            decoded = base64.b64decode(b64).decode("utf-8")
            cfg = json.loads(decoded)
            return cfg.get("add", "").strip()
        except:
            return ""
    try:
        if "@" in link:
            rest = link.split("@", 1)[1]
            host = rest.split(":")[0].split("/")[0].split("?")[0].split("#")[0]
            return host
    except:
        pass
    return ""

def get_protocol_type(link: str) -> str:
    low = link.strip().lower()
    if low.startswith("vmess://"): return "VMess"
    if low.startswith("vless://"): return "VLESS"
    if low.startswith("trojan://"): return "Trojan"
    if low.startswith("ss://"): return "Shadowsocks"
    if low.startswith("hysteria2://"): return "Hysteria2"
    if low.startswith("hysteria://"): return "Hysteria"
    if low.startswith("tuic://"): return "TUIC"
    if low.startswith("socks://"): return "SOCKS"
    if low.startswith("http://") or low.startswith("https://"): return "HTTP"
    if low.startswith("ssh://"): return "SSH"
    if low.startswith("wireguard://"): return "WireGuard"
    if low.startswith("reality://"): return "Reality"
    if low.startswith("grpc://"): return "gRPC"
    return "Other"

def country_code_to_flag(code: str) -> str:
    if code and len(code) == 2:
        return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)
    return ""

# ----------------------------------------------------------------------
# دریافت اطلاعات جغرافیایی (همزمان با کش)
# ----------------------------------------------------------------------
class GeoIPResolver:
    """دریافت کد کشور با استفاده از ip-api.com (رایگان) به صورت ThreadPool"""
    def __init__(self, cache: GeoCache, max_workers: int = 20):
        self.cache = cache
        self.max_workers = max_workers
        # در این نسخه نیازی به session نداریم، از requests مستقیم استفاده می‌کنیم

    def _resolve_single(self, host: str) -> Tuple[str, str, str]:
        """برمی‌گرداند (host, country_code, flag)"""
        cached = self.cache.get(host)
        if cached:
            return host, cached[0], cached[1]

        if not host or host in ("127.0.0.1", "::1", "localhost"):
            return host, "", ""

        try:
            import requests as req
            url = f"http://ip-api.com/json/{host}?fields=countryCode"
            resp = req.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                code = data.get("countryCode", "")
                flag = country_code_to_flag(code)
                self.cache.set(host, code, flag)
                return host, code, flag
        except Exception as e:
            log_message(f"GeoIP resolve error for {host}: {e}")

        return host, "", ""

    def resolve_batch(self, hosts: List[str], progress_callback=None) -> Dict[str, Tuple[str, str]]:
        """دریافت موقعیت جغرافیایی برای لیستی از هاست‌ها"""
        results = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_host = {executor.submit(self._resolve_single, h): h for h in hosts}
            for future in as_completed(future_to_host):
                host = future_to_host[future]
                try:
                    h, code, flag = future.result()
                    results[h] = (code, flag)
                    if progress_callback:
                        progress_callback(host)
                except Exception as e:
                    log_message(f"GeoIP future error: {e}")
                    results[host] = ("", "")
        return results

# ----------------------------------------------------------------------
# رابط کاربری گرافیکی
# ----------------------------------------------------------------------
class ProApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("1100x800")
        self.root.minsize(950, 700)

        # تنظیمات
        self.settings = AppSettings()
        self.geo_cache = GeoCache()
        self.geo_resolver = GeoIPResolver(self.geo_cache, max_workers=self.settings.get("max_threads"))

        # استایل
        theme = self.settings.get("theme")
        self.style = Style(theme=theme)

        # متغیرهای کنترلی
        self.prefix_var = StringVar(value=self.settings.get("prefix"))
        self.start_num_var = IntVar(value=self.settings.get("start_num"))
        self.timestamp_enabled = BooleanVar(value=self.settings.get("timestamp_enabled"))
        self.flag_enabled = BooleanVar(value=self.settings.get("flag_enabled"))
        self.remove_dup_var = BooleanVar(value=self.settings.get("remove_duplicates"))
        self.sort_var = StringVar(value=self.settings.get("sort_by"))
        self.filter_var = StringVar(value=self.settings.get("filter_protocol"))
        self.theme_var = StringVar(value=theme)
        self.language_var = StringVar(value=self.settings.get("language"))

        # وضعیت پردازش
        self.processing = False
        self.paused = False
        self.cancel_requested = False
        self.current_task_thread = None
        self.processed_count = 0
        self.total_count = 0
        self.start_time = None

        # آمار
        self.stats = {
            "total": 0, "renamed": 0, "failed": 0,
            "duplicates": 0, "protocols": {}
        }

        # ساخت UI
        self._build_ui()
        self._bind_shortcuts()

    # ------------------------------------------------------------------
    # ساخت ویجت‌ها
    # ------------------------------------------------------------------
    def _build_ui(self):
        # منوی بالا (در حد چند دکمه تنظیمات سریع)
        self._create_menu()

        # نوت‌بوک برای تب‌های اصلی
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # تب اصلی (ورودی/خروجی)
        self.main_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text="📥 ورودی / خروجی")
        self._build_main_tab()

        # تب تنظیمات
        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="⚙️ تنظیمات")
        self._build_settings_tab()

        # تب لاگ
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text="📋 لاگ")
        self._build_log_tab()

        # نوار وضعیت
        self.status_bar = ttk.Label(self.root, text="آماده", relief=SUNKEN, anchor=W)
        self.status_bar.pack(side=BOTTOM, fill=X)

    def _create_menu(self):
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)
        # منوی ساده (اختیاری)

    def _build_main_tab(self):
        main_frame = ttk.Frame(self.main_tab)
        main_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)

        # بخش ورودی
        input_label = ttk.LabelFrame(main_frame, text="📥 لینک‌های ورودی")
        input_label.pack(fill=BOTH, expand=True, pady=5)

        self.input_text = scrolledtext.ScrolledText(
            input_label, height=8, font=("Consolas", 10), wrap=WORD
        )
        self.input_text.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # ---------- رفع خطای Drag & Drop ----------
        if DND_AVAILABLE:
            self.input_text.drop_target_register(DND_FILES)   # ✅ از متغیر واردشده استفاده کن
            self.input_text.dnd_bind('<<Drop>>', self.on_file_drop)
        # -------------------------------------------

        input_btn_frame = ttk.Frame(input_label)
        input_btn_frame.pack(fill=X, padx=5, pady=5)
        ttk.Button(input_btn_frame, text="📂 بارگذاری فایل", command=self.load_file, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(input_btn_frame, text="📋 چسباندن از کلیپ‌بورد", command=self.paste_clipboard, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(input_btn_frame, text="🌐 دریافت از URL اشتراک", command=self.fetch_subscription, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(input_btn_frame, text="🗑️ پاک کردن", command=lambda: self.input_text.delete(1.0, END), bootstyle="secondary-outline").pack(side=LEFT, padx=2)

        # بخش تنظیمات سریع نام‌گذاری
        naming_frame = ttk.LabelFrame(main_frame, text="🏷️ تنظیمات نام")
        naming_frame.pack(fill=X, pady=5)

        row1 = ttk.Frame(naming_frame)
        row1.pack(fill=X, padx=5, pady=2)
        ttk.Label(row1, text="پیشوند:").pack(side=LEFT)
        ttk.Entry(row1, textvariable=self.prefix_var, width=15).pack(side=LEFT, padx=5)
        ttk.Label(row1, text="شروع از:").pack(side=LEFT, padx=(15, 0))
        ttk.Entry(row1, textvariable=self.start_num_var, width=6).pack(side=LEFT, padx=5)

        row2 = ttk.Frame(naming_frame)
        row2.pack(fill=X, padx=5, pady=2)
        ttk.Checkbutton(row2, text="افزودن تاریخ/ساعت", variable=self.timestamp_enabled).pack(side=LEFT)
        self.date_combo = ttk.Combobox(row2, values=[
            "YYYYMMDD_HHMMSS", "YYYY-MM-DD HH:MM:SS", "DD/MM/YYYY HH:MM", "Unix Timestamp"
        ], state="readonly", width=22)
        self.date_combo.set("YYYYMMDD_HHMMSS")
        self.date_combo.pack(side=LEFT, padx=5)
        if not self.timestamp_enabled.get():
            self.date_combo.configure(state=DISABLED)
        self.timestamp_enabled.trace_add("write", self._toggle_timestamp_combo)

        row3 = ttk.Frame(naming_frame)
        row3.pack(fill=X, padx=5, pady=2)
        ttk.Checkbutton(row3, text="افزودن پرچم کشور (ممکن است کند شود)", variable=self.flag_enabled).pack(side=LEFT)

        # دکمه‌های عملیات
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=X, pady=5)
        self.run_btn = ttk.Button(action_frame, text="⚡ شروع پردازش", command=self.start_processing, bootstyle="success")
        self.run_btn.pack(side=LEFT, padx=5)
        self.pause_btn = ttk.Button(action_frame, text="⏸️ مکث", command=self.pause_processing, bootstyle="warning", state=DISABLED)
        self.pause_btn.pack(side=LEFT, padx=5)
        self.cancel_btn = ttk.Button(action_frame, text="⏹️ لغو", command=self.cancel_processing, bootstyle="danger", state=DISABLED)
        self.cancel_btn.pack(side=LEFT, padx=5)

        # نوار پیشرفت
        self.progress = ttk.Progressbar(action_frame, length=300, mode='determinate')
        self.progress.pack(side=LEFT, padx=10)
        self.progress_label = ttk.Label(action_frame, text="0%")
        self.progress_label.pack(side=LEFT)
        self.eta_label = ttk.Label(action_frame, text="")
        self.eta_label.pack(side=LEFT, padx=5)
        self.speed_label = ttk.Label(action_frame, text="")
        self.speed_label.pack(side=LEFT)

        # بخش خروجی
        output_frame = ttk.LabelFrame(main_frame, text="📤 خروجی")
        output_frame.pack(fill=BOTH, expand=True, pady=5)

        self.output_text = scrolledtext.ScrolledText(
            output_frame, height=10, font=("Consolas", 10), wrap=WORD
        )
        self.output_text.pack(fill=BOTH, expand=True, padx=5, pady=5)

        out_btn_frame = ttk.Frame(output_frame)
        out_btn_frame.pack(fill=X, padx=5, pady=5)
        ttk.Button(out_btn_frame, text="💾 ذخیره TXT", command=lambda: self.save_output("txt"), bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(out_btn_frame, text="📊 ذخیره CSV", command=lambda: self.save_output("csv"), bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(out_btn_frame, text="📦 ذخیره JSON", command=lambda: self.save_output("json"), bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(out_btn_frame, text="📋 کپی", command=self.copy_output, bootstyle="secondary-outline").pack(side=LEFT, padx=2)

        # تنظیمات فیلتر/مرتب‌سازی پایین خروجی
        filter_frame = ttk.Frame(output_frame)
        filter_frame.pack(fill=X, padx=5, pady=2)
        ttk.Label(filter_frame, text="فیلتر پروتکل:").pack(side=LEFT)
        ttk.Entry(filter_frame, textvariable=self.filter_var, width=12).pack(side=LEFT, padx=5)
        ttk.Button(filter_frame, text="اعمال فیلتر", command=self.apply_filter, bootstyle="info-outline").pack(side=LEFT, padx=5)
        ttk.Label(filter_frame, text="مرتب‌سازی:").pack(side=LEFT, padx=(20, 5))
        sort_combo = ttk.Combobox(filter_frame, textvariable=self.sort_var,
                                  values=["none", "name", "country", "protocol"], state="readonly", width=12)
        sort_combo.pack(side=LEFT, padx=5)
        ttk.Button(filter_frame, text="مرتب‌سازی", command=self.apply_sort, bootstyle="info-outline").pack(side=LEFT, padx=5)

        # پیش‌نمایش تغییرات (جدول)
        preview_frame = ttk.LabelFrame(main_frame, text="🔍 پیش‌نمایش تغییرات")
        preview_frame.pack(fill=X, pady=5)
        self.preview_tree = ttk.Treeview(preview_frame, columns=("index", "old", "new", "country"), show="headings", height=6)
        self.preview_tree.heading("index", text="شماره")
        self.preview_tree.heading("old", text="نام قبلی")
        self.preview_tree.heading("new", text="نام جدید")
        self.preview_tree.heading("country", text="کشور")
        self.preview_tree.column("index", width=50, anchor=CENTER)
        self.preview_tree.column("old", width=200)
        self.preview_tree.column("new", width=200)
        self.preview_tree.column("country", width=80, anchor=CENTER)
        self.preview_tree.pack(fill=X, padx=5, pady=5)

    def _build_settings_tab(self):
        settings_frame = ttk.Frame(self.settings_tab)
        settings_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        ttk.Label(settings_frame, text="تم برنامه:").grid(row=0, column=0, sticky=W, pady=5)
        themes = ["darkly", "superhero", "cyborg", "vapor", "solar", "cosmo", "flatly", "journal", "litera", "lumen", "minty", "pulse", "sandstone", "united", "yeti", "morph", "simplex", "cerculean"]
        theme_combo = ttk.Combobox(settings_frame, textvariable=self.theme_var, values=themes, state="readonly")
        theme_combo.grid(row=0, column=1, sticky=W, padx=10)
        ttk.Button(settings_frame, text="اعمال", command=self.change_theme, bootstyle="primary-outline").grid(row=0, column=2, padx=5)

        ttk.Label(settings_frame, text="زبان:").grid(row=1, column=0, sticky=W, pady=5)
        lang_combo = ttk.Combobox(settings_frame, textvariable=self.language_var, values=["fa", "en"], state="readonly")
        lang_combo.grid(row=1, column=1, sticky=W, padx=10)
        ttk.Button(settings_frame, text="اعمال", command=self.change_language, bootstyle="primary-outline").grid(row=1, column=2, padx=5)

        ttk.Label(settings_frame, text="تعداد نخ‌های موقعیت‌یابی:").grid(row=2, column=0, sticky=W, pady=5)
        thread_spin = ttk.Spinbox(settings_frame, from_=5, to=100, width=5)
        thread_spin.insert(0, str(self.settings.get("max_threads")))
        thread_spin.grid(row=2, column=1, sticky=W, padx=10)
        def save_threads():
            self.settings.set("max_threads", int(thread_spin.get()))
            self.geo_resolver.max_workers = int(thread_spin.get())
        ttk.Button(settings_frame, text="ذخیره", command=save_threads, bootstyle="primary-outline").grid(row=2, column=2, padx=5)

        ttk.Button(settings_frame, text="💾 ذخیره همه تنظیمات", command=self.save_all_settings, bootstyle="success").grid(row=3, column=1, pady=20)

    def _build_log_tab(self):
        log_frame = ttk.Frame(self.log_tab)
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, font=("Consolas", 9), wrap=WORD)
        self.log_text.pack(fill=BOTH, expand=True)

    # ------------------------------------------------------------------
    # رویدادهای UI
    # ------------------------------------------------------------------
    def _toggle_timestamp_combo(self, *args):
        if self.timestamp_enabled.get():
            self.date_combo.configure(state="readonly")
        else:
            self.date_combo.configure(state=DISABLED)

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self.input_text.delete(1.0, END)
                self.input_text.insert(END, f.read())
            self.update_status(f"فایل {path} بارگذاری شد.")

    def on_file_drop(self, event):
        """فقط در صورت وجود tkinterdnd2 فراخوانی می‌شود."""
        files = self.root.tk.splitlist(event.data)
        if files:
            path = files[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.input_text.delete(1.0, END)
                    self.input_text.insert(END, f.read())
                self.update_status(f"فایل {path} از طریق کشیدن و رها کردن بارگذاری شد.")
            except Exception as e:
                messagebox.showerror("خطا", f"خواندن فایل ممکن نیست:\n{e}")

    def paste_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            if clip:
                self.input_text.delete(1.0, END)
                self.input_text.insert(END, clip)
        except:
            messagebox.showerror("خطا", "کلیپ‌بورد خالی است.")

    def fetch_subscription(self):
        url = simpledialog.askstring("آدرس اشتراک", "لینک Subscribe را وارد کنید:")
        if not url:
            return
        self.update_status("در حال دریافت اشتراک...")
        try:
            import requests as req
            resp = req.get(url, timeout=15)
            if resp.status_code == 200:
                content = resp.text
                try:
                    decoded = base64.b64decode(content).decode("utf-8")
                    if "://" in decoded:
                        content = decoded
                except:
                    pass
                self.input_text.delete(1.0, END)
                self.input_text.insert(END, content)
                self.update_status("اشتراک با موفقیت دریافت شد.")
            else:
                messagebox.showerror("خطا", f"کد وضعیت: {resp.status_code}")
        except Exception as e:
            messagebox.showerror("خطا", f"دریافت ناموفق:\n{e}")

    def update_status(self, text):
        self.status_bar.config(text=text)
        self.log_text.insert(END, f"{text}\n")
        self.log_text.see(END)

    def change_theme(self):
        new_theme = self.theme_var.get()
        self.style.theme_use(new_theme)
        self.settings.set("theme", new_theme)

    def change_language(self):
        messagebox.showinfo("توجه", "تغییر زبان در این نسخه محدود است.")

    def save_all_settings(self):
        self.settings.set("prefix", self.prefix_var.get())
        self.settings.set("start_num", self.start_num_var.get())
        self.settings.set("timestamp_enabled", self.timestamp_enabled.get())
        self.settings.set("flag_enabled", self.flag_enabled.get())
        self.settings.set("remove_duplicates", self.remove_dup_var.get())
        self.settings.set("sort_by", self.sort_var.get())
        self.settings.set("filter_protocol", self.filter_var.get())
        self.settings.set("theme", self.theme_var.get())
        self.settings.set("language", self.language_var.get())
        messagebox.showinfo("ذخیره شد", "تنظیمات با موفقیت ذخیره گردید.")

    # ------------------------------------------------------------------
    # عملیات پردازش
    # ------------------------------------------------------------------
    def start_processing(self):
        if self.processing:
            messagebox.showwarning("هشدار", "پردازش در حال انجام است.")
            return

        raw_text = self.input_text.get(1.0, END).strip()
        if not raw_text:
            messagebox.showwarning("هشدار", "متنی وارد نشده است.")
            return

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not lines:
            return

        self.processing = True
        self.paused = False
        self.cancel_requested = False
        self.processed_count = 0
        self.total_count = len(lines)
        self.start_time = time.time()

        self.run_btn.configure(state=DISABLED)
        self.pause_btn.configure(state=NORMAL)
        self.cancel_btn.configure(state=NORMAL)

        self.output_text.delete(1.0, END)
        for row in self.preview_tree.get_children():
            self.preview_tree.delete(row)

        self.current_task_thread = threading.Thread(target=self._process_lines, args=(lines,), daemon=True)
        self.current_task_thread.start()

    def pause_processing(self):
        if self.processing and not self.paused:
            self.paused = True
            self.pause_btn.configure(text="▶️ ادامه", bootstyle="success")
            self.update_status("پردازش متوقف شد (مکث).")
        elif self.processing and self.paused:
            self.paused = False
            self.pause_btn.configure(text="⏸️ مکث", bootstyle="warning")
            self.update_status("پردازش از سر گرفته شد.")

    def cancel_processing(self):
        if self.processing:
            self.cancel_requested = True
            self.cancel_btn.configure(state=DISABLED)
            self.update_status("در حال لغو پردازش...")

    def _process_lines(self, lines):
        prefix = self.prefix_var.get().strip()
        start = self.start_num_var.get()
        use_timestamp = self.timestamp_enabled.get()
        use_flag = self.flag_enabled.get()
        remove_dup = self.remove_dup_var.get()
        filter_proto = self.filter_var.get().strip().lower()

        fmt_map = {
            "YYYYMMDD_HHMMSS": "%Y%m%d_%H%M%S",
            "YYYY-MM-DD HH:MM:SS": "%Y-%m-%d %H:%M:%S",
            "DD/MM/YYYY HH:MM": "%d/%m/%Y %H:%M",
            "Unix Timestamp": "%s"
        }
        sel_format = self.date_combo.get()
        date_fmt = fmt_map.get(sel_format, "%Y%m%d_%H%M%S")

        configs: List[ConfigLine] = []
        seen_links = set()
        stats = {"total": 0, "renamed": 0, "failed": 0, "duplicates": 0, "protocols": {}}

        # فاز ۱: ساخت اشیاء ConfigLine
        hosts_to_resolve = []
        for idx, link in enumerate(lines):
            if self.cancel_requested:
                break
            proto = get_protocol_type(link)
            if filter_proto and proto.lower() != filter_proto:
                continue

            cfg = ConfigLine(original=link, index=idx, protocol=proto, host=extract_host(link))

            if remove_dup:
                normalized = link.lower()
                if normalized in seen_links:
                    cfg.status = "duplicate"
                    stats["duplicates"] += 1
                    configs.append(cfg)
                    continue
                seen_links.add(normalized)

            stats["total"] += 1
            stats["protocols"][proto] = stats["protocols"].get(proto, 0) + 1
            configs.append(cfg)
            if use_flag and cfg.host:
                hosts_to_resolve.append(cfg.host)

        self.total_count = len(configs)

        # فاز ۲: GeoIP
        if use_flag and hosts_to_resolve:
            self.root.after(0, self.update_status, "دریافت اطلاعات موقعیت جغرافیایی...")
            unique_hosts = list(set(hosts_to_resolve))
            results = self.geo_resolver.resolve_batch(
                unique_hosts,
                progress_callback=lambda h: self.root.after(0, self.update_status, f"موقعیت‌یابی: {h}")
            )
            for cfg in configs:
                if cfg.host and cfg.host in results:
                    code, flag = results[cfg.host]
                    cfg.country = code
                    cfg.flag = flag
        elif use_flag:
            for cfg in configs:
                if cfg.host and not cfg.country:
                    _, code, flag = self.geo_resolver._resolve_single(cfg.host)
                    cfg.country = code
                    cfg.flag = flag

        # فاز ۳: تغییر نام
        processed = 0
        for idx, cfg in enumerate(configs):
            while self.paused and not self.cancel_requested:
                time.sleep(0.2)
            if self.cancel_requested:
                break

            base_name = f"{prefix}{start + idx}" if prefix else str(start + idx)
            if use_timestamp:
                now = datetime.now()
                try:
                    if date_fmt == "%s":
                        base_name += f"_{int(now.timestamp())}"
                    else:
                        base_name += f"_{now.strftime(date_fmt)}"
                except:
                    pass

            if use_flag and cfg.flag:
                new_name = base_name + " " + cfg.flag
            else:
                new_name = base_name

            renamer = protocol_factory(cfg.original)
            renamed_link = renamer.rename(cfg.original, new_name)
            if renamed_link:
                cfg.renamed = renamed_link
                cfg.status = "success"
                stats["renamed"] += 1
            else:
                cfg.renamed = cfg.original + "  ⚠ (خطا)"
                cfg.status = "failed"
                cfg.error_msg = "rename_failed"
                stats["failed"] += 1

            processed += 1
            self.processed_count = processed

            if processed % 10 == 0 or processed == len(configs):
                self.root.after(0, self._update_progress, processed, len(configs))

        self.root.after(0, self._finish_processing, configs, stats)

    def _update_progress(self, done, total):
        if total == 0:
            return
        percent = int((done / total) * 100)
        self.progress['value'] = percent
        self.progress_label.config(text=f"{percent}%")

        elapsed = time.time() - self.start_time if self.start_time else 0
        if done > 0 and elapsed > 0:
            rate = done / elapsed
            remaining = (total - done) / rate if rate > 0 else 0
            eta = str(timedelta(seconds=int(remaining)))
            self.speed_label.config(text=f"سرعت: {rate:.1f} config/s")
            self.eta_label.config(text=f"زمان باقی‌مانده: {eta}")

    def _finish_processing(self, configs, stats):
        self.processing = False
        self.paused = False
        self.run_btn.configure(state=NORMAL)
        self.pause_btn.configure(state=DISABLED, text="⏸️ مکث", bootstyle="warning")
        self.cancel_btn.configure(state=DISABLED)

        sort_by = self.sort_var.get()
        if sort_by == "name":
            configs.sort(key=lambda c: c.renamed or "")
        elif sort_by == "country":
            configs.sort(key=lambda c: c.country or "")
        elif sort_by == "protocol":
            configs.sort(key=lambda c: c.protocol)

        self.output_text.delete(1.0, END)
        self.preview_tree.delete(*self.preview_tree.get_children())

        for i, cfg in enumerate(configs):
            if cfg.status == "duplicate":
                display = cfg.original + "  ⚠ (تکراری)"
            else:
                display = cfg.renamed if cfg.status == "success" else cfg.original + "  ⚠ (خطا)"
            self.output_text.insert(END, display + "\n")

            old_name = self._get_old_name(cfg.original)
            new_name = cfg.name if cfg.name else "—"
            self.preview_tree.insert("", END, values=(i+1, old_name, new_name, cfg.flag if cfg.flag else "—"))

        msg = f"کل: {stats['total']} | موفق: {stats['renamed']} | ناموفق: {stats['failed']} | تکراری: {stats['duplicates']}"
        self.update_status(msg)
        messagebox.showinfo("پایان پردازش", msg)

    def _get_old_name(self, link: str) -> str:
        if "#" in link:
            try:
                return link.split("#")[-1]
            except:
                pass
        if link.startswith("vmess://"):
            try:
                b64 = link[8:].split("//")[-1]
                b64 += "=" * ((4 - len(b64)%4)%4)
                decoded = base64.b64decode(b64).decode("utf-8")
                config = json.loads(decoded)
                return config.get("ps", "—")
            except:
                pass
        return "—"

    def apply_filter(self):
        if self.processing:
            messagebox.showwarning("هشدار", "ابتدا عملیات فعلی تمام شود.")
            return
        self.settings.set("filter_protocol", self.filter_var.get())
        self.start_processing()

    def apply_sort(self):
        raw = self.output_text.get(1.0, END).strip()
        if not raw:
            return
        lines = raw.splitlines()
        sort_by = self.sort_var.get()
        if sort_by == "name":
            lines.sort()
        elif sort_by == "protocol":
            lines.sort(key=lambda l: get_protocol_type(l))
        self.output_text.delete(1.0, END)
        self.output_text.insert(END, "\n".join(lines))

    # ------------------------------------------------------------------
    # خروجی و ذخیره
    # ------------------------------------------------------------------
    def save_output(self, fmt):
        content = self.output_text.get(1.0, END).strip()
        if not content:
            messagebox.showwarning("هشدار", "خروجی خالی است.")
            return

        ext_map = {"txt": ".txt", "csv": ".csv", "json": ".json"}
        ftype_map = {"txt": ("Text files", "*.txt"), "csv": ("CSV files", "*.csv"), "json": ("JSON files", "*.json")}
        path = filedialog.asksaveasfilename(defaultextension=ext_map[fmt], filetypes=[ftype_map[fmt]])
        if not path:
            return

        try:
            if fmt == "txt":
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
            elif fmt == "csv":
                lines = content.splitlines()
                with open(path, "w", newline='', encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["index", "link"])
                    for i, line in enumerate(lines):
                        writer.writerow([i+1, line])
            elif fmt == "json":
                lines = content.splitlines()
                data = [{"index": i+1, "link": line} for i, line in enumerate(lines)]
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("ذخیره شد", f"فایل در {path} ذخیره گردید.")
        except Exception as e:
            messagebox.showerror("خطا", f"ذخیره ناموفق:\n{e}")

    def copy_output(self):
        content = self.output_text.get(1.0, END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("کپی شد", "خروجی در کلیپ‌بورد کپی شد.")
        else:
            messagebox.showwarning("هشدار", "خروجی خالی است.")

    def _bind_shortcuts(self):
        self.root.bind("<Control-s>", lambda e: self.save_all_settings())
        self.root.bind("<Control-o>", lambda e: self.load_file())
        self.root.bind("<Control-v>", lambda e: self.paste_clipboard())
        self.root.bind("<Control-z>", lambda e: self._undo())

    def _undo(self):
        try:
            self.input_text.edit_undo()
        except:
            pass

# ----------------------------------------------------------------------
# اجرای برنامه
# ----------------------------------------------------------------------
if __name__ == "__main__":
    ensure_dir(LOG_DIR)

    # انتخاب نوع ریشه بر اساس وجود tkinterdnd2
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()          # پشتیبانی از Drag & Drop
    else:
        root = tk.Tk()                  # حالت عادی

    # تنظیمات اولیه پنجره
    root.title(f"{APP_NAME} v{VERSION}")
    root.geometry("1100x800")
    root.minsize(950, 700)

    # اعمال تم ttkbootstrap بدون استفاده از Window(master=...)
    # کافی است یک Style با تم دلخواه بسازیم
    _ = Style(theme="darkly")           # ← تم روی همه ویجت‌ها اعمال می‌شود

    app = ProApp(root)                  # ارسال root به برنامه
    root.mainloop()
