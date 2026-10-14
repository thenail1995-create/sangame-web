#!/usr/bin/env python3
"""Máy bắt tin social Săn Game: đọc YouTube/Bluesky/RSS của các tài khoản game lớn, gom cụm, chấm điểm,
báo ntfy cụm nóng, ghi sổ lên Supabase (qua hàm sg-tin) cho hub theo dõi. (14/10/2026)

Chạy: python3 theo_doi_social.py [--dir <thư mục trạng thái>] [--thu]
  --thu : chế độ khô — đọc nguồn thật, in bảng, KHÔNG ntfy, KHÔNG POST, KHÔNG ghi file.
Trạng thái: social-da-thay.json (trong --dir; nhánh git riêng `theo-doi-social`). Nguồn: nguon-social.json (cùng thư mục).
Biến môi trường: NTFY_TIN (kênh ntfy), SG_TIN_URL + SG_TIN_KHOA (hàm sg-tin; thiếu thì chỉ in, không ghi).
Reddit: CHƯA hỗ trợ ở bản 1 (Reddit đòi OAuth cho dữ liệu; luật xoá nội dung).
Chỉ dùng thư viện chuẩn Python 3.12. Dùng lại helper của theo_doi_tin.py (chỉ import, không đổi hành vi).
"""
import argparse
import base64
import concurrent.futures
import copy
import datetime
import email.utils
import hashlib
import html
import json
import os
import pathlib
import re
import statistics
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import theo_doi_tin as cu  # noqa: E402  (http_get, tom_tat_rss, gui_mot, UA)

# ---- Cấu hình dễ sửa -------------------------------------------------------------------------
GIO_GIU = 48                 # giờ: chỉ giữ bài/cụm trong 48 giờ
GIO_CUM = 12                 # giờ: bài vào cụm có sẵn nếu cách bài mới nhất của cụm ≤ 12 giờ
GIO_CUM_TOI_DA = 24          # giờ: cụm không nhận bài mới sau 24 giờ kể từ bài đầu
JACCARD_CUNG_GAME = 0.2
JACCARD_KHAC = 0.4
NGUONG_BAO = 60
NGUONG_ANH = 40
ANH_TOI_DA_MOI_LUOT = 15
ANH_DOC_TOI_DA = 60_000      # dừng đọc khi vượt
ANH_TOI_DA_BYTE = 40_000     # ảnh > 40 KB thì bỏ (data URI phải ≤ 60.000 ký tự ở sg-tin)
ANH_THU_TOI_DA = 3
ANH_MOI_LO = 8
BAO_LUOT = 3
BAO_NGAY = 20
LO_TOI_DA = 200              # bài/cụm mỗi lô
LO_TOI_DA_BYTE = 700_000     # byte JSON UTF-8 thực của cả lô
CHO_TOI_DA = 2000            # bản ghi chờ ACK tối đa
BAI_TOI_DA, CUM_TOI_DA = 3000, 600
TRAN_TRANG_THAI = 1_000_000
LUONG = 8
TIMEOUT = 15
HAN_TOAN, HAN_DOC, HAN_ANH, HAN_NTFY, HAN_POST = 240, 120, 30, 15, 40   # giây
CHO_THU_LAI = 5
COOLDOWN_MAC_DINH, COOLDOWN_TOI_DA = 300, 3600
DON_SAU_GIO_VN = 3
GIO_VN = datetime.timezone(datetime.timedelta(hours=7))
# Opus 14/10 sau --thu thật: chính thức +30 làm 1 bài PR lẻ (Nintendo) đã 70 điểm -> hạ còn +20, nâng trần nguồn thêm +40,
# trừ 20 khi cụm không dính PlayStation (Săn Game chỉ theo mảng PlayStation).
DIEM_CHINH_THUC, DIEM_NGUON_THEM, DIEM_NGUON_TOI_DA = 20, 10, 40
DIEM_TU_KHOA, DIEM_TUONG_TAC, DIEM_TRU, DIEM_KHONG_PS = 20, 20, -10, -20
GAME_KHONG_PS = frozenset({"Switch 2", "Xbox"})
JACCARD_TRUNG = 0.85         # tiêu đề gần như y hệt (cùng video đăng ở 2 kênh) -> gom bất kể cửa sổ 12 giờ / loại sự kiện
TT_HE_SO, NEN_TOI_THIEU, NEN_GIU = 3, 5, 20
BLUESKY_LIMIT = 30

NHIEU_RE = re.compile(r"podcast|livestream replay|giveaway|happy birthday|sponsored|#ad\b", re.I)
PS_RE = re.compile(r"(?<!\w)(PS5|PS4|PS6|PlayStation|PS Plus|DualSense|PS Portal|PSVR2)(?!\w)", re.I)
TU_KHOA_SAN_GAME = ["PS Plus", "PlayStation Plus", "price", "sale", "discount", "release date", "launches", "pre-order",
                    "State of Play", "PS5 Pro"]
