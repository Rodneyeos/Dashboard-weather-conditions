let csrf='', stations=[],alerts=[],currentRole='viewer',currentUserId=null; const $=id=>document.getElementById(id);
async function api(path,opts={}){const r=await fetch('/api'+path,{credentials:'same-origin',...opts,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,...opts.headers}});if(!r.ok){let e=await r.json().catch(()=>({detail:r.statusText}));throw Error(e.detail||'Fout')}return r.headers.get('content-type')?.includes('json')?r.json():r}
function text(id,val){$(id).textContent=val} function fmt(v,unit=''){return v==null?'—':Number(v).toFixed(1)+' '+unit}function date(ts){return ts?new Date(ts*1000).toLocaleString('nl-NL'):'—'}
const windUnits={'km/h':1,'m/s':1/3.6,'kn':1/1.852,'mph':1/1.609344};
let windUnit=localStorage.getItem('ccWindUnit')||'km/h';if(!(windUnit in windUnits))windUnit='km/h';
function windFmt(v){return v==null?'—':(Number(v)*windUnits[windUnit]).toLocaleString('nl-NL',{minimumFractionDigits:1,maximumFractionDigits:1})+' '+windUnit}
function cell(row,content){let td=document.createElement('td');if(content instanceof Node)td.append(content);else td.textContent=content;row.append(td)}
function input(value,type='text'){let el=document.createElement('input');el.type=type;el.value=value;return el}
function btn(label,fn,klass='secondary'){let el=document.createElement('button');el.textContent=label;el.className=klass;el.onclick=fn;return el}
async function login(){try{let x=await api('/login',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});csrf=x.csrf;currentRole=x.role;currentUserId=x.id;applyRole();$('login').classList.add('hidden');$('app').classList.remove('hidden');$('logout').classList.remove('hidden');await refresh()}catch(e){text('loginError',e.message)}}
$('loginForm').onsubmit=e=>{e.preventDefault();login()};$('logout').onclick=async()=>{await api('/logout',{method:'POST'});location.reload()};
function fleetStatus(s){const r=s.latest||{},age=r.ts?Date.now()/1000-r.ts:Infinity;const active=alerts.filter(a=>Number(a.station_id)===Number(s.id)&&a.active);if(s.last_error||!s.enabled||age>600)return {label:'Offline / verouderd',kind:'offline'};if(active.length)return {label:'Alarm',kind:'alarm'};return {label:'Online',kind:'online'}}
function renderFleet(){const root=$('fleetCards'),stats=$('fleetStats');root.replaceChildren();stats.replaceChildren();const counts={online:0,alarm:0,offline:0};stations.forEach(s=>counts[fleetStatus(s).kind]++);for(const [label,value] of [['Toegewezen windmeters',stations.length],['Online',counts.online],['Actieve alarmstations',counts.alarm],['Offline / verouderd',counts.offline]]){const c=document.createElement('div');c.className='card';const l=document.createElement('label');l.textContent=label;const n=document.createElement('div');n.className='number';n.textContent=value;c.append(l,n);stats.append(c)}if(!stations.length){const msg=document.createElement('p');msg.className='muted';msg.textContent='Er zijn nog geen windmeters aan je account toegewezen.';root.append(msg)}for(const s of stations){const r=s.latest||{},status=fleetStatus(s),b=document.createElement('button');b.type='button';b.className='fleet-item '+status.kind+(String(s.id)===$('stationSelect').value?' selected':'');const head=document.createElement('div');head.className='fleet-head';const name=document.createElement('strong');name.textContent=s.name;const badge=document.createElement('span');badge.className='pill';badge.textContent=status.label;head.append(name,badge);b.append(head);const values=document.createElement('div');values.className='fleet-values';for(const [label,val] of [['Wind',windFmt(r.wind)],['Windstoot',windFmt(r.gust)],['Windrichting',fmt(r.direction,'°')],['Regen',fmt(r.rainrate,'mm/u')]]){const cell=document.createElement('div');const l=document.createElement('div');l.className='fleet-label';l.textContent=label;const v=document.createElement('div');v.className='fleet-value';v.textContent=val;cell.append(l,v);values.append(cell)}b.append(values);const foot=document.createElement('div');foot.className='fleet-foot';foot.textContent='Laatste meting: '+date(r.ts)+' · Bekijk details →';b.append(foot);b.onclick=()=>{$('stationSelect').value=String(s.id);renderFleet();renderStation();$('stationSelect').scrollIntoView({behavior:'smooth',block:'center'})};root.append(b)}text('fleetUpdated','Bijgewerkt: '+new Date().toLocaleTimeString('nl-NL'))}
async function refresh(){try{stations=await api('/stations');alerts=await api('/alerts');let sel=$('stationSelect'),old=sel.value;sel.replaceChildren();stations.forEach(s=>{let o=new Option(s.name,s.id);sel.add(o)});if(stations.some(s=>String(s.id)===old))sel.value=old;renderRows();renderAlerts();renderFleet();await renderStation();if(currentRole==='admin')await loadUsers()}catch(e){text('status','Fout: '+e.message)}}
async function renderStation(){let s=stations.find(s=>String(s.id)===$('stationSelect').value);if(!s){text('status','Voeg hieronder een weerstation toe.');return}let r=s.latest||{};text('wind',windFmt(r.wind));text('gust',windFmt(r.gust));text('rain',fmt(r.rainrate,'mm/u'));text('precip',fmt(r.precipitation,'mm'));text('temp',fmt(r.temp,'°C'));text('humidity',fmt(r.humidity,'%'));text('direction',fmt(r.direction,'°'));$('compass').style.transform=r.direction==null?'rotate(0deg)':`rotate(${r.direction}deg)`;$('compass').style.opacity=r.direction==null?'0.3':'1';text('updated','Meting: '+date(r.ts));let stale=!r.ts||Date.now()/1000-r.ts>600;let active=alerts.filter(a=>a.station_id===s.id&&a.active);let status=$('status');status.className='status'+(stale||s.last_error?' warning':active.length?' bad':'');status.textContent=s.last_error?'API-fout: '+s.last_error:stale?'LET OP: geen recente meting (ouder dan 10 minuten)':active.length?'ALARM: '+active.map(a=>a.kind).join(', '):'Station online · alarmgrenzen niet overschreden';text('activeAlerts',active.length?active.map(a=>a.kind+' · '+fmt(a.reading)+' / '+fmt(a.limit_value)).join(' | '):'Geen actieve alarmen');try{draw(await api('/history/'+s.id+'?hours='+$('period').value))}catch(e){text('status',e.message)}}
function renderRows(){let tbody=$('stationRows');tbody.replaceChildren();stations.forEach(s=>{let tr=document.createElement('tr'),name=input(s.name),wind=input(s.wind_limit,'number'),rain=input(s.rain_limit,'number'),enabled=document.createElement('input');wind.step=rain.step='0.1';wind.min=rain.min='0.1';enabled.type='checkbox';enabled.checked=!!s.enabled;cell(tr,name);cell(tr,wind);cell(tr,rain);cell(tr,enabled);let actions=document.createElement('div');actions.className='bar';actions.append(btn('Opslaan',async()=>{try{await api('/stations/'+s.id,{method:'PUT',body:JSON.stringify({name:name.value,wind_limit:Number(wind.value),rain_limit:Number(rain.value),enabled:enabled.checked})});await refresh()}catch(e){alert(e.message)}}),btn('Verwijderen',async()=>{if(confirm('Station inclusief historie en alarmen verwijderen?')){await api('/stations/'+s.id,{method:'DELETE'});await refresh()}},'danger'));cell(tr,actions);tbody.append(tr)})}
function renderAlerts(){let body=$('alertRows');body.replaceChildren();alerts.forEach(a=>{let tr=document.createElement('tr');[a.name,a.kind,date(a.started),a.active?'ACTIEF':'Gesloten '+date(a.ended),fmt(a.reading)+' / '+fmt(a.limit_value)].forEach(v=>cell(tr,v));body.append(tr)})}
let chartData=[],chartLayout=null;
function draw(data){
  chartData=Array.isArray(data)?data:[];
  const c=$('graph'),w=Math.max(260,c.clientWidth),h=290,dpr=window.devicePixelRatio||1;
  c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);
  const x=c.getContext('2d');x.setTransform(dpr,0,0,dpr,0,0);x.clearRect(0,0,w,h);
  const L=53,R=14,T=18,B=42,plotW=w-L-R,plotH=h-T-B;
  const factor=windUnits[windUnit];
  const values=chartData.flatMap(r=>[r.wind,r.gust].filter(v=>v!=null).map(v=>Number(v)*factor));
  const max=Math.max(5,...values)*1.12;
  chartLayout={L,R,T,B,plotW,plotH,max,w,h};
  x.font='12px system-ui,sans-serif';x.textBaseline='middle';
  for(let i=0;i<=4;i++){
    const yy=T+plotH*i/4,val=max*(1-i/4);
    x.strokeStyle='#3b5167';x.lineWidth=1;x.beginPath();x.moveTo(L,yy);x.lineTo(w-R,yy);x.stroke();
    x.fillStyle='#a9bbcb';x.textAlign='right';x.fillText(val.toFixed(1),L-9,yy);
  }
  x.fillStyle='#a9bbcb';x.textAlign='left';x.fillText(windUnit,4,9);
  if(!chartData.length){x.fillText('Nog geen historische metingen',L+10,T+55);return}
  const timestamps=chartData.map(r=>Number(r.ts)||0),start=Math.min(...timestamps),end=Math.max(...timestamps),range=Math.max(1,end-start);
  const px=r=>L+((Number(r.ts)||start)-start)/range*plotW;
  for(let i=0;i<=4;i++){
    const ts=start+range*i/4,xx=L+plotW*i/4;
    x.fillStyle='#a9bbcb';x.textAlign=i===0?'left':i===4?'right':'center';
    x.fillText(new Date(ts*1000).toLocaleString('nl-NL',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}),xx,h-20);
  }
  for(const [field,color] of [['wind','#38bdf8'],['gust','#fbbf24']]){
    x.beginPath();x.strokeStyle=color;x.lineWidth=2.5;let started=false;
    for(const r of chartData){
      if(r[field]==null||!Number.isFinite(Number(r[field]))){started=false;continue}
      const yy=T+plotH*(1-Number(r[field])*factor/max);
      if(!started)x.moveTo(px(r),yy);else x.lineTo(px(r),yy);started=true;
    }
    x.stroke();
  }
}
$('graph').addEventListener('mousemove',e=>{
  if(!chartData.length||!chartLayout)return;
  const c=$('graph'),rect=c.getBoundingClientRect(),mx=e.clientX-rect.left,{L,plotW}=chartLayout;
  if(mx<L||mx>L+plotW){$('graphTooltip').style.display='none';return}
  const first=Number(chartData[0].ts),last=Number(chartData[chartData.length-1].ts);
  const target=first+(mx-L)/plotW*(last-first);
  const r=chartData.reduce((best,item)=>Math.abs(Number(item.ts)-target)<Math.abs(Number(best.ts)-target)?item:best,chartData[0]);
  const tip=$('graphTooltip');tip.textContent='';
  for(const line of [date(r.ts),'Windsnelheid: '+windFmt(r.wind),'Windstoten: '+windFmt(r.gust),'Regen: '+fmt(r.rainrate,'mm/u')]){
    const div=document.createElement('div');div.textContent=line;tip.append(div);
  }
  tip.style.display='block';tip.style.left=Math.min(Math.max(0,mx+12),Math.max(0,rect.width-190))+'px';tip.style.top='30px';
});
$('graph').addEventListener('mouseleave',()=>{$('graphTooltip').style.display='none'});
window.addEventListener('resize',()=>{if(chartData.length)draw(chartData)});
$('windUnit').value=windUnit;$('windUnit').onchange=()=>{windUnit=$('windUnit').value;localStorage.setItem('ccWindUnit',windUnit);renderFleet();renderStation()};
$('stationSelect').onchange=()=>{renderFleet();renderStation()};$('period').onchange=renderStation;$('refresh').onclick=refresh;$('csv').onclick=()=>{let id=$('stationSelect').value;if(id)location.href='/api/export/'+id+'?hours='+$('period').value+'&unit='+encodeURIComponent(windUnit)};
$('addForm').onsubmit=async e=>{e.preventDefault();try{await api('/stations',{method:'POST',body:JSON.stringify({name:$('newName').value,api_key:$('newKey').value,wind_limit:Number($('newWind').value),rain_limit:Number($('newRain').value)})});$('newKey').value='';await refresh()}catch(e){alert(e.message)}};
api('/me').then(x=>{csrf=x.csrf;currentRole=x.role;currentUserId=x.id;applyRole();currentRole=x.role;currentUserId=x.id;applyRole();$('login').classList.add('hidden');$('app').classList.remove('hidden');$('logout').classList.remove('hidden');refresh()}).catch(()=>{});setInterval(()=>{if(csrf)refresh()},30000);

