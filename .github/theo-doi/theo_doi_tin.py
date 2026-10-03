#!/usr/bin/env python3
"""Theo dõi tin PlayStation (blog, PS Store, PS Plus) và báo điện thoại qua ntfy.

Chạy: python3 theo_doi_tin.py [--dir <thư mục trạng thái>] [--thu]
  --thu : chế độ khô — đọc nguồn thật, in ra, KHÔNG gửi ntfy, KHÔNG ghi file trạng thái.
Trạng thái: tin-da-thay.json; hàng đợi cho phụ tá viết bài: tin-moi.json (cả hai nằm trong --dir).
Kênh ntfy lấy từ biến môi trường NTFY_TIN (không có thì chỉ in ra).
Gọi viết tin (Hào 03/10): có tin đáng viết thì tạo GitHub release `viet-*` (cần GITHUB_TOKEN + GITHUB_REPOSITORY, không có thì chỉ in).
Chỉ dùng thư viện chuẩn Python 3.12.
"""
import argparse
import datetime
import email.utils
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zoneinfo

# ---- Cấu hình dễ sửa -------------------------------------------------------------------------
TU_KHOA_HOT = [
    "PlayStation Plus", "PS Plus", "State of Play", "Days of Play", "sale", "discount", "pre-order", "price",
    "PS5 Pro", "free", "launches", "out now", "God of War", "Marvel", "Spider-Man", "Wolverine", "Ghost of",
    "Horizon", "Gran Turismo", "The Last of Us", "Astro Bot", "Death Stranding", "GTA", "Resident Evil",
    "Final Fantasy", "Call of Duty", "EA Sports FC",
]
FEEDS = {
    "blog": "https://blog.playstation.com/feed/",
    "blog-ps-plus": "https://blog.playstation.com/category/ps-plus/feed/",
}
NGUON_TEN = {"blog": "PlayStation Blog", "blog-ps-plus": "PlayStation Blog (PS Plus)"}
DEALS_ID = "3f772501-f6f8-49b7-abac-874a88ca4897"
EXTRA_ID = "3a7006fe-e26f-49fe-87e5-4473d7ed0fb2"
VUNG_DEALS = ["en-US", "en-SG"]
VUNG_EXTRA = ["en-SG"]
GAMES_PLUS_URL = "https://www.playstation.com/bin/imagic/gameslist?locale=en-sg&categoryList=plus-monthly-games-list"
HASH_GRID = "88c0b9a1273c6d320c51cd73e390924e21ae28bf09f01cde8b84b1034b16cd03"
NGUONG_DEALS = 0.15
GIU_GUID = 300
GIU_TIN = 200
TOI_DA_THONG_BAO = 8
CHO_THU_LAI = (5, 15)  # giây; 1 lần đầu + 2 lần thử lại
TIMEOUT_YEU_CAU = 15  # giây mỗi request
NGAN_SACH_NGUON = 240  # giây tổng cho mọi nguồn một lượt
CUA_SO = 12  # số mẫu Deals/Extra giữ lại
LAN_GUI_TOI_DA = 3
GOP_TOI_DA_BYTE = 3500
VIET_GIAN_GIO = 3  # giờ tối thiểu giữa 2 lần gọi viết (Hào 03/10)
VIET_TOI_DA = 5  # tin tối đa mỗi lần gọi viết
VIET_HAN_GIO = 72  # chỉ viết tin trong 72 giờ gần nhất
VIET_GIU_NGAY = 7  # release viet-* cũ hơn số ngày này thì xoá
LOAI_BLOG_RE = re.compile(r"podcast|share of the week|blogcast|this week in playstation", re.I)
API_GITHUB = "https://api.github.com"
UA = {"User-Agent": "Mozilla/5.0"}
NTFY_URL = "https://ntfy.sh/"
GIO_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")

_HOT_RE = [(k, re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)", re.I)) for k in TU_KHOA_HOT]


def bay_gio():
    return datetime.datetime.now(GIO_VN).replace(microsecond=0).isoformat()


# ---- Đọc nguồn -------------------------------------------------------------------------------
def http_get(url, headers=None, timeout=TIMEOUT_YEU_CAU):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout).read()


