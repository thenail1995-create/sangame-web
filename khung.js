(function(){var a=document.getElementById("lh-email");if(!a)return;var em=a.getAttribute("data-u")+"@"+a.getAttribute("data-d");a.href="mailto:"+em;a.textContent=em;})();
(function(){
  var KHOA = "sangame_vung", MAC_DINH = "US";
  var vungHienTai = null;  // vùng đang chọn giữ trong biến JS — localStorage chỉ là chỗ nhớ phụ (có thể bị chặn)
  function docVung(){
    if (vungHienTai) return vungHienTai;
    try { return localStorage.getItem(KHOA) || MAC_DINH; } catch (err) { return MAC_DINH; }
  }
  function apPanel(vung){
    var panels = document.querySelectorAll("[data-vung-panel]");
    for (var i = 0; i < panels.length; i++) {
      var p = panels[i];
      p.hidden = p.getAttribute("data-vung-panel") !== vung;
    }
    var boc = document.querySelectorAll("[data-vung-empty-hide]");
    for (var j = 0; j < boc.length; j++) {
      var hienDang = boc[j].querySelector('[data-vung-panel="' + vung + '"]');
      boc[j].hidden = !hienDang || hienDang.hasAttribute("data-rong");
    }
  }
  function apNut(vung){
    var nut = document.querySelectorAll("[data-vung-switcher] .chip-vung");
    for (var i = 0; i < nut.length; i++) {
      var chon = nut[i].getAttribute("data-vung") === vung;
      nut[i].setAttribute("aria-pressed", chon ? "true" : "false");
    }
    datTruot();
  }
  // Thanh trượt: đặt khối nền .vung-truot đúng dưới nút đang chọn (vị trí tính theo nút, nên
  // đúng cả khi chữ/cỡ chữ đổi), và cuộn nút đó vào tầm nhìn khi thanh hẹp hơn 6 nút (điện thoại).
  function datTruot(){
    var thanh = document.querySelectorAll(".vung-thanh");
    for (var i = 0; i < thanh.length; i++) {
      var t = thanh[i], truot = t.querySelector(".vung-truot");
      var dang = t.querySelector('.chip-vung[aria-pressed="true"]');
      if (!truot || !dang || !dang.offsetWidth) continue;
      var lanDau = !t.classList.contains("co-truot");
      if (lanDau) truot.style.transition = "none";  // lần đầu đặt thẳng chỗ, không trượt từ mép trái
      truot.style.width = dang.offsetWidth + "px";
      truot.style.transform = "translateX(" + dang.offsetLeft + "px)";
      t.classList.add("co-truot");
      if (lanDau) { void truot.offsetWidth; truot.style.transition = ""; }
      var trai = dang.offsetLeft - 8, phai = dang.offsetLeft + dang.offsetWidth + 8 - t.clientWidth;
      if (t.scrollLeft > trai) t.scrollLeft = trai;
      else if (t.scrollLeft < phai) t.scrollLeft = phai;
      danhDauCuon(t);
    }
  }
  // Mờ dần mép còn nút khuất (giống menu có mũi tên) để người dùng biết vuốt ngang được.
  function danhDauCuon(t){
    t.classList.toggle("con-trai", t.scrollLeft > 2);
    t.classList.toggle("con-phai", t.scrollLeft + t.clientWidth < t.scrollWidth - 2);
    if (!t.__cuon) { t.__cuon = true; t.addEventListener("scroll", function(){ danhDauCuon(t); }, { passive: true }); }
  }
  window.addEventListener("resize", datTruot);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(datTruot);
  function ve(){ var v = docVung(); apPanel(v); apNut(v); }
  function chonVung(vung){
    vungHienTai = vung;
    try { localStorage.setItem(KHOA, vung); } catch (err) { /* riêng tư/đầy bộ nhớ: bỏ qua, biến JS đã giữ vùng */ }
    ve();
    window.dispatchEvent(new CustomEvent("sangame-vung", { detail: vung }));
  }
  document.addEventListener("click", function(ev){
    var nut = ev.target.closest("[data-vung-switcher] .chip-vung");
    if (!nut) return;
    chonVung(nut.getAttribute("data-vung"));
  });
  window.SGVUNG = { doc: docVung, dat: chonVung };
  ve();
})();
(function(){var n=document.querySelector('.kenh nav');if(n){var w=n.parentNode;
function u(){w.classList.toggle('con-phai',n.scrollLeft+n.clientWidth<n.scrollWidth-4);w.classList.toggle('con-trai',n.scrollLeft>4);}
function giua(){var a=n.querySelector('[aria-current="page"]');if(a){var r=a.getBoundingClientRect(),rn=n.getBoundingClientRect();if(r.left<rn.left||r.right>rn.right)n.scrollLeft+=r.left-rn.left-(rn.width-r.width)/2;}u();}
n.addEventListener('scroll',u,{passive:true});addEventListener('resize',u);giua();
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(giua);addEventListener('load',giua);}
var tc=document.querySelector('.tab-con');if(tc){var gt=function(){var a=tc.querySelector('[aria-current="page"]');if(a){var r=a.getBoundingClientRect(),rn=tc.getBoundingClientRect();if(r.left<rn.left||r.right>rn.right)tc.scrollLeft+=r.left-rn.left-(rn.width-r.width)/2;}};
gt();if(document.fonts&&document.fonts.ready)document.fonts.ready.then(gt);addEventListener('load',gt);addEventListener('resize',gt);}
var t=document.getElementById('len-dau');if(t){var hien=function(){t.classList.toggle('hien',scrollY>600);};
addEventListener('scroll',hien,{passive:true});hien();t.addEventListener('click',function(){scrollTo({top:0,behavior:'smooth'});});}})();
