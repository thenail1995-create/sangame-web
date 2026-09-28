(function(){
  var KHOA_LS = "sangame_cho_sale";
  var KHOA_DONG = "sangame_cho_sale_dong_ngay";
  var DATA_URL = "du-lieu/tim-gia.json";

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

  function capNhatHuyHieu(){
    var ds = docDs();
    var a = document.querySelector('nav a[href="cho-sale.html"]');
    if (!a) return;
    var badge = a.querySelector(".cs-huy-hieu");
    if (!ds.length) { if (badge) badge.remove(); return; }
    if (!badge) {
      badge = document.createElement("span");
      badge.className = "cs-huy-hieu";
      a.appendChild(badge);
    }
    badge.textContent = ds.length;
  }

  function coGiam(g){
    var gia = g[3] || [];
    for (var i = 0; i < gia.length; i++) if (gia[i] && gia[i][2] > 0) return true;
    return false;
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
    a.textContent = "🔔 " + soLuong + " game bạn chờ đang giảm giá — Xem";
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
    fetch(DATA_URL).then(function(r){ return r.json(); }).then(function(d){
      var theoKhoa = {};
      (d.game || []).forEach(function(g){ theoKhoa[boDau(g[0])] = g; });
      var soDangGiam = 0;
      ds.forEach(function(item){
        var g = theoKhoa[item.khoa];
        if (g && coGiam(g)) soDangGiam++;
      });
      if (soDangGiam > 0) hienBanner(soDangGiam);
    }).catch(function(){ /* không tải được — im lặng, không bịa số */ });
  }

  window.SGCS = {
    boDau: boDau, docDs: docDs, themGame: themGame, boGame: boGame, dangCho: dangCho,
    quetNut: quetNut, capNhatHuyHieu: capNhatHuyHieu,
  };

  quetNut(document);
  capNhatHuyHieu();
  kiemBanner();
})();
