#!/usr/bin/env python3
"""
V2Ray / Xray Config Renamer Pro v4.0
Fully modernized, with GitHub URL auto-detection, upload modes, country-to-flag conversion,
and enhanced paste support in GitHub tab.
"""

import base64
import json
import re
import threading
import time
import csv
import os
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, scrolledtext, StringVar, IntVar, BooleanVar, simpledialog
from tkinter import ttk as tk_ttk
from urllib.parse import quote, unquote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import Style

# Optional imports
try:
    import httpx
except ImportError:
    httpx = None
try:
    import dns.resolver
except ImportError:
    dns = None

# Try to import tkinterdnd2 for drag & drop
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    DND_FILES = None

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
APP_NAME = "V2Ray Config Renamer Pro"
VERSION = "4.0.1"
CONFIG_FILE = "config.json"
LOG_DIR = "logs"
CACHE_FILE = "geo_cache.json"

# Default theme (modern)
DEFAULT_THEME = "cyborg"

# Colors
PRIMARY = "#0d6efd"
SUCCESS = "#198754"
DANGER = "#dc3545"
WARNING = "#ffc107"
INFO = "#0dcaf0"

# ----------------------------------------------------------------------
# Data Models
# ----------------------------------------------------------------------
@dataclass
class ConfigLine:
    """Holds information about a single configuration line."""
    original: str
    index: int = 0
    protocol: str = ""
    host: str = ""
    old_name: str = ""
    new_name: str = ""
    country: str = ""      # ISO code
    flag: str = ""         # emoji flag
    status: str = "success"  # success, failed, duplicate
    error_msg: str = ""

# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------
def ensure_dir(path: str):
    Path(path).mkdir(parents=True, exist_ok=True)

def log_message(message: str):
    """Log message to daily log file."""
    ensure_dir(LOG_DIR)
    log_file = Path(LOG_DIR) / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