class HetNganSach(Exception):
    pass


def voi_thu_lai(ham, ngu=time.sleep, dong_ho=time.monotonic, han=None):
    """Gọi ham(); lỗi thì chờ 5s rồi 15s thử lại; vẫn lỗi thì ném lỗi cuối. Quá hạn `han` (giờ dong_ho) thì bỏ."""
    for i in range(len(CHO_THU_LAI) + 1):
        if han is not None and dong_ho() >= han:
            raise HetNganSach("hết ngân sách thời gian")
        try:
            return ham()
        except Exception:
            if i == len(CHO_THU_LAI):
                raise
            if han is not None and dong_ho() + CHO_THU_LAI[i] >= han:
                raise HetNganSach("hết ngân sách thời gian")
            ngu(CHO_THU_LAI[i])


def phan_tich_rss(xml_bytes):
    """RSS 2.0 -> [{guid, tieu_de, url, ngay, the_loai}]. Ngày đổi sang giờ VN (ISO)."""
    goc = ET.fromstring(xml_bytes)
    if goc.tag != "rss" or goc.find("channel") is None:
        raise ValueError("không phải RSS hợp lệ (thiếu rss/channel)")
    ra = []
    for it in goc.find("channel").findall("item"):
        tieu_de = (it.findtext("title") or "").strip()
        url = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or url).strip()
        if not (tieu_de and guid):  # bài thiếu tiêu đề hoặc cả guid lẫn link thì bỏ
            continue
        ngay = ""
        pd = it.findtext("pubDate")
        if pd:
            try:
                ngay = email.utils.parsedate_to_datetime(pd).astimezone(GIO_VN).replace(microsecond=0).isoformat()
            except (TypeError, ValueError):
                ngay = ""
        the_loai = [c.text.strip() for c in it.findall("category") if c.text and c.text.strip()]
        ra.append({"guid": guid, "tieu_de": tieu_de, "url": url, "ngay": ngay or bay_gio(), "the_loai": the_loai})
    if not ra:
        raise ValueError("RSS không có bài nào có guid/link — coi là nguồn lỗi")
    return ra


def lay_feed(url, http=http_get):
    return phan_tich_rss(http(url))


def lay_tong_grid(cat, loc, http=http_get):
    v = {"id": cat, "pageArgs": {"size": 1, "offset": 0}, "sortBy": None, "filterBy": [], "facetOptions": []}
    ext = {"persistedQuery": {"version": 1, "sha256Hash": HASH_GRID}}
    url = ("https://web.np.playstation.com/api/graphql/v1/op?operationName=categoryGridRetrieve"
           f"&variables={urllib.parse.quote(json.dumps(v))}&extensions={urllib.parse.quote(json.dumps(ext))}")
    data = json.loads(http(url, {"x-psn-store-locale-override": loc, "apollo-require-preflight": "true",
                                 "content-type": "application/json"}))
    if "errors" in data:
        raise RuntimeError(f"PS Store báo lỗi: {data['errors']}")
    tong = data["data"]["categoryGridRetrieve"]["pageInfo"]["totalCount"]
    if not isinstance(tong, int) or tong <= 0:
        raise RuntimeError(f"totalCount bất thường: {tong!r}")
    return tong


def lay_game_thang(http=http_get):
    data = json.loads(http(GAMES_PLUS_URL))
    if not isinstance(data, list):
        raise RuntimeError("gameslist: gốc không phải list")
    ten = set()
    for nhom in data:
        if not isinstance(nhom, dict) or not isinstance(nhom.get("games"), list):
            raise RuntimeError("gameslist: 'games' không phải list")
        for g in nhom["games"]:
            n = g.get("name") if isinstance(g, dict) else None
            if not isinstance(n, str) or not n.strip():
                raise RuntimeError("gameslist: 'name' không phải chuỗi không rỗng")
            ten.add(n)
    if not ten:
        raise RuntimeError("danh sách game PS Plus tháng rỗng")
    return sorted(ten)


