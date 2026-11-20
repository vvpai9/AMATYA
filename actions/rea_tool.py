"""
Reverse Engineering Anything (REA) Tool for JARVIS.
Reverse engineers APIs, Android APKs, Native Binaries (Mach-O, ELF, PE), and Network requests.
Provides decompilation helpers, secret extraction, JWT decoding, client code generation,
entropy analysis, and binary symbol inspection.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse

def _calc_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of byte data in [0.0, 8.0]. High entropy (>7.2) indicates compression/encryption."""
    if not data:
        return 0.0
    occ = [0] * 256
    for b in data:
        occ[b] += 1
    total = len(data)
    entropy = 0.0
    for count in occ:
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return round(entropy, 3)

def _extract_strings(data: bytes, min_len: int = 4, max_strings: int = 150) -> List[str]:
    """Extract printable ASCII strings from raw bytes."""
    pattern = rb"[A-Za-z0-9_\-\.\:\/\?\&\=\@\#\$\%\*\+\(\)]{" + str(min_len).encode() + rb",}"
    matches = re.findall(pattern, data)
    results = []
    seen = set()
    for m in matches:
        s = m.decode("latin-1", errors="ignore")
        if s not in seen and len(s) >= min_len:
            seen.add(s)
            results.append(s)
            if len(results) >= max_strings:
                break
    return results

def _decode_jwt(token: str) -> dict:
    """Decode JWT header and payload without signature verification."""
    parts = token.strip().split(".")
    if len(parts) < 2:
        return {"error": "Invalid JWT format"}
    def _b64_decode(p):
        p += "=" * ((4 - len(p) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(p).decode("utf-8", errors="ignore"))
    try:
        header = _b64_decode(parts[0])
        payload = _b64_decode(parts[1])
        return {"header": header, "payload": payload}
    except Exception as e:
        return {"error": f"JWT decode failed: {e}"}

def reverse_api(target: str, sample_payload: Optional[str] = None) -> str:
    """Reverse engineer an API from a URL, cURL command, or network snippet."""
    clean_target = target.strip()
    headers = {}
    method = "GET"
    url = ""
    body = sample_payload or ""

    # Parse cURL command if provided
    if clean_target.lower().startswith("curl "):
        try:
            parts = shlex.split(clean_target)
        except Exception:
            parts = clean_target.split()
        for i, p in enumerate(parts):
            if p in ("-X", "--request") and i + 1 < len(parts):
                method = parts[i + 1].strip("'\"")
            elif p in ("-H", "--header") and i + 1 < len(parts):
                h = parts[i + 1].strip("'\"")
                if ":" in h:
                    k, v = h.split(":", 1)
                    headers[k.strip()] = v.strip()
            elif p in ("-d", "--data", "--data-raw") and i + 1 < len(parts):
                body = parts[i + 1].strip("'\"")
                if method == "GET": method = "POST"
            elif p.startswith("http://") or p.startswith("https://"):
                url = p.strip("'\"")
    else:
        # Check if URL directly
        if "http://" in clean_target or "https://" in clean_target:
            urls = re.findall(r"https?://[^\s'\"]+", clean_target)
            if urls:
                url = urls[0]
        else:
            url = clean_target

    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)

    # Detect Auth Tokens & JWTs
    auth_analysis = []
    jwt_claims = None
    for hk, hv in list(headers.items()):
        if "bearer " in hv.lower():
            token = hv.split(" ", 1)[1]
            jwt_data = _decode_jwt(token)
            if "payload" in jwt_data:
                jwt_claims = jwt_data["payload"]
                auth_analysis.append(f"JWT Bearer Token detected! Decoded claims: {json.dumps(jwt_claims, indent=2)}")
        elif "authorization" in hk.lower():
            auth_analysis.append(f"Auth Header: {hk} = {hv[:20]}...")

    # Generate Python Client
    py_code = [
        "import requests",
        "",
        f"url = '{url}'",
    ]
    if headers:
        py_code.append(f"headers = {json.dumps(headers, indent=4)}")
    if query_params:
        py_code.append(f"params = {json.dumps(query_params, indent=4)}")
    if body:
        py_code.append(f"data = {body if body.startswith('{') else repr(body)}")
    
    call_args = ["url"]
    if headers: call_args.append("headers=headers")
    if query_params: call_args.append("params=params")
    if body:
        if body.strip().startswith("{"):
            call_args.append("json=data")
        else:
            call_args.append("data=data")

    py_code.append(f"response = requests.{method.lower()}({', '.join(call_args)})")
    py_code.append("print(response.status_code)")
    py_code.append("print(response.text)")

    output = [
        f"🔍 REA: API Reverse Engineering Report",
        f"• Endpoint: {method} {url}",
        f"• Host: {parsed.netloc} | Path: {parsed.path}",
        f"• Query Parameters: {json.dumps(query_params) if query_params else 'None'}",
        f"• Headers Count: {len(headers)}",
    ]
    if auth_analysis:
        output.extend(auth_analysis)
    
    output.append("\n📦 Generated Python Client Code:\n```python\n" + "\n".join(py_code) + "\n```")
    return "\n".join(output)

