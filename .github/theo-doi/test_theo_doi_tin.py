import json
import pathlib
import sys
import tempfile
import datetime
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import theo_doi_tin as t

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>State of Play returns tomorrow</title><link>https://blog.playstation.com/a</link><pubDate>Tue, 29 Sep 2026 10:00:00 +0000</pubDate>
<category>PS5</category><guid isPermaLink="false">https://blog.playstation.com/?p=1</guid></item>
<item><title>New indie roundup</title><link>https://blog.playstation.com/b</link><pubDate>Tue, 29 Sep 2026 09:00:00 +0000</pubDate>
<category>Indie</category><guid isPermaLink="false">https://blog.playstation.com/?p=2</guid></item>
</channel></rss>""".encode()


def bai(n, tieu_de="Something", the_loai=()):
    return {"guid": f"g{n}", "tieu_de": tieu_de, "url": f"https://x/{n}", "ngay": "2026-09-29T10:00:00+07:00", "the_loai": list(the_loai)}


def dl(blog=None, deals=None, extra=None, plus=None):
    return {"blog": blog if blog is not None else {"blog": [], "blog-ps-plus": []},
            "deals": deals if deals is not None else {"en-US": 1000, "en-SG": 1000},
            "extra": extra if extra is not None else {"en-SG": 400},
            "plus": plus if plus is not None else ["A", "B"]}


class TestRss(unittest.TestCase):
    def test_doc_rss_mau(self):
        ds = t.phan_tich_rss(RSS)
        self.assertEqual(len(ds), 2)
        self.assertEqual(ds[0]["tieu_de"], "State of Play returns tomorrow")
        self.assertEqual(ds[0]["the_loai"], ["PS5"])
        self.assertEqual(ds[0]["guid"], "https://blog.playstation.com/?p=1")
        self.assertTrue(ds[0]["ngay"].startswith("2026-09-29T17:00:00"))  # 10:00 UTC = 17:00 VN


class TestHot(unittest.TestCase):
    def test_tu_khoa(self):
        self.assertTrue(t.kiem_hot("State of Play returns")[0])
        self.assertTrue(t.kiem_hot("Lots of games", ["PS Plus"])[0])
        self.assertTrue(t.kiem_hot("new god of war trailer")[0])
        self.assertFalse(t.kiem_hot("New indie roundup", ["Indie"])[0])
        self.assertFalse(t.kiem_hot("Wholesale plans")[0])  # 'sale' không khớp giữa từ


class TestSoSanh(unittest.TestCase):
    def test_lan_dau_khong_bao(self):
        tin, tt = t.so_sanh({}, dl(blog={"blog": [bai(1), bai(2)], "blog-ps-plus": [bai(3)]}))
        self.assertEqual(tin, [])
        self.assertEqual(tt["deals_ds"]["en-US"], [1000])
        self.assertEqual(tt["plus_thang"], ["A", "B"])
        self.assertEqual(tt["guid"]["blog"], ["g1", "g2"])

    def test_bai_moi_bao_dung_1_lan(self):
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(1)], "blog-ps-plus": [bai(9)]}))
        d = dl(blog={"blog": [bai(2, "PS Plus sale"), bai(1)], "blog-ps-plus": [bai(9), bai(2, "PS Plus sale")]})
        tin, tt2 = t.so_sanh(tt, d)
        self.assertEqual(len(tin), 1)  # bài g2 có ở cả hai feed, chỉ báo 1 lần
        self.assertTrue(tin[0]["hot"])
        self.assertFalse(tin[0]["da_viet"])
        tin2, _ = t.so_sanh(tt2, d)
        self.assertEqual(tin2, [])

    def test_bai_thuong_khong_hot(self):
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(1)], "blog-ps-plus": [bai(9)]}))
        tin, _ = t.so_sanh(tt, dl(blog={"blog": [bai(5, "Indie roundup"), bai(1)], "blog-ps-plus": [bai(9)]}))
        self.assertEqual(len(tin), 1)
        self.assertFalse(tin[0]["hot"])

    def test_deals_15_phan_tram(self):
        _, tt = t.so_sanh({}, dl())
        tin, tt2 = t.so_sanh(tt, dl(deals={"en-US": 1150, "en-SG": 1000}))
        self.assertEqual(len(tin), 1)
        self.assertIn("1000 → 1150", tin[0]["tieu_de"])
        self.assertTrue(tin[0]["hot"])
        tin, _ = t.so_sanh(tt, dl(deals={"en-US": 1050, "en-SG": 1000}))
        self.assertEqual(tin, [])

    def test_game_thang_doi(self):
        _, tt = t.so_sanh({}, dl())
        tin, tt2 = t.so_sanh(tt, dl(plus=["A", "B", "C"]))
        self.assertEqual(len(tin), 1)
        self.assertIn("C", tin[0]["tieu_de"])
        self.assertEqual(tt2["plus_thang"], ["A", "B", "C"])
        self.assertEqual(t.so_sanh(tt2, dl(plus=["A", "B", "C"]))[0], [])

    def test_extra_tang(self):
        _, tt = t.so_sanh({}, dl())
        tin, _ = t.so_sanh(tt, dl(extra={"en-SG": 412}))
        self.assertEqual(len(tin), 1)
        self.assertIn("tăng từ 400 lên 412", tin[0]["tieu_de"])
        self.assertNotIn("thêm", tin[0]["tieu_de"])

    def test_nguon_loi_khong_mat_trang_thai(self):
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(1)], "blog-ps-plus": [bai(2)]}))
        loi = {"blog": {"blog": None, "blog-ps-plus": [bai(2), bai(3)]}, "deals": {"en-US": None, "en-SG": 1000},
               "extra": {"en-SG": None}, "plus": None}
        tin, tt2 = t.so_sanh(tt, loi)
        self.assertEqual(tt2["guid"]["blog"], tt["guid"]["blog"])
        self.assertEqual(tt2["deals_ds"]["en-US"], [1000])
        self.assertEqual(tt2["extra_ds"]["en-SG"], [400])
        self.assertEqual(tt2["plus_thang"], ["A", "B"])
        self.assertEqual([x["url"] for x in tin], ["https://x/3"])  # nguồn lành vẫn chạy

    def test_nguon_loi_lan_dau_roi_lanh_lai_khong_bao(self):
        loi = {"blog": {"blog": None, "blog-ps-plus": None}, "deals": {"en-US": None, "en-SG": None},
               "extra": {"en-SG": None}, "plus": None}
        tin, tt = t.so_sanh({}, loi)
        self.assertEqual(tin, [])
        tin, _ = t.so_sanh(tt, dl(blog={"blog": [bai(1)], "blog-ps-plus": []}))
        self.assertEqual(tin, [])  # lần đầu của nguồn đó -> chỉ ghi nhận

    def test_giu_300_guid(self):
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(0)], "blog-ps-plus": []}))
        tin, tt2 = t.so_sanh(tt, dl(blog={"blog": [bai(i) for i in range(1, 400)], "blog-ps-plus": []}))
        self.assertEqual(len(tt2["guid"]["blog"]), 300)
        self.assertEqual(tt2["guid"]["blog"][-1], "g399")


class TestDaoDong(unittest.TestCase):
    def test_deals_dao_dong_khong_bao(self):
        tt = {}
        for n in (1000, 700, 1000, 1100):  # 700 rồi 1000 lại: không phải đợt mới
            tin, tt = t.so_sanh(tt, dl(deals={"en-US": n, "en-SG": 1000}))
            self.assertEqual(tin, [])
        tin, tt = t.so_sanh(tt, dl(deals={"en-US": 1265, "en-SG": 1000}))  # 1265 = 1,15 x 1100
        self.assertEqual(len(tin), 1)
        self.assertIn("1100 → 1265", tin[0]["tieu_de"])

    def test_extra_dao_dong_khong_bao(self):
        tt = {}
        for n in (400, 380, 400):
            tin, tt = t.so_sanh(tt, dl(extra={"en-SG": n}))
            self.assertEqual(tin, [])
        tin, _ = t.so_sanh(tt, dl(extra={"en-SG": 401}))
        self.assertEqual(len(tin), 1)

    def test_cua_so_12(self):
        tt = {}
        for n in range(1, 30):
            _, tt = t.so_sanh(tt, dl(deals={"en-US": 100, "en-SG": n}))
        self.assertEqual(len(tt["deals_ds"]["en-SG"]), 12)


class TestGuidRieng(unittest.TestCase):
    def test_moi_feed_cap_nhat_rieng_va_chi_bao_1_lan(self):
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(1)], "blog-ps-plus": [bai(9)]}))
        # g2 xuất hiện ở feed 'blog' trước; feed ps-plus chỉ thấy nó lượt sau
        tin, tt = t.so_sanh(tt, dl(blog={"blog": [bai(2), bai(1)], "blog-ps-plus": [bai(9)]}))
        self.assertEqual(len(tin), 1)
        self.assertIn("g2", tt["guid"]["blog"])
        self.assertNotIn("g2", tt["guid"]["blog-ps-plus"])
        tin, tt = t.so_sanh(tt, dl(blog={"blog": [bai(2), bai(1)], "blog-ps-plus": [bai(2), bai(9)]}))
        self.assertEqual(tin, [])  # đã báo ở feed kia, không báo lại
        self.assertIn("g2", tt["guid"]["blog-ps-plus"])

    def test_cung_link_khac_guid_hai_feed_1_lan(self):
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(1)], "blog-ps-plus": [bai(9)]}))
        a, b = bai(5), bai(6)
        b["url"] = a["url"]
        tin, _ = t.so_sanh(tt, dl(blog={"blog": [a, bai(1)], "blog-ps-plus": [b, bai(9)]}))
        self.assertEqual(len(tin), 1)


class TestNganSach(unittest.TestCase):
    def test_het_ngan_sach_bo_nguon_con_lai(self):
        gio = [0.0]
        goi = []
        def http(url, headers=None, timeout=15):
            goi.append(url)
            gio[0] += 100  # mỗi request "tốn" 100s
            raise OSError("chậm")
        d = t.lay_du_lieu(http, lambda s: gio.__setitem__(0, gio[0] + s), log=lambda *_: None, dong_ho=lambda: gio[0], ngan_sach=240)
        self.assertTrue(all(v is None for v in d["blog"].values()))
        self.assertIsNone(d["plus"])
        self.assertLessEqual(len([u for u in goi if u not in t.FEEDS_NGOAI.values()]), 3)  # nguồn cũ: sau ~240s thì ngừng gọi, không đủ 3 lần x 6 nguồn

    def test_timeout_15s(self):
        self.assertEqual(t.TIMEOUT_YEU_CAU, 15)
        self.assertEqual(t.CHO_THU_LAI, (5, 15))
        self.assertEqual(t.NGAN_SACH_NGUON, 240)
        import inspect
        self.assertEqual(inspect.signature(t.http_get).parameters["timeout"].default, 15)


class TestNguonHong(unittest.TestCase):
    def test_rss_bao_tri_khong_phai_feed_rong(self):
        for xml in (b"<html><body>Bao tri</body></html>", b"<rss version='2.0'></rss>",
                    b"<rss version='2.0'><channel><title>x</title></channel></rss>",
                    b"<rss><channel><item><title>no id</title></item></channel></rss>", b"khong phai xml"):
            with self.assertRaises(Exception):
                t.phan_tich_rss(xml)

    def test_rss_hong_khong_cap_nhat_trang_thai(self):
        def http(url, headers=None, timeout=15):
            if "/feed/" in url:
                return b"<html>Bao tri</html>"
            raise OSError("x")
        d = t.lay_du_lieu(http, lambda s: None, log=lambda *_: None)
        self.assertIsNone(d["blog"]["blog"])
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(1)], "blog-ps-plus": [bai(2)]}))
        d2 = dl(blog={"blog": None, "blog-ps-plus": [bai(2)]})
        _, tt2 = t.so_sanh(tt, d2)
        self.assertEqual(tt2["guid"]["blog"], ["g1"])

    def test_gameslist_schema(self):
        tot = json.dumps([{"games": [{"name": "X"}]}, {"games": []}]).encode()
        self.assertEqual(t.lay_game_thang(lambda u: tot), ["X"])
        for xau in ({"a": 1}, [{"games": None}], [{"games": [{"name": ""}]}], [{"games": [{"name": 5}]}],
                    [{"games": ["x"]}], [{"games": []}], [{}]):
            with self.assertRaises(Exception):
                t.lay_game_thang(lambda u, x=xau: json.dumps(x).encode())

    def test_gameslist_hong_khong_dung_ca_luot(self):
        def http(url, headers=None, timeout=15):
            if "gameslist" in url:
                return b'{"loi": 1}'
            if "/feed/" in url:
                return RSS
            return json.dumps({"data": {"categoryGridRetrieve": {"pageInfo": {"totalCount": 5}}}}).encode()
        d = t.lay_du_lieu(http, lambda s: None, log=lambda *_: None)
        self.assertIsNone(d["plus"])
        self.assertEqual(d["deals"]["en-US"], 5)


class TestHangDoiGui(unittest.TestCase):
    def _tin(self, n):
        return {"nguon": "PlayStation Blog", "tieu_de": f"Tin {n}", "url": f"https://x/{n}", "ngay": "", "the_loai": [],
                "hot": True, "ly_do_hot": "", "da_viet": False}

    def test_gui_loi_giu_lai_va_gui_lai_luot_sau(self):
        with tempfile.TemporaryDirectory() as d:
            _, _ = t.so_sanh({}, dl())
            t.chay(d, du_lieu=dl(), gui=lambda b: None, kenh="k")  # lần đầu
            def hong(b):
                raise OSError("ntfy 500")
            t.chay(d, du_lieu=dl(plus=["A", "B", "C"]), gui=hong, kenh="k")
            tt = json.loads((pathlib.Path(d) / "tin-da-thay.json").read_text(encoding="utf-8"))
            self.assertEqual(len(tt["cho_gui"]), 1)
            self.assertEqual(tt["cho_gui"][0]["lan"], 1)
            sent = []
            t.chay(d, du_lieu=dl(plus=["A", "B", "C"]), gui=sent.append, kenh="k")  # không có tin mới, gửi lại hàng đợi
            self.assertEqual(len(sent), 1)
            tt = json.loads((pathlib.Path(d) / "tin-da-thay.json").read_text(encoding="utf-8"))
            self.assertEqual(tt["cho_gui"], [])
            t.chay(d, du_lieu=dl(plus=["A", "B", "C"]), gui=sent.append, kenh="k")
            self.assertEqual(len(sent), 1)  # không gửi lại lần nữa

    def test_toi_da_3_lan_roi_bo(self):
        logs = []
        def hong(b):
            raise OSError("x")
        hd = [{"tin": self._tin(1), "lan": 0}]
        for _ in range(2):
            hd = t.gui_hang_doi(hd, "k", hong, logs.append)
            self.assertEqual(len(hd), 1)
        hd = t.gui_hang_doi(hd, "k", hong, logs.append)
        self.assertEqual(hd, [])
        self.assertTrue(any("BỎ tin" in l for l in logs))

    def test_gui_khong_2xx_la_loi(self):
        class R:
            status = 500
            def __enter__(self): return self
            def __exit__(self, *a): pass
        orig = t.urllib.request.urlopen
        t.urllib.request.urlopen = lambda *a, **k: R()
        try:
            with self.assertRaises(RuntimeError):
                t.gui_mot({"topic": "k"})
        finally:
            t.urllib.request.urlopen = orig

    def test_gui_mot_phan_loi_giu_phan_con_lai(self):
        n = [0]
        def nua(b):
            n[0] += 1
            if n[0] == 2:
                raise OSError("x")
        hd = t.gui_hang_doi([{"tin": self._tin(i), "lan": 0} for i in range(3)], "k", nua, lambda *_: None)
        self.assertEqual(len(hd), 1)
        self.assertEqual(hd[0]["lan"], 1)


class TestGop(unittest.TestCase):
    def test_gop_url_va_cat_byte(self):
        tins = [{"nguon": "n", "tieu_de": "Tiêu đề dài " * 5 + str(i), "url": f"https://x/{i}", "ngay": "", "the_loai": [],
                 "hot": False, "ly_do_hot": "", "da_viet": False} for i in range(60)]
        b = t.soan_thong_bao(tins, "k")
        g = b[-1]
        self.assertEqual(g["title"], "và 53 tin khác")
        self.assertEqual(g["click"], "https://x/7")  # tin đầu tiên trong nhóm gộp
        self.assertIn("https://x/7", g["message"])
        self.assertLessEqual(len(g["message"].encode("utf-8")), 3500)
        self.assertEqual(g["message"], g["message"].encode("utf-8").decode("utf-8"))  # không đứt giữa ký tự


class TestLayDuLieu(unittest.TestCase):
    def test_loi_mang_thu_lai_roi_bo_nguon(self):
        goi, ngu = [], []
        def http(url, headers=None, timeout=30):
            goi.append(url)
            if "category/ps-plus" in url:
                raise OSError("mạng")
            if "/feed/" in url:
                return RSS
            if "gameslist" in url:
                return json.dumps([{"games": [{"name": "X"}]}]).encode()
            return json.dumps({"data": {"categoryGridRetrieve": {"pageInfo": {"totalCount": 77}}}}).encode()
        d = t.lay_du_lieu(http, ngu.append, log=lambda *_: None)
        self.assertIsNone(d["blog"]["blog-ps-plus"])
        self.assertEqual(len(d["blog"]["blog"]), 2)
        self.assertEqual(sum("category/ps-plus" in u for u in goi), 3)
        self.assertEqual(ngu[:2], [5, 15])
        self.assertEqual(d["deals"]["en-SG"], 77)
        self.assertEqual(d["plus"], ["X"])


class TestNtfy(unittest.TestCase):
    def _tin(self, n, hot=True):
        return {"nguon": "PlayStation Blog", "tieu_de": f"Tin số {n}", "url": f"https://x/{n}", "ngay": "", "the_loai": [],
                "hot": hot, "ly_do_hot": "có từ khoá 'sale'" if hot else "", "da_viet": False}

    def test_gioi_han_8(self):
        b = t.soan_thong_bao([self._tin(i) for i in range(12)], "kenh")
        self.assertEqual(len(b), 8)
        self.assertEqual(b[-1]["title"], "và 5 tin khác")
        self.assertEqual(len(t.soan_thong_bao([self._tin(i) for i in range(8)], "kenh")), 8)

    def test_json_utf8(self):
        tin = self._tin(1)
        tin["tieu_de"] = "PS Store vừa mở đợt giảm giá mới"
        b = t.soan_thong_bao([tin], "kenh")[0]
        self.assertEqual(b["topic"], "kenh")
        self.assertEqual(b["tags"], ["fire"])
        self.assertEqual(b["click"], "https://x/1")
        raw = json.dumps(b, ensure_ascii=False).encode("utf-8")
        self.assertEqual(json.loads(raw.decode("utf-8"))["title"], "PS Store vừa mở đợt giảm giá mới")
        self.assertEqual(t.soan_thong_bao([self._tin(2, hot=False)], "k")[0]["tags"], ["newspaper"])

    def test_title_cat_80(self):
        tin = self._tin(1)
        tin["tieu_de"] = "á" * 200
        self.assertEqual(len(t.soan_thong_bao([tin], "k")[0]["title"]), 80)


class TestChay(unittest.TestCase):
    def test_luong_day_du(self):
        with tempfile.TemporaryDirectory() as d:
            sent = []
            t.chay(d, du_lieu=dl(), gui=sent.append, kenh="k")
            self.assertEqual(sent, [])
            self.assertTrue((pathlib.Path(d) / "tin-da-thay.json").exists())
            self.assertFalse((pathlib.Path(d) / "tin-moi.json").exists())
            t.chay(d, du_lieu=dl(plus=["A", "B", "C"]), gui=sent.append, kenh="k")
            self.assertEqual(len(sent), 1)
            hd = json.loads((pathlib.Path(d) / "tin-moi.json").read_text(encoding="utf-8"))
            self.assertEqual(len(hd), 1)

    def test_che_do_thu_khong_ghi(self):
        with tempfile.TemporaryDirectory() as d:
            t.chay(d, thu=True, du_lieu=dl())
            self.assertEqual(list(pathlib.Path(d).iterdir()), [])

    def test_khong_secret_khong_loi(self):
        with tempfile.TemporaryDirectory() as d:
            t.chay(d, du_lieu=dl(), kenh="")
            t.chay(d, du_lieu=dl(plus=["A", "Z"]), kenh="")


NOW = "2026-10-03T12:00:00+07:00"


def tin_blog(n, tieu_de="Some news", the_loai=("PS5",), ngay="2026-10-03T08:00:00+07:00", **kw):
    return {"nguon": "PlayStation Blog", "tieu_de": tieu_de, "url": f"https://b/{n}", "ngay": ngay,
            "the_loai": list(the_loai), "hot": False, "ly_do_hot": "", "da_viet": False, **kw}


class GiaApi:
    """goi_api giả: ghi lại lời gọi, trả mã theo bảng."""
    def __init__(self, ma_post=201, releases=None, loi=None):
        self.goi, self.ma_post, self.releases, self.loi = [], ma_post, releases or [], loi

    def __call__(self, pt, dd, token, body=None):
        self.goi.append((pt, dd, token, body))
        if self.loi:
            raise self.loi
        if pt == "POST":
            return self.ma_post, {}
        if pt == "GET":
            return 200, self.releases
        return 204, None


class TestDangViet(unittest.TestCase):
    def test_loc(self):
        self.assertTrue(t.dang_viet(tin_blog(1, "AI upscaling is coming to PS5")))
        for tde in ("Official PlayStation Podcast Episode 5", "Share of the Week: X", "PlayStation Blogcast 12",
                    "This Week in PlayStation: news"):
            self.assertFalse(t.dang_viet(tin_blog(1, tde)), tde)
        self.assertFalse(t.dang_viet(tin_blog(1, the_loai=["Uncategorized"])))
        self.assertTrue(t.dang_viet(tin_blog(1, the_loai=["Uncategorized", "PS5"])))
        store = {"nguon": "PS Store", "tieu_de": "x", "url": "u", "ngay": NOW, "the_loai": ["PS Store"], "hot": True}
        self.assertFalse(t.dang_viet(store))                      # tin store không gửi viết (Astra 03/10)
        self.assertFalse(t.dang_viet({**store, "hot": False}))

    def test_tin_tuong_lai_bi_loai(self):
        mai = (datetime.datetime.fromisoformat(NOW) + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(t.ly_do_khong_gui_viet({**tin_blog(1), "ngay": mai}, datetime.datetime.fromisoformat(NOW)), "ngày ở tương lai")

    def test_don_release_loi_xoa_thi_giu_tag(self):
        goi = []
        def api(pt, dd, tk, body=None):
            goi.append((pt, dd))
            if pt == "GET":
                return 200, [{"id": 9, "tag_name": "viet-20260901-0900", "published_at": "2026-09-01T02:00:00Z"}]
            return 500, None
        self.assertEqual(t.don_release_viet(NOW, "o/r", "tk", goi_api=api, log=lambda *a: None), 0)
        self.assertNotIn(("DELETE", "/repos/o/r/git/refs/tags/viet-20260901-0900"), goi)

    def test_don_release_tinh_tuoi_theo_published_at(self):
        goi = []
        def api(pt, dd, tk, body=None):
            goi.append((pt, dd))
            if pt == "GET":   # created_at cũ (ngày commit) nhưng vừa đăng -> giữ
                return 200, [{"id": 5, "tag_name": "viet-x", "created_at": "2026-09-01T00:00:00Z", "published_at": NOW}]
            return 204, None
        self.assertEqual(t.don_release_viet(NOW, "o/r", "tk", goi_api=api), 0)
        self.assertEqual([g for g in goi if g[0] == "DELETE"], [])


class TestChonGuiViet(unittest.TestCase):
    def test_gian_3_gio(self):
        ds = [tin_blog(1)]
        self.assertEqual(t.chon_tin_gui_viet(ds, NOW, "2026-10-03T09:30:00+07:00"), [])
        self.assertEqual(len(t.chon_tin_gui_viet(ds, NOW, "2026-10-03T08:30:00+07:00")), 1)
        self.assertEqual(len(t.chon_tin_gui_viet(ds, NOW, None)), 1)

    def test_toi_da_5_moi_nhat_truoc(self):
        ds = [tin_blog(i, ngay=f"2026-10-03T0{i}:00:00+07:00") for i in range(1, 8)]
        ra = t.chon_tin_gui_viet(ds, NOW)
        self.assertEqual([x["url"] for x in ra], [f"https://b/{i}" for i in range(7, 2, -1)])

    def test_qua_72_gio_va_da_danh_dau_bi_bo(self):
        ds = [tin_blog(1, ngay="2026-09-30T11:00:00+07:00"), tin_blog(2, da_gui_viet="x"), tin_blog(3, da_viet=True),
              tin_blog(4, ngay="2026-09-30T13:00:00+07:00")]
        self.assertEqual([x["url"] for x in t.chon_tin_gui_viet(ds, NOW)], ["https://b/4"])

    def test_bay_gio_datetime(self):
        d = t._dt(NOW)
        self.assertEqual(len(t.chon_tin_gui_viet([tin_blog(1)], d)), 1)


# ---- 12/10: 3 nguồn tin nóng ngoài (Gematsu, Push Square, PlayStation LifeStyle) -------------------
RSS_GEMATSU = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Foo Quest launches February 2027 for PS5 and Switch</title><link>https://www.gematsu.com/2026/10/foo</link>
<pubDate>Mon, 12 Oct 2026 04:00:00 +0000</pubDate><category><![CDATA[PS5]]></category><category><![CDATA[Switch]]></category><guid isPermaLink="false">https://www.gematsu.com/?p=1</guid>
<description><![CDATA[<img src="https://x/y.jpg"> Foo Quest for PS5 &amp; Switch launches <b>February 2027</b> &hellip;]]></description></item>
<item><title>Bar Saga announced for Switch</title><link>https://www.gematsu.com/2026/10/bar</link>
<pubDate>Mon, 12 Oct 2026 03:00:00 +0000</pubDate><category><![CDATA[Switch]]></category><category><![CDATA[Xbox Series]]></category><guid isPermaLink="false">https://www.gematsu.com/?p=2</guid></item>
<item><title>Baz Wars multiplatform release date set</title><link>https://www.gematsu.com/2026/10/baz</link>
<pubDate>Mon, 12 Oct 2026 02:00:00 +0000</pubDate><category><![CDATA[PC]]></category><category><![CDATA[Xbox Series]]></category><guid isPermaLink="false">https://www.gematsu.com/?p=3</guid></item>
</channel></rss>""".encode()

