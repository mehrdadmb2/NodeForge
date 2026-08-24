# NodeForge

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Tkinter](https://img.shields.io/badge/UI-Tkinter%20%2B%20ttkbootstrap-green)
![Web](https://img.shields.io/badge/Web-Responsive%20HTML%2FCSS%2FJS-orange)
![Platform](https://img.shields.io/badge/Platform-Windows%20%2F%20Cross--Platform-lightgrey)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Version](https://img.shields.io/badge/Version-4.0.0-brightgreen)

**NodeForge** is a powerful, modern tool for batch‑renaming V2Ray/Xray subscription links. It offers both a **desktop application** (Python + Tkinter/ttkbootstrap) and a **web edition** (HTML/CSS/JS) with an advanced glassmorphism UI. It supports many protocols, smart naming with timestamps and country flags, geolocation caching, GitHub integration, and much more.

---

## ✨ Features

### Core Functionality
- **Batch rename** hundreds of subscription links in seconds
- **Protocol auto‑detection** for:
  - VMess, VLESS, Trojan, Shadowsocks, Hysteria, Hysteria2, TUIC, SOCKS, HTTP, SSH, WireGuard, Reality, gRPC, and more
- **Smart naming**:
  - Custom prefix and start number
  - Optional timestamp (multiple formats)
  - Optional country flag (from GeoIP)
  - Preserve original country/flag from old names (with automatic conversion of country names to flag emoji)
  - Choose flag position (beginning or end)
- **Duplicate removal**, **protocol filtering**, **sorting** (by name, country, protocol)
- **Live preview** of old and new names
- **Detailed statistics** including protocol counts and country flag distribution

### Input & Output
- **Input sources**:
  - Paste from clipboard
  - Load `.txt` file
  - Drag & drop (desktop, if `tkinterdnd2` installed)
  - Fetch from subscription URL (base64 decoded automatically)
- **Output destinations**:
  - Copy to clipboard
  - Save as TXT, CSV, or JSON
  - **Direct upload to GitHub** (see below)

### GitHub Integration
- **Auto‑detect** GitHub file URL – paste a link like `https://github.com/owner/repo/blob/main/Mix.txt` and it extracts repository, branch, and file path automatically.
- **Three upload modes**:
  - **Replace**: overwrite the file with new content
  - **Prepend**: add new content at the beginning of the existing file
  - **Append**: add new content at the end of the existing file
- **Test connection** button to validate token, repo, and file before uploading.
- Secure token storage (locally in `config.json` or browser `localStorage`).

### User Interface
- **Modern glassmorphism design** with gradient backgrounds, animated blobs, and smooth transitions.
- **Responsive layout** – works on any screen size from desktop to mobile.
- **Multiple themes** (desktop) including `cyborg`, `darkly`, `superhero`, etc.
- **Live progress** with percentage, ETA, and processing speed.
- **Pause / Resume / Cancel** during processing.
- **Multi‑threaded** GeoIP resolution for fast country lookup (desktop) or asynchronous fetch (web).

---

## 🌐 Web Edition

The repository includes a fully functional **web version** (`index.html`) that runs entirely in the browser.  
**Try it live:** [GitHub Pages link – to be added]  

### Web Edition Features
- All core renaming features (no installation required)
- Client‑side geolocation using `ipwho.is` with caching
- Export to TXT, CSV, JSON, or clipboard
- GitHub upload with replace/prepend/append modes (requires a GitHub token)
- Beautiful responsive UI with glassmorphism and animated background

---

## 📥 Installation (Desktop)

### Requirements
- Python 3.10 or newer
- `ttkbootstrap`
- `requests`
- Optional: `tkinterdnd2` for drag‑and‑drop support

### Steps
1. **Clone the repository**
   ```bash
   git clone https://github.com/mehrdadmb2/NodeForge.git
   cd NodeForge
   ```

2. **Install dependencies**
   ```bash
   pip install ttkbootstrap requests
   # Optional for drag & drop:
   pip install tkinterdnd2
   ```

3. **Run the program**
   ```bash
   python confign.py
   ```

---

## 🚀 Usage

### Desktop App
1. **Input** – paste links, load a file, or fetch a subscription.
2. **Configure naming** – set prefix, start number, timestamp, flags, etc.
3. **Process** – click “Start Processing”. You can pause, resume, or cancel.
4. **Output** – view the renamed links, copy them, export to file, or upload to GitHub.

### Web Edition
1. Open `index.html` in a browser.
2. Paste or load your links.
3. Adjust settings and click **Start Processing**.
4. Use the **GitHub tab** to upload directly to your repository.

---

## 🧪 Example

**Input**
```
vmess://eyJhZGQiOiIxLjIuMy40IiwiYWlkIjoiMCIsInBzIjoiVGVzdCIsInBvcnQiOiI0NDMiLCJpZCI6ImFiYyJ9
vless://uuid@example.com:443?type=tcp#OldName
trojan://password@example.com:443#OldName
ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@example.com:8388#OldName
```

**Settings**  
`prefix = "Node-"`, `start = 0`, `timestamp = off`, `flags = off`

**Output**
```
vmess://...
vless://...#Node-0
trojan://...#Node-1
ss://...#Node-2
```

---

## 📁 File Structure

```
NodeForge/
│
├── confign.py               # Desktop application (Python)
├── index.html               # Web edition (HTML/CSS/JS)
├── README.md
├── LICENSE
├── screenshots/
│   ├── desktop-main.png
│   ├── desktop-github.png
│   ├── web-main.png
│   └── ...
├── config.json              # Settings (auto‑generated)
├── geo_cache.json           # GeoIP cache (auto‑generated)
└── logs/                    # Daily logs
```

---

## ⚙️ Configuration

Settings are stored locally in `config.json` (desktop) or browser `localStorage` (web).  
You can edit the file directly or use the **Settings** tab in the app.

### GitHub Upload Configuration
- **GitHub Token** – obtain from [GitHub Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens). Select `repo` scope.
- **Repository** – format `owner/repo` (e.g., `mehrdadmb2/NodeForge`).
- **File Path** – relative to the repository root (e.g., `Mix.txt` or `folder/subfolder/file.txt`).
- **Branch** – usually `main` or `master`.

---

## 🛠️ Tech Stack

| Component      | Technology                               |
|----------------|------------------------------------------|
| Desktop app    | Python, Tkinter, ttkbootstrap            |
| Web app        | HTML5, CSS3, JavaScript (vanilla)        |
| GeoIP          | `ip-api.com` (desktop), `ipwho.is` (web) |
| GitHub API     | REST API v3                              |

---

## 🔮 Future Improvements

- [ ] Full Persian (Farsi) translation
- [ ] Batch processing from multiple files
- [ ] Config health check (ping, TCP connect)
- [ ] QR code generation
- [ ] Undo history
- [ ] Advanced filtering with regex
- [ ] Export as subscription (base64‑encoded)

---

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

---

## 📄 License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**Mehrdad**  
[GitHub](https://github.com/mehrdadmb2) • [Repository](https://github.com/mehrdadmb2/NodeForge)

---

**Enjoy renaming your V2Ray configs with style!**  
If you find this project useful, please give it a ⭐ on GitHub.
```