def reverse_apk(file_path: str) -> str:
    """Reverse engineer an Android APK file."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return f"File not found: {file_path}"
    
    output = [f"📱 REA: Android APK Analysis for {path.name} ({path.stat().st_size / 1024 / 1024:.2f} MB)"]
    
    try:
        with zipfile.ZipFile(path, "r") as z:
            names = z.namelist()
            dex_files = [n for n in names if n.endswith(".dex")]
            native_libs = [n for n in names if n.startswith("lib/")]
            assets = [n for n in names if n.startswith("assets/")]
            
            # Framework detection
            framework = "Native Java/Kotlin"
            if any("libflutter.so" in n for n in native_libs):
                framework = "Flutter"
            elif any("libreactnative" in n or "index.android.bundle" in n for n in names):
                framework = "React Native"
            elif any("libunity.so" in n for n in native_libs):
                framework = "Unity 3D"
            elif any("libmonosgen" in n for n in native_libs):
                framework = "Xamarin"

            output.append(f"• Framework Detected: **{framework}**")
            output.append(f"• DEX Files Count: {len(dex_files)}")
            output.append(f"• Native Architectures: {', '.join(set(n.split('/')[1] for n in native_libs if '/' in n)) or 'None'}")
            
            # String search inside primary DEX for secrets & endpoints
            if dex_files:
                dex_data = z.read(dex_files[0])
                strings = _extract_strings(dex_data, min_len=6, max_strings=2000)
                
                urls = [s for s in strings if s.startswith("http://") or s.startswith("https://")]
                api_keys = [s for s in strings if any(k in s.lower() for k in ("apikey", "api_key", "secret", "firebase", "aws_"))]
                
                if urls:
                    output.append(f"\n🌐 Embedded Endpoints ({len(urls)} found, top 5):\n" + "\n".join(f"  - {u}" for u in urls[:5]))
                if api_keys:
                    output.append(f"\n🔑 Suspicious Keys / Credentials ({len(api_keys)} found):\n" + "\n".join(f"  - {k}" for k in api_keys[:5]))

            # Check if jadx or apktool is available
            jadx_path = shutil.which("jadx")
            if jadx_path:
                output.append(f"\n⚡ JADX is available on this system at `{jadx_path}`. Can decompile full Java source.")
            else:
                output.append("\n💡 Tip: Install `jadx` (`brew install jadx`) for full one-click Java source decompilation.")

    except Exception as e:
        output.append(f"Error inspecting APK zip archive: {e}")

    return "\n".join(output)

def reverse_binary(file_path: str) -> str:
    """Reverse engineer a native executable or library (Mach-O, ELF, PE)."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return f"Binary file not found: {file_path}"
    
    size = path.stat().st_size
    output = [f"⚙️ REA: Binary Reverse Engineering for `{path.name}` ({size / 1024:.1f} KB)"]

    try:
        with open(path, "rb") as f:
            header = f.read(1024)
            f.seek(0)
            full_data = f.read(min(size, 2 * 1024 * 1024)) # read up to 2MB for analysis
        
        # File Format Identification
        fmt = "Unknown Binary"
        if header.startswith(b"\x7fELF"):
            fmt = f"ELF Binary ({'64-bit' if header[4] == 2 else '32-bit'})"
        elif header.startswith(b"\xcf\xfa\xed\xfe") or header.startswith(b"\xfe\xed\xfa\xcf"):
            fmt = "Mach-O 64-bit (macOS/iOS)"
        elif header.startswith(b"\xce\xfa\xed\xfe") or header.startswith(b"\xfe\xed\xfa\xce"):
            fmt = "Mach-O 32-bit (macOS/iOS)"
        elif header.startswith(b"\xca\xfe\xba\xbe"):
            fmt = "Mach-O Universal / Fat Binary"
        elif header.startswith(b"MZ"):
            fmt = "PE / Windows Executable"

        entropy = _calc_entropy(full_data)
        packed_str = "⚠️ Packed or Encrypted (High Entropy)" if entropy > 7.1 else "Normal (Not Packed)"
        output.append(f"• Format: **{fmt}**")
        output.append(f"• Shannon Entropy: **{entropy} / 8.0** ({packed_str})")

        # Run system inspection tools if on macOS
        if sys.platform == "darwin" and shutil.which("otool"):
            try:
                res = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    libs = [l.strip() for l in res.stdout.splitlines()[1:] if l.strip()]
                    output.append(f"\n📚 Linked Dynamic Libraries ({len(libs)} total, showing first 5):\n" + "\n".join(f"  • {l.split()[0]}" for l in libs[:5]))
            except Exception:
                pass

        # String extraction
        strings = _extract_strings(full_data, min_len=5, max_strings=30)
        interesting = [s for s in strings if any(w in s.lower() for w in ("http", "error", "pass", "token", "key", "root", "admin", "debug"))]
        if interesting:
            output.append(f"\n🔍 Discovered Interesting Strings ({len(interesting)} found):\n" + "\n".join(f"  • {s}" for s in interesting[:10]))

    except Exception as e:
        output.append(f"Binary analysis error: {e}")

    return "\n".join(output)