# ----------------------------------------------------------------------
# Settings Management
# ----------------------------------------------------------------------
class AppSettings:
    DEFAULTS = {
        "prefix": "Node-",
        "start_num": 0,
        "timestamp_enabled": False,
        "timestamp_format": "%Y%m%d_%H%M%S",
        "flag_enabled": False,
        "preserve_country": False,
        "country_position": "prefix",  # "prefix" or "suffix"
        "theme": DEFAULT_THEME,
        "language": "en",
        "max_threads": 20,
        "remove_duplicates": True,
        "sort_by": "none",
        "filter_protocol": "",
        "github_token": "",
        "github_repo": "mehrdadmb2/V2ray_Sub",
        "github_path": "Mix.txt",
        "github_branch": "main",
        "upload_mode": "replace"  # "replace", "prepend", "append"
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
# Geo Cache
# ----------------------------------------------------------------------
class GeoCache:
    def __init__(self):
        self.cache: Dict[str, Tuple[str, str]] = {}
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
# Protocol Handling
# ----------------------------------------------------------------------
class ProtocolBase:
    def rename(self, link: str, new_name: str) -> Optional[str]:
        raise NotImplementedError

class VMess(ProtocolBase):
    def rename(self, link, new_name):
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
    def rename(self, link, new_name):
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
    def rename(self, link, new_name):
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
    return URIProtocol()

def extract_host(link: str) -> str:
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
# Country name and code to ISO code mapping (for conversion to flag)
# ----------------------------------------------------------------------
COUNTRY_NAME_TO_CODE = {
    "united states": "US", "usa": "US", "us": "US",
    "germany": "DE", "netherlands": "NL", "france": "FR",
    "united kingdom": "GB", "uk": "GB", "canada": "CA",
    "japan": "JP", "singapore": "SG", "sweden": "SE",
    "switzerland": "CH", "finland": "FI", "norway": "NO",
    "denmark": "DK", "italy": "IT", "spain": "ES",
    "australia": "AU", "new zealand": "NZ", "brazil": "BR",
    "india": "IN", "russia": "RU", "china": "CN",
    "turkey": "TR", "iran": "IR", "uae": "AE",
    "saudi arabia": "SA", "israel": "IL", "south korea": "KR",
    "hong kong": "HK", "taiwan": "TW", "indonesia": "ID",
    "malaysia": "MY", "thailand": "TH", "vietnam": "VN",
    "poland": "PL", "austria": "AT", "belgium": "BE",
    "czech republic": "CZ", "ireland": "IE", "portugal": "PT",
    "greece": "GR", "romania": "RO", "bulgaria": "BG",
    "hungary": "HU", "slovakia": "SK", "slovenia": "SI",
    "croatia": "HR", "serbia": "RS", "ukraine": "UA",
    "latvia": "LV", "lithuania": "LT", "estonia": "EE",
    "luxembourg": "LU", "iceland": "IS", "cyprus": "CY",
    "malta": "MT", "moldova": "MD", "georgia": "GE",
    "armenia": "AM", "azerbaijan": "AZ", "kazakhstan": "KZ",
    "uzbekistan": "UZ", "kyrgyzstan": "KG", "turkmenistan": "TM",
    "tajikistan": "TJ", "afghanistan": "AF", "pakistan": "PK",
    "bangladesh": "BD", "sri lanka": "LK", "nepal": "NP",
    "bhutan": "BT", "maldives": "MV", "myanmar": "MM",
    "laos": "LA", "cambodia": "KH", "brunei": "BN",
    "philippines": "PH", "mongolia": "MN", "north korea": "KP",
    "egypt": "EG", "libya": "LY", "tunisia": "TN",
    "algeria": "DZ", "morocco": "MA", "sudan": "SD",
    "south sudan": "SS", "ethiopia": "ET", "somalia": "SO",
    "kenya": "KE", "uganda": "UG", "rwanda": "RW",
    "burundi": "BI", "tanzania": "TZ", "mozambique": "MZ",
    "zambia": "ZM", "zimbabwe": "ZW", "botswana": "BW",
    "namibia": "NA", "south africa": "ZA", "nigeria": "NG",
    "ghana": "GH", "ivory coast": "CI", "senegal": "SN",
    "mali": "ML", "burkina faso": "BF", "niger": "NE",
    "chad": "TD", "cameroon": "CM", "gabon": "GA",
    "congo": "CG", "dr congo": "CD", "angola": "AO",
    "madagascar": "MG", "mauritius": "MU", "seychelles": "SC",
    "cape verde": "CV", "sao tome": "ST", "equatorial guinea": "GQ",
    "central african republic": "CF", "benin": "BJ", "togo": "TG",
    "liberia": "LR", "sierra leone": "SL", "guinea": "GN",
    "guinea-bissau": "GW", "gambia": "GM", "mauritania": "MR",
    "western sahara": "EH", "eritrea": "ER", "djibouti": "DJ",
    "comoros": "KM", "lesotho": "LS", "eswatini": "SZ", "malawi": "MW"
}

# Two-letter ISO code mapping for direct code detection (e.g., "US", "NL", "HK")
COUNTRY_CODE_MAP = {
    "US": "US", "GB": "GB", "UK": "GB", "DE": "DE", "NL": "NL", "FR": "FR",
    "CA": "CA", "JP": "JP", "SG": "SG", "SE": "SE", "CH": "CH", "FI": "FI",
    "NO": "NO", "DK": "DK", "IT": "IT", "ES": "ES", "AU": "AU", "NZ": "NZ",
    "BR": "BR", "IN": "IN", "RU": "RU", "CN": "CN", "TR": "TR", "IR": "IR",
    "AE": "AE", "SA": "SA", "IL": "IL", "KR": "KR", "HK": "HK", "TW": "TW",
    "ID": "ID", "MY": "MY", "TH": "TH", "VN": "VN", "PL": "PL", "AT": "AT",
    "BE": "BE", "CZ": "CZ", "IE": "IE", "PT": "PT", "GR": "GR", "RO": "RO",
    "BG": "BG", "HU": "HU", "SK": "SK", "SI": "SI", "HR": "HR", "RS": "RS",
    "UA": "UA", "LV": "LV", "LT": "LT", "EE": "EE", "LU": "LU", "IS": "IS",
    "CY": "CY", "MT": "MT", "MD": "MD", "GE": "GE", "AM": "AM", "AZ": "AZ",
    "KZ": "KZ", "UZ": "UZ", "KG": "KG", "TM": "TM", "TJ": "TJ", "AF": "AF",
    "PK": "PK", "BD": "BD", "LK": "LK", "NP": "NP", "BT": "BT", "MV": "MV",
    "MM": "MM", "LA": "LA", "KH": "KH", "BN": "BN", "PH": "PH", "MN": "MN",
    "KP": "KP", "EG": "EG", "LY": "LY", "TN": "TN", "DZ": "DZ", "MA": "MA",
    "SD": "SD", "SS": "SS", "ET": "ET", "SO": "SO", "KE": "KE", "UG": "UG",
    "RW": "RW", "BI": "BI", "TZ": "TZ", "MZ": "MZ", "ZM": "ZM", "ZW": "ZW",
    "BW": "BW", "NA": "NA", "ZA": "ZA", "NG": "NG", "GH": "GH", "CI": "CI",
    "SN": "SN", "ML": "ML", "BF": "BF", "NE": "NE", "TD": "TD", "CM": "CM",
    "GA": "GA", "CG": "CG", "CD": "CD", "AO": "AO", "MG": "MG", "MU": "MU",
    "SC": "SC", "CV": "CV", "ST": "ST", "GQ": "GQ", "CF": "CF", "BJ": "BJ",
    "TG": "TG", "LR": "LR", "SL": "SL", "GN": "GN", "GW": "GW", "GM": "GM",
    "MR": "MR", "EH": "EH", "ER": "ER", "DJ": "DJ", "KM": "KM", "LS": "LS",
    "SZ": "SZ", "MW": "MW"
}

def extract_country_flag_from_name(name: str) -> str:
    """
    Extract a flag emoji from the name.
    If a flag emoji already exists, return it.
    If a country name or two-letter code is found, convert to flag emoji.
    Returns empty string if none.
    """
    if not name:
        return ""
    # Look for flag emoji first
    flag_match = re.search(r'[\U0001F1E6-\U0001F1FF]{2}', name)
    if flag_match:
        return flag_match.group(0)

    # Look for country name (case-insensitive)
    name_lower = name.lower()
    for country, code in COUNTRY_NAME_TO_CODE.items():
        if country in name_lower:
            # Avoid false positives (e.g., "us" in "status")
            if re.search(r'\b' + re.escape(country) + r'\b', name_lower):
                return country_code_to_flag(code)

    # Look for two-letter ISO code (e.g., US, NL, HK)
    # We search as whole word, case-insensitive
    for code, iso in COUNTRY_CODE_MAP.items():
        # Use regex to match code as a standalone word
        if re.search(r'\b' + re.escape(code) + r'\b', name, re.IGNORECASE):
            return country_code_to_flag(iso)

    return ""

# ----------------------------------------------------------------------
# GeoIP Resolver
# ----------------------------------------------------------------------
class GeoIPResolver:
    def __init__(self, cache: GeoCache, max_workers: int = 20):
        self.cache = cache
        self.max_workers = max_workers

    def _resolve_single(self, host: str) -> Tuple[str, str, str]:
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

    def resolve_batch(self, hosts, progress_callback=None):
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
# GitHub Uploader (supports get file content and upload modes)
# ----------------------------------------------------------------------
class GitHubUploader:
    def __init__(self, token: str):
        self.token = token

    def _headers(self):
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def test_connection(self, repo: str, path: str, branch: str = "main") -> Tuple[bool, str]:
        try:
            import requests
            api_url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
            resp = requests.get(api_url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                return True, "Connection successful. File exists."
            elif resp.status_code == 404:
                return True, "Connection successful. File does not exist yet."
            else:
                return False, f"GitHub API error: {resp.status_code} - {resp.text}"
        except Exception as e:
            return False, f"Connection error: {e}"

    def get_file_content(self, repo: str, path: str, branch: str = "main") -> Tuple[bool, str, str]:
        """
        Fetch the raw content of a file.
        Returns (success, content, error_message)
        """
        try:
            import requests
            api_url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
            resp = requests.get(api_url, headers=self._headers(), timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("encoding") == "base64":
                    content = base64.b64decode(data["content"]).decode("utf-8")
                    return True, content, ""
                else:
                    return False, "", "Unsupported encoding."
            elif resp.status_code == 404:
                return True, "", ""  # File doesn't exist, return empty content
            else:
                return False, "", f"GitHub API error: {resp.status_code} - {resp.text}"
        except Exception as e:
            return False, "", f"Failed to fetch file: {e}"

    def upload(self, repo: str, path: str, content: str, branch: str = "main",
               mode: str = "replace", commit_msg: str = "Update configs") -> Tuple[bool, str]:
        """
        Upload content to GitHub repository.
        mode: "replace" (overwrite), "prepend" (new content at beginning), "append" (new content at end).
        """
        try:
            import requests
            api_url = f"https://api.github.com/repos/{repo}/contents/{path}"

            # Get current file SHA and content if needed
            sha = None
            current_content = ""
            try:
                resp = requests.get(api_url, headers=self._headers(), timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    sha = data.get("sha")
                    if data.get("encoding") == "base64":
                        current_content = base64.b64decode(data["content"]).decode("utf-8")
                elif resp.status_code == 404:
                    pass  # File doesn't exist
                else:
                    return False, f"GitHub API error: {resp.status_code} - {resp.text}"
            except Exception as e:
                return False, f"Failed to check file: {e}"

            # Prepare final content based on mode
            if mode == "replace":
                final_content = content
            elif mode == "prepend":
                final_content = content + "\n" + current_content if current_content else content
            elif mode == "append":
                final_content = current_content + "\n" + content if current_content else content
            else:
                return False, "Invalid upload mode."

            import base64 as b64
            content_bytes = final_content.encode("utf-8")
            b64_content = b64.b64encode(content_bytes).decode("utf-8")
            payload = {
                "message": commit_msg,
                "content": b64_content,
                "branch": branch
            }
            if sha:
                payload["sha"] = sha

            resp = requests.put(api_url, headers=self._headers(), json=payload, timeout=15)
            if resp.status_code in (200, 201):
                return True, "File uploaded successfully!"
            else:
                return False, f"Upload failed: {resp.status_code} - {resp.text}"
        except Exception as e:
            return False, f"Upload error: {e}"

# ----------------------------------------------------------------------
# Main Application
# ----------------------------------------------------------------------
class ProApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("1200x850")
        self.root.minsize(1000, 700)

        # Settings
        self.settings = AppSettings()
        self.geo_cache = GeoCache()
        self.geo_resolver = GeoIPResolver(self.geo_cache, max_workers=self.settings.get("max_threads"))

        # Style
        theme = self.settings.get("theme")
        self.style = Style(theme=theme)

        # Variables
        self.prefix_var = StringVar(value=self.settings.get("prefix"))
        self.start_num_var = IntVar(value=self.settings.get("start_num"))
        self.timestamp_enabled = BooleanVar(value=self.settings.get("timestamp_enabled"))
        self.flag_enabled = BooleanVar(value=self.settings.get("flag_enabled"))
        self.preserve_country = BooleanVar(value=self.settings.get("preserve_country"))
        self.country_position = StringVar(value=self.settings.get("country_position"))
        self.remove_dup_var = BooleanVar(value=self.settings.get("remove_duplicates"))
        self.sort_var = StringVar(value=self.settings.get("sort_by"))
        self.filter_var = StringVar(value=self.settings.get("filter_protocol"))
        self.theme_var = StringVar(value=theme)
        self.language_var = StringVar(value=self.settings.get("language"))
        self.github_token_var = StringVar(value=self.settings.get("github_token"))
        self.github_repo_var = StringVar(value=self.settings.get("github_repo"))
        self.github_path_var = StringVar(value=self.settings.get("github_path"))
        self.github_branch_var = StringVar(value=self.settings.get("github_branch"))
        self.github_url_var = StringVar()
        self.upload_mode_var = StringVar(value=self.settings.get("upload_mode"))

        # Processing state
        self.processing = False
        self.paused = False
        self.cancel_requested = False
        self.current_task_thread = None
        self.processed_count = 0
        self.total_count = 0
        self.start_time = None

        self.stats = {"total": 0, "renamed": 0, "failed": 0, "duplicates": 0, "protocols": {}, "countries": {}}

        # Build UI
        self._build_ui()
        self._bind_shortcuts()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        self._create_menu()

        # Main container using grid for responsive layout
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Tabs
        self.main_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.main_tab, text="📥 Input / Output")
        self._build_main_tab()

        self.settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab, text="⚙️ Settings")
        self._build_settings_tab()

        self.github_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.github_tab, text="🚀 GitHub")
        self._build_github_tab()

        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text="📋 Log")
        self._build_log_tab()

        # Status bar
        self.status_bar = ttk.Label(self.root, text="Ready", relief=SUNKEN, anchor=W)
        self.status_bar.grid(row=1, column=0, sticky="ew")

    def _create_menu(self):
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)

    def _build_main_tab(self):
        # Configure grid weights for responsiveness
        self.main_tab.grid_rowconfigure(0, weight=1)
        self.main_tab.grid_rowconfigure(1, weight=0)
        self.main_tab.grid_rowconfigure(2, weight=0)
        self.main_tab.grid_rowconfigure(3, weight=1)
        self.main_tab.grid_rowconfigure(4, weight=0)
        self.main_tab.grid_columnconfigure(0, weight=1)

        # Input Section
        input_frame = ttk.LabelFrame(self.main_tab, text="Input Links")
        input_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        input_frame.grid_rowconfigure(0, weight=1)
        input_frame.grid_columnconfigure(0, weight=1)

        self.input_text = scrolledtext.ScrolledText(
            input_frame, height=8, font=("Consolas", 10), wrap=WORD,
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white"
        )
        self.input_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        if DND_AVAILABLE:
            self.input_text.drop_target_register(DND_FILES)
            self.input_text.dnd_bind('<<Drop>>', self.on_file_drop)

        input_btn_frame = ttk.Frame(input_frame)
        input_btn_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(input_btn_frame, text="📂 Load File", command=self.load_file, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(input_btn_frame, text="📋 Paste from Clipboard", command=self.paste_clipboard, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(input_btn_frame, text="🌐 Fetch Subscription URL", command=self.fetch_subscription, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(input_btn_frame, text="🗑️ Clear", command=lambda: self.input_text.delete(1.0, END), bootstyle="secondary-outline").pack(side=LEFT, padx=2)

        # Naming Settings
        naming_frame = ttk.LabelFrame(self.main_tab, text="Naming Settings")
        naming_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        row1 = ttk.Frame(naming_frame)
        row1.pack(fill=X, padx=5, pady=2)
        ttk.Label(row1, text="Prefix:").pack(side=LEFT)
        ttk.Entry(row1, textvariable=self.prefix_var, width=15).pack(side=LEFT, padx=5)
        ttk.Label(row1, text="Start Number:").pack(side=LEFT, padx=(15, 0))
        ttk.Entry(row1, textvariable=self.start_num_var, width=6).pack(side=LEFT, padx=5)

        row2 = ttk.Frame(naming_frame)
        row2.pack(fill=X, padx=5, pady=2)
        ttk.Checkbutton(row2, text="Add Date/Time", variable=self.timestamp_enabled, bootstyle="round-toggle").pack(side=LEFT)
        self.date_combo = ttk.Combobox(row2, values=[
            "YYYYMMDD_HHMMSS", "YYYY-MM-DD HH:MM:SS", "DD/MM/YYYY HH:MM", "Unix Timestamp"
        ], state="readonly", width=22)
        self.date_combo.set("YYYYMMDD_HHMMSS")
        self.date_combo.pack(side=LEFT, padx=5)
        self.timestamp_enabled.trace_add("write", self._toggle_timestamp_combo)
        if not self.timestamp_enabled.get():
            self.date_combo.configure(state=DISABLED)

        row3 = ttk.Frame(naming_frame)
        row3.pack(fill=X, padx=5, pady=2)
        ttk.Checkbutton(row3, text="Add Country Flag (GeoIP)", variable=self.flag_enabled, bootstyle="round-toggle").pack(side=LEFT)

        row4 = ttk.Frame(naming_frame)
        row4.pack(fill=X, padx=5, pady=2)
        ttk.Checkbutton(row4, text="Preserve Original Country/Flag", variable=self.preserve_country, bootstyle="round-toggle").pack(side=LEFT)
        ttk.Radiobutton(row4, text="At Beginning", variable=self.country_position, value="prefix", bootstyle="toolbutton").pack(side=LEFT, padx=10)
        ttk.Radiobutton(row4, text="At End", variable=self.country_position, value="suffix", bootstyle="toolbutton").pack(side=LEFT, padx=5)

        # Action Buttons + Progress
        action_frame = ttk.Frame(self.main_tab)
        action_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self.run_btn = ttk.Button(action_frame, text="⚡ Start Processing", command=self.start_processing, bootstyle="success")
        self.run_btn.pack(side=LEFT, padx=5)
        self.pause_btn = ttk.Button(action_frame, text="⏸️ Pause", command=self.pause_processing, bootstyle="warning", state=DISABLED)
        self.pause_btn.pack(side=LEFT, padx=5)
        self.cancel_btn = ttk.Button(action_frame, text="⏹️ Cancel", command=self.cancel_processing, bootstyle="danger", state=DISABLED)
        self.cancel_btn.pack(side=LEFT, padx=5)

        self.progress = ttk.Progressbar(action_frame, length=300, mode='determinate')
        self.progress.pack(side=LEFT, padx=10, fill=X, expand=True)
        self.progress_label = ttk.Label(action_frame, text="0%")
        self.progress_label.pack(side=LEFT)
        self.eta_label = ttk.Label(action_frame, text="")
        self.eta_label.pack(side=LEFT, padx=5)
        self.speed_label = ttk.Label(action_frame, text="")
        self.speed_label.pack(side=LEFT)

        # Output Section
        output_frame = ttk.LabelFrame(self.main_tab, text="Output")
        output_frame.grid(row=3, column=0, sticky="nsew", padx=5, pady=5)
        output_frame.grid_rowconfigure(0, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)

        self.output_text = scrolledtext.ScrolledText(
            output_frame, height=10, font=("Consolas", 10), wrap=WORD,
            bg="#1e1e1e", fg="#d4d4d4", insertbackground="white"
        )
        self.output_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        out_btn_frame = ttk.Frame(output_frame)
        out_btn_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        ttk.Button(out_btn_frame, text="💾 Save TXT", command=lambda: self.save_output("txt"), bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(out_btn_frame, text="📊 Save CSV", command=lambda: self.save_output("csv"), bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(out_btn_frame, text="📦 Save JSON", command=lambda: self.save_output("json"), bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(out_btn_frame, text="📋 Copy", command=self.copy_output, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        self.github_upload_btn = ttk.Button(out_btn_frame, text="🚀 Upload to GitHub", command=self.upload_to_github, bootstyle="info-outline")
        self.github_upload_btn.pack(side=LEFT, padx=2)

        # Filter/sort frame
        filter_frame = ttk.Frame(output_frame)
        filter_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(filter_frame, text="Filter Protocol:").pack(side=LEFT)
        ttk.Entry(filter_frame, textvariable=self.filter_var, width=12).pack(side=LEFT, padx=5)
        ttk.Button(filter_frame, text="Apply Filter", command=self.apply_filter, bootstyle="info-outline").pack(side=LEFT, padx=5)
        ttk.Label(filter_frame, text="Sort By:").pack(side=LEFT, padx=(20, 5))
        sort_combo = ttk.Combobox(filter_frame, textvariable=self.sort_var,
                                  values=["none", "name", "country", "protocol"], state="readonly", width=12)
        sort_combo.pack(side=LEFT, padx=5)
        ttk.Button(filter_frame, text="Sort", command=self.apply_sort, bootstyle="info-outline").pack(side=LEFT, padx=5)

        # Preview + Stats frame
        preview_frame = ttk.LabelFrame(self.main_tab, text="Preview & Statistics")
        preview_frame.grid(row=4, column=0, sticky="ew", padx=5, pady=5)

        # Preview Tree
        self.preview_tree = ttk.Treeview(preview_frame, columns=("index", "old", "new", "country"), show="headings", height=5, bootstyle="primary")
        self.preview_tree.heading("index", text="#")
        self.preview_tree.heading("old", text="Old Name")
        self.preview_tree.heading("new", text="New Name")
        self.preview_tree.heading("country", text="Country")
        self.preview_tree.column("index", width=50, anchor=CENTER)
        self.preview_tree.column("old", width=250)
        self.preview_tree.column("new", width=250)
        self.preview_tree.column("country", width=100, anchor=CENTER)
        self.preview_tree.pack(fill=X, padx=5, pady=5)

        # Statistics labels
        self.stats_frame = ttk.Frame(preview_frame)
        self.stats_frame.pack(fill=X, padx=5, pady=5)
        self.stats_summary_label = ttk.Label(self.stats_frame, text="", justify=LEFT)
        self.stats_summary_label.pack(anchor=W)

    def _build_settings_tab(self):
        canvas = tk.Canvas(self.settings_tab, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.settings_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        scrollable_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(scrollable_frame, text="Theme:").grid(row=0, column=0, sticky=W, padx=10, pady=5)
        themes = ["darkly", "superhero", "cyborg", "vapor", "solar", "cosmo", "flatly", "journal", "litera", "lumen", "minty", "pulse", "sandstone", "united", "yeti", "morph", "simplex", "cerculean"]
        theme_combo = ttk.Combobox(scrollable_frame, textvariable=self.theme_var, values=themes, state="readonly")
        theme_combo.grid(row=0, column=1, sticky=EW, padx=10)
        ttk.Button(scrollable_frame, text="Apply", command=self.change_theme, bootstyle="primary-outline").grid(row=0, column=2, padx=5)

        ttk.Label(scrollable_frame, text="Language:").grid(row=1, column=0, sticky=W, padx=10, pady=5)
        lang_combo = ttk.Combobox(scrollable_frame, textvariable=self.language_var, values=["en", "fa"], state="readonly")
        lang_combo.grid(row=1, column=1, sticky=EW, padx=10)
        ttk.Button(scrollable_frame, text="Apply", command=self.change_language, bootstyle="primary-outline").grid(row=1, column=2, padx=5)

        ttk.Label(scrollable_frame, text="GeoIP Threads:").grid(row=2, column=0, sticky=W, padx=10, pady=5)
        thread_spin = ttk.Spinbox(scrollable_frame, from_=5, to=100, width=5)
        thread_spin.insert(0, str(self.settings.get("max_threads")))
        thread_spin.grid(row=2, column=1, sticky=EW, padx=10)
        def save_threads():
            self.settings.set("max_threads", int(thread_spin.get()))
            self.geo_resolver.max_workers = int(thread_spin.get())
        ttk.Button(scrollable_frame, text="Save", command=save_threads, bootstyle="primary-outline").grid(row=2, column=2, padx=5)

        ttk.Button(scrollable_frame, text="💾 Save All Settings", command=self.save_all_settings, bootstyle="success").grid(row=3, column=1, pady=20)

    def _build_github_tab(self):
        canvas = tk.Canvas(self.github_tab, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.github_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        scrollable_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(scrollable_frame, text="GitHub Upload Configuration", font=("Helvetica", 14, "bold")).grid(row=0, column=0, columnspan=3, pady=10)

        url_frame = ttk.LabelFrame(scrollable_frame, text="Auto-detect from URL")
        url_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        url_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(url_frame, text="GitHub URL:").grid(row=0, column=0, padx=5, pady=5)
        self.github_url_entry = ttk.Entry(url_frame, textvariable=self.github_url_var, width=50)
        self.github_url_entry.grid(row=0, column=1, padx=5, pady=5, sticky=EW)
        self._add_paste_support(self.github_url_entry)
        ttk.Button(url_frame, text="🔍 Detect", command=self.detect_github_url, bootstyle="primary-outline").grid(row=0, column=2, padx=5)

        ttk.Label(scrollable_frame, text="GitHub Token:").grid(row=2, column=0, sticky=W, padx=10, pady=5)
        self.token_entry = ttk.Entry(scrollable_frame, textvariable=self.github_token_var, width=50, show="*")
        self.token_entry.grid(row=2, column=1, sticky=EW, padx=10)
        self._add_paste_support(self.token_entry)

        self.show_token = False
        self.toggle_token_btn = ttk.Button(scrollable_frame, text="Show", command=self.toggle_token_visibility, bootstyle="secondary-outline")
        self.toggle_token_btn.grid(row=2, column=2, padx=5)

        ttk.Label(scrollable_frame, text="Repository (owner/repo):").grid(row=3, column=0, sticky=W, padx=10, pady=5)
        repo_entry = ttk.Entry(scrollable_frame, textvariable=self.github_repo_var, width=50)
        repo_entry.grid(row=3, column=1, sticky=EW, padx=10)
        self._add_paste_support(repo_entry)

        ttk.Label(scrollable_frame, text="File Path:").grid(row=4, column=0, sticky=W, padx=10, pady=5)
        path_entry = ttk.Entry(scrollable_frame, textvariable=self.github_path_var, width=50)
        path_entry.grid(row=4, column=1, sticky=EW, padx=10)
        self._add_paste_support(path_entry)

        ttk.Label(scrollable_frame, text="Branch:").grid(row=5, column=0, sticky=W, padx=10, pady=5)
        branch_entry = ttk.Entry(scrollable_frame, textvariable=self.github_branch_var, width=20)
        branch_entry.grid(row=5, column=1, sticky=W, padx=10)
        self._add_paste_support(branch_entry)

        mode_frame = ttk.LabelFrame(scrollable_frame, text="Upload Mode")
        mode_frame.grid(row=6, column=0, columnspan=3, sticky="ew", padx=10, pady=5)
        ttk.Radiobutton(mode_frame, text="Replace file (clear and add new)", variable=self.upload_mode_var, value="replace", bootstyle="toolbutton").pack(anchor=W, padx=5, pady=2)
        ttk.Radiobutton(mode_frame, text="Prepend (add new at beginning)", variable=self.upload_mode_var, value="prepend", bootstyle="toolbutton").pack(anchor=W, padx=5, pady=2)
        ttk.Radiobutton(mode_frame, text="Append (add new at end)", variable=self.upload_mode_var, value="append", bootstyle="toolbutton").pack(anchor=W, padx=5, pady=2)

        btn_frame = ttk.Frame(scrollable_frame)
        btn_frame.grid(row=7, column=1, sticky=W, pady=10)
        ttk.Button(btn_frame, text="💾 Save GitHub Settings", command=self.save_github_settings, bootstyle="primary-outline").pack(side=LEFT, padx=5)
        self.test_gh_btn = ttk.Button(btn_frame, text="🔍 Test Connection", command=self.test_github_connection, bootstyle="info-outline")
        self.test_gh_btn.pack(side=LEFT, padx=5)

        self.gh_status_label = ttk.Label(scrollable_frame, text="", foreground=INFO)
        self.gh_status_label.grid(row=8, column=0, columnspan=3, pady=5)

        guide_text = """How to get your GitHub token:
1. Go to https://github.com/settings/tokens
2. Click 'Generate new token' (classic)
3. Give it a name, select 'repo' scope
4. Generate and copy the token (it starts with 'ghp_')

How to find the file path:
- The repository is in the format 'owner/repo' (e.g., 'mehrdadmb2/V2ray_Sub')
- The file path is relative to the repository root (e.g., 'Mix.txt')
- If the file is inside a folder, use 'folder/file.txt'"""
        guide = ttk.Label(scrollable_frame, text=guide_text, justify=LEFT, font=("TkDefaultFont", 9))
        guide.grid(row=9, column=0, columnspan=3, sticky=W, padx=10, pady=10)

    def _build_log_tab(self):
        self.log_tab.grid_rowconfigure(0, weight=1)
        self.log_tab.grid_columnconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(self.log_tab, font=("Consolas", 9), wrap=WORD)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

    # ------------------------------------------------------------------
    # Paste support helper
    # ------------------------------------------------------------------
    def _add_paste_support(self, widget):
        """Add right-click context menu and Ctrl+V paste to Entry widgets."""
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        widget.bind("<Control-v>", lambda e: widget.event_generate("<<Paste>>"))
        widget.bind("<Control-V>", lambda e: widget.event_generate("<<Paste>>"))

    # ------------------------------------------------------------------
    # Helper methods for GitHub tab
    # ------------------------------------------------------------------
    def detect_github_url(self):
        url = self.github_url_var.get().strip()
        if not url:
            return
        match = re.search(r'https?://github\.com/([^/]+)/([^/]+)/(?:blob|tree)/([^/]+)/(.+)', url)
        if match:
            owner = match.group(1)
            repo = match.group(2)
            branch = match.group(3)
            path = match.group(4)
            self.github_repo_var.set(f"{owner}/{repo}")
            self.github_branch_var.set(branch)
            self.github_path_var.set(path)
            self.update_status("GitHub URL detected successfully.")
        else:
            messagebox.showerror("Error", "Invalid GitHub URL format.\nExpected: https://github.com/owner/repo/blob/branch/path")

    def toggle_token_visibility(self):
        self.show_token = not self.show_token
        self.token_entry.config(show="" if self.show_token else "*")
        self.toggle_token_btn.config(text="Hide" if self.show_token else "Show")

    def test_github_connection(self):
        token = self.github_token_var.get().strip()
        repo = self.github_repo_var.get().strip()
        path = self.github_path_var.get().strip()
        branch = self.github_branch_var.get().strip()
        if not token or not repo or not path or not branch:
            self.gh_status_label.config(text="Please fill all fields.", foreground=DANGER)
            return
        self.test_gh_btn.config(state=DISABLED)
        self.gh_status_label.config(text="Testing connection...", foreground=INFO)

        def do_test():
            uploader = GitHubUploader(token)
            success, msg = uploader.test_connection(repo, path, branch)
            self.root.after(0, self._github_test_done, success, msg)

        threading.Thread(target=do_test, daemon=True).start()

    def _github_test_done(self, success, msg):
        self.test_gh_btn.config(state=NORMAL)
        if success:
            self.gh_status_label.config(text=msg, foreground=SUCCESS)
        else:
            self.gh_status_label.config(text=msg, foreground=DANGER)

    def save_github_settings(self):
        self.settings.set("github_token", self.github_token_var.get())
        self.settings.set("github_repo", self.github_repo_var.get())
        self.settings.set("github_path", self.github_path_var.get())
        self.settings.set("github_branch", self.github_branch_var.get())
        self.settings.set("upload_mode", self.upload_mode_var.get())
        messagebox.showinfo("Saved", "GitHub settings saved.")

    # ------------------------------------------------------------------
    # Event Handlers
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
            self.update_status(f"Loaded file: {path}")

    def on_file_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if files:
            path = files[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.input_text.delete(1.0, END)
                    self.input_text.insert(END, f.read())
                self.update_status(f"File dropped: {path}")
            except Exception as e:
                messagebox.showerror("Error", f"Cannot read file:\n{e}")

    def paste_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            if clip:
                self.input_text.delete(1.0, END)
                self.input_text.insert(END, clip)
        except:
            messagebox.showerror("Error", "Clipboard is empty or inaccessible.")

    def fetch_subscription(self):
        url = simpledialog.askstring("Subscription URL", "Enter the subscription link:")
        if not url:
            return
        self.update_status("Fetching subscription...")
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
                self.update_status("Subscription fetched successfully.")
            else:
                messagebox.showerror("Error", f"HTTP status: {resp.status_code}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch:\n{e}")

    def update_status(self, text):
        self.status_bar.config(text=text)
        self.log_text.insert(END, f"{text}\n")
        self.log_text.see(END)

    def change_theme(self):
        new_theme = self.theme_var.get()
        self.style.theme_use(new_theme)
        self.settings.set("theme", new_theme)

    def change_language(self):
        messagebox.showinfo("Language", "Language change will take full effect after restart.")

    def save_all_settings(self):
        self.settings.set("prefix", self.prefix_var.get())
        self.settings.set("start_num", self.start_num_var.get())
        self.settings.set("timestamp_enabled", self.timestamp_enabled.get())
        self.settings.set("flag_enabled", self.flag_enabled.get())
        self.settings.set("preserve_country", self.preserve_country.get())
        self.settings.set("country_position", self.country_position.get())
        self.settings.set("remove_duplicates", self.remove_dup_var.get())
        self.settings.set("sort_by", self.sort_var.get())
        self.settings.set("filter_protocol", self.filter_var.get())
        self.settings.set("theme", self.theme_var.get())
        self.settings.set("language", self.language_var.get())
        self.settings.set("github_token", self.github_token_var.get())
        self.settings.set("github_repo", self.github_repo_var.get())
        self.settings.set("github_path", self.github_path_var.get())
        self.settings.set("github_branch", self.github_branch_var.get())
        self.settings.set("upload_mode", self.upload_mode_var.get())
        messagebox.showinfo("Saved", "All settings saved successfully.")

    # ------------------------------------------------------------------
    # Processing (with country to flag conversion)
    # ------------------------------------------------------------------
    def start_processing(self):
        if self.processing:
            messagebox.showwarning("Warning", "Processing already in progress.")
            return

        raw_text = self.input_text.get(1.0, END).strip()
        if not raw_text:
            messagebox.showwarning("Warning", "No input provided.")
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
        self.stats_summary_label.config(text="")

        self.current_task_thread = threading.Thread(target=self._process_lines, args=(lines,), daemon=True)
        self.current_task_thread.start()

    def pause_processing(self):
        if self.processing and not self.paused:
            self.paused = True
            self.pause_btn.configure(text="▶️ Resume", bootstyle="success")
            self.update_status("Processing paused.")
        elif self.processing and self.paused:
            self.paused = False
            self.pause_btn.configure(text="⏸️ Pause", bootstyle="warning")
            self.update_status("Processing resumed.")

    def cancel_processing(self):
        if self.processing:
            self.cancel_requested = True
            self.cancel_btn.configure(state=DISABLED)
            self.update_status("Cancelling...")

    def _process_lines(self, lines):
        prefix = self.prefix_var.get().strip()
        start = self.start_num_var.get()
        use_timestamp = self.timestamp_enabled.get()
        use_flag = self.flag_enabled.get()
        preserve_country = self.preserve_country.get()
        country_pos = self.country_position.get()
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
        stats = {"total": 0, "renamed": 0, "failed": 0, "duplicates": 0, "protocols": {}, "countries": {}}

        # Phase 1: Build ConfigLine objects
        hosts_to_resolve = []
        for idx, link in enumerate(lines):
            if self.cancel_requested:
                break
            proto = get_protocol_type(link)
            if filter_proto and proto.lower() != filter_proto:
                continue

            cfg = ConfigLine(
                original=link,
                index=idx,
                protocol=proto,
                host=extract_host(link),
                old_name=self._get_old_name(link)   # <-- now decoded
            )
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

        # Phase 2: GeoIP
        if use_flag and hosts_to_resolve:
            self.root.after(0, self.update_status, "Resolving country flags...")
            unique_hosts = list(set(hosts_to_resolve))
            results = self.geo_resolver.resolve_batch(
                unique_hosts,
                progress_callback=lambda h: self.root.after(0, self.update_status, f"GeoIP: {h}")
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

        # Phase 3: Rename
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

            new_name_parts = []
            extracted = None
            if preserve_country:
                extracted = extract_country_flag_from_name(cfg.old_name)
                if extracted and country_pos == "prefix":
                    new_name_parts.append(extracted)
            if use_flag and cfg.flag:
                if country_pos == "prefix" and preserve_country and extracted:
                    # If both are at prefix, we might duplicate; prefer extracted
                    pass
                else:
                    new_name_parts.append(cfg.flag)
            new_name_parts.append(base_name)
            if preserve_country and extracted and country_pos == "suffix":
                new_name_parts.append(extracted)
            if use_flag and cfg.flag and country_pos != "prefix":
                new_name_parts.append(cfg.flag)

            new_name = " ".join([p for p in new_name_parts if p])

            renamer = protocol_factory(cfg.original)
            renamed_link = renamer.rename(cfg.original, new_name)
            if renamed_link:
                cfg.renamed = renamed_link
                cfg.new_name = new_name
                cfg.status = "success"
                stats["renamed"] += 1
                if cfg.flag:
                    stats["countries"][cfg.flag] = stats["countries"].get(cfg.flag, 0) + 1
            else:
                cfg.renamed = cfg.original + "  ⚠ (error)"
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
            self.speed_label.config(text=f"Speed: {rate:.1f} config/s")
            self.eta_label.config(text=f"ETA: {eta}")

    def _finish_processing(self, configs, stats):
        self.processing = False
        self.paused = False
        self.run_btn.configure(state=NORMAL)
        self.pause_btn.configure(state=DISABLED, text="⏸️ Pause", bootstyle="warning")
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
                display = cfg.original + "  ⚠ (duplicate)"
            else:
                display = cfg.renamed if cfg.status == "success" else cfg.original + "  ⚠ (error)"
            self.output_text.insert(END, display + "\n")
            self.preview_tree.insert("", END, values=(i+1, cfg.old_name, cfg.new_name, cfg.flag if cfg.flag else "—"))

        summary_lines = []
        summary_lines.append(f"Total configs: {stats['total']}")
        summary_lines.append(f"Successfully renamed: {stats['renamed']}")
        summary_lines.append(f"Failed: {stats['failed']}")
        summary_lines.append(f"Duplicates: {stats['duplicates']}")
        if stats["protocols"]:
            summary_lines.append("\nProtocols:")
            for proto, count in sorted(stats["protocols"].items()):
                summary_lines.append(f"  {proto}: {count}")
        if stats["countries"]:
            summary_lines.append("\nCountries (flags):")
            for flag, count in sorted(stats["countries"].items(), key=lambda x: -x[1]):
                summary_lines.append(f"  {flag}: {count}")
        summary_text = "\n".join(summary_lines)
        self.stats_summary_label.config(text=summary_text)

        msg = f"Total: {stats['total']} | Renamed: {stats['renamed']} | Failed: {stats['failed']} | Duplicates: {stats['duplicates']}"
        self.update_status(msg)
        messagebox.showinfo("Processing Complete", msg)

    def _get_old_name(self, link: str) -> str:
        """Extract the old name from a link, decoding percent-encoded parts."""
        if "#" in link:
            try:
                raw = link.split("#")[-1]
                return unquote(raw)   # <-- decode %XX
            except:
                pass
        if link.startswith("vmess://"):
            try:
                b64 = link[8:].split("//")[-1]
                b64 += "=" * ((4 - len(b64)%4)%4)
                decoded = base64.b64decode(b64).decode("utf-8")
                config = json.loads(decoded)
                return config.get("ps", "")
            except:
                pass
        return ""

    def apply_filter(self):
        if self.processing:
            messagebox.showwarning("Warning", "Wait for current operation to finish.")
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
    # GitHub Upload
    # ------------------------------------------------------------------
    def upload_to_github(self):
        content = self.output_text.get(1.0, END).strip()
        if not content:
            messagebox.showwarning("Warning", "No output to upload.")
            return

        token = self.github_token_var.get().strip()
        repo = self.github_repo_var.get().strip()
        path = self.github_path_var.get().strip()
        branch = self.github_branch_var.get().strip()
        mode = self.upload_mode_var.get()
        if not token or not repo or not path or not branch:
            messagebox.showerror("Error", "Please set GitHub token, repository, file path, and branch in the GitHub tab.")
            return

        self.github_upload_btn.configure(state=DISABLED)
        self.update_status("Uploading to GitHub...")

        def do_upload():
            uploader = GitHubUploader(token)
            success, msg = uploader.upload(repo, path, content, branch, mode)
            self.root.after(0, self._github_upload_done, success, msg)

        threading.Thread(target=do_upload, daemon=True).start()

    def _github_upload_done(self, success, msg):
        self.github_upload_btn.configure(state=NORMAL)
        self.update_status(msg)
        if success:
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)

    # ------------------------------------------------------------------
    # Save / Copy Output
    # ------------------------------------------------------------------
    def save_output(self, fmt):
        content = self.output_text.get(1.0, END).strip()
        if not content:
            messagebox.showwarning("Warning", "Output is empty.")
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
            messagebox.showinfo("Saved", f"File saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Save failed:\n{e}")

    def copy_output(self):
        content = self.output_text.get(1.0, END).strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("Copied", "Output copied to clipboard.")
        else:
            messagebox.showwarning("Warning", "Output is empty.")

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
# Application Entry Point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    ensure_dir(LOG_DIR)

    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    root.title(f"{APP_NAME} v{VERSION}")
    root.geometry("1200x850")
    root.minsize(1000, 700)

    _ = Style(theme=DEFAULT_THEME)

    app = ProApp(root)
    root.mainloop()