RSS_PUSH = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Tekken 9 Gets a Date</title><link>https://www.pushsquare.com/news/2026/10/tekken-9</link><pubDate>Mon, 12 Oct 2026 04:00:00 +0000</pubDate>
<guid isPermaLink="false">https://www.pushsquare.com/#article-1</guid>
<description><![CDATA[<p><strong>Soon.</strong></p><p><a href="https://www.pushsquare.com/games/ps5/tekken_9">Tekken 9</a> is coming.</p>]]></description></item>
<item><title>Nintendo Showcase Recap</title><link>https://www.pushsquare.com/news/2026/10/nintendo</link><pubDate>Mon, 12 Oct 2026 03:00:00 +0000</pubDate>
<guid isPermaLink="false">https://www.pushsquare.com/#article-2</guid>
<description><![CDATA[<p><a href="https://www.pushsquare.com/games/switch/zelda">Zelda</a> stuff.</p>]]></description></item>
</channel></rss>""".encode()

RSS_PSLS = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Popular RPG Is 80% Off</title><link>https://www.playstationlifestyle.net/2026/10/a</link><pubDate>Mon, 12 Oct 2026 04:00:00 +0000</pubDate>
<category>News</category><category>PS5</category><guid isPermaLink="false">https://www.playstationlifestyle.net/?p=1</guid>
<content:encoded><![CDATA[<p>A popular RPG is on sale.</p>]]></content:encoded></item>
<item><title>Xbox Game Pass October wave</title><link>https://www.playstationlifestyle.net/2026/10/b</link><pubDate>Mon, 12 Oct 2026 03:00:00 +0000</pubDate>
<category>News</category><category>Xbox</category><guid isPermaLink="false">https://www.playstationlifestyle.net/?p=2</guid></item>
</channel></rss>""".encode()