GAME_LON = [
    ("GTA 6", r"GTA\s*(?:6|VI)|Grand Theft Auto\s*(?:6|VI)"), ("Ghost of Yotei", r"Ghost of Y[oō]tei"),
    ("Marvel's Wolverine", r"Wolverine"), ("Death Stranding 2", r"Death Stranding"), ("007 First Light", r"007 First Light"),
    ("Resident Evil", r"Resident Evil"), ("Silent Hill f", r"Silent Hill"), ("Marathon", r"Marathon"),
    ("Fairgame$", r"Fairgames?\$?"), ("Intergalactic", r"Intergalactic"), ("The Witcher 4", r"Witcher\s*4"),
    ("Elden Ring", r"Elden Ring"), ("Monster Hunter", r"Monster Hunter"), ("Final Fantasy", r"Final Fantasy"),
    ("Kingdom Hearts", r"Kingdom Hearts"), ("Call of Duty", r"Call of Duty"), ("Battlefield 6", r"Battlefield\s*6"),
    ("EA Sports FC", r"EA Sports FC|EA FC"), ("Astro Bot", r"Astro Bot"), ("Gran Turismo", r"Gran Turismo"),
    ("Horizon", r"Horizon"), ("Spider-Man", r"Spider-?Man"), ("God of War", r"God of War"),
    ("The Last of Us", r"Last of Us"), ("Persona", r"Persona\s*\d?"), ("Metal Gear", r"Metal Gear"),
    ("Hollow Knight Silksong", r"Silksong"), ("Borderlands 4", r"Borderlands\s*4"),
    ("Assassin's Creed", r"Assassin[’']?s Creed"), ("Minecraft", r"Minecraft"), ("Fortnite", r"Fortnite"),
    ("Hogwarts Legacy", r"Hogwarts Legacy"), ("Cyberpunk", r"Cyberpunk"), ("Stellar Blade", r"Stellar Blade"),
    ("Black Myth", r"Black Myth"), ("Phantom Blade Zero", r"Phantom Blade"), ("Crimson Desert", r"Crimson Desert"),
    ("Onimusha", r"Onimusha"), ("Nioh 3", r"Nioh\s*3"), ("Pragmata", r"Pragmata"), ("PS Plus", r"PS Plus|PlayStation Plus"),
    ("State of Play", r"State of Play"), ("PS5 Pro", r"PS5 Pro"), ("PS6", r"PS6"), ("Switch 2", r"Switch 2"),
    ("Xbox", r"Xbox"),
]
# Loại sự kiện (ưu tiên từ trên xuống); 'khac' là ký tự đại diện: không chặn gom với loại nào.
LOAI_SU_KIEN = [
    ("gia_sale", r"price|sale\b|discount|deal\b|% off|\$\d"), ("ps_plus", r"ps plus|playstation plus|game catalog|ps extra|ps premium"),
    ("release_date", r"release date|launch(?:es|ing)? (?:on|in|date)|launches|out now|delayed|delay\b|coming (?:on|to|in)"),
    ("trailer", r"trailer|gameplay|teaser|reveal"), ("review", r"review|metacritic|opencritic"),
    ("phan_cung", r"ps5 pro|ps6|switch 2|dualsense|console|handheld|hardware|price hike"),
    ("nhan_su_studio", r"layoffs?|laid off|studio|joins|leaves|steps down|hires|director"),
    ("ro_ri", r"leak|rumou?r|reportedly|insider|allegedly"),
]
NHOM_HANG = {"chinh_thuc": 0, "bao": 1, "ro_ri": 2, "cong_dong": 3}
NHAN_THEO_NHOM = {"chinh_thuc": "CHINH_THUC", "bao": "BAO_LON", "ro_ri": "RO_RI", "cong_dong": "TIN_DON"}
TU_DUNG = frozenset("""the a an and or of to in on for with is are was were be been by at as it its this that from has have had will
new after now out says say about you your we our they their he she his her but not more into over up who what when how get gets
just here all can one""".split())

_GAME_RE = [(ten, re.compile(r"(?<!\w)(?:" + mau + r")(?!\w)", re.I)) for ten, mau in GAME_LON]
_SK_RE = [(k, re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)", re.I)) for k in TU_KHOA_SAN_GAME]
_LOAI_RE = [(k, re.compile(m, re.I)) for k, m in LOAI_SU_KIEN]
NS_YT = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015", "m": "http://search.yahoo.com/mrss/"}
DUONG_NGUON = pathlib.Path(__file__).resolve().parent / "nguon-social.json"


# ---- Thời gian -------------------------------------------------------------------------------
def bay_gio():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def doc_gio(s):
    if not isinstance(s, str) or not s.strip():
        return None
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.strip().replace("Z", "+00:00"))
    try:
        d = datetime.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d.replace(tzinfo=datetime.timezone.utc) if d.tzinfo is None else d.astimezone(datetime.timezone.utc)


def doc_gio_rss(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s.strip())
        return d.replace(tzinfo=datetime.timezone.utc) if d.tzinfo is None else d.astimezone(datetime.timezone.utc)
    except (TypeError, ValueError):
        return doc_gio(s)


def iso(d):
    return d.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def bai_id(mang, url):
    return hashlib.sha1(f"{mang}|{url}".encode()).hexdigest()


# ---- Phân tích từng loại nguồn (lỗi cú pháp -> ném lỗi = nguồn lỗi) ---------------------------
def sach(s, toi_da=None):
    van = re.sub(r"\s+", " ", html.unescape(html.unescape(re.sub(r"<[^>]+>", " ", s or "")))).strip()   # 2 lần: YouTube gửi "&amp;amp;"
    return van if toi_da is None or len(van) <= toi_da else van[:toi_da].rstrip() + "…"


