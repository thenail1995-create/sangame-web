(function(){
  var KHOA_LS = "sangame_cho_sale";
  var KHOA_DONG = "sangame_cho_sale_dong_ngay";
  var DATA_URL = "du-lieu/tim-gia.json";
  var GIA_THE_URL = "du-lieu/gia-the-vung.json";

  function ngayHomNay(){
    var d = new Date();
    return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
  }

  // Chuẩn hoá tên game — PHẢI giống tuyệt đối trang_cho_sale.khoa_ten() bên Python (xử lý đ/Đ
  // trước NFD, bỏ mọi dấu tổ hợp, hạ chữ, gọn khoảng trắng) để 1 khoá tạo bằng nút render sẵn ở
  // server (dung-web.py) khớp lại được với tên tính bằng JS ở đây.
  function boDau(s){
    return (s || "").replace(/đ/g, "d").replace(/Đ/g, "D")
      .normalize("NFD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  // Tên kênh ntfy của 1 game — PHẢI giống tuyệt đối trang_cho_sale.kenh_ntfy() bên Python
  // (FNV-1a 32 bit trên byte UTF-8, 2 lần: khoa và "sg|"+khoa). khoa đã qua boDau() nên chỉ còn
  // [a-z0-9 ] -> mỗi ký tự là đúng 1 byte, charCodeAt dùng thẳng được.
  function fnv1a32(s){
    var h = 0x811c9dc5;
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i) & 0xff; h = Math.imul(h, 0x01000193) >>> 0; }
    return ("0000000" + h.toString(16)).slice(-8);
  }
  function kenhNtfy(khoa){ return "sangame-" + fnv1a32(khoa) + fnv1a32("sg|" + khoa); }

  function docDs(){
    try {
      var raw = localStorage.getItem(KHOA_LS);
      var ds = raw ? JSON.parse(raw) : [];
      return Array.isArray(ds) ? ds : [];
    } catch (err) { return []; }
  }
  function luuDs(ds){
    try { localStorage.setItem(KHOA_LS, JSON.stringify(ds)); } catch (err) { /* riêng tư/đầy bộ nhớ: bỏ qua */ }
  }
  function dangCho(khoa){
    var ds = docDs();
    for (var i = 0; i < ds.length; i++) if (ds[i].khoa === khoa) return true;
    return false;
  }
  // C4: `may` (g[2] của tim-gia.json, có thể là "" nên phân biệt bằng != null) + `loai` (g[1]) ghi
  // lại ĐÚNG phiên bản người dùng đã bấm ở Tìm giá — cùng tên khác máy (Gran Turismo 7 PS4 / PS4+PS5)
  // là 2 dòng riêng trong tim-gia.json. Mục cũ không có may/loai vẫn đọc được (xem chonDong).
  // Đã có mục cùng khoá thì chỉ cập nhật phiên bản (không tạo mục thứ 2 — 1 game = 1 kênh ntfy).
  // R1: ngoài may/loai còn lưu "dấu vân tay" của dòng lúc bấm — ten (tên gốc g[0], chưa gọn) + vt (chỉ
  // số vùng đầu tiên có giá) + goc (giá gốc ở vùng đó): cùng (tên, máy, loại) vẫn có thể là nhiều dòng
  // khác giá (KINGDOM HEARTS III có 3 dòng máy "4"), tim-gia.json chưa có id nên dùng giá trị ổn định này.
  function dauVan(g){
    var gia = (g && g[3]) || [];
    for (var i = 0; i < gia.length; i++) if (Array.isArray(gia[i])) return { vt: i, goc: gia[i][0] };
    return { vt: -1, goc: null };
  }
  function themGame(khoa, ten, may, loai, dau){
    var ds = docDs(), it = null;
    for (var i = 0; i < ds.length; i++) if (ds[i].khoa === khoa) { it = ds[i]; break; }
    if (!it) { it = { khoa: khoa, ten: ten, ngay: ngayHomNay() }; ds.push(it); }
    else if (may == null) return ds;
    if (may != null) {
      it.may = may; it.loai = loai;
      if (dau) { it.ten = ten; it.vt = dau.vt; it.goc = dau.goc; }
    }
    luuDs(ds);
    return ds;
  }
  function layMuc(khoa){
    var ds = docDs();
    for (var i = 0; i < ds.length; i++) if (ds[i].khoa === khoa) return ds[i];
    return null;
  }
  // Nút có mã máy (Tìm giá) chỉ "đang chờ" khi mục đã lưu ĐÚNG phiên bản đó (đủ dấu vân tay); mục
  // chưa có mã máy/dấu vân tay được coi là khớp nếu khoá chỉ có 1 dòng duy nhất (duy).
  function khopPhienBan(item, may, loai, duy, dau){
    if (may == null) return true;
    if (item.may == null || item.vt == null) return !!duy && (item.may == null || String(item.may) === String(may));
    return String(item.may) === String(may) && String(item.loai) === String(loai) &&
      item.vt === dau.vt && item.goc === dau.goc;
  }
  function dangChoPhienBan(khoa, may, loai, duy, dau){
    var it = layMuc(khoa);
    return it ? khopPhienBan(it, may, loai, duy, dau) : false;
  }
  // Gom dòng tim-gia.json theo khoá tên -> mảng dòng (nhiều bản trùng tên). R3: Object.create(null)
  // để tên game như "Constructor"/"toString" không đụng thuộc tính có sẵn của Object.
  function chiMucDong(d){
    var m = Object.create(null);
    var gs = (d && d.game) || [];
    for (var i = 0; i < gs.length; i++) { var k = boDau(gs[i][0]); (m[k] = m[k] || []).push(gs[i]); }
    return m;
  }
  function locDong(rows, f){ var r = []; for (var i = 0; i < rows.length; i++) if (f(rows[i])) r.push(rows[i]); return r; }
  function mot(r){ return r.length === 1 ? { dong: r[0] } : r.length ? { nhieu: true } : null; }
  // Chọn dòng tim-gia.json cho 1 mục danh sách: null = chưa có dữ liệu; {nhieu:true} = còn nhiều dòng
  // khớp (KHÔNG tự chọn); {dong:g} = dòng đúng. Mục có dấu vân tay: khớp đủ (tên gốc, máy, loại, vùng
  // đầu, giá gốc); 0 dòng (giá gốc đổi) -> khớp lại theo (tên gốc, máy, loại).
  function chonDong(item, rows){
    if (!rows || !rows.length) return null;
    if (item.may == null) return rows.length === 1 ? { dong: rows[0] } : { nhieu: true };
    var cung = function(g){ return String(g[2]) === String(item.may) && String(g[1]) === String(item.loai); };
    if (item.vt == null) return mot(locDong(rows, cung));
    var cungTen = function(g){ return cung(g) && g[0] === item.ten; };
    var day = locDong(rows, function(g){
      var dv = dauVan(g);
      return cungTen(g) && dv.vt === item.vt && dv.goc === item.goc;
    });
    return day.length ? mot(day) : mot(locDong(rows, cungTen));
  }
  // C1: giá MUA thật của 1 vùng, v = [goc, con, giam, gia_plus?]. `con` hợp lệ -> dùng; `con` null mà
  // không giảm và `goc` hợp lệ -> goc; còn lại null ("chưa có giá"). 0 là giá thật (miễn phí).
  function soHopLe(x){ return typeof x === "number" && isFinite(x) && x >= 0; }
  function giaMua(v){
    if (!Array.isArray(v)) return null;
    if (soHopLe(v[1])) return v[1];
    if (!(v[2] > 0) && soHopLe(v[0])) return v[0];
    return null;
  }
  function boGame(khoa){
    var ds = docDs().filter(function(g){ return g.khoa !== khoa; });
    luuDs(ds);
    return ds;
  }
  // Mục G — ngưỡng giá "Báo khi dưới … đ": lưu NGAY TRONG cùng dòng game ở localStorage
  // (item.nguong = số VNĐ, hoặc null = không đặt). nguong=null (chứ không phải xoá field) để
  // trang_cho_sale.py phân biệt được "chưa từng đặt" và "đã đặt rồi bỏ" nếu cần sau này.
  function datNguong(khoa, nguong){
    var ds = docDs();
    for (var i = 0; i < ds.length; i++) {
      if (ds[i].khoa === khoa) { ds[i].nguong = (nguong == null || isNaN(nguong)) ? null : nguong; break; }
    }
    luuDs(ds);
    return ds;
  }

  function capNhatNut(btn, dang){
    btn.textContent = dang ? "★ Đang chờ" : "☆ Chờ sale";
    btn.classList.toggle("dang-cho", dang);
    btn.setAttribute("aria-pressed", dang ? "true" : "false");
  }
  function ganNut(btn){
    var khoa = btn.getAttribute("data-cs-khoa");
    if (!khoa) return;
    var ten = btn.getAttribute("data-cs-ten") || "";
    var may = btn.hasAttribute("data-cs-may") ? btn.getAttribute("data-cs-may") : null;
    var loai = btn.hasAttribute("data-cs-loai") ? Number(btn.getAttribute("data-cs-loai")) : null;
    var duy = btn.getAttribute("data-cs-duy") === "1";
    var dau = btn.hasAttribute("data-cs-vt") ? { vt: Number(btn.getAttribute("data-cs-vt")),
      goc: btn.hasAttribute("data-cs-goc") ? Number(btn.getAttribute("data-cs-goc")) : null } : null;
    if (may != null && !dau) dau = { vt: -1, goc: null };
    capNhatNut(btn, dangChoPhienBan(khoa, may, loai, duy, dau));
    btn.addEventListener("click", function(ev){
      ev.preventDefault();
      ev.stopPropagation();
      // R2: nút KHÔNG có phiên bản (trang chủ/Giảm giá) chỉ thêm/bỏ mục KHÔNG có phiên bản; đang có
      // mục có-phiên-bản của khoá này thì không xoá nó — mở trang Chờ sale.
      if (may == null) {
        var co = layMuc(khoa);
        if (co && co.may != null) { location.href = "cho-sale.html"; return; }
      }
      var dang = dangChoPhienBan(khoa, may, loai, duy, dau);
      if (dang) boGame(khoa); else themGame(khoa, ten, may, loai, dau);
      capNhatNut(btn, !dang);
      capNhatHuyHieu();
    });
  }
  function quetNut(goc){
    var ds = (goc || document).querySelectorAll("[data-cs-khoa]");
    for (var i = 0; i < ds.length; i++) {
      if (ds[i].__csGan) continue;
      ds[i].__csGan = true;
      ganNut(ds[i]);
    }
  }

  // Huy hiệu số cạnh mục menu — dùng chung 1 khuôn (xoá khi n<=0, tạo/ghi đè khi n>0).
  function boHuyHieu(a){ var b = a.querySelector(".cs-huy-hieu"); if (b) b.remove(); }
  function datHuyHieu(a, n){
    if (!n) { boHuyHieu(a); return; }
    var b = a.querySelector(".cs-huy-hieu");
    if (!b) { b = document.createElement("span"); b.className = "cs-huy-hieu"; a.appendChild(b); }
    b.textContent = n;
  }

  // tim-gia.json chỉ cần tải 1 lần/trang — mọi nơi cần (huy hiệu Chờ sale, dải banner) dùng
  // chung cache này thay vì tự fetch riêng.
  var _choTimGia = null;
  function taiTimGiaCache(){
    if (!_choTimGia) {
      _choTimGia = fetch(DATA_URL).then(function(r){ return r.json(); }).catch(function(){ return null; });
    }
    return _choTimGia;
  }
  // gia-the-vung.json (giá thẻ PSN — dòng chính, mục C) — cache riêng, lỗi/thiếu thì null và
  // giaVndHienTai() tự rơi về tỷ giá ngân hàng của tim-gia.json (không chặn tính năng ngưỡng giá).
  var _choGiaThe = null;
  function taiGiaTheCache(){
    if (!_choGiaThe) {
      _choGiaThe = fetch(GIA_THE_URL).then(function(r){ return r.json(); }).catch(function(){ return null; });
    }
    return _choGiaThe;
  }
  function rateChinhTaiVung(dataTimGia, giaThe, idx){
    if (giaThe && giaThe.the[idx] != null) return giaThe.the[idx];
    return dataTimGia.ty_gia[idx];
  }
  // VNĐ hiện tại của 1 game (g = bản ghi tim-gia.json) ở đúng vùng `vungMa` đang chọn — null nếu
  // game không có giá ở vùng đó hoặc vùng không hợp lệ.
  function giaVndHienTai(g, dataTimGia, giaThe, vungMa){
    var idx = dataTimGia.vung.indexOf(vungMa);
    if (idx < 0) return null;
    var gm = giaMua((g[3] || [])[idx]);
    if (gm == null) return null;
    return gm * rateChinhTaiVung(dataTimGia, giaThe, idx);
  }
  // Mục G + C6: 1 game "đáng báo" khi ĐANG GIẢM Ở VÙNG ĐANG CHỌN (giống thẻ), hoặc đã đặt ngưỡng và
  // giá vùng đó (theo thẻ) đã xuống dưới ngưỡng. Mục cũ trùng nhiều phiên bản (chonDong) thì không đếm.
  function dangDangChu(item, rows, dataTimGia, giaThe, vungMa){
    var c = chonDong(item, rows);
    if (!c || !c.dong) return false;
    var idx = dataTimGia.vung.indexOf(vungMa);
    if (idx < 0) return false;
    var v = (c.dong[3] || [])[idx];
    if (giaMua(v) == null) return false;
    if (v[2] > 0) return true;
    if (item.nguong == null) return false;
    var vnd = giaVndHienTai(c.dong, dataTimGia, giaThe, vungMa);
    return vnd != null && vnd <= item.nguong;
  }
  function demSoDangChu(ds, d, giaThe, vungMa){
    var chiMuc = chiMucDong(d);
    var so = 0;
    ds.forEach(function(item){
      if (dangDangChu(item, chiMuc[item.khoa], d, giaThe, vungMa)) so++;
    });
    return so;
  }

  // Huy hiệu "Chờ sale" trên menu = SỐ GAME ĐANG GIẢM HOẶC ĐÃ ĐẠT NGƯỠNG trong danh sách đang
  // chờ (không phải tổng số đang chờ) — Hào chốt 28/09: huy hiệu phải nói "có gì đáng xem ngay".
  function capNhatHuyHieu(vungMoi){
    var ds = docDs();
    var a = document.querySelector('a.nut-dau[href="cho-sale.html"]');  // Hào 30/09: gom menu — Chờ sale chỉ còn nút đầu trang
    if (!a) return;
    if (!ds.length) { boHuyHieu(a); return; }
    var vungMa = (typeof vungMoi === "string" && vungMoi) || (window.SGVUNG ? window.SGVUNG.doc() : "US");
    Promise.all([taiTimGiaCache(), taiGiaTheCache()]).then(function(ket){
      var d = ket[0], giaThe = ket[1];
      if (!d || !d.game) { boHuyHieu(a); return; }
      datHuyHieu(a, demSoDangChu(ds, d, giaThe, vungMa));
    });
  }

  // Huy hiệu "Kho PS Plus" trên menu = số game MỚI VÀO kho (đọc kho-plus.json, có sẵn field
  // moi_vao — xem trang_kho_plus.build_du_lieu()); không có dữ liệu (file thiếu/rỗng) thì ẩn,
  // không suy đoán.
  function capNhatHuyHieuKhoPlus(){
    // Hào 30/09: gom menu — Kho PS Plus không còn là mục menu: huy hiệu lên menu PS Plus (mọi trang) + tab Kho (nhóm PS Plus).
    var ds = document.querySelectorAll('.kenh nav a[href="ps-plus.html"], .tab-con a[href="kho-plus.html"]');
    if (!ds || !ds.length) return;
    var xoa = function(){ for (var i = 0; i < ds.length; i++) boHuyHieu(ds[i]); };
    fetch("du-lieu/kho-plus.json").then(function(r){ return r.json(); }).then(function(d){
      var n = (d && d.moi_vao) ? d.moi_vao.length : 0;
      for (var i = 0; i < ds.length; i++) datHuyHieu(ds[i], n);
    }).catch(xoa);
  }

  function daDongHomNay(){
    try { return localStorage.getItem(KHOA_DONG) === ngayHomNay(); } catch (err) { return false; }
  }
  function dongBanner(){
    try { localStorage.setItem(KHOA_DONG, ngayHomNay()); } catch (err) { /* bỏ qua */ }
    var b = document.getElementById("cs-banner");
    if (b) b.remove();
  }
  function goBanner(){
    var b = document.getElementById("cs-banner");
    if (b) b.remove();
  }
  function hienBanner(soLuong){
    var chu = "🔔 " + soLuong + " game bạn chờ đang giảm giá hoặc đã xuống ngưỡng bạn đặt — Xem";
    var cu = document.getElementById("cs-banner");
    if (cu) { var ac = cu.querySelector("a"); if (ac) ac.textContent = chu; return; }
    if (!document.body) return;
    var div = document.createElement("div");
    div.id = "cs-banner";
    div.className = "cs-banner";
    var a = document.createElement("a");
    a.href = "cho-sale.html";
    a.textContent = chu;
    var nut = document.createElement("button");
    nut.type = "button";
    nut.setAttribute("aria-label", "Đóng thông báo");
    nut.textContent = "✕";
    nut.addEventListener("click", dongBanner);
    div.appendChild(a);
    div.appendChild(nut);
    document.body.insertBefore(div, document.body.firstChild);
  }

  // C7: gọi lúc tải trang VÀ mỗi lần đổi vùng — tính lại theo vùng mới; 0 game thì gỡ banner.
  function kiemBanner(vungMoi){
    var ds = docDs();
    if (!ds.length || daDongHomNay()) { goBanner(); return; }
    var vungMa = vungMoi || (window.SGVUNG ? window.SGVUNG.doc() : "US");
    Promise.all([taiTimGiaCache(), taiGiaTheCache()]).then(function(ket){
      var d = ket[0], giaThe = ket[1];
      if (!d || !d.game) { goBanner(); return; }
      var so = demSoDangChu(ds, d, giaThe, vungMa);
      if (so > 0) hienBanner(so); else goBanner();
    });
  }

  window.SGCS = {
    boDau: boDau, docDs: docDs, themGame: themGame, boGame: boGame, dangCho: dangCho,
    datNguong: datNguong, quetNut: quetNut, capNhatHuyHieu: capNhatHuyHieu, kenhNtfy: kenhNtfy,
    chiMucDong: chiMucDong, chonDong: chonDong, giaMua: giaMua, dauVan: dauVan,
  };

  quetNut(document);
  capNhatHuyHieu();
  capNhatHuyHieuKhoPlus();
  kiemBanner();
  // Đổi vùng (mục G tính ngưỡng theo giá VÙNG ĐANG CHỌN) -> huy hiệu/banner phải tính lại ngay,
  // không chờ tải lại trang.
  window.addEventListener("sangame-vung", function(ev){
    capNhatHuyHieu(ev && ev.detail); kiemBanner(ev && ev.detail);
  });
})();
