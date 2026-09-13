window.A=window.A||{};A.landing=A.map;
const CHAR=[
{name:'THE TRAVELER',line:'Ready for anything.',hair:'#171717',shirt:'#397a5c',accent:'#eab634'},
{name:'THE EXPLORER',line:"Let's see what's out there.",hair:'#392619',shirt:'#3b7189',accent:'#d3a846'},
{name:'THE UNCLE',line:'I packed snacks.',hair:'#33251f',shirt:'#8f653a',accent:'#e0c26b'},
{name:'THE GRANDMA',line:'No need to rush.',hair:'#b9b7aa',shirt:'#8d5575',accent:'#e8b9cc'},
{name:'THE KID',line:'Can we go now?',hair:'#292929',shirt:'#d58c31',accent:'#da4239'},
{name:'THE OLD FISHERMAN',line:'I know these waters.',hair:'#d4d0bd',shirt:'#3b6579',accent:'#d5a74e'},
{name:'PHU QUOC RIDGEBACK',line:'No ticket needed.',special:'dog'},
{name:'PEPPER',line:'A little spicy.',special:'pepper'}
];
let selected=0,totalJo=+(localStorage.pqJo||0);const views=[...document.querySelectorAll('.view')];
const landingMap=document.getElementById('landingMap'),mapImg=document.getElementById('mapImg'),grid=document.getElementById('charGrid');
landingMap.src=A.landing||A.map||'';mapImg.src=A.map||'';
function showView(id){views.forEach(v=>v.classList.toggle('on',v.id===id));if(id==='gameView')resizeGame();}
CHAR.forEach((c,i)=>{const b=document.createElement('button');b.className='char'+(i===0?' sel':'');const sp=c.special?` ${c.special}`:'';b.innerHTML=`<div class="face${sp}" style="--hair:${c.hair||'#171717'};--shirt:${c.shirt||'#397a5c'};--accent:${c.accent||'#eab634'}"><i class="headp"></i><i class="bodyp"></i><i class="acc"></i></div><div class="copy"><b>${c.name}</b><small>${c.line}</small></div>`;b.onclick=()=>{selected=i;[...grid.children].forEach((x,j)=>x.classList.toggle('sel',j===i))};grid.appendChild(b)});
function openMap(){const n=document.getElementById('playerName').value.trim()||'Traveler';document.getElementById('mapHello').textContent=`WELCOME, ${n.toUpperCase()}`;document.getElementById('mapJo').textContent=totalJo;showView('map')}
function openGame(){showView('gameView');document.getElementById('tutorial').classList.add('on');document.getElementById('over').classList.remove('on');drawIdle()}
function backMap(){stopGame();document.getElementById('tutorial').classList.remove('on');document.getElementById('over').classList.remove('on');document.getElementById('mapJo').textContent=totalJo;showView('map')}

const gameView=document.getElementById('gameView'),scaler=document.getElementById('gameScaler'),canvas=document.getElementById('gameCanvas'),ctx=canvas.getContext('2d');ctx.imageSmoothingEnabled=false;
const ambient=document.getElementById('ambient');ambient.style.backgroundImage=A.bg?`url("${A.bg}")`:'linear-gradient(#4fa4d0,#105a7f)';
function resizeGame(){const w=innerWidth,h=innerHeight;let s;if(w/h<.75){s=Math.max(w/540,h/960)}else{s=h/960}scaler.style.transform=`translate(-50%,-50%) scale(${s})`;}
addEventListener('resize',resizeGame,{passive:true});

const imgKeys=['bg','ride1','ride2','ride3','ride4','planter','chair','table','menu','tripod','suitcase','coin'];const imgs={};
let assetsReady=false;const readyPromise=Promise.all(imgKeys.map(k=>new Promise(res=>{const im=new Image();imgs[k]=im;im.onload=()=>res();im.onerror=()=>res();im.src=A[k]||'';}))).then(()=>{assetsReady=true;drawIdle()});