def rea_tool(parameters: dict, player=None, session_memory=None) -> str:
    """Entry handler for rea_tool."""
    target_type = parameters.get("target_type", "api").lower().strip()
    target = parameters.get("target", "").strip()
    payload = parameters.get("payload")

    if not target:
        return "Please specify a target (URL, cURL command, APK path, or binary file path) to reverse engineer."

    if player:
        try: player.write_log(f"REA: Analyzing {target_type} target...")
        except Exception: pass

    if target_type in ("api", "http", "curl", "url", "web"):
        return reverse_api(target, payload)
    elif target_type in ("apk", "android"):
        return reverse_apk(target)
    elif target_type in ("binary", "exe", "macho", "elf", "dll", "dylib"):
        return reverse_binary(target)
    else:
        # Auto-detect target
        if target.endswith(".apk"):
            return reverse_apk(target)
        elif Path(target).is_file():
            return reverse_binary(target)
        else:
            return reverse_api(target, payload)

TOOL = {
    "name": "rea_tool",
    "description": (
        "Reverse Engineering Anything (REA) tool. Reverse engineers APIs, Android APKs, "
        "Native Binaries (Mach-O, ELF, PE), and Network requests. Extracts secrets, decodes JWT tokens, "
        "reconstructs endpoints, auto-generates Python/Node client code, detects app frameworks, "
        "inspects binary headers, analyzes entropy, and searches DEX/binary string tables."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_type": {
                "type": "STRING",
                "description": "api | apk | binary | auto (default: auto)",
            },
            "target": {
                "type": "STRING",
                "description": "The URL, cURL command, raw HTTP request, APK file path, or binary file path to reverse engineer",
            },
            "payload": {
                "type": "STRING",
                "description": "Optional payload data or request body for API reverse engineering",
            }
        },
        "required": ["target"],
    },
    "handler": rea_tool,
}