def tin_ngoai(feed, rss, i):
    ds = t.phan_tich_rss(rss)
    b = ds[i]
    return {"nguon": t.NGUON_TEN[feed], "tieu_de": b["tieu_de"], "url": b["url"], "ngay": "2026-10-03T08:00:00+07:00", "the_loai": b["the_loai"],
            "hot": False, "ly_do_hot": "", "da_viet": False, "tom_tat": b["tom_tat"], "goi_y_ps": b["goi_y_ps"]}


class TestNguonNgoai(unittest.TestCase):
    def test_feeds_va_ten(self):
        self.assertEqual(t.FEEDS["gematsu"], "https://www.gematsu.com/feed")
        self.assertEqual(t.FEEDS["pushsquare"], "https://www.pushsquare.com/feeds/latest")
        self.assertEqual(t.FEEDS["pslifestyle"], "https://www.playstationlifestyle.net/feed/")
        self.assertEqual((t.NGUON_TEN["gematsu"], t.NGUON_TEN["pushsquare"], t.NGUON_TEN["pslifestyle"]),
                         ("Gematsu", "Push Square", "PlayStation LifeStyle"))

    def test_tom_tat_bo_html_thuc_the_va_cat_600(self):
        g = t.phan_tich_rss(RSS_GEMATSU)[0]
        self.assertEqual(g["tom_tat"], "Foo Quest for PS5 & Switch launches February 2027 …")
        self.assertEqual(t.phan_tich_rss(RSS_PSLS)[0]["tom_tat"], "A popular RPG is on sale.")        # content:encoded khi thiếu description
        dai = t.tom_tat_rss("<p>" + "a" * 2000 + "</p>")
        self.assertLessEqual(len(dai), 601)
        self.assertTrue(dai.endswith("…"))

    def test_loc_playstation_ca_3_nguon(self):
        co = lambda feed, rss, i: t.dang_viet(tin_ngoai(feed, rss, i))
        self.assertTrue(co("gematsu", RSS_GEMATSU, 0))          # thể loại PS5 (đa nền tảng có PS)
        self.assertFalse(co("gematsu", RSS_GEMATSU, 1))         # Switch + Xbox -> loại
        self.assertFalse(co("gematsu", RSS_GEMATSU, 2))         # đa nền tảng không có PS -> loại
        self.assertTrue(co("pushsquare", RSS_PUSH, 0))          # link trang game PS5
        self.assertFalse(co("pushsquare", RSS_PUSH, 1))         # link trang game Switch -> loại
        self.assertTrue(co("pslifestyle", RSS_PSLS, 0))
        self.assertFalse(co("pslifestyle", RSS_PSLS, 1))

    def test_so_sanh_nguon_ngoai_mang_tom_tat_va_lan_dau_chi_ghi(self):
        d0 = dl(blog={"blog": [], "blog-ps-plus": [], "gematsu": [], "pushsquare": [], "pslifestyle": []})
        _, tt = t.so_sanh({}, d0)
        g = t.phan_tich_rss(RSS_GEMATSU)
        d1 = dl(blog={"blog": [], "blog-ps-plus": [], "gematsu": g, "pushsquare": [], "pslifestyle": []})
        tin, _ = t.so_sanh(tt, d1)
        self.assertEqual(len(tin), 3)
        self.assertEqual(tin[0]["nguon"], "Gematsu")
        self.assertIn("February 2027", tin[0]["tom_tat"])
        _, tt_dau = t.so_sanh({}, d1)
        self.assertEqual(t.so_sanh(tt_dau, d1)[0], [])           # lần đầu chỉ ghi mốc

    def test_release_kem_tom_tat_nguon_ngoai_khong_kem_o_blog(self):
        goi = []
        def api(pt, dd, tk, body=None):
            goi.append(body)
            return 201, None
        ngoai = tin_ngoai("gematsu", RSS_GEMATSU, 0)
        t.tao_release_viet([ngoai, tin_blog(1)], NOW, "o/r", "tk", goi_api=api)
        tin = json.loads(goi[0]["body"])["tin"]
        self.assertIn("February 2027", tin[0]["tom_tat"])
        self.assertNotIn("tom_tat", tin[1])
        self.assertEqual(tin[0]["nguon"], "Gematsu")

    def test_viet_toi_da_va_chinh_chu_truoc(self):
        ngoai = [{**tin_ngoai("gematsu", RSS_GEMATSU, 0), "url": f"https://g/{i}", "ngay": f"2026-10-03T1{i}:00:00+07:00"} for i in range(0, 1)]
        ngoai += [{**tin_ngoai("pslifestyle", RSS_PSLS, 0), "url": f"https://p/{i}", "ngay": f"2026-10-03T1{i}:30:00+07:00"} for i in range(0, 1)]
        ngoai += [{**tin_ngoai("pushsquare", RSS_PUSH, 0), "url": f"https://s/{i}", "ngay": f"2026-10-03T0{i}:15:00+07:00"} for i in range(1, 6)]
        chinh = [tin_blog(1, ngay="2026-10-03T07:00:00+07:00"), tin_blog(2, ngay="2026-10-03T06:00:00+07:00")]
        ra = t.chon_tin_gui_viet(ngoai + chinh, NOW)
        self.assertEqual(len(ra), t.VIET_TOI_DA)                              # giới hạn giữ nguyên
        self.assertEqual([x["url"] for x in ra[:2]], ["https://b/1", "https://b/2"])   # chính chủ trước
        self.assertTrue(all(t.la_tin_ngoai(x) for x in ra[2:]))

    def test_tin_switch_only_khong_vao_hang_gui_viet(self):
        sw = tin_ngoai("gematsu", RSS_GEMATSU, 1)
        self.assertEqual(t.chon_tin_gui_viet([sw], NOW), [])
        self.assertIn("không đáng viết", t.ly_do_khong_gui_viet(sw, datetime.datetime.fromisoformat(NOW)))

    def test_tin_tong_hop_japanese_game_releases_bi_loai(self):
        x = {**tin_ngoai("gematsu", RSS_GEMATSU, 0), "tieu_de": "This Week’s Japanese Game Releases: A, B, more"}
        self.assertFalse(t.dang_viet(x))