let run=false,raf=0,last=0,score=0,runJo=0,best=+(localStorage.pqBestR4||0),world=0,obstacle=null,coinObj=null,jumpStart=0,jumpY=0,rideFrame=0,rideClock=0,firstGrace=true,startedAt=0,audio=null,engineOsc=null,engineGain=null,toastText='',toastUntil=0,dust=[];
const player={x:82,y:798,w:132,h:174};
const obstacleTypes=[
{name:'planter',w:84,h:84,hitW:48,hitH:48},
{name:'chair',w:62,h:82,hitW:32,hitH:50},
{name:'table',w:78,h:68,hitW:42,hitH:36},
{name:'menu',w:70,h:88,hitW:38,hitH:55},
{name:'tripod',w:74,h:88,hitW:32,hitH:56},
{name:'suitcase',w:58,h:72,hitW:34,hitH:46}
];
function difficulty(){if(score<10)return{speed:88,gap:[650,820],label:'EASY'};if(score<25)return{speed:118,gap:[470,620],label:'WARMING UP'};if(score<50)return{speed:150,gap:[380,520],label:'GETTING QUICK'};return{speed:182+Math.min(34,(score-50)*.8),gap:[320,450],label:'NO BRAKES'}}
function startEngine(){try{audio=audio||new (AudioContext||webkitAudioContext)();if(audio.state==='suspended')audio.resume();stopEngine();engineOsc=audio.createOscillator();engineGain=audio.createGain();engineOsc.type='sawtooth';engineOsc.frequency.value=62;engineGain.gain.value=.012;engineOsc.connect(engineGain).connect(audio.destination);engineOsc.start()}catch(e){}}
function stopEngine(){try{if(engineOsc)engineOsc.stop();engineOsc=null}catch(e){}}
function beep(freq=700,d=.07,v=.025){try{audio=audio||new (AudioContext||webkitAudioContext)();const o=audio.createOscillator(),g=audio.createGain();o.type='square';o.frequency.value=freq;g.gain.setValueAtTime(v,audio.currentTime);g.gain.exponentialRampToValueAtTime(.0001,audio.currentTime+d);o.connect(g).connect(audio.destination);o.start();o.stop(audio.currentTime+d)}catch(e){}}
function flash(t,ms=600){toastText=t;toastUntil=performance.now()+ms}
function spawnObstacle(first=false){const max=score<10?3:obstacleTypes.length;const t=obstacleTypes[Math.floor(Math.random()*max)];const d=difficulty();obstacle={...t,x:first?1320:540+d.gap[0]+Math.random()*(d.gap[1]-d.gap[0]),y:820-t.h};}
function spawnCoin(){coinObj={x:760+Math.random()*420,y:650+Math.random()*90,w:48,h:48,collected:false}}
function hop(){if(!run||jumpStart)return;jumpStart=performance.now();beep(520,.05,.018)}
function jumpPhysics(now){if(!jumpStart){jumpY=0;return}const p=Math.min(1,(now-jumpStart)/720);jumpY=112*4*p*(1-p);if(p>=1){jumpStart=0;jumpY=0;beep(210,.035,.012)}}
function startGame(){document.getElementById('tutorial').classList.remove('on');document.getElementById('over').classList.remove('on');if(!assetsReady){flash('LOADING...');readyPromise.then(startGame);return}run=true;score=0;runJo=0;world=0;jumpStart=0;jumpY=0;rideFrame=0;rideClock=0;firstGrace=true;startedAt=performance.now();last=performance.now();dust=[];spawnObstacle(true);spawnCoin();startEngine();cancelAnimationFrame(raf);raf=requestAnimationFrame(loop)}
function stopGame(){run=false;cancelAnimationFrame(raf);stopEngine()}
function gameOver(){run=false;cancelAnimationFrame(raf);stopEngine();best=Math.max(best,score);localStorage.pqBestR4=best;totalJo+=runJo;localStorage.pqJo=totalJo;document.getElementById('result').innerHTML=`SCORE <b>${score}</b> · JO <b>+${runJo}</b><br><span class="small">${score<3?'No rush. Watch the obstacle and hop a little earlier.':'Nice run.'}</span>`;document.getElementById('over').classList.add('on');beep(145,.16,.035)}
function loop(t){if(!run)return;const dt=Math.min(34,t-last);last=t;const d=difficulty();world+=d.speed*dt/1000;if(engineOsc&&audio)engineOsc.frequency.setValueAtTime(62+Math.min(26,score*.4),audio.currentTime);rideClock+=dt;if(rideClock>110){rideClock=0;rideFrame=(rideFrame+1)%4}jumpPhysics(t);obstacle.x-=d.speed*dt/1000;if(coinObj)coinObj.x-=d.speed*.94*dt/1000;if(Math.random()<.18)dust.push({x:player.x+24,y:822,vx:-35-Math.random()*25,vy:-12-Math.random()*16,a:.7});dust.forEach(p=>{p.x+=p.vx*dt/1000;p.y+=p.vy*dt/1000;p.a-=dt/700});dust=dust.filter(p=>p.a>0);
if(obstacle.x<-obstacle.w){score++;if(score===1)flash('EASY.');if(score===10)flash('WARMING UP!');if(score===25)flash('FASTER!');if(score===69)flash('NICE.');spawnObstacle(false)}if(coinObj&&coinObj.x<-60)spawnCoin();
const pL=player.x+26,pR=player.x+108,ow=obstacle.hitW,hL=obstacle.x+(obstacle.w-ow)/2,hR=hL+ow;const collide=pR>hL&&pL<hR;if(collide&&jumpY<obstacle.hitH*.78&&t-startedAt>1800){if(firstGrace&&score<2){firstGrace=false;obstacle.x+=170;flash('TAP TO HOP!',850);beep(430,.09,.02)}else{drawFrame(t);gameOver();return}}
if(coinObj&&!coinObj.collected&&pR>coinObj.x&&pL<coinObj.x+coinObj.w&&jumpY>38){coinObj.collected=true;runJo++;flash('+1 JO');beep(1180,.07,.028);spawnCoin()}
drawFrame(t);raf=requestAnimationFrame(loop)}
function drawCover(im,x,y,w,h){if(!im||!im.complete||!im.naturalWidth){ctx.fillStyle='#235875';ctx.fillRect(x,y,w,h);return}const r=Math.max(w/im.naturalWidth,h/im.naturalHeight),sw=w/r,sh=h/r,sx=(im.naturalWidth-sw)/2,sy=(im.naturalHeight-sh)/2;ctx.drawImage(im,sx,sy,sw,sh,x,y,w,h)}
function drawFrame(now=performance.now()){ctx.clearRect(0,0,540,960);drawCover(imgs.bg,0,0,540,960);const grad=ctx.createLinearGradient(0,0,0,960);grad.addColorStop(0,'rgba(0,20,30,.04)');grad.addColorStop(.68,'rgba(0,0,0,.08)');grad.addColorStop(1,'rgba(0,0,0,.45)');ctx.fillStyle=grad;ctx.fillRect(0,0,540,960);
ctx.fillStyle='rgba(83,66,49,.92)';ctx.fillRect(0,820,540,140);for(let x=-(world%72);x<600;x+=72){ctx.fillStyle='rgba(177,151,117,.34)';ctx.fillRect(x,842,34,5);ctx.fillStyle='rgba(49,37,28,.34)';ctx.fillRect(x+38,842,30,5)}
if(score>=25){ctx.strokeStyle='rgba(255,255,255,.10)';ctx.lineWidth=2;for(let i=0;i<8;i++){const yy=180+i*75;ctx.beginPath();ctx.moveTo((world*1.8+i*70)%600-60,yy);ctx.lineTo((world*1.8+i*70)%600+35,yy-15);ctx.stroke()}}
for(const p of dust){ctx.globalAlpha=Math.max(0,p.a);ctx.fillStyle='#ddc49e';ctx.beginPath();ctx.arc(p.x,p.y,4+(1-p.a)*3,0,Math.PI*2);ctx.fill()}ctx.globalAlpha=1;
ctx.fillStyle='rgba(0,0,0,.42)';ctx.beginPath();ctx.ellipse(player.x+70,824,Math.max(18,55-jumpY*.22),Math.max(4,9-jumpY*.02),0,0,Math.PI*2);ctx.fill();
if(obstacle){const im=imgs[obstacle.name];if(im&&im.complete&&im.naturalWidth)ctx.drawImage(im,obstacle.x,obstacle.y,obstacle.w,obstacle.h);else{ctx.fillStyle='#d49d4f';ctx.fillRect(obstacle.x,obstacle.y,obstacle.w,obstacle.h)}}
if(coinObj){const im=imgs.coin;if(im&&im.complete&&im.naturalWidth)ctx.drawImage(im,coinObj.x,coinObj.y,coinObj.w,coinObj.h);}
const ride=imgs['ride'+(rideFrame+1)]||imgs.ride1;const py=player.y-jumpY;ctx.save();ctx.translate(player.x+player.w/2,py+player.h);const p=jumpStart?Math.min(1,(now-jumpStart)/720):0,rot=jumpStart?(p<.5?-0.07*(p/.5):-0.07+0.11*((p-.5)/.5)):0;ctx.rotate(rot);if(ride&&ride.complete&&ride.naturalWidth)ctx.drawImage(ride,-player.w/2,-player.h,player.w,player.h);ctx.restore();
ctx.textBaseline='top';ctx.font='900 18px monospace';ctx.shadowColor='rgba(0,0,0,.8)';ctx.shadowOffsetX=2;ctx.shadowOffsetY=2;ctx.fillStyle='#fff';ctx.fillText(`SCORE ${score}`,20,24);ctx.textAlign='center';ctx.fillText(`JO ${runJo}`,270,24);ctx.textAlign='right';ctx.fillText(`BEST ${best}`,520,24);ctx.textAlign='center';ctx.shadowOffsetX=0;ctx.shadowOffsetY=0;ctx.fillStyle='#f6bb38';ctx.font='900 14px monospace';ctx.fillText('SUNSET TOWN',270,88);ctx.fillStyle='#fff';ctx.font='900 31px monospace';ctx.fillText('NO BRAKES',270,108);ctx.font='12px monospace';ctx.fillText('TAP · CLICK · SPACE TO HOP',270,150);ctx.font='11px monospace';ctx.fillStyle='rgba(255,255,255,.88)';ctx.fillText(`${difficulty().label}${score<10?' · FIRST 10 ARE FRIENDLY':''}`,270,918);if(now<toastUntil){ctx.font='900 22px monospace';ctx.fillStyle='#f6bb38';ctx.fillText(toastText,270,220)}ctx.textAlign='left';ctx.shadowColor='transparent';}
function drawIdle(){if(!canvas)return;resizeGame();if(assetsReady){if(!obstacle)obstacle={...obstacleTypes[0],x:620,y:736};if(!coinObj)coinObj={x:430,y:650,w:48,h:48};drawFrame()}else{ctx.fillStyle='#0c3d55';ctx.fillRect(0,0,540,960);ctx.fillStyle='#fff';ctx.font='18px monospace';ctx.textAlign='center';ctx.fillText('LOADING ISLAND...',270,470);ctx.textAlign='left'}}

gameView.addEventListener('pointerdown',()=>{if(run)hop()});addEventListener('keydown',e=>{if(e.code==='Space'){e.preventDefault();if(run)hop()}});resizeGame();drawIdle();
