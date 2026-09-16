(() => {
  const PQ_ASSETS=window.PQ_ASSETS||{};
  const lp=document.getElementById('landingPlane');if(lp)lp.src=PQ_ASSETS['plane']||'';
  const li=document.getElementById('landingIsland');if(li)li.src=PQ_ASSETS['island']||'';
  const mi=document.getElementById('mapIsland');if(mi)mi.src=PQ_ASSETS['island']||'';
  const kw=document.getElementById('kenWave');if(kw)kw.src=PQ_ASSETS['ken-wave']||'';
  document.documentElement.style.setProperty('--airport-bg',`url("${PQ_ASSETS['airport-scene']||''}")`);
  document.documentElement.style.setProperty('--sunset-bg',`url("${PQ_ASSETS['sunset-bg']||''}")`);

  const screens=[...document.querySelectorAll('.screen')];
  const go=id=>{screens.forEach(s=>s.classList.toggle('active',s.id===id));if(id==='game'){resizeCanvas();drawIdle();}};
  document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>{uiClick();go(b.dataset.go)}));
  const chars=[
    ['THE TRAVELER','Ready for anything.','traveler'],['THE EXPLORER',"Let's see what's out there.",'explorer'],['THE UNCLE','I packed snacks.','uncle'],['THE GRANDMA','No need to rush.','grandma'],['THE KID','Can we go now?','kid'],['THE OLD FISHERMAN','I know these waters.','fisherman'],['PHU QUOC RIDGEBACK','No ticket needed.','ridgeback'],['PEPPER','A little spicy.','pepper']
  ];
  let selected=0,totalJo=+(localStorage.pq_rebuild_jo||0);
  const grid=document.getElementById('characterGrid');
  chars.forEach((c,i)=>{const b=document.createElement('button');b.className='character-card'+(i===0?' selected':'');b.innerHTML=`<img src="${PQ_ASSETS['char-'+c[2]]||''}" alt="${c[0]}"><div class="char-label"><b>${c[0]}</b><small>${c[1]}</small></div>`;b.onclick=()=>{uiClick();selected=i;[...grid.children].forEach((x,j)=>x.classList.toggle('selected',j===i))};grid.appendChild(b)});
  document.getElementById('openMapBtn').onclick=()=>{uiClick();const n=document.getElementById('playerName').value.trim()||'Traveler';document.getElementById('mapHello').textContent=`WELCOME, ${n.toUpperCase()}`;document.getElementById('mapJo').textContent=totalJo;go('map')};
  document.getElementById('sunsetPin').onclick=()=>{uiClick();go('game');document.getElementById('tutorial').classList.add('active');document.getElementById('gameOver').classList.remove('active')};
  document.getElementById('backMapFromTutorial').onclick=()=>{stopGame();go('map')};
  document.getElementById('backMapBtn').onclick=()=>{stopGame();document.getElementById('mapJo').textContent=totalJo;go('map')};

  let ac=null,engine=null,engineGain=null;
  function audioCtx(){if(!ac)ac=new (window.AudioContext||window.webkitAudioContext)();if(ac.state==='suspended')ac.resume();return ac}
  function beep(freq=700,dur=.06,vol=.025,type='square'){try{const a=audioCtx(),o=a.createOscillator(),g=a.createGain();o.type=type;o.frequency.setValueAtTime(freq,a.currentTime);g.gain.setValueAtTime(vol,a.currentTime);g.gain.exponentialRampToValueAtTime(.0001,a.currentTime+dur);o.connect(g).connect(a.destination);o.start();o.stop(a.currentTime+dur)}catch{}}
  function uiClick(){beep(520,.035,.012,'square')}
  function engineStart(){try{const a=audioCtx();engineStop();engine=a.createOscillator();engineGain=a.createGain();engine.type='sawtooth';engine.frequency.value=78;engineGain.gain.value=.012;engine.connect(engineGain).connect(a.destination);engine.start()}catch{}}
  function engineStop(){try{engine&&engine.stop()}catch{}engine=null}

  const canvas=document.getElementById('gameCanvas'),ctx=canvas.getContext('2d');ctx.imageSmoothingEnabled=false;
  const keys=['sunset-bg','ride1','ride2','ride3','ride4','planter','chair','table','menu','tripod','suitcase','coin1','coin2','coin3','coin4'];
  const imgs={};let ready=false;
  Promise.all(keys.map(k=>new Promise(res=>{const im=new Image();imgs[k]=im;im.onload=res;im.onerror=res;im.src=PQ_ASSETS[k]||''}))).then(()=>{ready=true;drawIdle()});
  let run=false,raf=0,last=0,score=0,runJo=0,best=+(localStorage.pq_rebuild_best||0),world=0,playerY=0,vy=0,onGround=true,rideFrame=0,rideClock=0,obstacles=[],coin=null,trainingLeft=2,toast='',toastUntil=0,cameraShake=0,dust=[];
  const W=540,H=960,GROUND=806,PLAYER={x:92,w:118,h:132};
  const obstacleDefs=[
    {k:'planter',w:68,h:65,hit:42},{k:'chair',w:55,h:70,hit:33},{k:'table',w:72,h:58,hit:42},{k:'menu',w:61,h:76,hit:39},{k:'tripod',w:62,h:76,hit:34},{k:'suitcase',w:50,h:62,hit:32}
  ];
  function difficulty(){if(score<5)return{speed:300,gap:[350,420]};if(score<15)return{speed:335,gap:[320,385]};if(score<35)return{speed:375,gap:[285,345]};if(score<60)return{speed:415,gap:[255,315]};return{speed:455+Math.min(65,(score-60)*1.4),gap:[225,285]}}
  function spawnObstacle(initial=false){const d=difficulty(),def=obstacleDefs[Math.floor(Math.random()*(score<6?3:obstacleDefs.length))];const x=initial?W+190:W+d.gap[0]+Math.random()*(d.gap[1]-d.gap[0]);obstacles.push({...def,x,y:GROUND-def.h,passed:false,training:trainingLeft>0});if(trainingLeft>0)trainingLeft--}
  function spawnCoin(){coin={x:W+260+Math.random()*240,y:620+Math.random()*90,w:42,h:42,frame:0}}
  function hop(auto=false){if(!run||!onGround)return;vy=-720;onGround=false;if(!auto)beep(590,.05,.018,'square')}
  function toastMsg(t,ms=650){toast=t;toastUntil=performance.now()+ms}
  function startGame(){if(!ready){toastMsg('LOADING ISLAND...');setTimeout(startGame,120);return}document.getElementById('tutorial').classList.remove('active');document.getElementById('gameOver').classList.remove('active');score=0;runJo=0;best=+(localStorage.pq_rebuild_best||0);world=0;playerY=0;vy=0;onGround=true;rideFrame=0;rideClock=0;obstacles=[];coin=null;trainingLeft=2;dust=[];cameraShake=0;toast='';spawnObstacle(true);spawnCoin();run=true;last=performance.now();engineStart();cancelAnimationFrame(raf);raf=requestAnimationFrame(loop)}
  function stopGame(){run=false;cancelAnimationFrame(raf);engineStop()}
  function endGame(){stopGame();best=Math.max(best,score);localStorage.pq_rebuild_best=best;totalJo+=runJo;localStorage.pq_rebuild_jo=totalJo;beep(150,.18,.04,'sawtooth');document.getElementById('gameOverText').innerHTML=`SCORE <b>${score}</b> · JO <b>+${runJo}</b><br><small>${score<5?'Fast game. Friendly start. Try the rhythm again.':'Nice run.'}</small>`;document.getElementById('gameOver').classList.add('active')}
  function loop(t){if(!run)return;const dt=Math.min(.034,(t-last)/1000);last=t;const d=difficulty();world+=d.speed*dt;rideClock+=dt;if(rideClock>.08){rideClock=0;rideFrame=(rideFrame+1)%4}if(engine&&ac)engine.frequency.setTargetAtTime(78+Math.min(34,score*.7),ac.currentTime,.04);
    if(!onGround){vy+=2300*dt;playerY+=vy*dt;if(playerY>=0){playerY=0;vy=0;onGround=true;cameraShake=4;beep(210,.03,.01,'square')}}
    obstacles.forEach(o=>o.x-=d.speed*dt);if(coin)coin.x-=d.speed*.96*dt;
    obstacles.forEach(o=>{if(!o.passed&&o.x+o.w<PLAYER.x){o.passed=true;score++;if(score===1)toastMsg('THAT\'S IT.');if(score===5)toastMsg('NOW WE RIDE.');if(score===25)toastMsg('FASTER!');if(score===69)toastMsg('NICE.');spawnObstacle(false)}});obstacles=obstacles.filter(o=>o.x>-160);
    if(coin&&coin.x<-60)spawnCoin();
    const pLeft=PLAYER.x+24,pRight=PLAYER.x+PLAYER.w-15,pBottom=GROUND+playerY,pTop=pBottom-PLAYER.h;
    for(const o of obstacles){const ox=o.x+(o.w-o.hit)/2,or=ox+o.hit,ot=o.y+8;if(pRight>ox&&pLeft<or&&pBottom>ot&&pTop<GROUND){if(o.training){o.training=false;toastMsg('HOP EARLIER!',800);hop(true);o.x+=120;beep(420,.08,.02,'square')}else{draw(t);endGame();return}}}
    if(coin&&pRight>coin.x&&pLeft<coin.x+coin.w&&pTop<coin.y+coin.h&&pBottom>coin.y){runJo++;toastMsg('+1 JO',450);beep(1180,.06,.025,'square');spawnCoin()}
    if(Math.random()<.32)dust.push({x:PLAYER.x+22,y:GROUND-5,a:.7,vx:-90-Math.random()*80,vy:-16-Math.random()*18});dust.forEach(p=>{p.x+=p.vx*dt;p.y+=p.vy*dt;p.a-=dt*1.7});dust=dust.filter(p=>p.a>0);
    cameraShake*=.84;draw(t);raf=requestAnimationFrame(loop)}
  function drawCover(im,x,y,w,h){if(!im||!im.complete||!im.naturalWidth)return;const r=Math.max(w/im.naturalWidth,h/im.naturalHeight),sw=w/r,sh=h/r,sx=(im.naturalWidth-sw)/2,sy=(im.naturalHeight-sh)/2;ctx.drawImage(im,sx,sy,sw,sh,x,y,w,h)}
  function draw(now=performance.now()){ctx.save();ctx.translate((Math.random()-.5)*cameraShake,(Math.random()-.5)*cameraShake);ctx.clearRect(-10,-10,W+20,H+20);drawCover(imgs['sunset-bg'],0,0,W,H);
    const d=difficulty(),roadY=GROUND+10;ctx.fillStyle='rgba(55,42,31,.97)';ctx.fillRect(0,roadY,W,H-roadY);for(let x=-(world*1.6%94)-94;x<W+94;x+=94){ctx.fillStyle='rgba(200,178,143,.28)';ctx.fillRect(x,roadY+33,50,5);ctx.fillStyle='rgba(24,17,12,.35)';ctx.fillRect(x+57,roadY+33,30,5)}
    ctx.strokeStyle=`rgba(255,255,255,${score<5?.07:.12})`;ctx.lineWidth=2;for(let i=0;i<7;i++){const yy=210+i*72;const sx=((world*2.1+i*83)%680)-120;ctx.beginPath();ctx.moveTo(sx,yy);ctx.lineTo(sx+58,yy-8);ctx.stroke()}
    for(const p of dust){ctx.globalAlpha=Math.max(0,p.a);ctx.fillStyle='#e2c49b';ctx.beginPath();ctx.arc(p.x,p.y,3+(1-p.a)*4,0,Math.PI*2);ctx.fill()}ctx.globalAlpha=1;
    for(const o of obstacles){const im=imgs[o.k];if(im&&im.complete)ctx.drawImage(im,o.x,o.y,o.w,o.h)}
    if(coin){coin.frame=((now/80)|0)%4;const im=imgs['coin'+(coin.frame+1)];if(im&&im.complete)ctx.drawImage(im,coin.x,coin.y,coin.w,coin.h)}
    const y=GROUND+playerY;ctx.fillStyle='rgba(0,0,0,.42)';const lift=Math.min(1,Math.abs(playerY)/130);ctx.beginPath();ctx.ellipse(PLAYER.x+61,GROUND+6,50*(1-lift*.45),9*(1-lift*.6),0,0,Math.PI*2);ctx.fill();const im=imgs['ride'+(rideFrame+1)];if(im&&im.complete){ctx.save();ctx.translate(PLAYER.x+PLAYER.w/2,y);const tilt=onGround?Math.sin(world/18)*.015:Math.max(-.10,Math.min(.08,vy/7000));ctx.rotate(tilt);ctx.drawImage(im,-PLAYER.w/2,-PLAYER.h,PLAYER.w,PLAYER.h);ctx.restore()}
    ctx.textBaseline='top';ctx.font='900 18px monospace';ctx.fillStyle='#fff';ctx.shadowColor='rgba(0,0,0,.8)';ctx.shadowOffsetX=2;ctx.shadowOffsetY=2;ctx.fillText(`SCORE ${score}`,18,22);ctx.textAlign='center';ctx.fillText(`JO ${runJo}`,270,22);ctx.textAlign='right';ctx.fillText(`BEST ${best}`,522,22);ctx.textAlign='center';ctx.shadowOffsetX=0;ctx.shadowOffsetY=0;ctx.fillStyle='#f7b72d';ctx.font='900 13px monospace';ctx.fillText('SUNSET TOWN',270,82);ctx.fillStyle='#fff';ctx.font='900 30px monospace';ctx.fillText('NO BRAKES',270,103);ctx.font='11px monospace';ctx.fillText('TAP · CLICK · SPACE',270,145);ctx.font='10px monospace';ctx.fillStyle='rgba(255,255,255,.82)';ctx.fillText(`${d.speed|0} PX/S · ${score<2?'TRAINING':score<5?'FAST START':'NO BRAKES'}`,270,918);if(now<toastUntil){ctx.font='900 22px monospace';ctx.fillStyle='#f7b72d';ctx.fillText(toast,270,205)}ctx.textAlign='left';ctx.shadowColor='transparent';ctx.restore()}
  function drawIdle(){if(!ready){ctx.fillStyle='#08344a';ctx.fillRect(0,0,W,H);return}if(!obstacles.length)obstacles=[{...obstacleDefs[0],x:660,y:GROUND-65,passed:false,training:true}];if(!coin)coin={x:420,y:660,w:42,h:42,frame:0};draw()}
  function resizeCanvas(){}
  document.getElementById('startRideBtn').onclick=()=>{uiClick();startGame()};document.getElementById('retryBtn').onclick=()=>{uiClick();startGame()};canvas.addEventListener('pointerdown',()=>hop());window.addEventListener('keydown',e=>{if(e.code==='Space'){e.preventDefault();hop()}});
})();
