#!/usr/bin/env python3
"""
recon — a passive OSINT / recon toolkit for the terminal.

  IP trace     -> DNS resolve + geoIP + RDAP/whois + traceroute
  Phone intel  -> E.164 parse, country / carrier / type / timezone

WHAT IT IS:
  recon collects ONLY publicly available information — the same kind of
  data a normal browser, DNS resolver, or `whois` client would collect.

  It does NOT scan, exploit, crack, or break into anything.Regardless

STANDALONE: Python 3.8+ stdlib only. No pip install required.
 Optional:
  pip install phonenumbers     -> richer phone metadata (carrier/validity)

Usage:
  python3 recon.py                          interactive menu
  python3 recon.py ip 8.8.8.8 --trace
  python3 recon.py ip example.com
  python3 recon.py phone "+44 7700 900123"
  python3 recon.py phone 07700900123 --country GB
  python3 recon.py --demo ip 8.8.8.8    (synthetic demo, no net)

Exit codes: 0 ok, 1 failure, 2 usage/acknowledgement.
  """

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

APP_NAME = "recon"
VERSION = "1.0.0"

DISCLAIMER = """\
""".strip()

BANNER = r"""\

  ██████  ███████ ██████   ██████  ███    ██
  ██    ██ ██      ██   ██ ██    ██ ████   ██
  ██    ██ █████   ██████  ██    ██ ██ ██  ██
  ██    ██ ██      ██   ██ ██    ██ ██  ██ ██
   ██████  ███████ ██   ██  ██████  ██   ███

        passive OSINT toolkit — trace IPs, locate phone numbers
""".strip("\n")

# ---- ANSI colors ---------------------------------------------------------

class C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"

USE_COLOR = True


def paint(code: str, text: str) -> str:
    if not USE_COLOR:
        return text
    return f"{code}{text}{C.RESET}"


def bold(t): return paint(C.BOLD, str(t))


def red(t): return paint(C.RED, str(t))


def green(t): return paint(C.GREEN, str(t))


def yellow(t): return paint(C.YELLOW, str(t))


def cyan(t): return paint(C.CYAN, str(t))


def dim(t): return paint(C.DIM, str(t))


# ---- TUI helpers (pure ANSI, zero deps) ---------------------------------

import shutil as _sh
import threading as _th
import itertools as _it

_BX = {
    "H": """─""", "V": """│""",
    "TL": """┌""", "TR": """┐""",
    "BL": """└""", "BR": """┘""",
    "LT": """├""", "RT": """┤""",
    "BB": """┬""", "TB": """┴""",
}

def _tw():
    try: return _sh.get_terminal_size().columns
    except: return 80

