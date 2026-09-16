(()=>{
const $=s=>document.querySelector(s);
const setText=(el,text)=>{if(el&&el.textContent!==text)el.textContent=text};
const replaceText=(el,replacements)=>{if(!el||!el.textContent)return;let next=el.textContent;for(const [a,b] of replacements)next=next.replace(a,b);if(next!==el.textContent)el.textContent=next};
const replaceHtml=(el,replacements)=>{if(!el||!el.textContent)return;let next=el.innerHTML;for(const [a,b] of replacements)next=next.replace(a,b);if(next!==el.innerHTML)el.innerHTML=next};
const cleanPublicCopy=()=>{
  setText($('.source-label'),'JoTrip Live · Auto refresh');
  replaceText($('#updatedAt'),[[/JoTrip Live API/g,'JoTrip Live']]);
  replaceText($('#errorBox'),[
    [/Không đọc được dữ liệu Sun Airport lúc này\./g,'Không đọc được dữ liệu chuyến bay lúc này.'],
    [/JoTrip Live API tạm gián đoạn - đang dùng snapshot JoTrip AutoSync gần nhất\./g,'Luồng live tạm gián đoạn - đang dùng bản lưu JoTrip AutoSync gần nhất.']
  ]);
  replaceHtml($('#drawerContent'),[
    [/Actual time lấy từ API chính thức Sun Airport\./g,'Giờ thực tế đã được ghi nhận trong dữ liệu chuyến bay.'],
    [/Nguồn sân bay:/g,'Trạng thái gốc:'],
    [/Trạng thái lấy trực tiếp từ dữ liệu Sun Airport\./g,'Trạng thái theo dữ liệu đang ghi nhận.'],
    [/Giờ cập nhật lấy từ dữ liệu sân bay\./g,'Giờ cập nhật theo dữ liệu chuyến bay.'],
    [/JoTrip Live API \/ Sun Airport/g,'JoTrip Live'],
    [/JoTrip AutoSync \/ Sun Airport/g,'JoTrip AutoSync']
  ]);
};
if(typeof renderSummary==='function'){
  const base=renderSummary;
  renderSummary=function(){base();setText($('.source-label'),'JoTrip Live · Auto refresh');replaceText($('#updatedAt'),[[/JoTrip Live API/g,'JoTrip Live']]);const ops=$('#opsState');if(ops&&ops.textContent.startsWith('WATCH ·'))setText(ops,ops.textContent.replace('BẤT THƯỜNG','ISSUES'));cleanPublicCopy();};
}
if(typeof renderHealth==='function'){
  const base=renderHealth;
  renderHealth=function(){base();const title=$('#healthTitle'),desc=$('#healthDescription'),l=state?.latest,h=state?.health,age=l?.collected_at_vn?ageInfo(l.collected_at_vn):null,qa=!!(h?.collector_completed&&h?.parser_passed&&h?.normalization_passed&&h?.qa_passed&&l?.quality?.usable);if(title&&desc){if(!qa){setText(title,'QA FAILED');setText(desc,'Luồng thu thập hoặc chuẩn hóa chưa đạt. Không nên dùng số liệu để điều hành.');}else if(state?.dataSource==='fallback'){setText(title,'FALLBACK · AUTOSYNC');setText(desc,'Luồng live tạm không phản hồi. Giao diện đã chuyển sang bản lưu gần nhất.');}else if(age?.level==='good'){setText(title,'GOOD · DATA FRESH');setText(desc,'JoTrip Live đang cập nhật tự động, có cache ngắn để giữ ổn định.');}else if(age?.level==='watch'){setText(title,'WATCH · DATA DELAYED');setText(desc,'Dữ liệu đang có độ trễ cao hơn bình thường. Trang sẽ tự kiểm tra lại mỗi phút.');}else if(age?.level==='stale'){setText(title,'STALE · DATA OLD');setText(desc,'Dữ liệu không còn đủ mới để xem như trạng thái tức thời.');}}cleanPublicCopy();};
}
if(typeof openDrawer==='function'){
  const base=openDrawer;
  openDrawer=function(...args){base(...args);cleanPublicCopy();};
}
const observer=new MutationObserver(cleanPublicCopy);observer.observe(document.body,{subtree:true,childList:true,characterData:true});
cleanPublicCopy();
})();