# ---- 12/10 (Sol soi lại): nguồn ngoài đọc SAU nguồn cũ, ngân sách riêng; lọc PS cần bằng chứng trực tiếp; tóm tắt rỗng thì dùng content:encoded ----
class TestNguonNgoaiNganSach(unittest.TestCase):
    def test_doc_nguon_ngoai_sau_nguon_cu_va_timeout_ngan(self):
        thu_tu, timeouts = [], {}

        def http(url, headers=None, timeout=15):
            thu_tu.append(url)
            timeouts[url] = timeout
            if url in t.FEEDS_NGOAI.values():
                raise OSError("chậm")
            if "/feed/" in url:
                return RSS
            if "gameslist" in url:
                return json.dumps([{"games": [{"name": "X"}]}]).encode()
            return json.dumps({"data": {"categoryGridRetrieve": {"pageInfo": {"totalCount": 5}}}}).encode()
        d = t.lay_du_lieu(http, lambda s: None, log=lambda *_: None)
        ngoai = set(t.FEEDS_NGOAI.values())
        vi_tri = [i for i, u in enumerate(thu_tu) if u in ngoai]
        self.assertTrue(vi_tri)
        self.assertGreater(min(vi_tri), max(i for i, u in enumerate(thu_tu) if u not in ngoai))   # mọi nguồn cũ xong trước nguồn ngoài đầu tiên
        self.assertEqual([timeouts[u] for u in ngoai], [t.TIMEOUT_NGOAI] * len(t.FEEDS_NGOAI))
        self.assertLessEqual(t.TIMEOUT_NGOAI, 15)
        for u in ngoai:
            self.assertEqual(thu_tu.count(u), 2)                      # 1 lần đầu + đúng 1 lần thử lại
        self.assertIsNotNone(d["blog"]["blog"])
        self.assertEqual(d["plus"], ["X"])
        self.assertEqual(d["deals"]["en-US"], 5)
        self.assertTrue(all(d["blog"][k] is None for k in t.FEEDS_NGOAI))

    def test_nguon_ngoai_treo_khong_an_ngan_sach_nguon_cu_va_bi_chan_o_ngan_sach_rieng(self):
        gio = [0.0]
        goi = []

        def http(url, headers=None, timeout=15):
            goi.append(url)
            if url in t.FEEDS_NGOAI.values():
                gio[0] += 40                                           # mỗi lần đọc nguồn ngoài "treo" 40s
                raise OSError("treo")
            gio[0] += 1
            if "/feed/" in url:
                return RSS
            if "gameslist" in url:
                return json.dumps([{"games": [{"name": "X"}]}]).encode()
            return json.dumps({"data": {"categoryGridRetrieve": {"pageInfo": {"totalCount": 5}}}}).encode()
        d = t.lay_du_lieu(http, lambda s: gio.__setitem__(0, gio[0] + s), log=lambda *_: None, dong_ho=lambda: gio[0])
        self.assertIsNotNone(d["blog"]["blog"])
        self.assertIsNotNone(d["blog"]["blog-ps-plus"])
        self.assertEqual((d["plus"], d["deals"]["en-US"], d["extra"]["en-SG"]), (["X"], 5, 5))   # nguồn cũ đủ hết
        # tổng thời gian nguồn ngoài bị chặn quanh ngân sách riêng (45s) + 1 request cuối, không tới 3 x (40+5+40)
        self.assertLess(gio[0], 6 + t.NGAN_SACH_NGOAI + 40 + 1)


