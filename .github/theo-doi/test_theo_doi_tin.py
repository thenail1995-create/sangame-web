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
        self.assertLessEqual(len(goi), 3)  # sau ~240s thì ngừng gọi, không đủ 3 lần x 6 nguồn

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


if __name__ == "__main__":
    unittest.main()