def lay_du_lieu(http=http_get, ngu=time.sleep, log=print, dong_ho=time.monotonic, ngan_sach=NGAN_SACH_NGUON):
    """Trả {'blog': {khoá: [bài]|None}, 'deals': {vùng: n|None}, 'extra': {vùng: n|None}, 'plus': [tên]|None}.
    None = nguồn lỗi lượt này (đã thử lại) hoặc hết ngân sách; phần còn lại vẫn chạy."""
    han = dong_ho() + ngan_sach

    def thu(ten, ham):
        try:
            return voi_thu_lai(ham, ngu, dong_ho, han)
        except Exception as e:
            log(f"LỖI nguồn {ten}: {e} — bỏ qua lượt này.")
            return None
    return {
        "blog": {k: thu(k, lambda u=u: lay_feed(u, http)) for k, u in FEEDS.items()},
        "deals": {v: thu(f"deals-{v}", lambda v=v: lay_tong_grid(DEALS_ID, v, http)) for v in VUNG_DEALS},
        "extra": {v: thu(f"extra-{v}", lambda v=v: lay_tong_grid(EXTRA_ID, v, http)) for v in VUNG_EXTRA},
        "plus": thu("plus-thang", lambda: lay_game_thang(http)),
    }


# ---- Logic tin -------------------------------------------------------------------------------
def kiem_hot(tieu_de, the_loai=()):
    """(hot, lý do) theo TU_KHOA_HOT, so cả tiêu đề lẫn thể loại, không phân biệt hoa thường, theo từ nguyên."""
    van = " | ".join([tieu_de, *the_loai])
    for k, rx in _HOT_RE:
        if rx.search(van):
            return True, f"có từ khoá '{k}'"
    return False, ""


def tin_store(nguon, tieu_de, url, ly_do):
    return {"nguon": nguon, "tieu_de": tieu_de, "url": url, "ngay": bay_gio(), "the_loai": ["PS Store"],
            "hot": True, "ly_do_hot": ly_do, "da_viet": False}


def so_sanh(trang_thai, du_lieu):
    """Trả (tin_mới, trạng_thái_mới). Nguồn lỗi (None) giữ nguyên trạng thái cũ của nguồn đó.
    Nguồn chưa từng có trạng thái (lần đầu) chỉ ghi nhận, không báo.
    GUID lưu riêng từng feed (feed nào đọc được thì luôn cập nhật); chỉ chống trùng ở bước phát tin."""
    tt = json.loads(json.dumps(trang_thai))
    for k in ("guid", "deals_ds", "extra_ds"):
        tt.setdefault(k, {})
    tin = []

    cu_guid = trang_thai.get("guid", {})
    da_phat = set()  # guid và link đã phát trong lượt này
    for khoa, bai in du_lieu["blog"].items():
        if bai is None:
            continue
        cu = cu_guid.get(khoa)
        if cu is not None:
            khac = {g for k2, ds in cu_guid.items() if k2 != khoa for g in ds}
            for b in bai:
                if b["guid"] in cu:
                    continue
                if b["guid"] in khac or b["guid"] in da_phat or (b["url"] and b["url"] in da_phat):
                    continue
                hot, ly = kiem_hot(b["tieu_de"], b["the_loai"])
                tin.append({"nguon": NGUON_TEN[khoa], "tieu_de": b["tieu_de"], "url": b["url"], "ngay": b["ngay"],
                            "the_loai": b["the_loai"], "hot": hot, "ly_do_hot": ly, "da_viet": False})
                da_phat.add(b["guid"])
                if b["url"]:
                    da_phat.add(b["url"])
        hop = list(cu or [])
        hop += [b["guid"] for b in bai if b["guid"] not in hop]
        tt["guid"][khoa] = hop[-GIU_GUID:]

    for vung, n in du_lieu["deals"].items():
        if n is None:
            continue
        cs = trang_thai.get("deals_ds", {}).get(vung) or []
        if cs and n >= max(cs) * (1 + NGUONG_DEALS):
            tin.append(tin_store("PS Store", f"PS Store ({vung[-2:]}) vừa mở đợt giảm giá mới ({max(cs)} → {n} món)",
                                 f"https://store.playstation.com/{vung.lower()}/category/{DEALS_ID}/1",
                                 f"số món giảm giá tăng {round((n / max(cs) - 1) * 100)}% so với đỉnh {len(cs)} lần gần nhất"))
        tt["deals_ds"][vung] = (cs + [n])[-CUA_SO:]

    plus = du_lieu["plus"]
    if plus is not None:
        cu = trang_thai.get("plus_thang")
        if cu is not None:
            moi = [g for g in plus if g not in cu]
            if moi:
                tin.append(tin_store("PS Plus", "Game PS Plus tháng mới đã lên: " + ", ".join(moi),
                                     "https://www.playstation.com/en-sg/ps-plus/games/", "danh sách game tháng PS Plus đổi"))
        tt["plus_thang"] = plus

    for vung, n in du_lieu["extra"].items():
        if n is None:
            continue
        cs = trang_thai.get("extra_ds", {}).get(vung) or []
        if cs and n > max(cs):
            tin.append(tin_store("PS Plus Extra", f"Kho PS Plus Extra: tổng số game trong kho tăng từ {max(cs)} lên {n}",
                                 f"https://store.playstation.com/{vung.lower()}/category/{EXTRA_ID}/1",
                                 f"tổng kho vượt đỉnh {len(cs)} lần gần nhất"))
        tt["extra_ds"][vung] = (cs + [n])[-CUA_SO:]
    return tin, tt


