import base64
import json
import re
import threading
import time
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, StringVar, IntVar, BooleanVar
from urllib.parse import quote
import tkinter as tk

import ttkbootstrap as ttk
from ttkbootstrap import Style

import requests  # فقط برای قابلیت بتا

# ----------------------------------------------------------------------
# تنظیمات تم و استایل
# ----------------------------------------------------------------------
PRIMARY_COLOR = "#0d6efd"
SUCCESS_COLOR = "#198754"
DANGER_COLOR = "#dc3545"
WARNING_COLOR = "#ffc107"

# ----------------------------------------------------------------------
# توابع تغییر نام لینک
# ----------------------------------------------------------------------
def rename_vmess_link(link: str, new_name: str) -> str:
    """لینک vmess:// را گرفته و بخش 'ps' را با new_name جایگزین می‌کند."""
    try:
        b64_part = link[len("vmess://"):].strip()
        if b64_part.startswith("//"):
            b64_part = b64_part[2:]
        missing_padding = len(b64_part) % 4
        if missing_padding:
            b64_part += "=" * (4 - missing_padding)
        decoded = base64.b64decode(b64_part).decode("utf-8")
        config = json.loads(decoded)
        config["ps"] = new_name
        new_json = json.dumps(config, separators=(",", ":"), ensure_ascii=False)
        new_b64 = base64.b64encode(new_json.encode("utf-8")).decode("utf-8")
        return "vmess://" + new_b64
    except Exception:
        return None


def rename_uri_link(link: str, new_name: str) -> str:
    """
    لینک‌های vless://, trojan://, hysteria:// و ... را پردازش می‌کند.
    بخش نام (بعد از #) را حذف و نام جدید را جایگزین می‌کند.
    """
    try:
        if "#" in link:
            base = link[:link.index("#")]
        else:
            base = link
        encoded_name = quote(new_name, safe="")
        return base + "#" + encoded_name
    except Exception:
        return None


def rename_ss_link(link: str, new_name: str) -> str:
    """لینک‌های Shadowsocks را (با یا بدون fragment) تغییر نام می‌دهد."""
    try:
        if "#" in link:
            base = link[:link.index("#")]
            return base + "#" + quote(new_name, safe="")
        else:
            return link + "#" + quote(new_name, safe="")
    except Exception:
        return None


def rename_link(link: str, new_name: str) -> str:
    """تشخیص پروتکل و اعمال تغییر نام."""
    link = link.strip()
    if not link:
        return None
    low = link.lower()
    if low.startswith("vmess://"):
        return rename_vmess_link(link, new_name)
    elif low.startswith("ss://"):
        return rename_ss_link(link, new_name)
    elif any(low.startswith(p) for p in [
        "vless://", "trojan://", "hysteria2://",
        "hysteria://", "tuic://", "socks://", "http://"
    ]):
        return rename_uri_link(link, new_name)
    else:
        return None

# ----------------------------------------------------------------------
# استخراج IP یا دامنه از لینک (برای موقعیت‌یابی)
# ----------------------------------------------------------------------
def extract_host_from_link(link: str) -> str:
    """هاست (IP یا دامنه) را از لینک خارج می‌کند."""
    link = link.strip()

    if link.startswith("vmess://"):
        try:
            b64 = link[len("vmess://"):].strip()
            if b64.startswith("//"):
                b64 = b64[2:]
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

# ----------------------------------------------------------------------
# تبدیل کد کشور به پرچم ایموجی
# ----------------------------------------------------------------------
def country_code_to_flag(code: str) -> str:
    """کد ISO-3166-1 alpha-2 را به پرچم ایموجی تبدیل می‌کند (مثلاً US -> 🇺🇸)."""
    if not code or len(code) != 2:
        return ""
    return chr(ord(code[0]) + 127397) + chr(ord(code[1]) + 127397)

# ----------------------------------------------------------------------
# دریافت موقعیت جغرافیایی (قابلیت بتا)
# ----------------------------------------------------------------------
def get_country_flag(host: str, timeout=3) -> str:
    """
    از API رایگان ip-api.com برای دریافت کد کشور استفاده می‌کند.
    در صورت خطا یا timeout رشتهٔ خالی برمی‌گرداند.
    """
    try:
        url = f"http://ip-api.com/json/{host}?fields=countryCode"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            code = data.get("countryCode", "")
            if code:
                return country_code_to_flag(code)
    except:
        pass
    return ""