RSS_PS_PUSH_AM = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Zelda Gets A Date On Switch</title><link>https://www.pushsquare.com/news/2026/10/zelda</link><pubDate>Mon, 12 Oct 2026 04:00:00 +0000</pubDate>
<guid isPermaLink="false">https://www.pushsquare.com/#a1</guid>
<description><![CDATA[<p><a href="https://www.pushsquare.com/games/switch/zelda">Zelda</a> is coming. Unlike <a href="https://www.pushsquare.com/games/ps5/astro_bot">Astro Bot</a>, it is Nintendo only.</p>]]></description></item>
<item><title>Big Showcase Recap</title><link>https://www.pushsquare.com/news/2026/10/recap</link><pubDate>Mon, 12 Oct 2026 03:00:00 +0000</pubDate>
<guid isPermaLink="false">https://www.pushsquare.com/#a2</guid>
<description><![CDATA[<p>We also saw <a href="https://www.pushsquare.com/games/ps5/tekken_9">Tekken 9</a> in passing.</p>]]></description></item>
<item><title>Tekken 9 And Zelda Both Dated</title><link>https://www.pushsquare.com/news/2026/10/both</link><pubDate>Mon, 12 Oct 2026 02:00:00 +0000</pubDate>
<guid isPermaLink="false">https://www.pushsquare.com/#a3</guid>
<description><![CDATA[<p><a href="https://www.pushsquare.com/games/ps5/tekken_9">Tekken 9</a> and <a href="https://www.pushsquare.com/games/switch/zelda">Zelda</a> have dates.</p>]]></description></item>
<item><title>Tekken 9 Gets A Date</title><link>https://www.pushsquare.com/news/2026/10/tekken</link><pubDate>Mon, 12 Oct 2026 01:00:00 +0000</pubDate>
<guid isPermaLink="false">https://www.pushsquare.com/#a4</guid>
<description><![CDATA[<p><a href="https://www.pushsquare.com/games/ps5/tekken_9">Tekken 9</a> arrives soon.</p>]]></description></item>
</channel></rss>""".encode()


class TestLocPsChatChe(unittest.TestCase):
    def co(self, rss, i, feed="pushsquare"):
        return t.dang_viet(tin_ngoai(feed, rss, i))

    def test_link_ps_tham_khao_khong_du(self):
        self.assertFalse(self.co(RSS_PS_PUSH_AM, 0))     # bài Switch, chỉ nhắc game PS5 để so sánh
        self.assertFalse(self.co(RSS_PS_PUSH_AM, 1))     # link game PS5 nhưng chữ link không nằm trong tiêu đề (nhắc qua loa)
        self.assertFalse(self.co(RSS_PS_PUSH_AM, 2))     # tiêu đề nhắc cả game PS lẫn Switch: không đủ bằng chứng chỉ-PS
        self.assertTrue(self.co(RSS_PS_PUSH_AM, 3))      # link game PS5 là chủ đề chính (chữ link nằm trong tiêu đề)

    def test_the_loai_playstation_la_bang_chung_truc_tiep(self):
        x = {**tin_ngoai("gematsu", RSS_GEMATSU, 1), "the_loai": ["PlayStation 5"], "tieu_de": "Quiet Game gets a date"}
        self.assertTrue(t.dang_viet(x))
        x["the_loai"] = ["PS Plus"]
        self.assertTrue(t.dang_viet(x))
        x["the_loai"] = ["Nintendo Switch", "Xbox Series"]
        self.assertFalse(t.dang_viet(x))

    def test_tieu_de_khong_ghi_nen_tang_va_khong_the_loai_khong_nhan(self):
        x = {**tin_ngoai("gematsu", RSS_GEMATSU, 1), "the_loai": [], "tieu_de": "Quiet Game gets a date", "goi_y_ps": False}
        self.assertFalse(t.dang_viet(x))


class TestTomTatRong(unittest.TestCase):
    def test_description_chi_co_anh_thi_dung_content_encoded(self):
        xml = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Quiet PS5 Game</title><link>https://www.pushsquare.com/news/x</link><guid isPermaLink="false">g1</guid>
<description><![CDATA[<img src="https://x/y.jpg"/>]]></description>
<content:encoded><![CDATA[<p>Real <b>summary</b> text.</p>]]></content:encoded></item>
<item><title>Both Empty</title><link>https://www.pushsquare.com/news/y</link><guid isPermaLink="false">g2</guid>
<description><![CDATA[<img src="https://x/y.jpg"/>]]></description></item>
<item><title>Has Description</title><link>https://www.pushsquare.com/news/z</link><guid isPermaLink="false">g3</guid>
<description><![CDATA[<p>From description.</p>]]></description>
<content:encoded><![CDATA[<p>From encoded.</p>]]></content:encoded></item>
</channel></rss>""".encode()
        a, b, c = t.phan_tich_rss(xml)
        self.assertEqual(a["tom_tat"], "Real summary text.")
        self.assertEqual(b["tom_tat"], "")
        self.assertEqual(c["tom_tat"], "From description.")