# ---- Gọi viết tin (release GitHub) ---------------------------------------------------------
def la_tin_blog(tin):
    return tin.get("nguon") in NGUON_TEN.values()


def dang_viet(tin):
    """Tin đáng viết: CHỈ tin blog (trừ podcast/share of the week/…, trừ thể loại chỉ 'Uncategorized').
    Tin store (Deals/Extra/PS Plus tháng) KHÔNG gửi viết: dùng chung URL danh mục nên routine không chống trùng được,
    và tin_tu_sinh.py đã tự viết deal/PS Plus tháng từ dữ liệu (Astra 03/10).
    Cố ý KHÔNG dùng TU_KHOA_HOT cho blog — từ khoá từng bỏ sót 'AI upscaling is coming to PS5' (Hào 03/10)."""
    if la_tin_blog(tin):
        if LOAI_BLOG_RE.search(tin.get("tieu_de", "")):
            return False
        tl = {str(x).strip().lower() for x in tin.get("the_loai") or []}
        return tl != {"uncategorized"}
    return False


def _dt(x):
    """ISO (str) hoặc datetime -> datetime có múi giờ; không đọc được -> None."""
    if isinstance(x, datetime.datetime):
        d = x
    else:
        try:
            d = datetime.datetime.fromisoformat(str(x))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=GIO_VN)


def ly_do_khong_gui_viet(tin, bay_gio_dt):
    """'' nếu tin được xét gửi viết; ngược lại lý do loại (dùng cho --thu và chon_tin_gui_viet)."""
    if not dang_viet(tin):
        return "không đáng viết (podcast/share/Uncategorized hoặc tin store)"
    if tin.get("da_viet"):
        return "đã viết"
    if tin.get("da_gui_viet"):
        return f"đã gửi viết lúc {tin['da_gui_viet']}"
    ngay = _dt(tin.get("ngay"))
    if ngay is None:
        return "không đọc được ngày"
    if bay_gio_dt - ngay > datetime.timedelta(hours=VIET_HAN_GIO):
        return f"quá {VIET_HAN_GIO} giờ"
    if ngay - bay_gio_dt > datetime.timedelta(minutes=10):   # ngày tương lai (lệch đồng hồ nhỏ thì cho qua) — Astra 03/10
        return "ngày ở tương lai"
    return ""


def chon_tin_gui_viet(tin_moi, bay_gio, lan_goi_cuoi=None):
    """Tối đa VIET_TOI_DA tin đáng viết, chưa viết/chưa gửi, trong VIET_HAN_GIO giờ, mới nhất trước.
    [] nếu lần gọi cuối cách bay_gio < VIET_GIAN_GIO giờ. bay_gio/lan_goi_cuoi: chuỗi ISO hoặc datetime."""
    bg = _dt(bay_gio)
    if lan_goi_cuoi:
        cu = _dt(lan_goi_cuoi)
        if cu is not None and bg - cu < datetime.timedelta(hours=VIET_GIAN_GIO):
            return []
    ok = [x for x in tin_moi if not ly_do_khong_gui_viet(x, bg)]
    ok.sort(key=lambda x: (bool(x.get("hot")), _dt(x["ngay"])), reverse=True)  # tin hot trước (vd PS Plus tháng), rồi mới nhất
    return ok[:VIET_TOI_DA]