def box(msg, color=None):
    w = min(_tw()-4, 72)
    p = max(0, (_tw()-w)//2)
    h = _BX["H"]*(w-2)
    c = lambda t: color+t+C.RESET if color else t
    print(" "*p + c(_BX["TL"]) + c(h) + c(_BX["TR"]))
    for ln in msg.split(chr(92)+"n"):
        print(" "*p + c(_BX["V"]) + " " + (bold if USE_COLOR else str)(ln.center(w-6)) + " " + c(_BX["V"]))
    print(" "*p + c(_BX["BL"]) + c(h) + c(_BX["BR"]))

def hdr(t):
    print("")
    print("  " + cyan(_BX["BB"]) + " " + bold(t))

def ask(p):
    print("")
    print("  " + cyan(_BX["V"]) + " " + p)
    print("  " + cyan(_BX["LT"]) + cyan(_BX["H"]) + " ", end="")
    try:
        return input().strip()
    except:
        print()
        return ""

def ok(m): print("  " + green(chr(10003)) + " " + m)
def info(m): print("  " + cyan(chr(9433)) + " " + m)
def warn(m): print("  " + yellow(chr(9888)) + " " + m)
def fail(m): print("  " + red(chr(10007)) + " " + m)

def kv(k, v, c=""):
    vv = bold(v) if c else v
    print("    " + dim(k+":") + " " + (c+vv+C.RESET if c else vv))

class Spin:
    def __init__(self, m=""):
        self.m = m; self._r = False; self._t = None
    def start(self):
        self._r = True
        self._t = _th.Thread(target=self._run, daemon=True)
        self._t.start()
    def _run(self):
        ch = ["|", "/", "-", "\\"]
        while self._r:
            for c in ch:
                if not self._r: return
                sys.stdout.write(chr(13) + "  " + cyan(c) + " " + self.m + "   ")
                sys.stdout.flush(); time.sleep(0.1)
    def stop(self, ok=True):
        self._r = False
        if self._t: self._t.join(timeout=0.5)
        icon = green(chr(10003)) if ok else yellow(chr(9888))
        sys.stdout.write(chr(13) + "  " + icon + " " + self.m + "     " + chr(10))
        sys.stdout.flush()




# ---- country code table: cc (no "+") -> (iso2, full name) ----

CC_TABLE: Dict[str, Tuple[str, str]] = {
    "1": ("US", "United States / Canada (NANP)"),
    "20": ("EG", "Egypt"),
    "211": ("SS", "South Sudan"),
    "212": ("MA", "Morocco"),
    "213": ("DZ", "Algeria"),
    "216": ("TN", "Tunisia"),
    "218": ("LY", "Libya"),
    "220": ("GM", "Gambia"),
    "221": ("SN", "Senegal"),
    "222": ("MR", "Mauritania"),
    "223": ("ML", "Mali"),
    "224": ("GN", "Guinea"),
    "225": ("CI", "Cote d'Ivoire"),
    "226": ("BF", "Burkina Faso"),
    "227": ("NE", "Niger"),
    "228": ("TG", "Togo"),
    "229": ("BJ", "Benin"),
    "230": ("MU", "Mauritius"),
    "231": ("LR", "Liberia"),
    "232": ("SL", "Sierra Leone"),
    "233": ("GH", "Ghana"),
    "234": ("NG", "Nigeria"),
    "235": ("TD", "Chad"),
    "236": ("CF", "Central African Rep."),
    "237": ("CM", "Cameroon"),
    "238": ("CV", "Cape Verde"),
    "239": ("ST", "Sao Tome & Principe"),
    "240": ("GQ", "Equatorial Guinea"),
    "241": ("GA", "Gabon"),
    "242": ("CG", "Congo (Brazzaville)"),
    "243": ("CD", "DR Congo (Kinshasa)"),
    "244": ("AO", "Angola"),
    "245": ("GW", "Guinea-Bissau"),
    "248": ("SC", "Seychelles"),
    "249": ("SD", "Sudan"),
    "250": ("RW", "Rwanda"),
    "251": ("ET", "Ethiopia"),
    "252": ("SO", "Somalia"),
    "253": ("DJ", "Djibouti"),
    "254": ("KE", "Kenya"),
    "255": ("TZ", "Tanzania"),
    "256": ("UG", "Uganda"),
    "257": ("BI", "Burundi"),
    "258": ("MZ", "Mozambique"),
    "260": ("ZM", "Zambia"),
    "261": ("MG", "Madagascar"),
    "262": ("RE", "Reunion"),
    "263": ("ZW", "Zimbabwe"),
    "264": ("NA", "Namibia"),
    "265": ("MW", "Malawi"),
    "266": ("LS", "Lesotho"),
    "267": ("BW", "Botswana"),
    "268": ("SZ", "Eswatini"),
    "269": ("KM", "Comoros"),
    "27": ("ZA", "South Africa"),
    "290": ("SH", "Saint Helena"),
    "291": ("ER", "Eritrea"),
    "297": ("AW", "Aruba"),
    "298": ("FO", "Faroe Islands"),
    "299": ("GL", "Greenland"),
    "30": ("GR", "Greece"),
    "31": ("NL", "Netherlands"),
    "32": ("BE", "Belgium"),
    "33": ("FR", "France"),
    "34": ("ES", "Spain"),
    "350": ("GI", "Gibraltar"),
    "351": ("PT", "Portugal"),
    "352": ("LU", "Luxembourg"),
    "353": ("IE", "Ireland"),
    "354": ("IS", "Iceland"),
    "355": ("AL", "Albania"),
    "356": ("MT", "Malta"),
    "357": ("CY", "Cyprus"),
    "358": ("FI", "Finland"),
    "359": ("BG", "Bulgaria"),
    "36": ("HU", "Hungary"),
    "370": ("LT", "Lithuania"),
    "371": ("LV", "Latvia"),
    "372": ("EE", "Estonia"),
    "373": ("MD", "Moldova"),
    "374": ("AM", "Armenia"),
    "375": ("BY", "Belarus"),
    "376": ("AD", "Andorra"),
    "377": ("MC", "Monaco"),
    "378": ("SM", "San Marino"),
    "379": ("VA", "Vatican City"),
    "380": ("UA", "Ukraine"),
    "381": ("RS", "Serbia"),
    "382": ("ME", "Montenegro"),
    "383": ("XK", "Kosovo"),
    "385": ("HR", "Croatia"),
    "386": ("SI", "Slovenia"),
    "387": ("BA", "Bosnia & Herzegovina"),
    "389": ("MK", "North Macedonia"),
    "39": ("IT", "Italy"),
    "40": ("RO", "Romania"),
    "41": ("CH", "Switzerland"),
    "420": ("CZ", "Czechia"),
    "421": ("SK", "Slovakia"),
    "423": ("LI", "Liechtenstein"),
    "43": ("AT", "Austria"),
    "44": ("GB", "United Kingdom"),
    "45": ("DK", "Denmark"),
    "46": ("SE", "Sweden"),
    "47": ("NO", "Norway"),
    "48": ("PL", "Poland"),
    "49": ("DE", "Germany"),
    "51": ("PE", "Peru"),
    "52": ("MX", "Mexico"),
    "53": ("CU", "Cuba"),
    "54": ("AR", "Argentina"),
    "55": ("BR", "Brazil"),
    "56": ("CL", "Chile"),
    "57": ("CO", "Colombia"),
    "58": ("VE", "Venezuela"),
    "590": ("GP", "Guadeloupe"),
    "591": ("BO", "Bolivia"),
    "592": ("GY", "Guyana"),
    "593": ("EC", "Ecuador"),
    "594": ("GF", "French Guiana"),
    "595": ("PY", "Paraguay"),
    "596": ("MQ", "Martinique"),
    "597": ("SR", "Suriname"),
    "598": ("UY", "Uruguay"),
    "599": ("CW", "Curacao"),
    "60": ("MY", "Malaysia"),
    "61": ("AU", "Australia"),
    "62": ("ID", "Indonesia"),
    "63": ("PH", "Philippines"),
    "64": ("NZ", "New Zealand"),
    "65": ("SG", "Singapore"),
    "66": ("TH", "Thailand"),
    "670": ("TL", "Timor-Leste"),
    "673": ("BN", "Brunei"),
    "674": ("NR", "Nauru"),
    "675": ("PG", "Papua New Guinea"),
    "676": ("TO", "Tonga"),
    "677": ("SB", "Solomon Islands"),
    "678": ("VU", "Vanuatu"),
    "679": ("FJ", "Fiji"),
    "680": ("PW", "Palau"),
    "681": ("WF", "Wallis & Futuna"),
    "682": ("CK", "Cook Islands"),
    "683": ("NU", "Niue"),
    "685": ("WS", "Samoa"),
    "686": ("KI", "Kiribati"),
    "687": ("NC", "New Caledonia"),
    "688": ("TV", "Tuvalu"),
    "689": ("PF", "French Polynesia"),
    "690": ("TK", "Tokelau"),
    "691": ("FM", "Micronesia"),
    "692": ("MH", "Marshall Islands"),
    "7": ("RU", "Russia / Kazakhstan"),
    "81": ("JP", "Japan"),
    "82": ("KR", "South Korea"),
    "84": ("VN", "Vietnam"),
    "850": ("KP", "North Korea"),
    "852": ("HK", "Hong Kong"),
    "853": ("MO", "Macau"),
    "855": ("KH", "Cambodia"),
    "856": ("LA", "Laos"),
    "86": ("CN", "China"),
    "880": ("BD", "Bangladesh"),
    "886": ("TW", "Taiwan"),
    "90": ("TR", "Turkey"),
    "91": ("IN", "India"),
    "92": ("PK", "Pakistan"),
    "93": ("AF", "Afghanistan"),
    "94": ("LK", "Sri Lanka"),
    "95": ("MM", "Myanmar"),
    "960": ("MV", "Maldives"),
    "961": ("LB", "Lebanon"),
    "962": ("JO", "Jordan"),
    "963": ("SY", "Syria"),
    "964": ("IQ", "Iraq"),
    "965": ("KW", "Kuwait"),
    "966": ("SA", "Saudi Arabia"),
    "967": ("YE", "Yemen"),
    "968": ("OM", "Oman"),
    "970": ("PS", "Palestine"),
    "971": ("AE", "United Arab Emirates"),
    "972": ("IL", "Israel"),
    "973": ("BH", "Bahrain"),
    "974": ("QA", "Qatar"),
    "975": ("BT", "Bhutan"),
    "976": ("MN", "Mongolia"),
    "977": ("NP", "Nepal"),
    "98": ("IR", "Iran"),
    "992": ("TJ", "Tajikistan"),
    "993": ("TM", "Turkmenistan"),
    "994": ("AZ", "Azerbaijan"),
    "995": ("GE", "Georgia"),
    "996": ("KG", "Kyrgyzstan"),
    "998": ("UZ", "Uzbekistan"),
}


def cc_lookup(cc: str) -> Optional[Tuple[str, str, str]]:
    """Lookup country code; return (matched_prefix, iso2, country_name) or None."""
    cc = cc.lstrip("+")
    for end in (3, 2, 1):
        if len(cc) >= end:
            key = cc[:end]
            hit = CC_TABLE.get(key)
            if hit:
                return (key, hit[0], hit[1])
    return None


def iso2_to_cc(iso2: str) -> Optional[str]:
    iso2 = iso2.strip().upper()
    for cc, (code, _) in CC_TABLE.items():
        if code == iso2:
            return cc
    return None


# ---- generic helpers ------------------------------------------------------

UA = "recon/{v} (+passive OSINT tool; authorized use only)".format(v=VERSION)


def http_get(url: str, timeout: int = 12) -> Optional[str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def http_get_json(url: str, timeout: int = 12) -> Optional[Dict[str, Any]]:
    body = http_get(url, timeout=timeout)
    if body is None:
        return None
    try:
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def split_host_port(host: str) -> Tuple[str, Optional[int]]:
    if host.count(":") == 1 and not is_ip(host):
        h, _, port = host.rpartition(":")
        if port.isdigit():
            return h, int(port)
    return host, None


def resolve(host: str) -> Optional[List[str]]:
    host, _ = split_host_port(host)
    if is_ip(host):
        return [host]
    try:
        infos = socket.getaddrinfo(host, None)
        seen = []
        for info in sorted(infos, key=lambda i: i[0] != socket.AF_INET):
            ip = info[4][0]
            if ip not in seen:
                seen.append(ip)
        return seen if seen else None
    except socket.gaierror:
        return None
# ---- legal gate ------------------------------------------------------------


def acknowledge(args: argparse.Namespace) -> bool:
    if getattr(args, "yes", False):
        return True
    if not sys.stdin.isatty():
        return False
    print(red(DISCLAIMER))
    print()
    try:
        ans = input(bold("type 'yes' to acknowledge  (anything else cancels): ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return ans == "yes"


# ---- IP trace ---------------------------------------------------------------

DEMO_GEO = {
    "8.8.8.8": {
        "status": "success",
        "query": "8.8.8.8",
        "country": "United States",
        "countryCode": "US",
        "region": "California",
        "city": "Mountain View",
        "zip": "94043",
        "isp": "Google LLC",
        "org": "Google LLC",
        "as": "AS15169 Google LLC",
        "lat": 37.422,
        "lon": -122.084,
        "timezone": "America/Los_Angeles",
    },
}

DEMO_RDAP = {
    "8.8.8.8": {
        "handle": "NET-8-8-8-0-1",
        "name": "LVLT-ORG-8-8-8",
        "country": "US",
        "status": ["active"],
        "startAddress": "8.8.8.8",
        "endAddress": "8.8.8.8",
        "entities": ["Google LLC | GOGL"],
    },
}


def geoip_lookup(ip: str, demo: bool = False) -> Optional[Dict[str, Any]]:
    if demo:
        return DEMO_GEO.get(ip, {
            "status": "success", "query": ip,
            "country": "United States", "countryCode": "US",
            "region": "California", "city": "Mountain View",
            "zip": "94043", "isp": "Example ISP Inc",
            "org": "Example Co", "as": "AS64500 Example",
            "lat": 37.422, "lon": -122.084,
            "timezone": "America/Los_Angeles",
        })
    url = "http://ip-api.com/json/{}?fields=status,message,country,countryCode,region,regionName,city,zip,isp,org,as,lat,lon,timezone,query".format(ip)
    data = http_get_json(url)
    if data and data.get("status") == "success":
        return data
    data = http_get_json("https://ipwho.is/{}".format(ip))
    if data and data.get("success") is not False:
        conn = data.get("connection") or {}
        return {
            "status": "success", "query": ip,
            "country": data.get("country"),
            "countryCode": data.get("country_code"),
            "region": data.get("region"), "city": data.get("city"),
            "isp": conn.get("isp"), "org": conn.get("org"),
            "as": conn.get("asn"),
            "lat": data.get("latitude"), "lon": data.get("longitude"),
            "timezone": data.get("timezone"),
        }
    data = http_get_json("https://ipinfo.io/json/{}".format(ip))
    if data:
        loc = (data.get("loc") or "0,0").split(",")
        return {
            "status": "success", "query": ip,
            "country": data.get("country"),
            "region": data.get("region"), "city": data.get("city"),
            "org": data.get("org"),
            "lat": float(loc[0]) if len(loc) == 2 else None,
            "lon": float(loc[1]) if len(loc) == 2 else None,
            "timezone": data.get("timezone"),
        }
    return None

def extract_vcard_fn(vcard: Any) -> Optional[str]:
    if isinstance(vcard, list) and len(vcard) >= 2 and isinstance(vcard[1], list):
        for item in vcard[1]:
            if isinstance(item, list) and len(item) > 2 and str(item[0]).lower() == "fn":
                return str(item[2])
    return None


def rdap_lookup(target: str, demo: bool = False) -> Optional[Dict[str, Any]]:
    if demo:
        key = "NET-" + target.replace(".", "-")
        out = {"handle": key, "name": "EXAMPLE-" + key,
                "country": "US", "status": ["active"]}
        out["startAddress"] = target
        out["endAddress"] = target
        return out
    data = http_get_json("https://rdap.org/ip/{}".format(target))
    if not data:
        return None
    out = {}
    for k in ("handle", "name", "country", "status", "type",
              "parentHandle", "startAddress", "endAddress",
              "ipVersion", "port43"):
        if k in data and data[k]:
            out[k] = data[k]
    entities = data.get("entities")
    if isinstance(entities, list):
        names = []
        for e in entities[:8]:
            if not isinstance(e, dict):
                continue
            name = extract_vcard_fn(e.get("vcardArray"))
            roles = e.get("roles") if isinstance(e.get("roles"), list) else []
            role = ",".join(str(r) for r in roles)
            hand = e.get("handle")
            label = name or ""
            if role:
                label += " (" + role + ")"
            if hand:
                label += " | " + str(hand)
            if label:
                names.append(label)
        if names:
            out["entities"] = names[:6]
    return out if out else None


def whois_cli(target: str)-> Optional[str]:
    if shutil.which("whois") is None:
        return None
    try:
        proc = subprocess.run(["whois", target], capture_output=True, text=True,
                              timeout=20, env={**os.environ, "LC_ALL": "C"})
        return (proc.stdout or "")[:8000] or None
    except Exception:
        return None


def traceroute(target: str, timeout: int = 75)-> None:
    tools = (("traceroute", ["-m", "15", "-q", "1"]),
              ("tracepath", ["-m", "15"]))
    for tool, extra in tools:
        path = shutil.which(tool)
        if not path:
            continue
        print(cyan("  *  Running {} ...".format(tool)))
        try:
            proc = subprocess.Popen([path] + extra + [target], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            deadline = time.monotonic() + timeout
            try:
                for line in proc.stdout:
                    sys.stdout.write(dim(line.rstrip()) + "\n")
                    sys.stdout.flush()
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
 
                proc.kill
                print(yellow("  ^  traceroute timed out"))
            return
        except Exception:
            continue
    print(dim("  (no traceroute/tracepath found)"))


# ---- IP output --------------------------------------------------------------

GEO_FIELDS = (
    ("country", "Country"),
    ("region", "Region"),
    ("city", "City"),
    ("zip", "ZIP"),
    ("lat", "Latitude"),
    ("lon", "Longitude"),
    ("isp", "ISP"),
    ("org", "Organization"),
    ("as", "AS"),
    ("timezone", "Timezone"),
)


def print_geo(data: Dict[str, Any]) -> None:
    target = data.get("query") or data.get("ip") or "unknown"
    hdr("GEO-LOCATION")
    for key, title in GEO_FIELDS:

        raw = data.get(key)
        if raw is None:
            continue
        if str(raw) == "":
            continue
        if key == "as"and str(raw).isdigit():
            raw = "AS" + str(raw)
        if key in ("lat", "lon")and isinstance(raw, (int, float)):
            raw = "{:.5f}".format(raw)
        kv(title, str(raw))


def print_rdap(data: Dict[str, Any]) -> None:
    print("")
    hdr("REGISTRY")
    plain = (
        ("handle", "Handle"),
        ("name", "Net name"),
        ("country", "Country"),
        ("type", "Type"),
        ("status", "Status"),
        ("parentHandle", "Parent"),
        ("startAddress", "Start"),
        ("endAddress", "End"),
        ("ipVersion", "IP version"),
        ("port43", "WHOIS port"),
    )
    for key, title in plain:
        if key in data:
            val = data[key]
            if isinstance(val, list):
                val = ", ".join(str(v) for v in val)
            print("   " + dim(title) + ": " + bold(val))
    for ent in data.get("entities", []):

        print("   " + dim("Entity") + ": " + bold(ent))

# ---- IP command ---------------------------------------------------------------

def cmd_ip(args) -> int:
    target = (args.target or "").strip()
    if not target:
        print(red("no target given"))
        return 2
    ips = resolve(target)
    if not ips:
        print(red("cannot resolve " + str(target)))
        return 1
    is_literal = is_ip(target.split(":")[0])
    result = {"target": target, "resolved": ips}
    print(bold(BANNER))
    print(" Target: " + bold(target))
    if not is_literal:
        print(" Resolved: " + green(", ".join(ips)))
    if args.offline:
        print(dim("offline mode — no live lookups"))
    else:
        ip0 = ips[0]
        sp = Spin("Querying geoIP..."); sp.start()
        geo = geoip_lookup(ip0, demo=args.demo)
        sp.stop(bool(geo))
        if geo:
            result["geoip"] = geo
            print_geo(geo)
        else:
            print(yellow("geoIP lookup failed (no network / rate-limited?)"))
        if not getattr(args, "no_whois", False):
            sp = Spin("Querying registry..."); sp.start()
            reg = rdap_lookup(ip0, demo=args.demo)
            sp.stop(bool(reg))
            if reg:
                result["registry"] = reg
                print_rdap(reg)
            else:
                w = whois_cli(ip0)
                if w:
                    lines = [l for l in w.splitlines() if l.strip()][ :45]
                    print(bold(cyan("REGISTRY (WHOIS CLI)")))
                    for line in lines:
                        print("   " + dim(line))
                else:
                    print(yellow("no registry data (RDAP unreachable)"))
    if getattr(args, "trace", False)and not args.offline:
        print(" Tracing route to " + str(ips[0]))
        traceroute(ips[0])
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, default=str))
    return 0

# ---- phone intel ---------------------------------------------------------------

PHONE_TYPES = {
    0: "unknown",
    1: "fixed-line",
    2: "mobile",
    3: "fixed-line or mobile",
    4: "toll-free",
    5: "premium-rate",
    6: "shared-cost",
    7: "VoIP",
    8: "personal number",
    9: "pager",
    10: "UAN",
    11: "voicemail",
}


def normalize_phone(raw: str) -> str:
    for ch in (" ", "-", "(", ")", ".", "/", "\t"):
        raw = raw.replace(ch, "")
    return raw.strip()


def parse_e164(raw: str, country_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    s = normalize_phone(raw)
    if not s:
        return None
    explicit = s.startswith("+")
    if s.startswith("00")and len(s) > 2:
        explicit = True
        s = "+" + s[2:]
    if s.startswith("+"):
        rest = s[1:]
        if not rest.isdigit()or len(rest) > 15:
            return {"country_code": None, "iso2": None, "country": "unknown",
                    "national": rest, "e164": s, "possible": False,
                    "valid": False, "reason": "malformed E.164"}
        for end in (3, 2, 1):
            cc = rest[:end]
            hit = cc_lookup(cc)
            if hit:
                matched_cc, iso2, country = hit
                national = rest[len(matched_cc):]
                return {"country_code": matched_cc, "iso2": iso2, "country": country,
                        "national": national, "e164": "+" + matched_cc + national,
                        "possible": True, "valid": len(national) >= 3,
                        "reason": "international format"}
        return {"country_code": None, "iso2": None, "country": "unknown",
                "national": rest, "e164": s, "possible": False,
                "valid": False, "reason": "unknown country code"}
    if not country_hint:

        return {"country_code": None, "iso2": None, "country": None,
                "national": s, "e164": None, "possible": False,
                "valid": False, "reason": "local number needs --country CC"}
    if not s.isdigit():
        return {"country_code": None, "iso2": None, "country": None,
                "national": s, "e164": None, "possible": False,
                "valid": False, "reason": "not digits"}
    cc = iso2_to_cc(country_hint)
    if not cc:
        return {"country_code": None, "iso2": None,"country": None,
                "national": s, "e164": None, "possible": False,
                "valid":False, "reason": "unknown country"}
    iso2, country = None, None
    match_r = cc_lookup(cc)
    if match_r:
        cc, iso2, country = match_r
    national = s
    if cc == "1":
        if len(s) == 10:
            e164 = "+1" + s
        elif len(s) == 11 and s.startswith("1"):
            e164 = "+" + spp
            national = s[1:]
        else:
            return {"country_code": cc, "iso2": iso2, "country": country,
                    "national": s, "e164": None, "possible": False,
                    "valid": False, "reason": "US/CA numbers use 10 digits"}
    else:
        if national.startswith("0"):
            national = national[1:]
        elif national.startswith(cc)and len(national) > len(cc):
            national = national[len(cc):]
        e164 = "+" + cc + national
    return {"country_code": cc, "iso2": iso2, "country": country,
            "national": national, "e164": e164, "possible": True,
            "valid": len(national) > 0, "reason": "parsed as " + iso2 + " national"}

def phonenumbers_lookup(e164: str) -> Optional[Dict[str, Any]]:
    try:
        import phonenumbers
    except ImportError:
        return None
    try:
        from phonenumbers import PhoneNumberFormat as PNFchina
    except Exception:
        return None
    num = phonenumbers.parse(e164, None)
    out = {}
    out["valid"] = phonenumbers.is_valid_number(num)
    out["possible"] = phonenumbers.is_possible_number(num)
    out["e164"] = phonenumbers.format_number(num, PNF.E164)
    out["country_code"] = num.country_code
    try:
        out["region"] = phonenumbers.region_code_for_country_code(num.country_code)
    except Exception:
        out["region"] = None
    try:
        carr = phonenumbers.carrier.name_for_number(num, "en")
        if carr:
            out["carrier"] = carr
    except Exception:
        pass
    try:
        loc = phonenumbers.geocoder.description_for_number(num, "en")
        if loc:
            out["location"] = loc
    except Exception:
        pass
    try:
        tzs = phonenumbers.time_zones.time_zones_for_number(num)
        if tzs:
            out["timezones"] = sorted(set(tzs))
    except Exception:
        pass
    try:
        t = phonenumbers.number_type(num)
        out["type"] = PHONE_TYPES.get(t, "unknown")
    except Exception:
        out["type"] = "unknown"
    return out


def print_phone_local(parsed: Dict[str, Any], pn: Optional[Dict[str, Any]] = None) -> None:
    print("")
    hdr("PHONE NUMBER INTELLIGENCE")
    e164 = parsed.get("e164") or (pn or {}).get("e164")
    if e164:
        kv("E.164", e164)
    iso2 = parsed.get("iso2") or (pn or {}).get("region")
    if iso2:
        print("   Region: " + bold(str(iso2)))
    kv("Country", str(parsed.get("country") or "?"))
    if parsed.get("country_code"):
        print("   Code: " + bold(str(parsed["country_code"])))
    if pn:
        if pn.get("possible") is not None:
            print("   Possible: " + ("yes" if pn["possible"] else "no"))
        if pn.get("valid") is not None:
            print("   Valid: " + ("yes" if pn["valid"] else "no"))
        if pn.get("carrier"):
            print("   Carrier: " + bold(pn["carrier"]))
        if pn.get("location"):
            print("   Geo area: " + bold(pn["location"]))
        if pn.get("timezones"):
            print("   Timezones: " + bold(", ".join(str(t) for t in pn["timezones"])))
        if pn.get("type"):
            print("   Type: " + bold(pn["type"].title()))
    else:
        print("   (stdlib only — install phonenumbers for more))")
    if parsed.get("national"):
        print("   National part: " + bold(parsed["national"]))

    if parsed.get("reason"):
        print("   Note: " + str(parsed["reason"]))

def phone_online_lookup(e164: str) -> Optional[Dict[str, Any]]:
    key = os.environ.get("RECON_PHONE_API_KEY")
    if not key:
        return None
    provider = (os.environ.get("RECON_PHONE_PROVIDER") or "veriphone").lower()
    if provider == "veriphone":
        url = "https://api.veriphone.io/v2/verify?" + urllib.parse.urlencode({"phone": e164, "key": key})
    elif provider == "abstract":
        url = "https://phonevalidation.abstractapi.com/v1/?" + urllib.parse.urlencode({"api_key": key, "phone": e164})
    elif provider == "numverify":
        url = "https://apilayer.net/api/validate?" + urllib.parse.urlencode({"access_key": key, "number": e164})
    else:
        print(yellow("unknown RECON_PHONE_PROVIDER '" + provider + "'"))
        return None
    data = http_get_json(url)
    if not data:
        return None
    out = {}
    for src_key, dst_key in [
        ("phone_type", "Type"), ("line_type", "Type"), ("type", "Type"),
        ("carrier", "Carrier"),
        ("location", "Location"), ("country_name", "Location"),
        ("country_code", "Country code"),
        ("phone_valid", "API valid"), ("valid", "API valid"),
        ("country_prefix", "Prefix"),
    ]:
        val = data.get(src_key)
        if val not in (None, "", ""):
            out[dst_key] = str(val)
    if "Prefix" in out and out["Prefix"].isdigit():
        out["Prefix"] = "+" + out["Prefix"]
    if "API valid" in out:
        out["API valid"] = "yes" if out["API valid"].lower() in ("true", "yes", "1") else "no"
    return out if out else None


def cmd_phone(args) -> int:
    raw = (args.number or "").strip()
    if not raw:
        print(red("no phone number given"))
        return 2
    print(bold(BANNER))
    if args.demo:
        print(dim("(DEMO MODE — synthetic data, no network)"))
    parsed = parse_e164(raw, getattr(args, "country", None))
    if not parsed:
        print(red("could not parse that number"))
        return 2
    result = dict(parsed)
    pn = None
    if parsed.get("e164"):
        pn = phonenumbers_lookup(parsed["e164"])
    if args.demo and not pn:
        pn = {
            "possible": True, "valid": True,
            "carrier": "Telkomsel (demo)",
            "location": "Indonesia (demo)",
            "type": "mobile",
            "timezones": ["Asia/Jakarta"],
        }
    print_phone_local(parsed, pn)
    if pn:
        result["phonenumbers"] = {k: v for k, v in pn.items() if v is not None}
    if args.offline:
        print(dim("(offline mode — skipping live API)"))
    elif not args.demo:
        ext = phone_online_lookup(parsed.get("e164") or "")
        if ext:
            print("")
            print(bold(cyan("API ENRICHMENT")))
            for k, v in ext.items():
                print("   " + dim(k) + ": " + bold(v))
            result["live"] = ext
        else:
            print(dim("(no live enrichment — set RECON_PHONE_API_KEY for optional phone APIs)"))
    if getattr(args, "json", False):
        print("")
        print(json.dumps(result, indent=2, default=str))
    return 0



def cmd_menu(args) -> int:
    try:
        subprocess.call("clear" if sys.platform != "win32" else "cls", shell=True)
    except Exception:
        pass
    while True:
        print(bold(BANNER))
        print()
        box("  RECON - Passive OSINT Toolkit" + chr(92) + "n  IP | Phone | Social", C.CYAN)
        print()
        print("  " + cyan(_BX["V"]) + "  " + bold("1") + "  " + cyan("IP") + dim("    Trace address / hostname"))
        print("  " + cyan(_BX["V"]) + "  " + bold("2") + "  " + cyan("Phone") + dim("  Look up phone number"))
        print("  " + cyan(_BX["V"]) + "  " + bold("3") + "  " + cyan("Social") + dim(" Search social media"))
        print("  " + cyan(_BX["V"]) + "  " + bold("4") + "  " + cyan("About") + dim("  Legal info"))
        print("  " + cyan(_BX["V"]) + "  " + bold("q") + "  " + dim(" Quit"))
        print("  " + cyan(_BX["LT"]) + cyan(_BX["H"]) * 26)
        try:
            ch = input("  " + bold(">> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if ch in ("q","quit","exit",""):
            break
        if ch == "1":
            t = ask("Enter IP or hostname")
            if not t: continue
            s = argparse.Namespace(**vars(args))
            s.command = "ip"; s.target = t; s.no_whois = False; s.trace = False
            if not s.yes and not acknowledge(args): continue
            cmd_ip(s)
            print()
            input("  " + dim("Press Enter..."))
        elif ch == "2":
            n = ask("Phone number (use + for intl)")
            if not n: continue
            s = argparse.Namespace(**vars(args))
            s.command = "phone"; s.number = n; s.country = None
            if not s.yes and not acknowledge(args): continue
            cmd_phone(s)
            print()
            input("  " + dim("Press Enter..."))
        elif ch == "3":
            q = ask("Username or phone number")
            if not q: continue
            s = argparse.Namespace(**vars(args))
            s.command = "social"; s.query = q
            if not s.yes and not acknowledge(args): continue
            cmd_social(s)
            print()
            input("  " + dim("Press Enter..."))
        elif ch == "4":
            print(red(DISCLAIMER))
            print(dim("Sources: ip-api, ipwho, ipinfo, rdap.org"))
            print(dim("Optional: pip install phonenumbers"))
            input("  " + dim("Press Enter..."))
        else:
            warn("Pick 1-4 or q")
    print()
    return 0

SOCIAL_PLATFORMS = [
    ("Instagram", "https://www.instagram.com/{}/", "web", ""),
    ("Twitter/X", "https://x.com/{}/", "web", ""),
    ("TikTok", "https://www.tiktok.com/@{}/", "web", ""),
    ("Facebook", "https://www.facebook.com/{}/", "web", "often blocked"),
    ("YouTube", "https://www.youtube.com/@{}/", "web", ""),
    ("GitHub", "https://github.com/{}", "web", ""),
    ("Reddit", "https://www.reddit.com/user/{}/", "web", ""),
    ("LinkedIn", "https://www.linkedin.com/in/{}/", "web", "often blocked"),
    ("Snapchat", "https://www.snapchat.com/add/{}", "web", ""),
    ("Telegram", "https://t.me/{}", "web", ""),
    ("WhatsApp", "https://wa.me/{}", "web", "phone number"),
    ("Pinterest", "https://www.pinterest.com/{}/", "web", ""),
    ("Twitch", "https://www.twitch.tv/{}", "web", ""),
    ("Spotify", "https://open.spotify.com/user/{}", "web", ""),
    ("Medium", "https://medium.com/@{}/", "web", ""),
    ("DeviantArt", "https://www.deviantart.com/{}", "web", ""),
    ("Behance", "https://www.behance.net/{}", "web", ""),
    ("Keybase", "https://keybase.io/{}", "web", ""),
    ("Flickr", "https://www.flickr.com/people/{}/", "web", ""),
    ("Patreon", "https://www.patreon.com/{}", "web", ""),
    ("ProductHunt", "https://www.producthunt.com/@{}/", "web", ""),
    ("Hashnode", "https://hashnode.com/@{}/", "web", ""),
    ("Dev.to", "https://dev.to/{}", "web", ""),
    ("Codepen", "https://codepen.io/{}", "web", ""),
    ("Replit", "https://replit.com/@{}/", "web", ""),
    ("Steam", "https://steamcommunity.com/id/{}", "web", ""),
    ("About.me", "https://about.me/{}", "web", ""),
    ("Linktree", "https://linktr.ee/{}", "web", ""),
    ("BuyMeACoffee", "https://www.buymeacoffee.com/{}", "web", ""),
    ("Kofi", "https://ko-fi.com/{}", "web", ""),
    ("Bio.link", "https://bio.link/{}", "web", ""),
    ("Goodreads", "https://www.goodreads.com/{}", "web", ""),
    ("Last.fm", "https://www.last.fm/user/{}", "web", ""),
    ("SoundCloud", "https://soundcloud.com/{}", "web", ""),
    ("VK", "https://vk.com/{}", "web", "Russian platform"),
    ("Weibo", "https://weibo.com/{}", "web", "Chinese platform"),
    ("Threads", "https://www.threads.net/@{}/", "web", ""),
]
def social_check_web(platform, url):
    """Check if a profile URL exists via HTTP HEAD request."""
    req = urllib.request.Request(url, method="HEAD",
                                  headers={"User-Agent": UA, "Accept": "text/html"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        code = resp.getcode()
        if code is None:
            code = 200
        return 200 <= code < 400, code
    except urllib.error.HTTPError as e:
        return e.code in (200, 301, 302, 403), e.code
    except Exception:
        return None, None


def social_check_username(username, offline=False, demo=False):
    """Check if a username exists across social media platforms."""
    results = []
    username = username.strip()
    if not username:
        return results
    for name, url_tmpl, check_type, note in SOCIAL_PLATFORMS:
        if "{}" in url_tmpl:
            url = url_tmpl.replace("{}", username)
        else:
            url = url_tmpl
        entry = {"platform": name, "url": url, "type": check_type, "note": note}
        if demo:
            import random
            r = random.random()
            entry["exists"] = r > 0.55
            entry["code"] = 200 if entry["exists"] else 404
        elif offline:
            entry["exists"] = None
            entry["code"] = None
        else:
            exists, code = social_check_web(name, url)
            entry["exists"] = exists
            entry["code"] = code
        results.append(entry)
    return results


def print_social_results(results):
    """Print social media check results."""
    found = [r for r in results if r.get("exists") or (r.get("code") is not None and r.get("code") < 400)]
    if not found:
        print(dim("  No social media accounts found for this query"))
        return
    print("")
    hdr("SOCIAL MEDIA ACCOUNTS")
    for entry in found:
        url = entry.get("url", "")
        plat = entry.get("platform", "")
        note = entry.get("note") or ""
        code = entry.get("code")
        icon = green("✔") if entry.get("exists") else dim("?")
        extras = ""
        if note:
            extras += dim(" (" + note + ")")
        if code:
            extras += dim(" [HTTP " + str(code) + "]")
        print("   " + icon + " " + bold(plat) + ": " + cyan(url) + extras)
    print("")


def cmd_social(args):
    query = (args.query or "").strip()
    if not query:
        print(red("no target given (username or phone number)"))
        return 2
    print(bold(BANNER))
    print("  Target: " + bold(query))
    is_phone = query.startswith("+") or (query.isdigit() and len(query) > 6)
    if is_phone:
        print("  " + dim("(detected as phone number)"))
    else:
        print("  " + dim("(detected as username)"))
    results = social_check_username(query, offline=args.offline, demo=args.demo)
    print_social_results(results)
    if getattr(args, "json", False):
        print("--- JSON ---")
        print(json.dumps(results, indent=2, default=str))
    return 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="recon",
        description="passive OSINT toolkit — trace IPs, locate phone numbers (authorized use only)",
        epilog="examples:\n  recon ip 8.8.8 --trace\n  recon ip example.com\n  recon phone +628123456789\n  recon phone 08123456789 --country ID\n  recon --demo ip 8.8.8",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-color", action="store_true", help="disable colors")
    common.add_argument("-y", "--yes", action="store_true", help="skip legal prompt")
    common.add_argument("--offline", action="store_true", help="no network")
    common.add_argument("--demo", action="store_true", help="synthetic demo data")
    common.add_argument("--json", action="store_true", help="also print JSON output")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    sub = p.add_subparsers(dest="command")
    ip_p = sub.add_parser("ip", parents=[common], help="trace IP or hostname")
    ip_p.add_argument("target", help="IPv4/IPv6 address or hostname")
    ip_p.add_argument("--no-whois", action="store_true", help="skip registry lookup")
    ip_p.add_argument("--trace", action="store_true", help="also run traceroute")
    phone_p = sub.add_parser("phone", parents=[common], help="validate & locate a phone number")
    phone_p.add_argument("number", help="phone number e.g. +628123456789")
    phone_p.add_argument("-c", "--country", metavar="CC", help="ISO-2 country for local numbers")
    social_p = sub.add_parser("social", parents=[common], help="look up social media / username across platforms")
    social_p.add_argument("query", help="username or phone number to search for")
    p.set_defaults(command="menu")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    global USE_COLOR
    args = build_parser().parse_args(argv)
    USE_COLOR = sys.stdout.isatty() and not args.no_color
    if args.command == "menu":
        return cmd_menu(args)
    if args.command == "social":
        return cmd_social(args)
    if not acknowledge(args):
        print(red("you must acknowledge the legal notice first"))
        return 2
    if args.command == "ip":
        return cmd_ip(args)
    if args.command == "phone":
        return cmd_phone(args)
    print("unknown command: " + str(args.command))
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("")
        sys.exit(130)