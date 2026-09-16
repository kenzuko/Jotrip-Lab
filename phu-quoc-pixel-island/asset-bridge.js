(() => {
  const A = window.A || {};
  const svg = (s) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(s);
  const pixelChar = (hair, shirt, accent, skin = '#e2a06d') => svg(`
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 112" shape-rendering="crispEdges">
      <rect width="96" height="112" fill="#0b3145"/>
      <rect x="35" y="21" width="26" height="26" fill="${skin}"/>
      <rect x="32" y="17" width="32" height="8" fill="${hair}"/>
      <rect x="29" y="47" width="38" height="46" fill="${shirt}"/>
      <rect x="20" y="54" width="9" height="31" fill="${skin}"/>
      <rect x="67" y="54" width="9" height="31" fill="${skin}"/>
      <rect x="35" y="93" width="10" height="14" fill="#24313a"/>
      <rect x="51" y="93" width="10" height="14" fill="#24313a"/>
      <rect x="69" y="58" width="7" height="19" fill="${accent}"/>
    </svg>`);
  const dog = svg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 112" shape-rendering="crispEdges"><rect width="96" height="112" fill="#10364b"/><rect x="26" y="35" width="44" height="30" fill="#805737"/><rect x="21" y="25" width="14" height="20" fill="#6b452c"/><rect x="61" y="25" width="14" height="20" fill="#6b452c"/><rect x="34" y="65" width="34" height="26" fill="#805737"/><rect x="28" y="88" width="10" height="17" fill="#6b452c"/><rect x="58" y="88" width="10" height="17" fill="#6b452c"/><rect x="39" y="45" width="5" height="5" fill="#111"/><rect x="54" y="45" width="5" height="5" fill="#111"/></svg>`);
  const pepper = svg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 112" shape-rendering="crispEdges"><rect width="96" height="112" fill="#123b2a"/><rect x="43" y="18" width="8" height="16" fill="#4c8b45"/><rect x="31" y="28" width="34" height="62" rx="14" fill="#d84c36"/><rect x="26" y="39" width="8" height="12" fill="#d84c36"/><rect x="62" y="65" width="8" height="14" fill="#b33a2c"/></svg>`);
  const ken = svg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 180" shape-rendering="crispEdges"><rect width="120" height="180" fill="none"/><rect x="43" y="27" width="34" height="35" fill="#e0a06f"/><rect x="39" y="21" width="42" height="11" fill="#161616"/><rect x="35" y="64" width="50" height="67" fill="#77944C"/><rect x="26" y="73" width="10" height="48" fill="#e0a06f"/><rect x="84" y="69" width="10" height="38" fill="#e0a06f"/><rect x="92" y="52" width="9" height="35" fill="#e0a06f"/><rect x="43" y="131" width="14" height="38" fill="#22313b"/><rect x="64" y="131" width="14" height="38" fill="#22313b"/><rect x="40" y="88" width="23" height="8" fill="#FCBC12"/></svg>`);
  const plane = svg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 90" shape-rendering="crispEdges"><rect x="18" y="41" width="128" height="12" fill="#eef7fb"/><rect x="118" y="29" width="31" height="10" fill="#eef7fb"/><rect x="61" y="26" width="16" height="42" fill="#dfeef4"/><rect x="41" y="17" width="9" height="32" fill="#eef7fb"/><rect x="146" y="41" width="20" height="12" fill="#d6e8ef"/></svg>`);
  const airport = svg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 960" shape-rendering="crispEdges"><rect width="540" height="960" fill="#66bce0"/><rect y="500" width="540" height="95" fill="#2e8eaf"/><rect y="595" width="540" height="145" fill="#707874"/><rect y="740" width="540" height="220" fill="#406f4d"/><rect x="335" y="438" width="165" height="95" fill="#e5dcc5"/><rect x="356" y="459" width="116" height="42" fill="#89a6b4"/><rect x="0" y="642" width="540" height="12" fill="#f1e3a3"/><rect x="40" y="646" width="74" height="4" fill="#747b76"/><rect x="168" y="646" width="74" height="4" fill="#747b76"/><rect x="296" y="646" width="74" height="4" fill="#747b76"/></svg>`);

  window.PQ_ASSETS = {
    island: A.map || '',
    plane,
    'ken-wave': ken,
    'airport-scene': airport,
    'sunset-bg': A.bg || '',
    ride1: A.ride1 || '', ride2: A.ride2 || '', ride3: A.ride3 || '', ride4: A.ride4 || '',
    planter: A.planter || '', chair: A.chair || '', table: A.table || '', menu: A.menu || '', tripod: A.tripod || '', suitcase: A.suitcase || '',
    coin1: A.coin || '', coin2: A.coin || '', coin3: A.coin || '', coin4: A.coin || '',
    'char-traveler': pixelChar('#171717','#397a5c','#eab634'),
    'char-explorer': pixelChar('#392619','#3b7189','#d3a846'),
    'char-uncle': pixelChar('#33251f','#8f653a','#e0c26b'),
    'char-grandma': pixelChar('#b9b7aa','#8d5575','#e8b9cc'),
    'char-kid': pixelChar('#292929','#d58c31','#da4239'),
    'char-fisherman': pixelChar('#d4d0bd','#3b6579','#d5a74e'),
    'char-ridgeback': dog,
    'char-pepper': pepper
  };
})();