def goi_api_github(phuong_thuc, duong_dan, token, body=None):
    """(mã HTTP, JSON hoặc None). Lỗi HTTP trả mã lỗi; lỗi mạng ném ngoại lệ."""
    req = urllib.request.Request(
        API_GITHUB + duong_dan, method=phuong_thuc,
        data=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={**UA, "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_YEU_CAU) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def tao_release_viet(tin_chon, bay_gio, repo, token, goi_api=None):
    """POST release viet-YYYYMMDD-HHMM (giờ VN). True nếu GitHub trả 201."""
    goi_api = goi_api or goi_api_github
    bg = _dt(bay_gio).astimezone(GIO_VN)
    nd = {"tin": [{k: x.get(k) for k in ("tieu_de", "url", "nguon", "ngay", "the_loai")} for x in tin_chon]}
    body = {"tag_name": bg.strftime("viet-%Y%m%d-%H%M"), "target_commitish": "main",
            "name": "Viết tin " + bg.strftime("%d/%m %H:%M"), "body": json.dumps(nd, ensure_ascii=False),
            "make_latest": "false"}
    ma, _ = goi_api("POST", f"/repos/{repo}/releases", token, body)
    return ma == 201


def don_release_viet(bay_gio, repo, token, goi_api=None, log=print):
    """Xoá release + tag viet-* cũ hơn VIET_GIU_NGAY ngày. Mọi lỗi bỏ qua (chỉ log). Trả số release đã xoá."""
    goi_api = goi_api or goi_api_github
    bg = _dt(bay_gio)
    xoa = 0
    try:
        ma, ds = goi_api("GET", f"/repos/{repo}/releases?per_page=100", token)
        if ma != 200 or not isinstance(ds, list):
            return 0
        for r in ds:
            tag = r.get("tag_name") or ""
            ngay = _dt(r.get("published_at") or r.get("created_at"))   # created_at = ngày commit, không phải ngày đăng
            if not tag.startswith("viet-") or ngay is None or bg - ngay <= datetime.timedelta(days=VIET_GIU_NGAY):
                continue
            try:
                ma1, _ = goi_api("DELETE", f"/repos/{repo}/releases/{r['id']}", token)
                if ma1 not in (200, 204):
                    log(f"Dọn release {tag}: mã {ma1}, giữ tag để lượt sau thử lại")
                    continue
                xoa += 1
                goi_api("DELETE", f"/repos/{repo}/git/refs/tags/{tag}", token)   # chỉ xoá tag khi release đã xoá
            except Exception as e:
                log(f"Dọn release {tag} lỗi (bỏ qua): {e}")
    except Exception as e:
        log(f"Dọn release cũ lỗi (bỏ qua): {e}")
    return xoa


# ---- ntfy ------------------------------------------------------------------------------------
def gop_noi_dung(du):
    """message của thông báo gộp: tiêu đề + URL từng tin, cắt còn <= GOP_TOI_DA_BYTE byte UTF-8."""
    van = "\n\n".join(f"{t['tieu_de']}\n{t['url']}" for t in du)
    return van.encode("utf-8")[:GOP_TOI_DA_BYTE].decode("utf-8", "ignore")


def nhom_thong_bao(tin, kenh, toi_da=TOI_DA_THONG_BAO):
    """[(body JSON ntfy, [tin mà thông báo này phụ trách])]. Tin hot xếp trước.
    Vượt toi_da: toi_da-1 tin riêng + 1 thông báo gộp."""
    xep = sorted(tin, key=lambda t: not t["hot"])
    if len(xep) > toi_da:
        rieng, du = xep[:toi_da - 1], xep[toi_da - 1:]
    else:
        rieng, du = xep, []
    ra = []
    for t in rieng:
        ra.append(({"topic": kenh, "title": t["tieu_de"][:80], "message": f"{t['nguon']}" + (f" · {t['ly_do_hot']}" if t["ly_do_hot"] else ""),
                    "click": t["url"], "tags": ["fire"] if t["hot"] else ["newspaper"]}, [t]))
    if du:
        ra.append(({"topic": kenh, "title": f"và {len(du)} tin khác", "message": gop_noi_dung(du),
                    "click": du[0]["url"], "tags": ["newspaper"]}, du))
    return ra


def soan_thong_bao(tin, kenh, toi_da=TOI_DA_THONG_BAO):
    return [b for b, _ in nhom_thong_bao(tin, kenh, toi_da)]


def gui_mot(body):
    req = urllib.request.Request(NTFY_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8", **UA}, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_YEU_CAU) as r:
        if not 200 <= r.status < 300:
            raise RuntimeError(f"ntfy trả {r.status}")


def gui_hang_doi(cho_gui, kenh, gui=None, log=print):
    """cho_gui: [{'tin':…, 'lan': số lần đã thử}]. Chỉ tin nào ntfy trả 2xx mới ra khỏi hàng đợi.
    Tin gửi lỗi tăng 'lan'; đủ LAN_GUI_TOI_DA lần thì bỏ + ghi log. Trả hàng đợi còn lại."""
    gui = gui or gui_mot
    theo_id = {id(m["tin"]): m for m in cho_gui}
    con = []
    for body, tins in nhom_thong_bao([m["tin"] for m in cho_gui], kenh):
        try:
            gui(body)
        except Exception as e:
            log(f"LỖI gửi ntfy: {e}")
            for tn in tins:
                m = theo_id[id(tn)]
                m["lan"] += 1
                if m["lan"] >= LAN_GUI_TOI_DA:
                    log(f"BỎ tin sau {m['lan']} lần gửi lỗi: {tn['tieu_de']}")
                else:
                    con.append(m)
    return con


# ---- Chạy ------------------------------------------------------------------------------------
def doc_json(p, mac_dinh):
    p = pathlib.Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else mac_dinh


def ghi_json(p, obj):
    pathlib.Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def tom_tat(du_lieu):
    dong = []
    for k, bai in du_lieu["blog"].items():
        dong.append(f"{k}: " + ("LỖI" if bai is None else f"{len(bai)} bài RSS"))
    for v, n in du_lieu["deals"].items():
        dong.append(f"Deals {v}: {n if n is not None else 'LỖI'}")
    for v, n in du_lieu["extra"].items():
        dong.append(f"Extra {v}: {n if n is not None else 'LỖI'}")
    p = du_lieu["plus"]
    dong.append("Game PS Plus tháng: " + ("LỖI" if p is None else f"{len(p)} game"))
    return dong


def in_ke_hoach_viet(hang_doi, now, lan_goi_cuoi):
    """--thu: in tin SẼ gọi viết và lý do từng tin bị loại (không gọi API)."""
    chon = chon_tin_gui_viet(hang_doi, now, lan_goi_cuoi)
    bg = _dt(now)
    if lan_goi_cuoi and not chon and _dt(lan_goi_cuoi) and bg - _dt(lan_goi_cuoi) < datetime.timedelta(hours=VIET_GIAN_GIO):
        print(f"(--thu) gọi viết: chưa đủ {VIET_GIAN_GIO} giờ từ lần gọi cuối ({lan_goi_cuoi}) — lượt này không gọi.")
    for x in chon:
        print(f"SẼ GỌI VIẾT {x['tieu_de']} — {x['url']}  ({x['ngay']})")
    ids = {id(x) for x in chon}
    for x in hang_doi:
        if id(x) in ids:
            continue
        ly = ly_do_khong_gui_viet(x, bg) or f"vượt {VIET_TOI_DA} tin mới nhất"
        print(f"LOẠI viết: {x['tieu_de']} — {ly}")
    print(f"(--thu) {len(chon)} tin sẽ gọi viết; không gọi API GitHub.")


def chay(thu_muc, thu=False, du_lieu=None, gui=None, kenh=None, goi_api=None, gio=None, token=None, repo=None):
    """gio: hàm trả giờ hiện tại (ISO) — tiêm để test. token/repo: GitHub; thiếu thì chỉ in, không gọi API (Hào 03/10)."""
    gio = gio or bay_gio
    thu_muc = pathlib.Path(thu_muc)
    f_tt, f_tin = thu_muc / "tin-da-thay.json", thu_muc / "tin-moi.json"
    trang_thai = doc_json(f_tt, {})
    if du_lieu is None:
        du_lieu = lay_du_lieu()
    for d in tom_tat(du_lieu):
        print(d)
    tin, tt_moi = so_sanh(trang_thai, du_lieu)
    if thu:
        if not trang_thai:
            print("(chưa có trạng thái — thật ra đây là lần đầu, sẽ chỉ ghi, không báo; dưới đây là phân loại hot của bài đang có)")
            for bai in du_lieu["blog"].values():
                for b in bai or []:
                    hot, ly = kiem_hot(b["tieu_de"], b["the_loai"])
                    print(f"  [{'HOT' if hot else '   '}] {b['tieu_de']}" + (f"  ({ly})" if hot else ""))
        for m in trang_thai.get("cho_gui", []):
            print(f"SẼ GỬI LẠI (đã thử {m['lan']} lần): {m['tin']['tieu_de']}")
        for t in tin:
            print(f"SẼ BÁO [{'HOT' if t['hot'] else '   '}] {t['tieu_de']} — {t['url']}")
        print(f"(--thu) {len(tin)} tin sẽ báo; không gửi ntfy, không ghi trạng thái.")
        in_ke_hoach_viet(doc_json(f_tin, []) + tin, gio(), trang_thai.get("lan_goi_viet"))
        return tin
    kenh = kenh if kenh is not None else os.environ.get("NTFY_TIN", "").strip()
    cho_gui = list(tt_moi.get("cho_gui", [])) + [{"tin": x, "lan": 0} for x in tin]
    if cho_gui:
        if kenh:
            cho_gui = gui_hang_doi(cho_gui, kenh, gui)
        else:
            print("Không có NTFY_TIN — chỉ in ra:")
            for m in cho_gui:
                print(f"  {m['tin']['tieu_de']} — {m['tin']['url']}")
            cho_gui = []
    tt_moi["cho_gui"] = cho_gui
    hang_doi = (doc_json(f_tin, []) + tin)[-GIU_TIN:]
    da_doi_hang = bool(tin)
    now = gio()
    chon = chon_tin_gui_viet(hang_doi, now, trang_thai.get("lan_goi_viet"))
    if token and repo:
        if chon:
            try:
                ok = tao_release_viet(chon, now, repo, token, goi_api)
            except Exception as e:
                print(f"LỖI gọi viết: {e} — lượt sau thử lại.")
                ok = False
            if ok:
                for x in chon:
                    x["da_gui_viet"] = now
                tt_moi["lan_goi_viet"] = now
                da_doi_hang = True
                print(f"Đã gọi viết {len(chon)} tin.")
            else:
                print("Gọi viết không thành — không đánh dấu, lượt sau thử lại.")
        don_release_viet(now, repo, token, goi_api)
    elif chon:
        print(f"Không có GITHUB_TOKEN/GITHUB_REPOSITORY — chỉ in {len(chon)} tin sẽ gọi viết:")
        for x in chon:
            print(f"  {x['tieu_de']} — {x['url']}")
    if da_doi_hang:
        ghi_json(f_tin, hang_doi)
    if tt_moi != trang_thai:
        ghi_json(f_tt, tt_moi)
    print(f"Xong: {len(tin)} tin mới, {len(cho_gui)} còn chờ gửi lại.")
    return tin


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=".", help="thư mục chứa tin-da-thay.json và tin-moi.json")
    ap.add_argument("--thu", action="store_true", help="chế độ khô: không gửi ntfy, không ghi file")
    a = ap.parse_args(argv)
    chay(a.dir, thu=a.thu, token=os.environ.get("GITHUB_TOKEN", "").strip() or None,
         repo=os.environ.get("GITHUB_REPOSITORY", "").strip() or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