class TestGoiViet(unittest.TestCase):
    def chay(self, d, api, **kw):
        return t.chay(d, du_lieu=dl(), kenh="", goi_api=api, gio=lambda: NOW, token="tk", repo="o/r", **kw)

    def _dat(self, d, tin, tt=None):
        (pathlib.Path(d) / "tin-moi.json").write_text(json.dumps(tin), encoding="utf-8")
        (pathlib.Path(d) / "tin-da-thay.json").write_text(json.dumps(tt or {}), encoding="utf-8")

    def test_thanh_cong_danh_dau(self):
        with tempfile.TemporaryDirectory() as d:
            self._dat(d, [tin_blog(1), tin_blog(2, "Official PlayStation Podcast 1")])
            api = GiaApi()
            self.chay(d, api)
            post = [g for g in api.goi if g[0] == "POST"]
            self.assertEqual(len(post), 1)
            self.assertEqual(post[0][1], "/repos/o/r/releases")
            self.assertEqual(post[0][2], "tk")
            b = post[0][3]
            self.assertEqual(b["tag_name"], "viet-20261003-1200")
            self.assertEqual(b["name"], "Viết tin 03/10 12:00")
            self.assertEqual(b["target_commitish"], "main")
            self.assertEqual(b["make_latest"], "false")
            nd = json.loads(b["body"])
            self.assertEqual([x["url"] for x in nd["tin"]], ["https://b/1"])
            self.assertEqual(set(nd["tin"][0]), {"tieu_de", "url", "nguon", "ngay", "the_loai"})
            hd = json.loads((pathlib.Path(d) / "tin-moi.json").read_text(encoding="utf-8"))
            self.assertEqual(hd[0]["da_gui_viet"], NOW)
            self.assertNotIn("da_gui_viet", hd[1])
            tt = json.loads((pathlib.Path(d) / "tin-da-thay.json").read_text(encoding="utf-8"))
            self.assertEqual(tt["lan_goi_viet"], NOW)
            # lượt sau (ngay sau đó) không gọi lại
            api2 = GiaApi()
            self.chay(d, api2)
            self.assertEqual([g for g in api2.goi if g[0] == "POST"], [])

    def test_loi_khong_danh_dau(self):
        for api in (GiaApi(ma_post=500), GiaApi(loi=OSError("mạng"))):
            with tempfile.TemporaryDirectory() as d:
                self._dat(d, [tin_blog(1)])
                self.chay(d, api)
                hd = json.loads((pathlib.Path(d) / "tin-moi.json").read_text(encoding="utf-8"))
                self.assertNotIn("da_gui_viet", hd[0])
                tt = json.loads((pathlib.Path(d) / "tin-da-thay.json").read_text(encoding="utf-8"))
                self.assertNotIn("lan_goi_viet", tt)

    def test_thieu_token_chi_in(self):
        with tempfile.TemporaryDirectory() as d:
            self._dat(d, [tin_blog(1)])
            api = GiaApi()
            t.chay(d, du_lieu=dl(), kenh="", goi_api=api, gio=lambda: NOW)
            self.assertEqual(api.goi, [])
            hd = json.loads((pathlib.Path(d) / "tin-moi.json").read_text(encoding="utf-8"))
            self.assertNotIn("da_gui_viet", hd[0])

    def test_thu_khong_goi_mang_khong_ghi(self):
        with tempfile.TemporaryDirectory() as d:
            self._dat(d, [tin_blog(1)])
            api = GiaApi()
            t.chay(d, thu=True, du_lieu=dl(), goi_api=api, gio=lambda: NOW, token="tk", repo="o/r")
            self.assertEqual(api.goi, [])
            hd = json.loads((pathlib.Path(d) / "tin-moi.json").read_text(encoding="utf-8"))
            self.assertNotIn("da_gui_viet", hd[0])

    def test_don_release_cu(self):
        rel = [{"id": 1, "tag_name": "viet-20260920-0900", "created_at": "2026-09-20T02:00:00Z"},
               {"id": 2, "tag_name": "viet-20261002-0900", "created_at": "2026-10-02T02:00:00Z"},
               {"id": 3, "tag_name": "v1.0", "created_at": "2026-01-01T00:00:00Z"}]
        api = GiaApi(releases=rel)
        self.assertEqual(t.don_release_viet(NOW, "o/r", "tk", api), 1)
        xoa = [(g[0], g[1]) for g in api.goi if g[0] == "DELETE"]
        self.assertEqual(xoa, [("DELETE", "/repos/o/r/releases/1"), ("DELETE", "/repos/o/r/git/refs/tags/viet-20260920-0900")])

    def test_don_release_loi_bo_qua(self):
        self.assertEqual(t.don_release_viet(NOW, "o/r", "tk", GiaApi(loi=OSError("x")), log=lambda m: None), 0)