def _so(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def phan_tich_youtube(xml_bytes):
    goc = ET.fromstring(xml_bytes)
    if not goc.tag.endswith("feed"):
        raise ValueError("không phải Atom YouTube")
    ra = []
    for e in goc.findall("a:entry", NS_YT):
        vid = (e.findtext("yt:videoId", "", NS_YT) or "").strip()
        tieu_de = sach(e.findtext("a:title", "", NS_YT))
        ngay = doc_gio(e.findtext("a:published", "", NS_YT))
        if not (vid and tieu_de and ngay):
            continue
        link = e.find("a:link[@rel='alternate']", NS_YT)
        url = link.get("href") if link is not None else f"https://www.youtube.com/watch?v={vid}"
        nhom = e.find("m:group", NS_YT)
        mo_ta = sach(nhom.findtext("m:description", "", NS_YT), 600) if nhom is not None else ""
        tt = {}
        st = nhom.find("m:community/m:statistics", NS_YT) if nhom is not None else None
        if st is not None and _so(st.get("views")) is not None:
            tt["views"] = _so(st.get("views"))
        sr = nhom.find("m:community/m:starRating", NS_YT) if nhom is not None else None
        if sr is not None and _so(sr.get("count")) is not None:
            tt["likes"] = _so(sr.get("count"))
        ra.append({"url": url, "tieu_de": tieu_de, "tom_tat": mo_ta, "dang_luc": ngay, "tuong_tac": tt,
                   "anh": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"})
    return ra


def _anh_bluesky(embed):
    if not isinstance(embed, dict):
        return None
    ext = embed.get("external")
    if isinstance(ext, dict) and ext.get("thumb"):
        return ext["thumb"]
    ims = embed.get("images")
    if isinstance(ims, list) and ims and isinstance(ims[0], dict) and ims[0].get("thumb"):
        return ims[0]["thumb"]
    return _anh_bluesky(embed.get("media"))


def phan_tich_bluesky(json_bytes, handle):
    d = json.loads(json_bytes)
    feed = d.get("feed")
    if not isinstance(feed, list):
        raise ValueError("Bluesky: thiếu feed")
    ra = []
    for it in feed:
        if not isinstance(it, dict) or it.get("reason"):  # bỏ bài repost của người khác
            continue
        p = it.get("post") or {}
        rec = p.get("record") or {}
        rkey = (p.get("uri") or "").rsplit("/", 1)[-1]
        ngay = doc_gio(rec.get("createdAt"))
        van = (rec.get("text") or "").strip()
        if not (rkey and ngay and (van or p.get("embed"))):
            continue
        emb = p.get("embed") or {}
        ext = emb.get("external") if isinstance(emb.get("external"), dict) else (emb.get("media") or {}).get("external") or {}
        dong = re.sub(r"https?://\S+", "", van.splitlines()[0] if van else "").strip()
        tieu_de = sach(dong, 140) or sach(ext.get("title"), 140) or sach(van, 140)
        if not tieu_de:
            continue
        tt = {k: p[f] for k, f in (("likes", "likeCount"), ("reposts", "repostCount"), ("replies", "replyCount"))
              if isinstance(p.get(f), int)}
        ra.append({"url": f"https://bsky.app/profile/{handle}/post/{rkey}", "tieu_de": tieu_de,
                   "tom_tat": sach(van, 600), "dang_luc": ngay, "tuong_tac": tt, "anh": _anh_bluesky(emb)})
    return ra


def phan_tich_rss_web(xml_bytes):
    """RSS 2.0 hoặc Atom. Bài thiếu tiêu đề/link/ngày thì bỏ."""
    goc = ET.fromstring(xml_bytes)
    ten = goc.tag.rsplit("}", 1)[-1]
    if ten == "rss" and goc.find("channel") is not None:
        muc = goc.find("channel").findall("item")
    elif ten == "feed":
        muc = goc.findall("{*}entry")
    else:
        raise ValueError("không phải RSS/Atom hợp lệ")
    ra = []
    for it in muc[:60]:
        tieu_de = sach(it.findtext("{*}title"))
        url = (it.findtext("link") or "").strip()
        if not url:
            for l in it.findall("{*}link"):
                if l.get("rel") in (None, "alternate") and l.get("href"):
                    url = l.get("href").strip()
                    break
        ngay = doc_gio_rss(it.findtext("pubDate")) or doc_gio(it.findtext("{*}published")) or doc_gio(it.findtext("{*}updated"))
        if not (tieu_de and url and ngay):
            continue
        tom = it.findtext("description") or it.findtext("{*}summary") or ""
        day_du = it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or it.findtext("{*}content") or ""
        anh = None
        for th in it.findall("{http://search.yahoo.com/mrss/}thumbnail"):
            if th.get("url"):
                anh = th.get("url")
                break
        if not anh:
            for mc in it.findall("{http://search.yahoo.com/mrss/}content") + it.findall("enclosure"):
                if mc.get("url") and (mc.get("medium") == "image" or (mc.get("type") or "").startswith("image/")):
                    anh = mc.get("url")
                    break
        ra.append({"url": url, "tieu_de": tieu_de, "tom_tat": cu.tom_tat_rss(tom) or cu.tom_tat_rss(day_du),
                   "dang_luc": ngay, "tuong_tac": {}, "anh": anh})
    return ra


# ---- Đọc nguồn -------------------------------------------------------------------------------
def tac_vu_cua(nguon):
    return [(n, m) for n in nguon for m in ("youtube", "bluesky", "rss") if n.get(m)]


def host_cua(url):
    return urllib.parse.urlsplit(url).netloc.lower()


def giay_cho_429(e):
    """Retry-After / ratelimit-reset (giây) -> cooldown, trần 1 giờ."""
    for k in ("Retry-After", "ratelimit-reset", "x-ratelimit-reset"):
        v = e.headers.get(k) if getattr(e, "headers", None) else None
        if v and str(v).strip().isdigit():
            return min(int(v), COOLDOWN_TOI_DA)
    return COOLDOWN_MAC_DINH


def url_nguon(n, mang):
    if mang == "youtube":
        return "https://www.youtube.com/feeds/videos.xml?channel_id=" + urllib.parse.quote(n["youtube"])
    if mang == "bluesky":
        return ("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=" + urllib.parse.quote(n["bluesky"])
                + f"&limit={BLUESKY_LIMIT}&filter=posts_no_replies")
    return n["rss"]


def doc_mot(n, mang, http, ngu, han, dong_ho, cooldown, now):
    """Đọc một (nguồn, mạng). Không bao giờ ném lỗi. 429 -> kq['cooldown']=(host, giây), không thử lại."""
    kq = {"nguon": n["khoa"], "mang": mang, "ten": n["ten"], "nhom": n["nhom"], "pub": n.get("publisher") or n["khoa"],
          "bc": bool(n.get("bo_cu")), "ok": False, "loi": None, "raw": []}
    url = url_nguon(n, mang)
    host = host_cua(url)
    ch = doc_gio(cooldown.get(host))
    if ch and ch > now:
        kq["loi"] = f"đang cooldown tới {iso(ch)}"
        return kq
    try:
        for lan in range(2):
            try:
                tho = http(url, headers=None, timeout=TIMEOUT)
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    kq["cooldown"] = (host, giay_cho_429(e))
                    raise
                if lan or (han is not None and dong_ho() + CHO_THU_LAI >= han):
                    raise
                ngu(CHO_THU_LAI)
            except Exception:
                if lan or (han is not None and dong_ho() + CHO_THU_LAI >= han):
                    raise
                ngu(CHO_THU_LAI)
        phan_tich = {"youtube": phan_tich_youtube, "bluesky": lambda b: phan_tich_bluesky(b, n["bluesky"]),
                     "rss": phan_tich_rss_web}[mang]
        kq["raw"] = phan_tich(tho)
        kq["ok"] = True
    except Exception as e:  # noqa: BLE001 — một nguồn lỗi không được kéo nguồn khác
        kq["loi"] = (f"{type(e).__name__}: {e}")[:300]
    return kq


def doc_tat_ca(nguon, http=cu.http_get, ngu=time.sleep, dong_ho=time.monotonic, ngan_sach=HAN_DOC, luong=LUONG,
               cooldown=None, now=None):
    han = dong_ho() + ngan_sach
    now = now or bay_gio()
    cooldown = cooldown or {}
    ra = []
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=luong)
    fut = {ex.submit(doc_mot, n, m, http, ngu, han, dong_ho, cooldown, now): (n, m) for n, m in tac_vu_cua(nguon)}
    xong, chua = concurrent.futures.wait(fut, timeout=max(0.0, han - dong_ho()))
    ra.extend(f.result() for f in xong)
    for f in chua:
        n, m = fut[f]
        ra.append({"nguon": n["khoa"], "mang": m, "ten": n["ten"], "nhom": n["nhom"], "pub": n.get("publisher") or n["khoa"],
                   "bc": bool(n.get("bo_cu")), "ok": False, "loi": "hết ngân sách thời gian", "raw": []})
    ex.shutdown(wait=False, cancel_futures=True)
    return ra


# ---- Chuẩn hoá -------------------------------------------------------------------------------
def tim_game(b):
    def tim(van):
        gap = [(m.start(), ten) for ten, re_ in _GAME_RE for m in [re_.search(van)] if m]
        return [t for _, t in sorted(gap)]
    ra = tim(b["tieu_de"])
    if not ra and b["mang"] == "bluesky":
        ra = tim(b.get("tom_tat") or "")
    return ra


def loai_su_kien(van):
    for k, re_ in _LOAI_RE:
        if re_.search(van):
            return k
    return "khac"


def gia_tri_tt(mang, tt, dang_luc, now):
    """(giá trị, đơn vị) tương tác để so với nền của chính tài khoản; None nếu chưa đủ điều kiện."""
    tuoi_gio = (now - dang_luc).total_seconds() / 3600
    if mang == "bluesky":
        if tuoi_gio < 1 or "likes" not in tt:
            return None
        return (tt.get("likes") or 0) + (tt.get("reposts") or 0), "likes+reposts"
    if mang == "youtube":
        if tt.get("views") is None:
            return None
        return tt["views"] / max(1.0, tuoi_gio), "views/gio"
    return None


def chuan_hoa(kq, now):
    ra, thay = [], set()
    han = now - datetime.timedelta(hours=GIO_GIU)
    for r in kq["raw"]:
        if r["dang_luc"] < han:
            continue
        van = r["tieu_de"] + (" " + (r.get("tom_tat") or "") if kq["mang"] == "bluesky" else "")
        if NHIEU_RE.search(van):
            continue
        bid = bai_id(kq["mang"], r["url"])
        if bid in thay:
            continue
        thay.add(bid)
        chu = r["tieu_de"] + " " + (r.get("tom_tat") or "")
        b = {"id": bid, "mang": kq["mang"], "nguon": kq["nguon"], "ten_nguon": kq["ten"], "nhom": kq["nhom"],
             "pub": kq.get("pub") or kq["nguon"], "bc": bool(kq.get("bc")), "url": r["url"], "tieu_de": r["tieu_de"][:300],
             "tom_tat": (r.get("tom_tat") or "")[:600], "dang_luc": r["dang_luc"], "tuong_tac": r["tuong_tac"],
             "anh": r.get("anh"), "ps": bool(PS_RE.search(chu)), "tu_khoa": [k for k, re_ in _SK_RE if re_.search(chu)],
             "loai": loai_su_kien(chu)}
        b["games"] = tim_game(b)
        ra.append(b)
    return ra


def nen_cua(kq, now):
    """Mẫu nền từ MỌI mục vừa đọc (kể cả cũ): [{i: id bài, v: giá trị, d: đơn vị, t: ngày đăng}], mới nhất trước, ≤ 20."""
    ra = []
    for r in sorted(kq["raw"], key=lambda x: x["dang_luc"], reverse=True):
        g = gia_tri_tt(kq["mang"], r["tuong_tac"], r["dang_luc"], now)
        if g:
            ra.append({"i": bai_id(kq["mang"], r["url"]), "v": g[0], "d": g[1], "t": iso(r["dang_luc"])})
    return ra[:NEN_GIU]


def tach_chu(s):
    s = html.unescape(s or "").casefold().replace("'", "").replace("’", "")
    return frozenset(w for w in re.findall(r"\w+", s) if w not in TU_DUNG and (w.isdigit() or len(w) >= 2))


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


# ---- Gom cụm + chấm điểm ---------------------------------------------------------------------
def chon_cum(tk, games, loai, dl, ci):
    """ci: chỉ mục cụm {cid: {'tk': [..], 'g': set, 'l': set loại cụ thể, 'cap': dt bài mới nhất, 'dau': dt bài đầu}}."""
    tot, tot_j = None, 0.0
    for cid, c in ci.items():
        j_trung = max((jaccard(tk, t) for t in c["tk"]), default=0.0)
        if j_trung >= JACCARD_TRUNG and abs((dl - c["cap"]).total_seconds()) <= GIO_GIU * 3600:
            if j_trung > tot_j:
                tot, tot_j = cid, j_trung
            continue
        if abs((dl - c["cap"]).total_seconds()) > GIO_CUM * 3600 or (dl - c["dau"]).total_seconds() > GIO_CUM_TOI_DA * 3600:
            continue
        if loai != "khac" and c["l"] and loai not in c["l"]:
            continue  # hai loại sự kiện cụ thể khác nhau -> không gom
        j = max((jaccard(tk, t) for t in c["tk"]), default=0.0)
        ok = (bool(set(games) & c["g"]) and j >= JACCARD_CUNG_GAME) if games else j >= JACCARD_KHAC
        if ok and j > tot_j:
            tot, tot_j = cid, j
    return tot


def cham_diem(tv):
    """tv: list rec bài trong cụm -> (điểm, chi tiết, nhãn). 'Nguồn thêm' đếm publisher khác nhau."""
    pub = {}
    for r in tv:
        pub.setdefault(r["p"], r["nh"])
    nhoms = {r["nh"] for r in tv}
    ct = {}
    if "chinh_thuc" in nhoms:
        ct["chinh_thuc"] = DIEM_CHINH_THUC
    them = min(max(0, len(pub) - 1) * DIEM_NGUON_THEM, DIEM_NGUON_TOI_DA)
    if them:
        ct["nguon_them"] = them
    if any(r.get("kw") or r.get("g") for r in tv):
        ct["tu_khoa"] = DIEM_TU_KHOA
    if any(r.get("ex") for r in tv):
        ct["tuong_tac"] = DIEM_TUONG_TAC
    if nhoms <= {"ro_ri", "cong_dong"}:
        ct["tru"] = DIEM_TRU
    if not any(r.get("ps") or any(g not in GAME_KHONG_PS for g in (r.get("g") or [])) for r in tv):
        ct["khong_ps"] = DIEM_KHONG_PS
    return max(0, min(100, sum(ct.values()))), ct, NHAN_THEO_NHOM[min(nhoms, key=lambda x: NHOM_HANG[x])]


def vuot_nen(b_id, v, don_vi, mau):
    gt = [s["v"] for s in mau if s["i"] != b_id and s["d"] == don_vi]
    return len(gt) >= NEN_TOI_THIEU and v > TT_HE_SO * max(statistics.median(gt), 1)


def xu_ly(tt_cu, bai_list, nen_moi, now, nguon_da_thay=frozenset()):
    """Gom cụm + chấm điểm. Trả (tt_moi, bai_thay_doi{id: bài}). tt_cu không bị sửa."""
    tt = copy.deepcopy(tt_cu) if tt_cu else {}
    for k in ("bai", "cum", "nen"):
        tt.setdefault(k, {})
    han = now - datetime.timedelta(hours=GIO_GIU)
    for bid in [k for k, r in tt["bai"].items() if (doc_gio(r["dl"]) or han) < han]:
        del tt["bai"][bid]
    # nền: gộp mẫu mới (theo id bài) vào mẫu cũ, giữ 20 mẫu mới nhất
    for k, mau in nen_moi.items():
        gop = {s["i"]: s for s in tt["nen"].get(k, [])}
        gop.update({s["i"]: s for s in mau})
        tt["nen"][k] = sorted(gop.values(), key=lambda s: s["t"], reverse=True)[:NEN_GIU]
    ci = {}
    for bid, r in tt["bai"].items():
        c = ci.setdefault(r["cum"], {"tk": [], "g": set(), "l": set(), "cap": None, "dau": None})
        c["tk"].append(frozenset(r["tk"].split()))
        c["g"].update(r.get("g") or [])
        if r.get("l") and r["l"] != "khac":
            c["l"].add(r["l"])
        d = doc_gio(r["dl"])
        c["cap"] = d if c["cap"] is None or d > c["cap"] else c["cap"]
        c["dau"] = d if c["dau"] is None or d < c["dau"] else c["dau"]
    thay_doi = {}
    for b in sorted(bai_list, key=lambda x: x["dang_luc"]):
        key = f"{b['nguon']}|{b['mang']}"
        g = gia_tri_tt(b["mang"], b["tuong_tac"], b["dang_luc"], now)
        vuot = bool(g and vuot_nen(b["id"], g[0], g[1], tt["nen"].get(key, [])))
        cu_rec = tt["bai"].get(b["id"])
        if cu_rec:
            if cu_rec["tt"] != b["tuong_tac"]:
                thay_doi[b["id"]] = b
            cu_rec["tt"] = b["tuong_tac"]
            cu_rec["ex"] = bool(cu_rec.get("ex") or vuot)
            b["cum_id"] = cu_rec["cum"]
            continue
        tk = tach_chu(b["tieu_de"])
        cid = chon_cum(tk, b["games"], b["loai"], b["dang_luc"], ci)
        if cid is None:
            cid = hashlib.sha1(("cum|" + b["id"]).encode()).hexdigest()
            ci[cid] = {"tk": [], "g": set(), "l": set(), "cap": b["dang_luc"], "dau": b["dang_luc"]}
        c = ci[cid]
        c["tk"].append(tk)
        c["g"].update(b["games"])
        if b["loai"] != "khac":
            c["l"].add(b["loai"])
        c["cap"], c["dau"] = max(c["cap"], b["dang_luc"]), min(c["dau"], b["dang_luc"])
        tt["bai"][b["id"]] = {"cum": cid, "dl": iso(b["dang_luc"]), "tk": " ".join(sorted(tk)), "tt": b["tuong_tac"],
                              "n": b["nguon"], "p": b["pub"], "bc": b["bc"], "nh": b["nhom"], "tn": b["ten_nguon"],
                              "m": b["mang"], "u": b["url"], "t": b["tieu_de"][:200], "g": b["games"], "l": b["loai"],
                              "kw": bool(b["tu_khoa"]), "ps": bool(b.get("ps")), "ex": vuot, "f": key not in nguon_da_thay,
                              "a": b["anh"] if (b.get("anh") and len(b["anh"]) <= 250) else None}
        b["cum_id"] = cid
        thay_doi[b["id"]] = b
    theo_cum = {}
    for r in tt["bai"].values():
        theo_cum.setdefault(r["cum"], []).append(r)
    cum_moi = {}
    for cid, tv in theo_cum.items():
        cc = tt["cum"].get(cid, {})
        diem, ct, nhan = cham_diem(tv)
        dau = min(tv, key=lambda r: (NHOM_HANG[r["nh"]], r["dl"]))
        games = Counter(g for r in tv for g in (r.get("g") or [])[:1])
        ten_pub = {}
        for r in sorted(tv, key=lambda r: NHOM_HANG[r["nh"]]):
            ten_pub.setdefault(r["p"], r["tn"])
        cum_moi[cid] = {
            "id": cid, "tieu_de": dau["t"], "chu_de": games.most_common(1)[0][0] if games else None, "nhan": nhan,
            "diem": diem, "chi_tiet_diem": ct, "so_nguon": len(ten_pub), "nguon": list(ten_pub.values()),
            "bat_dau": min(r["dl"] for r in tv), "cap_nhat": max(r["dl"] for r in tv), "url": dau["u"],
            "da_bao": bool(cc.get("da_bao")), "anh": bool(cc.get("anh")), "at": cc.get("at", 0), "hg": cc.get("hg", ""),
            "ff": all(r.get("f") for r in tv), "bc": all(r.get("bc") for r in tv),
            "a": [r["a"] for r in sorted(tv, key=lambda r: NHOM_HANG[r["nh"]]) if r.get("a")][:4],
            "yt": [r["u"] for r in tv if r["m"] == "youtube"][:3]}
    tt["cum"] = cum_moi
    return tt, thay_doi


# ---- Payload + hash -------------------------------------------------------------------------
def payload_bai(b):
    return {"id": b["id"], "mang": b["mang"], "nguon": b["nguon"], "ten_nguon": b["ten_nguon"], "nhom": b["nhom"],
            "url": b["url"], "tieu_de": b["tieu_de"], "tom_tat": b["tom_tat"], "dang_luc": iso(b["dang_luc"]),
            "tuong_tac": b["tuong_tac"], "cum_id": b.get("cum_id"), "ps": b["ps"], "tu_khoa": b["tu_khoa"]}


def payload_cum(c, anh=None):
    p = {"id": c["id"], "tieu_de": c["tieu_de"], "chu_de": c["chu_de"], "nhan": c["nhan"], "diem": c["diem"],
         "chi_tiet_diem": c["chi_tiet_diem"], "so_nguon": c["so_nguon"], "nguon": c["nguon"], "bat_dau": c["bat_dau"],
         "cap_nhat": c["cap_nhat"], "da_bao": c["da_bao"]}
    if anh:
        p["anh"] = anh
    return p


def hash_cum(c):
    return hashlib.sha1(json.dumps(payload_cum(c), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


# ---- Ảnh -------------------------------------------------------------------------------------
class _ChuyenHuong(urllib.request.HTTPRedirectHandler):
    max_redirections = 2


def tai_anh_mac_dinh(url):
    if not url.startswith("https://"):
        raise ValueError("chỉ nhận ảnh https")
    op = urllib.request.build_opener(_ChuyenHuong)
    with op.open(urllib.request.Request(url, headers=cu.UA), timeout=10) as r:
        return r.read(ANH_DOC_TOI_DA + 1)


def mime_anh(b):
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return None


def lay_anh(urls, tai=None):
    """Thử lần lượt; trả data URI của ảnh đầu tiên ≤ 40 KB có chữ ký byte hợp lệ, không có thì None. Không bao giờ ném lỗi."""
    tai = tai or tai_anh_mac_dinh
    for u in urls:
        try:
            b = tai(u)
        except Exception:  # noqa: BLE001
            continue
        if not b or len(b) > ANH_TOI_DA_BYTE:
            continue
        mime = mime_anh(b)
        if mime:
            return f"data:{mime};base64," + base64.b64encode(b).decode()
    return None


def url_anh_cum(c):
    ra = []
    for u in c.get("yt", []):
        m = re.search(r"[?&]v=([\w-]{6,})", u)
        if m:
            ra.append(f"https://i.ytimg.com/vi/{m.group(1)}/mqdefault.jpg")
    return ra + [u for u in c.get("a", []) if u not in ra]


def lay_anh_cum(tt, tai=None, han=None, dong_ho=time.monotonic):
    """Ảnh cho cụm điểm ≥ 40 chưa có ảnh (≤ 15/lượt, trong hạn pha). {cum_id: data_uri}; tăng 'at' khi không lấy được."""
    ra = {}
    ds = sorted((c for c in tt["cum"].values() if c["diem"] >= NGUONG_ANH and not c["anh"] and c["at"] < ANH_THU_TOI_DA),
                key=lambda c: -c["diem"])
    for c in ds[:ANH_TOI_DA_MOI_LUOT]:
        if han is not None and dong_ho() >= han:
            break
        d = lay_anh(url_anh_cum(c), tai)
        if d:
            ra[c["id"]] = d
        else:
            c["at"] += 1
    return ra


# ---- POST ------------------------------------------------------------------------------------
def kich_thuoc(p):
    return len(json.dumps(p, ensure_ascii=False).encode("utf-8")) + 1


def chia_lo(bai, cum, nguon, toi_da=LO_TOI_DA, toi_da_byte=LO_TOI_DA_BYTE, anh_moi_lo=None):
    """Lô {'bai','cum','nguon'}: mỗi loại ≤ toi_da phần tử, byte JSON thực ≤ toi_da_byte; anh_moi_lo: số cụm có ảnh tối đa/lô."""
    lo, hien, byte = [], {"bai": [], "cum": [], "nguon": []}, 100
    for loai, ds in (("cum", cum), ("bai", bai), ("nguon", nguon)):
        for p in ds:
            k = kich_thuoc(p)
            day = len(hien[loai]) >= (anh_moi_lo if (anh_moi_lo and loai == "cum") else toi_da)
            if (day or byte + k > toi_da_byte) and any(hien.values()):
                lo.append(hien)
                hien, byte = {"bai": [], "cum": [], "nguon": []}, 100
            hien[loai].append(p)
            byte += k
    if any(hien.values()):
        lo.append(hien)
    return lo


def goi_sg_tin(url, khoa, body, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "x-sg-khoa": khoa, **cu.UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            kq = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"sg-tin trả {e.code}: {e.read()[:200].decode('utf-8', 'replace')}") from None
    if not isinstance(kq, dict) or kq.get("loi") or not kq.get("ok"):
        raise RuntimeError(f"sg-tin lỗi: {str(kq)[:200]}")
    return kq


def _gui_lo(post, lo):
    """POST một lô; 413 -> chia đôi, thử lại mỗi nửa 1 lần. True nếu cả lô đã ACK."""
    try:
        post({"viec": "ghi", **lo})
        return True
    except Exception as e:  # noqa: BLE001
        if "413" not in str(e) or sum(len(v) for v in lo.values()) < 2:
            raise
    ok = True
    for i in (0, 1):
        nua = {k: (v[:len(v) // 2] if i == 0 else v[len(v) // 2:]) for k, v in lo.items()}
        if any(nua.values()):
            post({"viec": "ghi", **nua})
    return ok


def ghi_len_may_chu(tt, thay_doi, kqn, anh_moi, post, han=None, dong_ho=time.monotonic, log=print):
    """Đưa bản ghi vào hàng chờ chua_ghi (bai/cum/nguon), POST theo lô, chỉ xoá khỏi hàng sau ACK. Trả (lô ok, lô lỗi)."""
    cg = tt.setdefault("chua_ghi", {})
    for k in ("bai", "cum", "nguon"):
        cg.setdefault(k, {})
    for bid, b in thay_doi.items():
        cg["bai"][bid] = payload_bai(b)
    for c in tt["cum"].values():
        h = hash_cum(c)
        c["h"] = h
        if h != c.get("hg"):
            cg["cum"][c["id"]] = payload_cum(c)
            c["hg"] = h
    for k in kqn:
        cg["nguon"][f"{k['nguon']}|{k['mang']}"] = k
    tong = sum(len(v) for v in cg.values())
    if tong > CHO_TOI_DA:  # bỏ bài cũ nhất trước, in cảnh báo
        bo = sorted(cg["bai"].values(), key=lambda p: p["dang_luc"])[:tong - CHO_TOI_DA]
        for p in bo:
            del cg["bai"][p["id"]]
        log(f"CẢNH BÁO: hàng chờ ghi vượt {CHO_TOI_DA}, bỏ {len(bo)} bài cũ nhất.")
    ok_n = loi_n = 0

    def lam(lo, anh=None):
        nonlocal ok_n, loi_n
        if han is not None and dong_ho() >= han:
            loi_n += 1
            return False
        try:
            _gui_lo(post, lo)
        except Exception as e:  # noqa: BLE001
            loi_n += 1
            log(f"LỖI ghi lô lên sg-tin: {e} — giữ lại hàng chờ.")
            return False
        ok_n += 1
        for p in lo["bai"]:
            cg["bai"].pop(p["id"], None)
        for p in lo["cum"]:
            cg["cum"].pop(p["id"], None)
            if p.get("anh") and p["id"] in tt["cum"]:
                tt["cum"][p["id"]]["anh"] = True
        for p in lo["nguon"]:
            cg["nguon"].pop(f"{p['nguon']}|{p['mang']}", None)
        return True

    cum_thuong = [p for i, p in cg["cum"].items() if i not in anh_moi]
    for lo in chia_lo(list(cg["bai"].values()), cum_thuong, list(cg["nguon"].values())):
        if not lam(lo):
            break
    cum_anh = [payload_cum(tt["cum"][i], d) for i, d in anh_moi.items() if i in tt["cum"]]
    for lo in chia_lo([], cum_anh, [], anh_moi_lo=ANH_MOI_LO):
        if not lam(lo):
            break
    return ok_n, loi_n


# ---- ntfy + lệnh ----------------------------------------------------------------------------
def ngay_vn(now):
    return now.astimezone(GIO_VN).strftime("%Y-%m-%d")


def soan_bao(c):
    return {"title": f"🔥 {c['diem']} · {c['nhan']} · {c['tieu_de'][:70]}", "message": ", ".join(c["nguon"])[:400],
            "click": c["url"], "tags": ["fire", "satellite"]}


def bao_ntfy(tt, kenh, gui, now, han=None, dong_ho=time.monotonic, log=print):
    """Cụm ≥ 60 chưa báo -> ntfy (≤ 3/lượt, ≤ 20/ngày VN). da_bao chỉ đặt khi gửi 2xx; chưa gửi được nằm hàng chờ `cho_bao`.
    Cụm mà mọi bài đều của nguồn lần đầu, hoặc đều thuộc publisher bộ cũ (theo_doi_tin.py), thì đánh dấu đã báo âm thầm."""
    cum = tt["cum"]
    dat = [c for c in cum.values() if c["diem"] >= NGUONG_BAO and not c["da_bao"]]
    for c in dat:
        if c.get("ff") or c.get("bc"):
            c["da_bao"] = True
    dat = [c for c in dat if not c["da_bao"]]
    hang = [i for i in tt.get("cho_bao", []) if i in cum and cum[i] in dat]
    queue = [cum[i] for i in hang] + sorted((c for c in dat if c["id"] not in hang), key=lambda c: -c["diem"])
    ngay = ngay_vn(now)
    dem = tt.get("bao_ngay") or {}
    da_ngay = dem.get("n", 0) if dem.get("ngay") == ngay else 0
    suat = max(0, min(BAO_LUOT, BAO_NGAY - da_ngay))
    da = 0
    if not kenh:
        for c in queue[:BAO_LUOT]:
            log(f"(không có NTFY_TIN) SẼ BÁO: {soan_bao(c)['title']} — {c['url']}")
    else:
        for c in queue:
            if da >= suat or (han is not None and dong_ho() >= han):
                break
            try:
                gui({"topic": kenh, **soan_bao(c)})
            except Exception as e:  # noqa: BLE001
                log(f"LỖI gửi ntfy: {e} — giữ hàng chờ.")
                break
            c["da_bao"] = True
            da += 1
    tt["bao_ngay"] = {"ngay": ngay, "n": da_ngay + da}
    tt["cho_bao"] = [c["id"] for c in queue if not c["da_bao"]][:100]
    return da


def xu_ly_lenh(post, kenh, gui, tt, log=print):
    """Giai đoạn 1: lệnh video -> 1 ntfy rồi cap_nhat_lenh xong; lệnh dang để nguyên 'cho'. Cập nhật lỗi thì nhớ để lượt sau gửi lại."""
    cg = tt.setdefault("chua_ghi", {})
    lenh_cho = cg.setdefault("lenh", {})
    for i, body in list(lenh_cho.items()):
        try:
            post(body)
            del lenh_cho[i]
        except Exception as e:  # noqa: BLE001
            log(f"LỖI gửi lại cap_nhat_lenh {i}: {e}")
    kq = post({"viec": "doc_lenh"})
    xong = 0
    for l in kq.get("lenh") or []:
        if l.get("loai") != "video" or l.get("id") in lenh_cho:
            continue
        tieu = l.get("tieu_de") or l.get("cum_id") or "?"
        if not kenh:
            log(f"(không có NTFY_TIN) lệnh video chưa gửi được: {tieu}")
            continue
        try:
            gui({"topic": kenh, "title": f"🎬 Hào xếp làm video: {tieu}"[:200], "message": tieu[:400], "tags": ["clapper"]})
        except Exception as e:  # noqa: BLE001
            log(f"LỖI ntfy lệnh video {l.get('id')}: {e} — lượt sau thử lại.")
            continue
        body = {"viec": "cap_nhat_lenh", "id": l["id"], "trang_thai": "xong", "ket_qua": {"ntfy": True}}
        try:
            post(body)
        except Exception as e:  # noqa: BLE001
            lenh_cho[l["id"]] = body  # đã gửi ntfy rồi: nhớ cập nhật lại, đừng gửi ntfy lần nữa
            log(f"LỖI cập nhật lệnh {l['id']}: {e}")
        xong += 1
    return xong


# ---- Chạy ------------------------------------------------------------------------------------
def doc_json(p, mac_dinh):
    p = pathlib.Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else mac_dinh


def ghi_json(p, obj):
    pathlib.Path(p).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def thu_nho(tt):
    """bai ≤ 3.000, cum ≤ 600, file ≤ 1 MB: cắt cũ nhất."""
    def bo_bai(ids):
        for k in ids:
            tt["bai"].pop(k, None)
    if len(tt["bai"]) > BAI_TOI_DA:
        bo_bai(sorted(tt["bai"], key=lambda k: tt["bai"][k]["dl"])[:len(tt["bai"]) - BAI_TOI_DA])
    if len(tt["cum"]) > CUM_TOI_DA:
        cu_nhat = sorted(tt["cum"], key=lambda k: tt["cum"][k]["cap_nhat"])[:len(tt["cum"]) - CUM_TOI_DA]
        bo_bai([k for k, r in tt["bai"].items() if r["cum"] in cu_nhat])
        for k in cu_nhat:
            tt["cum"].pop(k, None)
    while len(json.dumps(tt, ensure_ascii=False).encode()) > TRAN_TRANG_THAI and tt["bai"]:
        bo_bai(sorted(tt["bai"], key=lambda k: tt["bai"][k]["dl"])[:max(1, len(tt["bai"]) // 10)])
    return tt


def ket_qua_nguon(kq, hop_le, now):
    return {"nguon": kq["nguon"], "mang": kq["mang"], "ten": kq["ten"], "nhom": kq["nhom"], "lan_doc": iso(now),
            "ok": kq["ok"], "loi": kq["loi"], "so_bai": len(hop_le),
            "bai_moi_nhat": iso(max(b["dang_luc"] for b in hop_le)) if hop_le else None}


def in_bang(ket_qua, tt, thoi_gian):
    theo = {}
    for k in ket_qua:
        d = theo.setdefault(k["mang"], [0, 0])
        d[0 if k["ok"] else 1] += 1
    print(f"Nguồn: {sum(d[0] for d in theo.values())} ok / {sum(d[1] for d in theo.values())} lỗi — "
          + ", ".join(f"{m}: {d[0]} ok {d[1]} lỗi" for m, d in sorted(theo.items())))
    for k in ket_qua:
        if not k["ok"]:
            print(f"  LỖI {k['nguon']} [{k['mang']}]: {k['loi']}")
    top = sorted(tt["cum"].values(), key=lambda c: c["cap_nhat"], reverse=True)
    top = sorted(top, key=lambda c: -c["diem"])[:15]
    print(f"{len(tt['bai'])} bài ≤48 giờ, {len(tt['cum'])} cụm. Top {len(top)} cụm:")
    for c in top:
        print(f"  {c['diem']:3d} · {c['nhan']:<10} · {c['so_nguon']} nguồn · {c['tieu_de'][:90]}")
    print(f"Thời gian chạy: {thoi_gian:.1f} giây")


def can_don(tt, now):
    """Dọn DB một lần mỗi ngày VN, lượt đầu tiên sau 03:00."""
    v = now.astimezone(GIO_VN)
    return v.hour >= DON_SAU_GIO_VN and tt.get("don_ngay") != ngay_vn(now)


def chay(thu_muc, thu=False, nguon=None, ket_qua_doc=None, http=cu.http_get, ngu=time.sleep, gio=None, kenh=None,
         gui=None, post=None, url_sg=None, khoa_sg=None, tai_anh=None, dong_ho=time.monotonic, log=print):
    """Một lượt, hạn chót toàn lượt HAN_TOAN giây chia pha (đọc 120, ảnh 30, ntfy 15, POST 40). Trả tt_moi."""
    bat_dau = dong_ho()
    han_toan = bat_dau + HAN_TOAN
    gio = gio or bay_gio
    now = gio()
    thu_muc = pathlib.Path(thu_muc)
    f_tt = thu_muc / "social-da-thay.json"
    tt_cu = doc_json(f_tt, {})
    nguon = nguon if nguon is not None else json.loads(DUONG_NGUON.read_text(encoding="utf-8"))
    url_sg = url_sg if url_sg is not None else os.environ.get("SG_TIN_URL", "").strip()
    khoa_sg = khoa_sg if khoa_sg is not None else os.environ.get("SG_TIN_KHOA", "").strip()
    kenh = kenh if kenh is not None else os.environ.get("NTFY_TIN", "").strip()
    gui = gui or cu.gui_mot
    if post is None and url_sg and khoa_sg:
        post = lambda body: goi_sg_tin(url_sg, khoa_sg, body)  # noqa: E731
    cooldown = {h: t for h, t in (tt_cu.get("cooldown") or {}).items() if (doc_gio(t) or now) > now}
    if ket_qua_doc is None:
        ket_qua_doc = doc_tat_ca(nguon, http=http, ngu=ngu, dong_ho=dong_ho, ngan_sach=min(HAN_DOC, han_toan - bat_dau),
                                 cooldown=cooldown, now=now)
    bai_list, nen_moi, kqn = [], {}, []
    for kq in ket_qua_doc:
        hop_le = chuan_hoa(kq, now) if kq["ok"] else []
        bai_list.extend(hop_le)
        if kq["ok"]:
            nen_moi[f"{kq['nguon']}|{kq['mang']}"] = nen_cua(kq, now)
        if kq.get("cooldown"):
            cooldown[kq["cooldown"][0]] = iso(now + datetime.timedelta(seconds=kq["cooldown"][1]))
        kqn.append(ket_qua_nguon(kq, hop_le, now))
    da_thay = set(tt_cu.get("nguon_da_thay") or [])
    tt, thay_doi = xu_ly(tt_cu, bai_list, nen_moi, now, da_thay)
    tt["cooldown"] = cooldown
    tt["nguon_da_thay"] = sorted(da_thay | {f"{k['nguon']}|{k['mang']}" for k in ket_qua_doc if k["ok"]})
    if thu:
        in_bang(kqn, tt, dong_ho() - bat_dau)
        print(f"(--thu) {len(thay_doi)} bài mới/đổi; không ntfy, không POST, không ghi file.")
        return tt
    tt["chua_ghi"] = tt_cu.get("chua_ghi", {})
    tt["cho_bao"] = tt_cu.get("cho_bao", [])
    for k in ("bao_ngay", "don_ngay"):
        if k in tt_cu:
            tt[k] = tt_cu[k]
    han_ntfy = min(dong_ho() + HAN_NTFY, han_toan)
    bao_ntfy(tt, kenh, gui, now, han_ntfy, dong_ho, log)
    if post is not None:
        try:
            xu_ly_lenh(post, kenh, gui, tt, log)
        except Exception as e:  # noqa: BLE001
            log(f"LỖI đọc lệnh từ sg-tin: {e}")
        anh_moi = lay_anh_cum(tt, tai_anh, min(dong_ho() + HAN_ANH, han_toan), dong_ho)
        ok_n, loi_n = ghi_len_may_chu(tt, thay_doi, kqn, anh_moi, post, min(dong_ho() + HAN_POST, han_toan), dong_ho, log)
        log(f"Ghi sg-tin: {ok_n} lô ok, {loi_n} lô lỗi, còn chờ {sum(len(v) for v in tt['chua_ghi'].values())} bản ghi.")
        if can_don(tt, now):
            try:
                post({"viec": "don"})
                tt["don_ngay"] = ngay_vn(now)
            except Exception as e:  # noqa: BLE001
                log(f"LỖI dọn sg-tin: {e}")
    else:
        log(f"Không có SG_TIN_URL/SG_TIN_KHOA — chỉ in: {len(thay_doi)} bài, {len(tt['cum'])} cụm.")
        tt["chua_ghi"] = {}
        for c in tt["cum"].values():
            c["hg"] = ""
    thu_nho(tt)
    if tt != tt_cu:
        thu_muc.mkdir(parents=True, exist_ok=True)
        ghi_json(f_tt, tt)
    print(f"Xong: {len(bai_list)} bài đọc được, {len(thay_doi)} mới/đổi, {len(tt['cum'])} cụm.")
    return tt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=".", help="thư mục chứa social-da-thay.json")
    ap.add_argument("--thu", action="store_true", help="chế độ khô: đọc thật, in bảng, không ntfy/POST/ghi file")
    a = ap.parse_args(argv)
    try:
        chay(a.dir, thu=a.thu)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
