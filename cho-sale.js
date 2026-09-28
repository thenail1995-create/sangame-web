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
  function themGame(khoa, ten){
    var ds = docDs();
    if (dangCho(khoa)) return ds;
    ds.push({ khoa: khoa, ten: ten, ngay: ngayHomNay() });
    luuDs(ds);
    return ds;
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
    capNhatNut(btn, dangCho(khoa));
    btn.addEventListener("click", function(ev){
      ev.preventDefault();
      ev.stopPropagation();
      var dang = dangCho(khoa);
      if (dang) boGame(khoa); else themGame(khoa, ten);
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

  function coGiam(g){
    var gia = g[3] || [];
    for (var i = 0; i < gia.length; i++) if (gia[i] && gia[i][2] > 0) return true;
    return false;
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
  // game không bán ở vùng đó hoặc vùng không hợp lệ.
  function giaVndHienTai(g, dataTimGia, giaThe, vungMa){
    var idx = dataTimGia.vung.indexOf(vungMa);
    if (idx < 0) return null;
    var v = (g[3] || [])[idx];
    if (!v) return null;
    return v[1] * rateChinhTaiVung(dataTimGia, giaThe, idx);
  }
  // Mục G: 1 game "đáng báo" khi ĐANG GIẢM GIÁ (như trước) HOẶC đã đặt ngưỡng và giá hiện tại
  // (đúng vùng đang chọn, giá theo thẻ) đã xuống dưới ngưỡng đó.
  function dangDangChu(item, g, dataTimGia, giaThe, vungMa){
    if (coGiam(g)) return true;
    if (item.nguong == null) return false;
    var vnd = giaVndHienTai(g, dataTimGia, giaThe, vungMa);
    return vnd != null && vnd <= item.nguong;
  }
  function demSoDangChu(ds, d, giaThe, vungMa){
    var theoKhoa = {};
    d.game.forEach(function(g){ theoKhoa[boDau(g[0])] = g; });
    var so = 0;
    ds.forEach(function(item){
      var g = theoKhoa[item.khoa];
      if (g && dangDangChu(item, g, d, giaThe, vungMa)) so++;
    });
    return so;
  }

  // Huy hiệu "Chờ sale" trên menu = SỐ GAME ĐANG GIẢM HOẶC ĐÃ ĐẠT NGƯỠNG trong danh sách đang
  // chờ (không phải tổng số đang chờ) — Hào chốt 28/09: huy hiệu phải nói "có gì đáng xem ngay".
  function capNhatHuyHieu(){
    var ds = docDs();
    var a = document.querySelector('nav a[href="cho-sale.html"]');
    if (!a) return;
    if (!ds.length) { boHuyHieu(a); return; }
    var vungMa = window.SGVUNG ? window.SGVUNG.doc() : "US";
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
    var a = document.querySelector('nav a[href="kho-plus.html"]');
    if (!a) return;
    fetch("du-lieu/kho-plus.json").then(function(r){ return r.json(); }).then(function(d){
      datHuyHieu(a, (d && d.moi_vao) ? d.moi_vao.length : 0);
    }).catch(function(){ boHuyHieu(a); });
  }

  function daDongHomNay(){
    try { return localStorage.getItem(KHOA_DONG) === ngayHomNay(); } catch (err) { return false; }
  }
  function dongBanner(){
    try { localStorage.setItem(KHOA_DONG, ngayHomNay()); } catch (err) { /* bỏ qua */ }
    var b = document.getElementById("cs-banner");
    if (b) b.remove();
  }
  function hienBanner(soLuong){
    if (document.getElementById("cs-banner") || !document.body) return;
    var div = document.createElement("div");
    div.id = "cs-banner";
    div.className = "cs-banner";
    var a = document.createElement("a");
    a.href = "cho-sale.html";
    a.textContent = "🔔 " + soLuong + " game bạn chờ đang giảm giá hoặc đã xuống ngưỡng bạn đặt — Xem";
    var nut = document.createElement("button");
    nut.type = "button";
    nut.setAttribute("aria-label", "Đóng thông báo");
    nut.textContent = "✕";
    nut.addEventListener("click", dongBanner);
    div.appendChild(a);
    div.appendChild(nut);
    document.body.insertBefore(div, document.body.firstChild);
  }

  function kiemBanner(){
    var ds = docDs();
    if (!ds.length || daDongHomNay()) return;
    var vungMa = window.SGVUNG ? window.SGVUNG.doc() : "US";
    Promise.all([taiTimGiaCache(), taiGiaTheCache()]).then(function(ket){
      var d = ket[0], giaThe = ket[1];
      if (!d || !d.game) return;
      var so = demSoDangChu(ds, d, giaThe, vungMa);
      if (so > 0) hienBanner(so);
    });
  }

  window.SGCS = {
    boDau: boDau, docDs: docDs, themGame: themGame, boGame: boGame, dangCho: dangCho,
    datNguong: datNguong, quetNut: quetNut, capNhatHuyHieu: capNhatHuyHieu, kenhNtfy: kenhNtfy,
  };

  quetNut(document);
  capNhatHuyHieu();
  capNhatHuyHieuKhoPlus();
  kiemBanner();
  // Đổi vùng (mục G tính ngưỡng theo giá VÙNG ĐANG CHỌN) -> huy hiệu/banner phải tính lại ngay,
  // không chờ tải lại trang.
  window.addEventListener("sangame-vung", function(){ capNhatHuyHieu(); kiemBanner(); });
})();
