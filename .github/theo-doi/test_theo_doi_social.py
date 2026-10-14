import base64
import datetime
import io
import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import theo_doi_social as s

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)

YT = """<?xml version="1.0"?><feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
<entry><yt:videoId>abc123XYZ_-</yt:videoId><title>GTA 6 Trailer 3</title><link rel="alternate" href="https://www.youtube.com/watch?v=abc123XYZ_-"/>
<published>2026-10-14T09:00:00+00:00</published><media:group><media:description>Watch the new trailer</media:description>
<media:community><media:starRating count="900" average="5.0"/><media:statistics views="30000"/></media:community></media:group></entry>
</feed>""".encode()

BSKY = json.dumps({"feed": [
    {"post": {"uri": "at://did:plc:x/app.bsky.feed.post/3kabc", "likeCount": 50, "repostCount": 10, "replyCount": 2,
              "record": {"text": "Ghost of Yotei release date announced https://t.co/x\nmore", "createdAt": "2026-10-14T10:01:01.033512003Z"},
              "embed": {"$type": "app.bsky.embed.external#view", "external": {"uri": "https://e.com", "title": "T", "thumb": "https://cdn/x.jpg"}}}},
    {"post": {"uri": "at://did:plc:y/app.bsky.feed.post/3krepost", "record": {"text": "other", "createdAt": "2026-10-14T10:00:00Z"}},
     "reason": {"$type": "app.bsky.feed.defs#reasonRepost"}}]}).encode()

RSS = """<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title>PS5 Pro price cut</title><link>https://x.com/a</link><pubDate>Wed, 14 Oct 2026 08:00:00 +0000</pubDate><description>&lt;p&gt;Big news&lt;/p&gt;</description>
<media:thumbnail url="https://x.com/t.jpg"/></item>
<item><title>Old story</title><link>https://x.com/b</link><pubDate>Mon, 10 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>No date</title><link>https://x.com/c</link></item></channel></rss>""".encode()