# ---- 12/10: tin rò rỉ billbil-kun (RSS Bluesky: item không có <title>, chữ bài ở <description>) ----
RSS_BSKY = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><link>https://bsky.app/profile/billbil-kun.bsky.social</link><title>@billbil-kun.bsky.social - billbil-kun</title>
<item><link>https://bsky.app/profile/billbil-kun.bsky.social/post/3mxjn2i36ss2y</link><description>🚨 EXCLUSIVE 🚨&#xA;Metro 2039 - Pre-orders&#xA;&#xA;Physical versions on PS5, Xbox and PC&#xA;PS5 edition has a bonus&#xA;&#xA;🔽&#xA;🔗 https://www.dealabs.com/magazine/metro-2039-61755</description><pubDate>10 Oct 2026 13:50 +0000</pubDate><guid isPermaLink="false">at://did:plc:x/app.bsky.feed.post/3mxjn2i36ss2y</guid></item>
<item><link>https://bsky.app/profile/billbil-kun.bsky.social/post/3mx7e725d6c2m</link><description>🚨 EXCLUSIVE 🚨&#xA;&#xA;Google&#39;s next Fitbit is called Fitbit Edge, and we got the full spec sheet&#xA;&#xA;🔽&#xA;🔗 https://www.dealabs.com/magazine/fitbit-edge-61736</description><pubDate>06 Oct 2026 11:45 +0000</pubDate><guid isPermaLink="false">at://did:plc:x/app.bsky.feed.post/3mx7e725d6c2m</guid></item>
<item><link>https://bsky.app/profile/billbil-kun.bsky.social/post/3mw1</link><description>CONFIRMED&#xA;&#xA;XBOX Series X25 Limited Edition will cost 899.99 USD as we estimated from EUR pricing</description><pubDate>26 Aug 2026 14:51 +0000</pubDate><guid isPermaLink="false">at://did:plc:x/app.bsky.feed.post/3mw1</guid></item>
<item><link>https://bsky.app/profile/billbil-kun.bsky.social/post/3mw2</link><description>🚨 EXCLUSIVE 🚨&#xA;&#xA;We now reveal, during PS Blackout, ALL titles for September&#39;s PS Plus Monthly Games&#xA;&#xA;🗒️ Available for all PS Plus tiers (Essential, Extra &amp; Premium)&#xA;⌛️ Sep 1st - Oct 6th, 2026 10AM UTC+2&#xA;&#xA;🔽&#xA;🔗 https://www.dealabs.com/magazine/ps-plus-septembre-2026-61681</description><pubDate>25 Aug 2026 14:53 +0000</pubDate><guid isPermaLink="false">at://did:plc:x/app.bsky.feed.post/3mw2</guid></item>
</channel></rss>""".encode()


class TestLeakBillbil(unittest.TestCase):
    def test_cau_hinh(self):
        self.assertEqual(t.FEEDS_LEAK["billbil"], "https://bsky.app/profile/billbil-kun.bsky.social/rss")
        self.assertEqual(t.NGUON_TEN["billbil"], "billbil-kun (Dealabs)")
        self.assertIn(t.FEEDS_LEAK["billbil"], t.FEEDS_NGOAI.values())       # đọc chung vòng nguồn ngoài (ngân sách riêng)

    def test_tieu_de_bo_nhan_emoji(self):
        td = t.tieu_de_leak
        self.assertEqual(td("🚨 EXCLUSIVE 🚨\nMetro 2039 - Pre-orders\n\nx"), "Metro 2039 - Pre-orders")
        self.assertEqual(td("⚠️ UPDATE ⚠️\n\nThe new controller is out"), "The new controller is out")
        self.assertEqual(td("CONFIRMED\n\nXBOX Series X25 costs 899 USD"), "XBOX Series X25 costs 899 USD")
        self.assertEqual(td("🚨 UPCOMING RELEASE 🚨\n\nSony is preparing a headphone 👀"), "Sony is preparing a headphone")
        self.assertEqual(td("🚨 EXCLUSIVE 🚨\n\n🔗\nhttps://x.y/z\nDòng kế có chữ"), "Dòng kế có chữ")   # dòng rỗng chữ/chỉ link -> dòng kế
        self.assertEqual(td("🚨 EXCLUSIVE 🚨"), "")
        self.assertLessEqual(len(td("A" + "b" * 300)), t.TIEU_DE_LEAK_TOI_DA)
        self.assertTrue(td("A" + "b" * 300).endswith("…"))

    def test_phan_tich_rss_bluesky(self):
        ds = t.phan_tich_rss_bsky(RSS_BSKY)
        self.assertEqual(len(ds), 4)                                           # item không có <title> vẫn đọc được
        self.assertEqual([d["ps"] for d in ds], [True, False, False, True])    # chỉ Metro (PS5 2 lần trong thân) và PS Plus (trong tiêu đề) qua lọc PS
        self.assertEqual(ds[0]["tieu_de"], "Metro 2039 - Pre-orders")
        self.assertEqual(ds[3]["tieu_de"], "We now reveal, during PS Blackout, ALL titles for September's PS Plus Monthly Games")
        self.assertEqual(ds[3]["link_goc"], "https://www.dealabs.com/magazine/ps-plus-septembre-2026-61681")
        self.assertEqual(ds[2]["link_goc"], "")
        self.assertEqual(ds[3]["url"], "https://bsky.app/profile/billbil-kun.bsky.social/post/3mw2")
        self.assertEqual(ds[3]["the_loai"], ["leak"])
        self.assertTrue(ds[3]["ngay"].startswith("2026-08-25T21:53:00"))      # 14:53 UTC = 21:53 VN
        self.assertIn("Essential, Extra & Premium", ds[3]["tom_tat"])
        for xau in (b"<html>x</html>", b"<rss version='2.0'><channel><title>x</title></channel></rss>"):
            with self.assertRaises(Exception):
                t.phan_tich_rss_bsky(xau)

    def test_loc_ps_cuc_bo(self):
        r = t.LEAK_PS_RE
        for co in ("on PS5", "PS Plus tiers", "the PlayStation 6", "ps portal", "DualSense Edge", "PSVR2", "PS VR2"):
            self.assertTrue(r.search(co), co)
        for khong in ("Xbox only", "UPS5", "Switch 2", "Pixel phone"):
            self.assertFalse(r.search(khong), khong)

    def test_so_sanh_chi_2_item_ps_qua_va_mang_truong(self):
        rong = {"blog": [], "blog-ps-plus": [], "billbil": []}
        _, tt = t.so_sanh({}, dl(blog=rong))                                   # lần đầu chỉ ghi mốc
        d = dl(blog={**rong, "billbil": t.phan_tich_rss_bsky(RSS_BSKY)})
        tin, tt2 = t.so_sanh(tt, d)
        self.assertEqual([x["tieu_de"][:5] for x in tin], ["Metro", "We no"])
        x = tin[1]
        self.assertEqual((x["nguon"], x["the_loai"], x["hot"], x["da_viet"]), ("billbil-kun (Dealabs)", ["leak"], True, False))
        self.assertEqual(x["link_goc"], "https://www.dealabs.com/magazine/ps-plus-septembre-2026-61681")
        self.assertIn("PS Plus", x["tom_tat"])
        self.assertEqual(len(tt2["guid"]["billbil"]), 4)                       # item không-PS vẫn ghi guid: lượt sau không xét lại
        self.assertEqual(t.so_sanh(tt2, d)[0], [])

    def test_leak_vao_hang_gui_viet_va_release_kem_link_goc(self):
        rong = {"blog": [], "blog-ps-plus": [], "billbil": []}
        _, tt = t.so_sanh({}, dl(blog=rong))
        tin, _ = t.so_sanh(tt, dl(blog={**rong, "billbil": t.phan_tich_rss_bsky(RSS_BSKY)}))
        for x in tin:
            x["ngay"] = "2026-10-03T08:00:00+07:00"
        self.assertTrue(all(t.dang_viet(x) for x in tin))
        chon = t.chon_tin_gui_viet(tin + [tin_blog(1, ngay="2026-10-03T09:00:00+07:00")], NOW)
        self.assertEqual(chon[0]["nguon"], "PlayStation Blog")                # Sony chính chủ đứng trước leak
        self.assertEqual([x["nguon"] for x in chon[1:]], ["billbil-kun (Dealabs)"] * 2)
        goi = []
        def api(pt, dd, tk, body=None):
            goi.append(body)
            return 201, None
        t.tao_release_viet(chon, NOW, "o/r", "tk", goi_api=api)
        nd = json.loads(goi[0]["body"])["tin"]
        leak = [x for x in nd if x["nguon"] == "billbil-kun (Dealabs)"]
        self.assertEqual(len(leak), 2)
        self.assertEqual(leak[1]["the_loai"], ["leak"])
        self.assertTrue(leak[1]["link_goc"].startswith("https://www.dealabs.com/"))
        self.assertIn("tom_tat", leak[1])
        self.assertNotIn("link_goc", [x for x in nd if x["nguon"] == "PlayStation Blog"][0])

    def _ps(self, mo_ta):
        xml = ("<rss version='2.0'><channel><item><link>https://bsky.app/profile/billbil-kun.bsky.social/post/a</link><description>"
               + mo_ta + "</description><guid>g</guid></item></channel></rss>").encode()
        return t.phan_tich_rss_bsky(xml)[0]["ps"]

    def test_loc_ps_tren_chu_da_lam_sach(self):
        self.assertFalse(self._ps("🚨 EXCLUSIVE 🚨&#xA;&#xA;New Xbox controller revealed&#xA;Unlike PS5, it has Hall effect sticks"))   # nhắc so sánh 1 lần
        self.assertFalse(self._ps("🚨 EXCLUSIVE 🚨&#xA;&#xA;Switch 2 bundle price&#xA;🔗 https://www.playstation.com/ps5/ https://www.dealabs.com/magazine/ps5-ps5"))   # PS chỉ nằm trong URL
        self.assertFalse(self._ps("🚨 EXCLUSIVE 🚨&#xA;&#xA;Switch 2 bundle&#xA;&lt;a href=&quot;https://www.playstation.com/PlayStation&quot;&gt;here&lt;/a&gt;"))   # PS trong thẻ HTML thuộc tính
        self.assertTrue(self._ps("🚨 EXCLUSIVE 🚨&#xA;&#xA;PS Plus Monthly Games for September leaked&#xA;Details soon"))   # trong tiêu đề
        self.assertTrue(self._ps("🚨 EXCLUSIVE 🚨&#xA;&#xA;Metro 2039 pre-orders&#xA;PS5 and PlayStation 5 Pro editions"))   # >= 2 lần trong thân

    def test_5_leak_va_1_tin_sony_sony_van_duoc_chon(self):
        leak = [{**tin_blog(i, ngay=f"2026-10-03T0{i}:00:00+07:00"), "nguon": "billbil-kun (Dealabs)", "the_loai": ["leak"], "hot": True,
                 "url": f"https://l/{i}"} for i in range(1, 6)]
        sony = tin_blog(9, ngay="2026-10-03T01:00:00+07:00")                 # cũ nhất, không hot
        chon = t.chon_tin_gui_viet(leak + [sony], NOW)
        self.assertEqual(len(chon), t.VIET_TOI_DA)
        self.assertEqual(chon[0]["url"], "https://b/9")
        self.assertIn("https://b/9", [x["url"] for x in chon])
        self.assertEqual(sum(la_ for la_ in map(t.la_tin_leak, chon)), 4)
        ngoai = {**tin_ngoai("gematsu", RSS_GEMATSU, 0), "url": "https://g/1"}
        chon2 = t.chon_tin_gui_viet([ngoai] + leak + [sony], NOW)
        self.assertEqual([t.la_tin_leak(x) for x in chon2], [False, True, True, True, True])   # Sony > leak > ngoài khác (ngoài bị đẩy khỏi giới hạn)

    def test_leak_hong_mang_khong_lam_hong_blog(self):
        def http(url, headers=None, timeout=15):
            if "bsky.app" in url:
                raise OSError("bluesky chết")
            if "/feed/" in url:
                return RSS
            if "gameslist" in url:
                return json.dumps([{"games": [{"name": "X"}]}]).encode()
            return json.dumps({"data": {"categoryGridRetrieve": {"pageInfo": {"totalCount": 5}}}}).encode()
        d = t.lay_du_lieu(http, lambda s: None, log=lambda *_: None)
        self.assertIsNone(d["blog"]["billbil"])
        self.assertEqual(len(d["blog"]["blog"]), 2)
        self.assertEqual(d["plus"], ["X"])
        _, tt = t.so_sanh({}, dl(blog={"blog": [bai(1)], "blog-ps-plus": [], "billbil": t.phan_tich_rss_bsky(RSS_BSKY)}))
        tin, tt2 = t.so_sanh(tt, d)                                             # billbil None: giữ guid cũ, blog vẫn chạy
        self.assertEqual(tt2["guid"]["billbil"], tt["guid"]["billbil"])

    def test_doc_leak_bang_parser_rieng(self):
        def http(url, headers=None, timeout=15):
            if "bsky.app" in url:
                return RSS_BSKY
            raise OSError("x")
        d = t.lay_du_lieu(http, lambda s: None, log=lambda *_: None)
        self.assertEqual(len(d["blog"]["billbil"]), 4)
        self.assertTrue(d["blog"]["billbil"][0]["ps"])

    def test_thu_in_ly_do_loai(self):
        import contextlib, io
        with tempfile.TemporaryDirectory() as dd:
            du = dl(blog={"blog": [], "blog-ps-plus": [], "billbil": t.phan_tich_rss_bsky(RSS_BSKY)})
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                t.chay(dd, thu=True, du_lieu=du, gio=lambda: NOW)
            out = buf.getvalue()
            self.assertIn("LEAK billbil-kun (Dealabs): 4 bài", out)
            self.assertIn("[PS ] We now reveal", out)
            self.assertIn("[loại: không nhắc PS5/PS4/PS Plus/PlayStation…] Google's next Fitbit", out)
            self.assertFalse((pathlib.Path(dd) / "tin-da-thay.json").exists())   # --thu không ghi file


if __name__ == "__main__":
    unittest.main()