# ----------------------------------------------------------------------
# پنجره اصلی برنامه
# ----------------------------------------------------------------------
class V2rayConfigRenamer:
    def __init__(self, root):
        self.root = root
        self.root.title("V2rayN Config Renamer Pro | نسخه‌ حرفه‌ای")
        self.root.geometry("850x750")
        self.root.minsize(800, 700)

        # استایل تیره با ttkbootstrap
        self.style = Style(theme="darkly")  # تم‌های دیگر: superhero, cyborg, vapor, ...

        # متغیرهای کنترلی
        self.prefix_var = StringVar(value="Node-")
        self.start_num_var = IntVar(value=0)
        self.timestamp_enabled = BooleanVar(value=False)
        self.timestamp_format = StringVar(value="%Y%m%d_%H%M%S")
        self.flag_enabled = BooleanVar(value=False)

        # متغیرهای آمار
        self.stats_text = StringVar(value="آماده")
        self.progress = None

        # لیست فرمت‌های تاریخ
        self.date_formats = [
            ("YYYYMMDD_HHMMSS", "%Y%m%d_%H%M%S"),
            ("YYYY-MM-DD HH:MM:SS", "%Y-%m-%d %H:%M:%S"),
            ("DD/MM/YYYY HH:MM", "%d/%m/%Y %H:%M"),
            ("Unix Timestamp", "%s"),
        ]

        # ساخت رابط کاربری
        self.create_widgets()

    # ------------------------------------------------------------------
    # ساخت ویجت‌ها
    # ------------------------------------------------------------------
    def create_widgets(self):
        # --- بخش ورودی ---
        input_frame = ttk.LabelFrame(self.root, text="📥 ورودی (لینک‌های اشتراک)")
        input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        input_inner = ttk.Frame(input_frame)
        input_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.input_text = scrolledtext.ScrolledText(
            input_inner,
            height=10,
            font=("Consolas", 10),
            wrap=tk.NONE,
            bg="#2b3e50",
            fg="#ecf0f1",
            insertbackground="white"
        )
        self.input_text.pack(fill=tk.BOTH, expand=True, pady=5)

        btn_frame1 = ttk.Frame(input_inner)
        btn_frame1.pack(fill=tk.X, pady=5)
        ttk.Button(
            btn_frame1,
            text="📂 بارگذاری فایل",
            command=self.load_file,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_frame1,
            text="📋 چسباندن از کلیپ‌بورد",
            command=self.paste_clipboard,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            btn_frame1,
            text="🗑️ پاک کردن",
            command=lambda: self.input_text.delete(1.0, tk.END),
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=5)

        # --- تنظیمات نام‌گذاری ---
        settings_frame = ttk.LabelFrame(self.root, text="⚙️ تنظیمات نام‌گذاری")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)

        settings_inner = ttk.Frame(settings_frame)
        settings_inner.pack(fill=tk.X, expand=True, padx=10, pady=10)

        # پیشوند و شروع
        top_row = ttk.Frame(settings_inner)
        top_row.pack(fill=tk.X)
        ttk.Label(top_row, text="پیشوند نام:", font=("Tahoma", 10)).pack(side=tk.LEFT)
        ttk.Entry(top_row, textvariable=self.prefix_var, width=15, font=("Tahoma", 10)).pack(side=tk.LEFT, padx=5)
        ttk.Label(top_row, text="شروع از:", font=("Tahoma", 10)).pack(side=tk.LEFT, padx=(20, 0))
        ttk.Entry(top_row, textvariable=self.start_num_var, width=6, font=("Tahoma", 10)).pack(side=tk.LEFT, padx=5)

        # گزینه‌های تاریخ و پرچم (بتا)
        mid_row = ttk.Frame(settings_inner)
        mid_row.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(
            mid_row,
            text="افزودن تاریخ/ساعت به اسم",
            variable=self.timestamp_enabled,
            command=self.toggle_timestamp
        ).pack(side=tk.LEFT)

        self.date_combo = ttk.Combobox(
            mid_row,
            textvariable=self.timestamp_format,
            values=[f[0] for f in self.date_formats],
            state="readonly",
            width=22
        )
        self.date_combo.pack(side=tk.LEFT, padx=5)
        self.date_combo.current(0)
        self.date_combo.configure(state="disabled")

        # قابلیت بتا
        beta_row = ttk.Frame(settings_inner)
        beta_row.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(
            beta_row,
            text="آزمایشی: افزودن پرچم کشور (IP Geolocation) - بتا",
            variable=self.flag_enabled
        ).pack(side=tk.LEFT)
        ttk.Label(
            beta_row,
            text="⚠️ ممکن است کند باشد",
            foreground=WARNING_COLOR,
            font=("Tahoma", 8, "italic")
        ).pack(side=tk.LEFT, padx=5)

        # --- دکمه پردازش ---
        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(
            action_frame,
            text="⚡ اعمال تغییرات و شماره‌گذاری",
            command=self.start_processing,
            bootstyle="success"
        ).pack(side=tk.LEFT, padx=5)
        self.progress_bar = ttk.Progressbar(action_frame, mode="indeterminate", length=200)
        self.progress_bar.pack(side=tk.LEFT, padx=10)
        self.progress_label = ttk.Label(action_frame, text="", foreground="gray")
        self.progress_label.pack(side=tk.LEFT)

        # --- بخش خروجی ---
        output_frame = ttk.LabelFrame(self.root, text="📤 خروجی (لینک‌های جدید)")
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        output_inner = ttk.Frame(output_frame)
        output_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.output_text = scrolledtext.ScrolledText(
            output_inner,
            height=12,
            font=("Consolas", 10),
            wrap=tk.NONE,
            bg="#2b3e50",
            fg="#ecf0f1",
            insertbackground="white"
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)

        out_btn_frame = ttk.Frame(output_inner)
        out_btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(
            out_btn_frame,
            text="💾 ذخیره خروجی به فایل TXT",
            command=self.save_file,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            out_btn_frame,
            text="📋 کپی خروجی در کلیپ‌بورد",
            command=self.copy_output,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=5)

        # --- پنل آمار ---
        stats_frame = ttk.LabelFrame(self.root, text="📊 آمار")
        stats_frame.pack(fill=tk.X, padx=10, pady=5)

        stats_inner = ttk.Frame(stats_frame)
        stats_inner.pack(fill=tk.X, expand=True, padx=10, pady=10)

        self.stats_label = ttk.Label(
            stats_inner,
            textvariable=self.stats_text,
            font=("Tahoma", 10, "bold"),
            justify=tk.LEFT
        )
        self.stats_label.pack(anchor=tk.W)

    # ------------------------------------------------------------------
    # رویدادها
    # ------------------------------------------------------------------
    def toggle_timestamp(self):
        if self.timestamp_enabled.get():
            self.date_combo.configure(state="readonly")
        else:
            self.date_combo.configure(state="disabled")

    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self.input_text.delete(1.0, tk.END)
                self.input_text.insert(tk.END, f.read())

    def paste_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            if clip:
                self.input_text.delete(1.0, tk.END)
                self.input_text.insert(tk.END, clip)
        except:
            messagebox.showerror("خطا", "کلیپ‌بورد خالی یا غیرقابل دسترس است.")

    def get_input_links(self):
        raw = self.input_text.get(1.0, tk.END)
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def get_protocol(self, link: str) -> str:
        """نوع پروتکل را برمی‌گرداند."""
        low = link.strip().lower()
        if low.startswith("vmess://"):
            return "VMess"
        if low.startswith("vless://"):
            return "VLESS"
        if low.startswith("trojan://"):
            return "Trojan"
        if low.startswith("ss://"):
            return "Shadowsocks"
        if low.startswith("hysteria2"):
            return "Hysteria2"
        if low.startswith("hysteria"):
            return "Hysteria"
        if low.startswith("tuic://"):
            return "TUIC"
        if low.startswith("socks://"):
            return "SOCKS"
        if low.startswith("http://"):
            return "HTTP"
        return "Other"

    def start_processing(self):
        """پردازش را در یک نخ جداگانه شروع می‌کند تا UI قفل نشود."""
        links = self.get_input_links()
        if not links:
            messagebox.showwarning("هشدار", "هیچ لینکی وارد نشده.")
            return

        self.set_ui_state(tk.DISABLED)
        self.progress_bar.start(10)
        self.progress_label.config(text="در حال پردازش...")

        threading.Thread(target=self.process_links, args=(links,), daemon=True).start()

    def process_links(self, links):
        """عملیات اصلی تغییر نام (و در صورت نیاز پرچم‌گذاری) را انجام می‌دهد."""
        prefix = self.prefix_var.get().strip()
        start = self.start_num_var.get()
        use_timestamp = self.timestamp_enabled.get()
        use_flag = self.flag_enabled.get()

        fmt_code = self.timestamp_format.get()
        actual_fmt = next((f[1] for f in self.date_formats if f[0] == fmt_code), "%Y%m%d_%H%M%S")

        new_links = []
        stats = {
            "total": len(links),
            "renamed": 0,
            "failed": 0,
            "protocols": {}
        }

        for idx, link in enumerate(links):
            base_name = f"{prefix}{start + idx}" if prefix else str(start + idx)

            if use_timestamp:
                now = datetime.now()
                try:
                    if actual_fmt == "%s":
                        ts = int(now.timestamp())
                        base_name += f"_{ts}"
                    else:
                        base_name += f"_{now.strftime(actual_fmt)}"
                except:
                    pass

            renamed = rename_link(link, base_name)
            proto = self.get_protocol(link)
            stats["protocols"][proto] = stats["protocols"].get(proto, 0) + 1

            if not renamed:
                stats["failed"] += 1
                renamed = link + "  ⚠ (خطا)"
                new_links.append(renamed)
                continue

            if use_flag:
                host = extract_host_from_link(link)
                if host:
                    flag = get_country_flag(host)
                    if flag:
                        new_name_with_flag = base_name + " " + flag
                        final_renamed = rename_link(link, new_name_with_flag)
                        if final_renamed:
                            renamed = final_renamed

            stats["renamed"] += 1
            new_links.append(renamed)

            if use_flag and idx > 0 and idx % 40 == 0:
                time.sleep(1.5)

        self.root.after(0, self.finish_processing, new_links, stats)

    def finish_processing(self, new_links, stats):
        """نتایج را در خروجی نمایش می‌دهد و آمار را به‌روز می‌کند."""
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, "\n".join(new_links))

        protocol_lines = []
        for proto, count in sorted(stats["protocols"].items()):
            protocol_lines.append(f"• {proto}: {count}")

        lines = [
            f"✅ کل ورودی: {stats['total']}",
            f"✔️ تغییر نام موفق: {stats['renamed']}",
            f"❌ ناموفق/خطا: {stats['failed']}",
            "📋 تعداد هر پروتکل:"
        ]
        lines.extend(protocol_lines if protocol_lines else ["• موردی ثبت نشد."])

        self.stats_text.set("\n".join(lines))

        self.set_ui_state(tk.NORMAL)
        self.progress_bar.stop()
        self.progress_label.config(text="")

        messagebox.showinfo(
            "پایان",
            f"پردازش {stats['total']} کانفیگ به پایان رسید.\n"
            f"موفق: {stats['renamed']} | ناموفق: {stats['failed']}"
        )

    def _iter_children(self, widget):
        """پیمایش بازگشتی همه ویجت‌ها برای اعمال state."""
        for child in widget.winfo_children():
            yield child
            yield from self._iter_children(child)

    def set_ui_state(self, state):
        """فعال/غیرفعال کردن ویجت‌های حین پردازش."""
        for child in self._iter_children(self.root):
            if isinstance(child, ttk.Button):
                child.configure(state=state)
            elif isinstance(child, ttk.Checkbutton):
                child.configure(state=state)
            elif isinstance(child, ttk.Entry):
                child.configure(state=state)
            elif isinstance(child, ttk.Combobox):
                child.configure(state=state)
        self.progress_bar.configure(mode="indeterminate")

    def save_file(self):
        out = self.output_text.get(1.0, tk.END).strip()
        if not out:
            messagebox.showwarning("هشدار", "خروجی خالی است.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(out)
            messagebox.showinfo("ذخیره شد", f"فایل در {path} ذخیره گردید.")

    def copy_output(self):
        out = self.output_text.get(1.0, tk.END).strip()
        if out:
            self.root.clipboard_clear()
            self.root.clipboard_append(out)
            messagebox.showinfo("کپی شد", "خروجی در کلیپ‌بورد کپی شد.")
        else:
            messagebox.showwarning("هشدار", "خروجی خالی است.")

# ----------------------------------------------------------------------
# اجرای برنامه
# ----------------------------------------------------------------------
if __name__ == "__main__":
    root = ttk.Window(themename="darkly")
    app = V2rayConfigRenamer(root)
    root.mainloop()