ATOM = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom item</title>
<link rel="alternate" href="https://a.com/1"/><updated>2026-10-14T07:00:00Z</updated><summary>sum</summary></entry></feed>""".encode()


def b(n, tieu_de, nguon="ign", nhom="bao", pub=None, mang="rss", gio=0, tt=None, loai=None, bc=False, anh=None, tk=()):
    d = NOW - datetime.timedelta(hours=gio)
    x = {"id": f"id{n}", "mang": mang, "nguon": nguon, "ten_nguon": nguon.upper(), "nhom": nhom, "pub": pub or nguon, "bc": bc,
         "url": f"https://x/{n}", "tieu_de": tieu_de, "tom_tat": "", "dang_luc": d, "tuong_tac": tt or {}, "anh": anh,
         "ps": False, "tu_khoa": list(tk), "loai": loai or s.loai_su_kien(tieu_de)}
    x["games"] = s.tim_game(x)
    return x


def kq(nguon, mang, raw, nhom="bao", ok=True, pub=None, bc=False):
    return {"nguon": nguon, "mang": mang, "ten": nguon.upper(), "nhom": nhom, "pub": pub or nguon, "bc": bc, "ok": ok,
            "loi": None if ok else "boom", "raw": raw}


def raw(n, tieu_de, gio=1, tt=None):
    return {"url": f"https://x/{n}", "tieu_de": tieu_de, "tom_tat": "", "dang_luc": NOW - datetime.timedelta(hours=gio),
            "tuong_tac": tt or {}, "anh": None}


class TestPhanTich(unittest.TestCase):
    def test_youtube(self):
        r = s.phan_tich_youtube(YT)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["tuong_tac"], {"views": 30000, "likes": 900})
        self.assertEqual(r[0]["anh"], "https://i.ytimg.com/vi/abc123XYZ_-/mqdefault.jpg")
        self.assertEqual(r[0]["url"], "https://www.youtube.com/watch?v=abc123XYZ_-")

    def test_bluesky_bo_repost(self):
        r = s.phan_tich_bluesky(BSKY, "ign.com")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["url"], "https://bsky.app/profile/ign.com/post/3kabc")
        self.assertEqual(r[0]["tieu_de"], "Ghost of Yotei release date announced")
        self.assertEqual(r[0]["tuong_tac"], {"likes": 50, "reposts": 10, "replies": 2})
        self.assertEqual(r[0]["anh"], "https://cdn/x.jpg")
        self.assertEqual(r[0]["dang_luc"].year, 2026)

    def test_rss_va_atom(self):
        r = s.phan_tich_rss_web(RSS)
        self.assertEqual([x["tieu_de"] for x in r], ["PS5 Pro price cut", "Old story"])  # bài không ngày bị bỏ
        self.assertEqual(r[0]["anh"], "https://x.com/t.jpg")
        self.assertEqual(r[0]["tom_tat"], "Big news")
        a = s.phan_tich_rss_web(ATOM)
        self.assertEqual(a[0]["url"], "https://a.com/1")
        with self.assertRaises(ValueError):
            s.phan_tich_rss_web(b"<html/>")


class TestChuanHoa(unittest.TestCase):
    def test_cu_hon_48h_va_nhieu_bi_bo(self):
        k = kq("ign", "rss", [raw(1, "GTA 6 news"), raw(2, "Old", gio=49), raw(3, "Weekly podcast ep 5"), raw(4, "Giveaway time"),
                              raw(5, "Sponsored: buy", ), raw(6, "Great game #ad")])
        r = s.chuan_hoa(k, NOW)
        self.assertEqual([x["tieu_de"] for x in r], ["GTA 6 news"])
        self.assertEqual(r[0]["games"], ["GTA 6"])

    def test_ps_va_tu_khoa(self):
        r = s.chuan_hoa(kq("ign", "rss", [raw(1, "PS Plus price rise for PS5")]), NOW)[0]
        self.assertTrue(r["ps"])
        self.assertIn("price", r["tu_khoa"])
        self.assertIn("PS Plus", r["tu_khoa"])

    def test_bluesky_tim_game_trong_chu(self):
        x = {"tieu_de": "big news", "tom_tat": "Elden Ring DLC", "mang": "bluesky"}
        self.assertEqual(s.tim_game(x), ["Elden Ring"])

    def test_loai_su_kien(self):
        self.assertEqual(s.loai_su_kien("GTA 6 trailer 3"), "trailer")
        self.assertEqual(s.loai_su_kien("Game on sale now"), "gia_sale")
        self.assertEqual(s.loai_su_kien("Something happened"), "khac")


class TestGomCum(unittest.TestCase):
    def xl(self, bais, tt=None, da_thay=frozenset({"ign|rss", "vgc|rss", "gs|rss"})):
        return s.xu_ly(tt or {}, bais, {}, NOW, da_thay)

    def test_hai_bai_gta_cung_chuyen_thanh_mot_cum(self):
        tt, _ = self.xl([b(1, "GTA 6 trailer 3 released", "ign", gio=3), b(2, "Rockstar GTA 6 trailer 3 is here", "vgc", gio=2)])
        self.assertEqual(len(tt["cum"]), 1)
        self.assertEqual(next(iter(tt["cum"].values()))["so_nguon"], 2)

    def test_khac_game_hai_cum(self):
        tt, _ = self.xl([b(1, "GTA 6 trailer 3 released", gio=3), b(2, "Elden Ring trailer 3 released", "vgc", gio=2)])
        self.assertEqual(len(tt["cum"]), 2)

    def test_cung_game_khac_loai_su_kien_khong_gom(self):
        tt, _ = self.xl([b(1, "GTA 6 trailer revealed today", gio=3), b(2, "GTA 6 review roundup today", "vgc", gio=2)])
        self.assertEqual(len(tt["cum"]), 2)

    def test_khong_khoa_game_can_jaccard_0_4(self):
        tt, _ = self.xl([b(1, "Studio announces mystery project soon", gio=3), b(2, "Totally different banana story", "vgc", gio=2)])
        self.assertEqual(len(tt["cum"]), 2)
        tt, _ = self.xl([b(1, "Studio announces mystery project soon", gio=3), b(2, "Studio announces mystery project", "vgc", gio=2)])
        self.assertEqual(len(tt["cum"]), 1)

    def test_cua_so_theo_bai_moi_nhat_va_24h(self):
        tt, _ = self.xl([b(1, "GTA 6 map details leak", gio=20), b(2, "GTA 6 map details shown", "vgc", gio=0)])
        self.assertEqual(len(tt["cum"]), 2)  # cách 20 giờ > 12 giờ
        # chuỗi bài cách nhau 10 giờ: bài thứ 3 cách bài đầu 20 giờ nhưng cách bài mới nhất 10 giờ -> gom (<24 giờ từ bài đầu)
        tt, _ = self.xl([b(1, "GTA 6 map details leak", gio=21), b(2, "GTA 6 map details seen", "vgc", gio=11),
                         b(3, "GTA 6 map details here", "gs", gio=1)])
        self.assertEqual(len(tt["cum"]), 1)

    def test_24h_tu_bai_dau(self):
        tt, _ = self.xl([b(1, "GTA 6 map details leak", gio=34), b(2, "GTA 6 map details seen", "vgc", gio=24),
                         b(3, "GTA 6 map details here", "gs", gio=13), b(4, "GTA 6 map details again", "ign", gio=2)])
        # bài 4 cách bài đầu 32 giờ (>24h) nên không vào cụm đầu -> cụm thứ hai
        self.assertEqual(len(tt["cum"]), 2)

    def test_hai_cum_giu_tren_hai_lan_chay(self):
        tt, _ = self.xl([b(1, "GTA 6 trailer 3 released", gio=3)])
        tt2, thay = self.xl([b(1, "GTA 6 trailer 3 released", gio=3), b(2, "Rockstar GTA 6 trailer 3 is here", "vgc", gio=1)], tt)
        self.assertEqual(len(tt2["cum"]), 1)
        self.assertEqual(list(thay), ["id2"])  # bài 1 không đổi -> không ghi lại


class TestDiem(unittest.TestCase):
    def cham(self, bais, nen=None, da_thay=frozenset({"a|rss", "b|rss", "c|rss", "d|rss"})):
        tt, _ = s.xu_ly({"nen": nen or {}}, bais, {}, NOW, da_thay)
        return next(iter(tt["cum"].values()))

    def test_chinh_thuc_va_2_bao(self):
        c = self.cham([b(1, "GTA 6 trailer 3 released", "a", "chinh_thuc"), b(2, "GTA 6 trailer 3 released today", "b", "bao"),
                       b(3, "GTA 6 trailer 3 released now", "c", "bao")])
        self.assertEqual(c["chi_tiet_diem"], {"chinh_thuc": 30, "nguon_them": 20, "tu_khoa": 20})
        self.assertEqual((c["diem"], c["nhan"], c["so_nguon"]), (70, "CHINH_THUC", 3))

    def test_nguon_them_toi_da_30(self):
        c = self.cham([b(i, "GTA 6 trailer 3 released", n, "bao") for i, n in enumerate("abcd", 1)])
        self.assertEqual(c["chi_tiet_diem"]["nguon_them"], 30)
        self.assertEqual(c["nhan"], "BAO_LON")

    def test_dem_publisher_khac_nhau(self):
        c = self.cham([b(1, "GTA 6 trailer 3 released", "ig-rss", "bao", pub="ig"), b(2, "GTA 6 trailer 3 released", "ig-yt", "bao", pub="ig"),
                       b(3, "GTA 6 trailer 3 released", "ig-bs", "bao", pub="ig")], da_thay=frozenset())
        self.assertEqual(c["so_nguon"], 1)
        self.assertNotIn("nguon_them", c["chi_tiet_diem"])

    def test_ro_ri_cong_dong_tru_10(self):
        c = self.cham([b(1, "GTA 6 trailer 3 leak", "a", "ro_ri")])
        self.assertEqual(c["chi_tiet_diem"], {"tu_khoa": 20, "tru": -10})
        self.assertEqual((c["diem"], c["nhan"]), (10, "RO_RI"))
        c = self.cham([b(1, "Random chatter thread", "a", "cong_dong")])
        self.assertEqual((c["diem"], c["nhan"]), (0, "TIN_DON"))

    def test_tuong_tac_vuot_nen_cong_20(self):
        nen = {"a|bluesky": [{"i": f"o{k}", "v": 10, "d": "likes+reposts", "t": "2026-10-13T00:00:00Z"} for k in range(5)]}
        bai = b(1, "Random news", "a", "bao", mang="bluesky", gio=2, tt={"likes": 100, "reposts": 10})
        c = self.cham([bai], nen)
        self.assertEqual(c["chi_tiet_diem"], {"tuong_tac": 20})
        # ít hơn 5 mẫu: không cộng
        c = self.cham([b(1, "Random news", "a", "bao", mang="bluesky", gio=2, tt={"likes": 100, "reposts": 10})],
                      {"a|bluesky": nen["a|bluesky"][:4]})
        self.assertNotIn("tuong_tac", c["chi_tiet_diem"])
        # bài đang chấm bị loại khỏi nền
        nen2 = {"a|bluesky": nen["a|bluesky"][:4] + [{"i": "id1", "v": 110, "d": "likes+reposts", "t": "2026-10-14T10:00:00Z"}]}
        c = self.cham([b(1, "Random news", "a", "bao", mang="bluesky", gio=2, tt={"likes": 100, "reposts": 10})], nen2)
        self.assertNotIn("tuong_tac", c["chi_tiet_diem"])

    def test_bluesky_duoi_1_gio_khong_tinh(self):
        self.assertIsNone(s.gia_tri_tt("bluesky", {"likes": 5}, NOW - datetime.timedelta(minutes=30), NOW))
        v, d = s.gia_tri_tt("youtube", {"views": 600}, NOW - datetime.timedelta(hours=3), NOW)
        self.assertEqual((v, d), (200.0, "views/gio"))

    def test_nen_cua_nguon(self):
        k = kq("a", "bluesky", [raw(i, f"t{i}", gio=2 + i, tt={"likes": i, "reposts": 1}) for i in range(7)], )
        m = s.nen_cua(k, NOW)
        self.assertEqual(len(m), 7)
        self.assertEqual(set(m[0]), {"i", "v", "d", "t"})


class TestBao(unittest.TestCase):
    def tt_nong(self, n=1, **kw):
        bais = []
        for i in range(n):
            ten = ["GTA 6", "Elden Ring", "God of War", "Astro Bot", "Fortnite"][i]
            bais += [b(10 * i + 1, f"{ten} trailer is out", "a", "chinh_thuc", **kw), b(10 * i + 2, f"{ten} trailer is out now", "b", "bao"),
                     b(10 * i + 3, f"{ten} trailer is out today", "c", "bao")]
        return bais

    def chay(self, kqs, tt_dir, post=None, gui=None, kenh="k", gio=NOW, **kw):
        goi = []
        nhan = gui if gui is not None else goi.append
        r = s.chay(tt_dir, ket_qua_doc=kqs, gui=nhan, kenh=kenh, post=post, url_sg="", khoa_sg="", gio=lambda: gio, **kw)
        return r, goi

    def kqs(self, n=1):
        ra = []
        for k, (ng, nh) in enumerate([("a", "chinh_thuc"), ("b", "bao"), ("c", "bao")]):
            raws = []
            for i in range(n):
                ten = ["GTA 6", "Elden Ring", "God of War", "Astro Bot", "Fortnite"][i]
                raws.append(raw(10 * i + k, f"{ten} trailer is out", gio=2))
            ra.append(kq(ng, "rss", raws, nh))
        return ra

    def test_lan_dau_khong_bao_roi_nguon_cu_khong_bao_lai(self):
        with tempfile.TemporaryDirectory() as d:
            _, goi = self.chay(self.kqs(), d)
            self.assertEqual(goi, [])  # lượt 1: chỉ ghi
            _, goi = self.chay(self.kqs(), d)
            self.assertEqual(goi, [])  # lượt 2: cụm cũ đã đánh dấu, không báo

    def test_bao_dung_mot_lan_khi_vuot_60(self):
        with tempfile.TemporaryDirectory() as d:
            nho = [kq("a", "rss", [raw(99, "Quiet note")], "chinh_thuc"), kq("b", "rss", [], "bao"), kq("c", "rss", [], "bao")]
            self.chay(nho, d)  # lượt 1: biết cả 3 nguồn
            _, goi = self.chay(self.kqs(), d)
            self.assertEqual(len(goi), 1)
            self.assertTrue(goi[0]["title"].startswith("🔥 70 · CHINH_THUC · GTA 6 trailer"))
            self.assertEqual(goi[0]["topic"], "k")
            self.assertEqual(goi[0]["click"], "https://x/0")  # nguồn chính thức
            _, goi = self.chay(self.kqs(), d)
            self.assertEqual(goi, [])

    def test_toi_da_3_moi_luot_va_hang_cho(self):
        with tempfile.TemporaryDirectory() as d:
            nho = [kq("a", "rss", [raw(99, "Quiet note")], "chinh_thuc"), kq("b", "rss", [], "bao"), kq("c", "rss", [], "bao")]
            self.chay(nho, d)
            _, goi = self.chay(self.kqs(5), d)
            self.assertEqual(len(goi), 3)
            tt = json.load(open(pathlib.Path(d) / "social-da-thay.json"))
            self.assertEqual(len(tt["cho_bao"]), 2)
            _, goi = self.chay(self.kqs(5), d)
            self.assertEqual(len(goi), 2)

    def test_toi_da_20_moi_ngay(self):
        tt = {"cum": {"x": {"id": "x", "diem": 70, "da_bao": False, "nhan": "BAO_LON", "tieu_de": "t", "nguon": ["A"], "url": "https://u",
                            "ff": False, "bc": False}}, "bao_ngay": {"ngay": s.ngay_vn(NOW), "n": 20}}
        goi = []
        self.assertEqual(s.bao_ntfy(tt, "k", goi.append, NOW), 0)
        self.assertEqual(tt["cho_bao"], ["x"])
        self.assertFalse(tt["cum"]["x"]["da_bao"])
        tt["bao_ngay"]["ngay"] = "2026-10-13"  # sang ngày mới -> gửi được
        self.assertEqual(s.bao_ntfy(tt, "k", goi.append, NOW), 1)
        self.assertEqual(tt["bao_ngay"]["n"], 1)

    def test_ntfy_loi_khong_danh_dau(self):
        def hong(body):
            raise urllib.error.URLError("429")
        tt = {"cum": {"x": {"id": "x", "diem": 70, "da_bao": False, "nhan": "BAO_LON", "tieu_de": "t", "nguon": ["A"], "url": "https://u",
                            "ff": False, "bc": False}}}
        logs = []
        self.assertEqual(s.bao_ntfy(tt, "k", hong, NOW, log=logs.append), 0)
        self.assertFalse(tt["cum"]["x"]["da_bao"])
        self.assertEqual(tt["cho_bao"], ["x"])

    def test_bo_cu_khong_bao(self):
        with tempfile.TemporaryDirectory() as d:
            nho = [kq("a", "rss", [raw(99, "Quiet note")], "chinh_thuc", bc=True), kq("b", "rss", [], "bao", bc=True), kq("c", "rss", [], "bao", bc=True)]
            self.chay(nho, d)
            ks = self.kqs()
            for k in ks:
                k["bc"] = True
            _, goi = self.chay(ks, d)
            self.assertEqual(goi, [])
            tt = json.load(open(pathlib.Path(d) / "social-da-thay.json"))
            self.assertTrue(all(c["da_bao"] for c in tt["cum"].values() if c["diem"] >= 60))

    def test_khong_co_kenh_chi_in(self):
        tt = {"cum": {"x": {"id": "x", "diem": 70, "da_bao": False, "nhan": "BAO_LON", "tieu_de": "t", "nguon": ["A"], "url": "https://u",
                            "ff": False, "bc": False}}}
        logs = []
        self.assertEqual(s.bao_ntfy(tt, "", lambda b: self.fail("không được gửi"), NOW, log=logs.append), 0)
        self.assertTrue(any("SẼ BÁO" in x for x in logs))

    def test_nguon_loi_khong_mat_nguon_khac(self):
        with tempfile.TemporaryDirectory() as d:
            ks = [kq("a", "rss", [], ok=False), kq("b", "rss", [raw(1, "Elden Ring DLC news")])]
            tt, _ = self.chay(ks, d)
            self.assertEqual(len(tt["cum"]), 1)

    def test_thu_khong_ghi_file_khong_ntfy(self):
        with tempfile.TemporaryDirectory() as d:
            tt = s.chay(d, thu=True, ket_qua_doc=self.kqs(), gui=lambda b: self.fail("ntfy"), post=lambda b: self.fail("post"),
                        kenh="k", gio=lambda: NOW, url_sg="", khoa_sg="")
            self.assertEqual(len(tt["cum"]), 1)
            self.assertEqual(list(pathlib.Path(d).iterdir()), [])


class TestGhi(unittest.TestCase):
    def test_chia_lo_200(self):
        bai = [{"id": str(i)} for i in range(450)]
        lo = s.chia_lo(bai, [], [])
        self.assertEqual([len(x["bai"]) for x in lo], [200, 200, 50])

    def test_chia_lo_theo_byte(self):
        bai = [{"id": str(i), "x": "é" * 1000} for i in range(100)]  # ~2 KB mỗi bài (UTF-8)
        lo = s.chia_lo(bai, [], [], toi_da_byte=20_000)
        for x in lo:
            self.assertLessEqual(len(json.dumps({"viec": "ghi", **x}, ensure_ascii=False).encode()), 20_000)
        self.assertEqual(sum(len(x["bai"]) for x in lo), 100)

    def test_lo_anh_toi_da_8(self):
        cum = [{"id": str(i), "anh": "data:image/jpeg;base64,AAAA"} for i in range(20)]
        lo = s.chia_lo([], cum, [], anh_moi_lo=8)
        self.assertEqual([len(x["cum"]) for x in lo], [8, 8, 4])

    def _tt(self):
        c = {"id": "c1", "tieu_de": "t", "chu_de": None, "nhan": "BAO_LON", "diem": 50, "chi_tiet_diem": {}, "so_nguon": 1,
             "nguon": ["A"], "bat_dau": "2026-10-14T10:00:00Z", "cap_nhat": "2026-10-14T10:00:00Z", "da_bao": False, "anh": False,
             "at": 0, "hg": ""}
        return {"cum": {"c1": c}}

    def test_chua_ghi_giu_khi_loi_va_xoa_sau_ack(self):
        tt = self._tt()
        bai = {"id1": b(1, "t1")}
        kqn = [{"nguon": "ign", "mang": "rss", "ten": "IGN", "nhom": "bao", "lan_doc": "2026-10-14T12:00:00Z", "ok": True, "loi": None,
                "so_bai": 1, "bai_moi_nhat": None}]

        def hong(body):
            raise RuntimeError("sg-tin trả 500")
        ok, loi = s.ghi_len_may_chu(tt, bai, kqn, {}, hong, log=lambda x: None)
        self.assertEqual((ok, loi), (0, 1))
        self.assertEqual(len(tt["chua_ghi"]["bai"]), 1)
        self.assertEqual(len(tt["chua_ghi"]["cum"]), 1)
        self.assertEqual(len(tt["chua_ghi"]["nguon"]), 1)
        gui = []
        ok, loi = s.ghi_len_may_chu(tt, {}, [], {}, lambda body: gui.append(body) or {"ok": True}, log=lambda x: None)  # lượt sau ghi lại
        self.assertEqual((ok, loi), (1, 0))
        self.assertEqual(gui[0]["viec"], "ghi")
        self.assertEqual(len(gui[0]["bai"]), 1)
        self.assertEqual(tt["chua_ghi"], {"bai": {}, "cum": {}, "nguon": {}})

    def test_413_chia_doi(self):
        tt = self._tt()
        bai = {f"id{i}": b(i, f"t{i}") for i in range(4)}
        goi = []

        def post(body):
            goi.append(len(body["bai"]))
            if len(body["bai"]) + len(body["cum"]) > 3:
                raise RuntimeError("sg-tin trả 413: too large")
            return {"ok": True}
        ok, loi = s.ghi_len_may_chu(tt, bai, [], {}, post, log=lambda x: None)
        self.assertEqual((ok, loi), (1, 0))
        self.assertEqual(goi, [4, 2, 2])
        self.assertEqual(tt["chua_ghi"]["bai"], {})

    def test_anh_vao_lo_rieng_va_danh_dau(self):
        tt = self._tt()
        goi = []
        ok, loi = s.ghi_len_may_chu(tt, {}, [], {"c1": "data:image/jpeg;base64,AAAA"}, lambda body: goi.append(body) or {"ok": True},
                                    log=lambda x: None)
        self.assertEqual(ok, 1)
        self.assertEqual(goi[-1]["cum"][0]["anh"], "data:image/jpeg;base64,AAAA")
        self.assertTrue(tt["cum"]["c1"]["anh"])

    def test_het_han_pha_post_giu_hang_cho(self):
        tt = self._tt()
        ok, loi = s.ghi_len_may_chu(tt, {"id1": b(1, "t")}, [], {}, lambda b: self.fail("không được gọi"), han=5, dong_ho=lambda: 10,
                                    log=lambda x: None)
        self.assertEqual((ok, loi), (0, 1))
        self.assertEqual(len(tt["chua_ghi"]["bai"]), 1)

    def test_thieu_khoa_chi_in(self):
        with tempfile.TemporaryDirectory() as d:
            logs = []
            tt = s.chay(d, ket_qua_doc=[kq("a", "rss", [raw(1, "Elden Ring DLC")])], kenh="", gio=lambda: NOW, url_sg="", khoa_sg="",
                        log=logs.append)
            self.assertTrue(any("chỉ in" in x for x in logs))
            self.assertEqual(tt["chua_ghi"], {})

    def test_goi_sg_tin_khong_in_khoa(self):
        def vo(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b'{"loi":"sai khoa"}'))
        orig = s.urllib.request.urlopen
        s.urllib.request.urlopen = vo
        try:
            with self.assertRaises(RuntimeError) as cm:
                s.goi_sg_tin("https://x.test/f", "BIMAT", {"viec": "ghi"})
        finally:
            s.urllib.request.urlopen = orig
        self.assertNotIn("BIMAT", str(cm.exception))
        self.assertIn("401", str(cm.exception))

    def test_don_mot_lan_moi_ngay_sau_3h_vn(self):
        t_2h = datetime.datetime(2026, 10, 14, 19, 30, tzinfo=UTC)  # 02:30 VN ngày 15
        t_4h = datetime.datetime(2026, 10, 14, 21, 0, tzinfo=UTC)   # 04:00 VN ngày 15
        tt = {}
        self.assertFalse(s.can_don(tt, t_2h))
        self.assertTrue(s.can_don(tt, t_4h))
        tt["don_ngay"] = s.ngay_vn(t_4h)
        self.assertFalse(s.can_don(tt, t_4h))

    def test_chay_goi_don_dung_mot_lan(self):
        with tempfile.TemporaryDirectory() as d:
            goi = []
            post = lambda body: goi.append(body["viec"]) or ({"ok": True, "lenh": []} if body["viec"] == "doc_lenh" else {"ok": True})  # noqa: E731
            gio = datetime.datetime(2026, 10, 14, 21, 0, tzinfo=UTC)
            for _ in range(2):
                s.chay(d, ket_qua_doc=[kq("a", "rss", [])], kenh="k", gio=lambda: gio, post=post, url_sg="x", khoa_sg="y", log=lambda x: None)
            self.assertEqual(goi.count("don"), 1)


class TestLenh(unittest.TestCase):
    def test_lenh_video_ntfy_roi_xong_lenh_dang_de_nguyen(self):
        goi, ghi = [], []
        lenh = [{"id": "11111111-1111-1111-1111-111111111111", "loai": "video", "cum_id": "c", "tieu_de": "GTA 6 trailer"},
                {"id": "22222222-2222-2222-2222-222222222222", "loai": "dang", "cum_id": "c", "tieu_de": "GTA 6 trailer"}]

        def post(body):
            ghi.append(body)
            return {"ok": True, "lenh": lenh} if body["viec"] == "doc_lenh" else {"ok": True}
        tt = {}
        n = s.xu_ly_lenh(post, "k", goi.append, tt, log=lambda x: None)
        self.assertEqual(n, 1)
        self.assertEqual(len(goi), 1)
        self.assertEqual(goi[0]["title"], "🎬 Hào xếp làm video: GTA 6 trailer")
        caps = [x for x in ghi if x["viec"] == "cap_nhat_lenh"]
        self.assertEqual(len(caps), 1)
        self.assertEqual((caps[0]["id"], caps[0]["trang_thai"], caps[0]["ket_qua"]), (lenh[0]["id"], "xong", {"ntfy": True}))

    def test_cap_nhat_loi_nho_lai_va_khong_ntfy_lan_hai(self):
        goi = []
        lenh = [{"id": "11111111-1111-1111-1111-111111111111", "loai": "video", "tieu_de": "X"}]
        hong = {"v": True, "xong": False}

        def post(body):
            if body["viec"] == "cap_nhat_lenh":
                if hong["v"]:
                    raise RuntimeError("500")
                hong["xong"] = True
            return {"ok": True, "lenh": [] if hong["xong"] else lenh} if body["viec"] == "doc_lenh" else {"ok": True}
        tt = {}
        s.xu_ly_lenh(post, "k", goi.append, tt, log=lambda x: None)
        self.assertEqual(len(tt["chua_ghi"]["lenh"]), 1)
        hong["v"] = False
        s.xu_ly_lenh(post, "k", goi.append, tt, log=lambda x: None)
        self.assertEqual(len(goi), 1)  # không ntfy lần hai
        self.assertEqual(tt["chua_ghi"]["lenh"], {})


class TestAnh(unittest.TestCase):
    JPG = b"\xff\xd8\xff\xe0" + b"0" * 100

    def test_anh_nho_thanh_data_uri(self):
        d = s.lay_anh(["https://i/x.jpg"], lambda u: self.JPG)
        self.assertEqual(d, "data:image/jpeg;base64," + base64.b64encode(self.JPG).decode())

    def test_anh_lon_hon_40kb_bi_bo_thu_url_ke(self):
        to = b"\xff\xd8\xff" + b"0" * 41_000
        d = s.lay_anh(["https://a", "https://b"], lambda u: to if u == "https://a" else self.JPG)
        self.assertTrue(d.startswith("data:image/jpeg"))
        self.assertIsNone(s.lay_anh(["https://a"], lambda u: to))

    def test_sai_chu_ky_va_loi_mang(self):
        self.assertIsNone(s.lay_anh(["https://a"], lambda u: b"<html>not image</html>"))

        def hong(u):
            raise OSError("x")
        self.assertIsNone(s.lay_anh(["https://a"], hong))

    def test_mime_dung(self):
        self.assertEqual(s.mime_anh(b"\x89PNG\r\n\x1a\n...."), "image/png")
        self.assertEqual(s.mime_anh(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")

    def test_lay_anh_cum_uu_tien_youtube_va_cho_toi_da_15(self):
        cum = {str(i): {"id": str(i), "diem": 50, "anh": False, "at": 0, "yt": [f"https://www.youtube.com/watch?v=vid{i}abcde"], "a": []}
               for i in range(20)}
        cum["x"] = {"id": "x", "diem": 30, "anh": False, "at": 0, "yt": [], "a": []}  # dưới 40 điểm
        goi = []
        r = s.lay_anh_cum({"cum": cum}, lambda u: goi.append(u) or self.JPG)
        self.assertEqual(len(r), 15)
        self.assertTrue(all("i.ytimg.com/vi/" in u and u.endswith("mqdefault.jpg") for u in goi))
        self.assertNotIn("x", r)

    def test_khong_tai_lai_cum_da_co_anh(self):
        cum = {"a": {"id": "a", "diem": 90, "anh": True, "at": 0, "yt": ["https://www.youtube.com/watch?v=zzzzzz"], "a": []}}
        self.assertEqual(s.lay_anh_cum({"cum": cum}, lambda u: self.fail("tải lại")), {})


class TestDocNguon(unittest.TestCase):
    N = {"khoa": "ign", "ten": "IGN", "nhom": "bao", "youtube": "UCx", "bluesky": "ign.com", "rss": "https://ign.com/rss"}

    def test_mot_nguon_loi_nguon_khac_van_ok(self):
        def http(url, headers=None, timeout=0):
            if "youtube" in url:
                raise OSError("boom")
            return RSS if "ign.com/rss" in url else BSKY
        r = s.doc_tat_ca([self.N], http=http, ngu=lambda g: None, ngan_sach=30)
        theo = {k["mang"]: k for k in r}
        self.assertFalse(theo["youtube"]["ok"])
        self.assertIn("boom", theo["youtube"]["loi"])
        self.assertTrue(theo["bluesky"]["ok"] and theo["rss"]["ok"])

    def test_thu_lai_mot_lan(self):
        dem = {"n": 0}

        def http(url, headers=None, timeout=0):
            dem["n"] += 1
            if dem["n"] == 1:
                raise OSError("tạm")
            return RSS
        n = {"khoa": "x", "ten": "X", "nhom": "bao", "rss": "https://x.com/rss"}
        ngu = []
        r = s.doc_mot(n, "rss", http, ngu.append, None, lambda: 0, {}, NOW)
        self.assertTrue(r["ok"])
        self.assertEqual(ngu, [5])

    def test_429_cooldown_theo_host_khong_thu_lai(self):
        dem = {"n": 0}

        def http(url, headers=None, timeout=0):
            dem["n"] += 1
            raise urllib.error.HTTPError(url, 429, "slow", {"Retry-After": "120"}, io.BytesIO(b""))
        n = {"khoa": "x", "ten": "X", "nhom": "bao", "bluesky": "x.com"}
        r = s.doc_mot(n, "bluesky", http, lambda g: None, None, lambda: 0, {}, NOW)
        self.assertFalse(r["ok"])
        self.assertEqual(dem["n"], 1)
        self.assertEqual(r["cooldown"], ("public.api.bsky.app", 120))
        # lượt sau trong cooldown: không gọi mạng
        r2 = s.doc_mot(n, "bluesky", lambda *a, **k: self.fail("gọi mạng"), lambda g: None, None, lambda: 0,
                       {"public.api.bsky.app": s.iso(NOW + datetime.timedelta(seconds=60))}, NOW)
        self.assertIn("cooldown", r2["loi"])

    def test_chay_luu_cooldown_vao_trang_thai(self):
        with tempfile.TemporaryDirectory() as d:
            k = kq("x", "bluesky", [], ok=False)
            k["cooldown"] = ("public.api.bsky.app", 300)
            tt = s.chay(d, ket_qua_doc=[k], kenh="", gio=lambda: NOW, url_sg="", khoa_sg="", log=lambda x: None)
            self.assertEqual(tt["cooldown"]["public.api.bsky.app"], s.iso(NOW + datetime.timedelta(seconds=300)))

    def test_het_ngan_sach_ghi_loi(self):
        import time as t
        n = {"khoa": "x", "ten": "X", "nhom": "bao", "rss": "https://x.com/rss"}

        def cham(url, headers=None, timeout=0):
            t.sleep(0.6)
            return RSS
        r = s.doc_tat_ca([n], http=cham, ngan_sach=0.1)
        self.assertFalse(r[0]["ok"])
        self.assertIn("ngân sách", r[0]["loi"])

    def test_nguon_social_json_hop_le(self):
        d = json.loads((pathlib.Path(__file__).parent / "nguon-social.json").read_text(encoding="utf-8"))
        self.assertTrue(all(x["nhom"] in s.NHOM_HANG for x in d))
        self.assertFalse(any("reddit" in x for x in d))
        self.assertEqual(len({x["khoa"] for x in d}), len(d))
        self.assertGreaterEqual(len(d), 25)


class TestTrangThai(unittest.TestCase):
    def test_thu_nho_gioi_han(self):
        tt = {"bai": {f"i{i}": {"dl": f"2026-10-14T{i % 24:02d}:00:00Z", "cum": f"c{i % 700}"} for i in range(3500)},
              "cum": {f"c{i}": {"cap_nhat": f"2026-10-{1 + i % 14:02d}T00:00:00Z"} for i in range(700)}}
        s.thu_nho(tt)
        self.assertLessEqual(len(tt["bai"]), s.BAI_TOI_DA)
        self.assertLessEqual(len(tt["cum"]), s.CUM_TOI_DA)

    def test_nen_gop_theo_id_giu_20(self):
        mau = lambda i, v, t: {"i": i, "v": v, "d": "views/gio", "t": t}  # noqa: E731
        cu_ = {"nen": {"a|youtube": [mau(f"o{k}", 1, f"2026-10-0{1 + k % 9}T00:00:00Z") for k in range(20)]}}
        moi = {"a|youtube": [mau("o0", 99, "2026-10-14T00:00:00Z"), mau("n1", 5, "2026-10-14T01:00:00Z")]}
        tt, _ = s.xu_ly(cu_, [], moi, NOW)
        ds = tt["nen"]["a|youtube"]
        self.assertEqual(len(ds), 20)
        self.assertEqual([x["v"] for x in ds if x["i"] == "o0"], [99])

    def test_chay_hai_luot_trang_thai_ben_vung(self):
        with tempfile.TemporaryDirectory() as d:
            ks = [kq("a", "rss", [raw(1, "Elden Ring DLC news"), raw(2, "Elden Ring DLC news today")], "bao")]
            s.chay(d, ket_qua_doc=ks, kenh="", gio=lambda: NOW, url_sg="", khoa_sg="", log=lambda x: None)
            f = pathlib.Path(d) / "social-da-thay.json"
            self.assertLess(f.stat().st_size, 1_000_000)
            tt = json.loads(f.read_text(encoding="utf-8"))
            self.assertIn("a|rss", tt["nguon_da_thay"])
            self.assertEqual(len(tt["cum"]), 1)


if __name__ == "__main__":
    unittest.main()
