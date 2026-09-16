(()=>{
const $=s=>document.querySelector(s);
const cleanPublicCopy=()=>{
  const source=$('.source-label');if(source)source.textContent='JoTrip Live · Tự động cập nhật';
  const error=$('#errorBox');if(error&&error.textContent){error.textContent=error.textContent.replace(/Không đọc được dữ liệu Sun Airport lúc này\./g,'Không đọc được dữ liệu chuyến bay lúc này.').replace(/JoTrip Live API tạm gián đoạn - đang dùng snapshot JoTrip AutoSync gần nhất\./g,'Luồng live tạm gián đoạn - đang dùng bản lưu JoTrip AutoSync gần nhất.');}
  const drawer=$('#drawerContent');if(drawer&&drawer.textContent){drawer.innerHTML=drawer.innerHTML
    .replace(/Actual time lấy từ API chính thức Sun Airport\./g,'Giờ thực tế đã được ghi nhận trong dữ liệu chuyến bay.')
    .replace(/Nguồn sân bay:/g,'Trạng thái gốc:')
    .replace(/Trạng thái lấy trực tiếp từ dữ liệu Sun Airport\./g,'Trạng thái theo dữ liệu đang ghi nhận.')
    .replace(/Giờ cập nhật lấy từ dữ liệu sân bay\./g,'Giờ cập nhật theo dữ liệu chuyến bay.')
    .replace(/JoTrip Live API \/ Sun Airport/g,'JoTrip Live')
    .replace(/JoTrip AutoSync \/ Sun Airport/g,'JoTrip AutoSync');}
};
if(typeof renderSummary==='function'){
  const base=renderSummary;
  renderSummary=function(){base();const source=$('.source-label');if(source)source.textContent='JoTrip Live · Tự động cập nhật';const ops=$('#opsState');if(ops){if(ops.textContent==='DATA STALE')ops.textContent='DỮ LIỆU CŨ';else if(ops.textContent==='OPERATIONS NORMAL')ops.textContent='VẬN HÀNH BÌNH THƯỜNG';else if(ops.textContent.startsWith('WATCH ·'))ops.textContent=ops.textContent.replace('WATCH ·','THEO DÕI ·');}cleanPublicCopy();};
}
if(typeof renderHealth==='function'){
  const base=renderHealth;
  renderHealth=function(){base();const title=$('#healthTitle'),desc=$('#healthDescription'),age=state?.latest?.collected_at_vn?ageInfo(state.latest.collected_at_vn):null;if(title&&desc){if(state?.dataSource==='fallback'){title.textContent='DỰ PHÒNG · đang dùng AutoSync';desc.textContent='Luồng live tạm không phản hồi. Giao diện đã chuyển sang bản lưu gần nhất.';}else if(age?.level==='good'){title.textContent='TỐT · dữ liệu đang mới';desc.textContent='JoTrip Live đang cập nhật tự động, có cache ngắn để giữ ổn định.';}else if(age?.level==='watch'){title.textContent='THEO DÕI · dữ liệu chậm cập nhật';desc.textContent='Dữ liệu đang có độ trễ cao hơn bình thường. Trang sẽ tự kiểm tra lại mỗi phút.';}else if(age?.level==='stale'){title.textContent='CŨ · dữ liệu đã quá 15 phút';desc.textContent='Dữ liệu không còn đủ mới để xem như trạng thái tức thời.';}}cleanPublicCopy();};
}
if(typeof openDrawer==='function'){
  const base=openDrawer;
  openDrawer=function(...args){base(...args);cleanPublicCopy();};
}
const observer=new MutationObserver(cleanPublicCopy);observer.observe(document.body,{subtree:true,childList:true,characterData:true});
cleanPublicCopy();
})();
