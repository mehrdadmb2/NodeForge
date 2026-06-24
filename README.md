# NodeForge

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Tkinter](https://img.shields.io/badge/UI-Tkinter%20%2B%20ttkbootstrap-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%2F%20Cross--Platform-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

NodeForge is a desktop application built with Python for batch-renaming V2Ray subscription links in a fast, clean, and protocol-aware way. It supports multiple link types, live protocol counters, timestamp-based naming, optional country flag tagging, and export to TXT or clipboard.

---

## Features

- Batch rename subscription links in one click
- Supports multiple protocols:
  - VMess
  - VLESS
  - Trojan
  - Shadowsocks
  - Hysteria
  - Hysteria2
  - TUIC
  - SOCKS
  - HTTP
  - Other
- Automatic numbering with custom prefix
- Optional timestamp in renamed nodes
- Optional beta country flag tagging using IP geolocation
- Live protocol counters in the UI
- Input from:
  - text file
  - clipboard
  - manual paste
- Output to:
  - TXT file
  - clipboard
- Friendly dark-themed GUI using `ttkbootstrap`
- Threaded processing to keep the interface responsive

---

## Preview

> Add screenshots here if you want your repository to look more professional.

Example:

```md
![Main Window](screenshots/main-window.png)
![Protocol Counter](screenshots/protocol-counter.png)
````

---

## How It Works

NodeForge reads a list of subscription links and detects the protocol of each one.
Then it applies a new name based on:

* a custom prefix
* an incremental number
* an optional timestamp

For example:

```text
Node-0
Node-1
Node-2
```

Or with timestamp:

```text
Node-0_20250624_153045
Node-1_20250624_153046
```

If the beta country-flag option is enabled, the app tries to detect the host IP/domain location and appends a country flag to the node name.

---

## Supported Link Types

### VMess

Renames the `ps` field inside the base64-encoded JSON config.

### URI-based protocols

For protocols like:

* VLESS
* Trojan
* Hysteria
* Hysteria2
* TUIC
* SOCKS
* HTTP

the app replaces the fragment after `#` with the new generated name.

### Shadowsocks

Adds or updates the fragment name after `#`.

---

## Requirements

* Python 3.10 or newer
* `ttkbootstrap`
* `requests`

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/nodeforge.git
cd nodeforge
```

### 2. Install dependencies

```bash
pip install ttkbootstrap requests
```

### 3. Run the program

```bash
python confign.py
```

---

## Usage

1. Paste subscription links into the input box
2. Or load them from a `.txt` file
3. Set the naming prefix
4. Choose the starting number
5. Enable timestamp if needed
6. Optionally enable country-flag tagging
7. Click **Apply Changes and Numbering**
8. Copy the result or save it to a TXT file

---

## Interface Overview

### Input Section

Used for pasting or loading subscription links.

### Naming Settings

Contains:

* prefix input
* start number
* timestamp toggle
* timestamp format selector
* country-flag beta option

### Output Section

Shows the renamed links after processing.

### Statistics Section

Displays:

* total input count
* successful renames
* failed links
* protocol breakdown

### Protocol Counter Panel

Shows live counts for each protocol type in a colored and organized layout.

---

## Example Input

```text
vmess://eyJhZGQiOiIxLjIuMy40IiwiYWlkIjoiMCIsInBzIjoiVGVzdCIsInBvcnQiOiI0NDMiLCJpZCI6ImFiYyJ9
vless://uuid@example.com:443?type=tcp#OldName
trojan://password@example.com:443#OldName
ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@example.com:8388#OldName
```

---

## Example Output

```text
vmess://...
vless://...#Node-0
trojan://...#Node-1
ss://...#Node-2
```

---

## File Structure

```text
nodeforge/
│
├── confign.py
├── README.md
└── screenshots/
    ├── main-window.png
    └── protocol-counter.png
```

---

## Notes

* The country flag feature is experimental.
* If geolocation lookup fails, the app continues working normally.
* Invalid or unsupported links are marked as failed.
* The UI is threaded so large lists do not freeze the window.

---

## Future Improvements

* Search and filter support
* Copy output with one click after processing
* Export counters as a report
* Better protocol parsing for edge cases
* Auto-detect mixed line formats
* Save user preferences
* Add drag-and-drop file support

---

## Contributing

Pull requests and suggestions are welcome.

If you want to contribute:

1. Fork the repository
2. Create a new branch
3. Commit your changes
4. Open a pull request

---

## License

This project is licensed under the MIT License.
See the `LICENSE` file for details.

---

## Author

Created by **Mehrdad**

```

```