function applyRole(){
  $('adminPortal').classList.toggle('hidden',currentRole!=='admin');
  $('stationAdmin').classList.toggle('hidden',currentRole!=='admin');
  $('espAdmin').classList.toggle('hidden',currentRole!=='admin');
}
function assignmentBox(selected=[]){
  const wrap=document.createElement('div');wrap.style.cssText='display:flex;flex-direction:column;gap:4px;min-width:170px';
  for(const st of stations){const label=document.createElement('label');label.style.cssText='font-size:13px;display:flex;align-items:center;gap:5px';const cb=document.createElement('input');cb.type='checkbox';cb.value=st.id;cb.checked=selected.includes(st.id);label.append(cb,document.createTextNode(st.name));wrap.append(label)}
  return wrap;
}
function assigned(box){return [...box.querySelectorAll('input:checked')].map(e=>Number(e.value))}
async function loadUsers(){
  const users=await api('/users');const fresh=$('newAssignments');
  const prev=assigned(fresh);fresh.replaceChildren(assignmentBox(prev));
  const tbody=$('userRows');tbody.replaceChildren();
  for(const u of users){
    const tr=document.createElement('tr');cell(tr,u.username);
    const role=document.createElement('select');for(const v of ['viewer','admin'])role.add(new Option(v==='viewer'?'Gebruiker':'Administrator',v));role.value=u.role;cell(tr,role);
    const enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=!!u.enabled;cell(tr,enabled);
    const checks=assignmentBox(u.station_ids);cell(tr,checks);
    const password=input('','password');password.placeholder='Ongewijzigd';password.minLength=12;cell(tr,password);
    const actions=document.createElement('div');actions.className='bar';
    actions.append(btn('Opslaan',async()=>{try{await api('/users/'+u.id,{method:'PUT',body:JSON.stringify({role:role.value,enabled:enabled.checked,station_ids:assigned(checks),password:password.value||null})});text('userMessage','Gebruiker opgeslagen');await loadUsers()}catch(e){text('userMessage',e.message)}}),btn('Verwijderen',async()=>{if(confirm('Gebruiker definitief verwijderen?')){try{await api('/users/'+u.id,{method:'DELETE'});await loadUsers()}catch(e){text('userMessage',e.message)}}},'danger'));
    cell(tr,actions);tbody.append(tr);
  }
}
$('userForm').onsubmit=async e=>{e.preventDefault();try{
  await api('/users',{method:'POST',body:JSON.stringify({username:$('userName').value,password:$('userPassword').value,role:$('userRole').value,station_ids:assigned($('newAssignments'))})});
  $('userPassword').value='';$('userName').value='';text('userMessage','Gebruiker aangemaakt');await loadUsers();
}catch(e){text('userMessage',e.message)}};

$('espForm').onsubmit=async e=>{e.preventDefault();try{
  const result=await api('/esp/stations',{method:'POST',body:JSON.stringify({name:$('espName').value,wind_limit:Number($('espWind').value),rain_limit:Number($('espRain').value)})});
  const el=$('espResult');el.replaceChildren();
  const title=document.createElement('strong');title.textContent='ESP32 station ID: '+result.id+' · Bewaar deze token veilig (eenmalig):';
  const token=document.createElement('code');token.textContent=result.device_token;token.style.cssText='display:block;padding:12px;margin:10px 0;background:#07101b;user-select:all';
  const copy=btn('Token kopiëren',()=>navigator.clipboard.writeText(result.device_token));
  el.append(title,token,copy);await refresh();
}catch(err){text('espResult','Fout: '+err.message)}};
