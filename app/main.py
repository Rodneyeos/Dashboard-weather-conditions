import os, sqlite3, time, asyncio, secrets, hashlib, hmac, base64, json, logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote
from datetime import datetime, timezone
import httpx
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
DB = os.getenv('DB_PATH', '/data/weather.sqlite3')
ADMIN = os.getenv('ADMIN_PASSWORD','')
SECRET = os.getenv('SESSION_SECRET','')
FERNET = os.getenv('FERNET_KEY','')
if not ADMIN or ADMIN.startswith('VERVANG_') or not SECRET or SECRET.startswith('VERVANG_') or not FERNET or FERNET.startswith('VERVANG_'):
    raise RuntimeError('Configureer ADMIN_PASSWORD, SESSION_SECRET en FERNET_KEY in .env')
crypto = Fernet(FERNET.encode())
INTERVAL = max(30,int(os.getenv('POLL_SECONDS','60')))
SECURE = os.getenv('COOKIE_SECURE','true').lower()=='true'

def db():
    con=sqlite3.connect(DB,timeout=20)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    return con

def setup():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS stations(id INTEGER PRIMARY KEY,name TEXT NOT NULL,api_key BLOB NOT NULL,wind_limit REAL NOT NULL DEFAULT 50,rain_limit REAL NOT NULL DEFAULT 10,enabled INTEGER NOT NULL DEFAULT 1,last_error TEXT);
        CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY,station_id INTEGER NOT NULL,ts INTEGER NOT NULL,wind REAL,gust REAL,direction REAL,rainrate REAL,precipitation REAL,temp REAL,humidity REAL,pressure REAL,UNIQUE(station_id,ts));
        CREATE INDEX IF NOT EXISTS idx_readings_station_ts ON readings(station_id,ts);
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY,station_id INTEGER NOT NULL,kind TEXT NOT NULL,active INTEGER NOT NULL,started INTEGER NOT NULL,ended INTEGER,reading REAL,limit_value REAL);
        CREATE INDEX IF NOT EXISTS idx_alerts_station ON alerts(station_id,active);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','viewer')),enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS user_stations(user_id INTEGER NOT NULL,station_id INTEGER NOT NULL,PRIMARY KEY(user_id,station_id));
        CREATE TABLE IF NOT EXISTS esp_devices(station_id INTEGER PRIMARY KEY,token_hash TEXT NOT NULL);''')
        cols={r['name'] for r in c.execute('PRAGMA table_info(stations)')}
        if 'source' not in cols: c.execute("ALTER TABLE stations ADD COLUMN source TEXT NOT NULL DEFAULT 'awekas'")
        admin_name=os.getenv('ADMIN_USERNAME','admin').strip().lower()
        if not c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone():
            c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(admin_name,hash_password(ADMIN),'admin'))

def hash_password(password):
    salt=secrets.token_bytes(16)
    return 'scrypt$'+base64.urlsafe_b64encode(salt).decode()+'$'+base64.urlsafe_b64encode(hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1)).decode()

def verify_password(password,stored):
    try:
        _,salt,digest=stored.split('$')
        expected=base64.urlsafe_b64decode(digest)
        actual=hashlib.scrypt(password.encode(),salt=base64.urlsafe_b64decode(salt),n=16384,r=8,p=1)
        return hmac.compare_digest(expected,actual)
    except (ValueError,TypeError): return False

def sign(value):
    return hmac.new(SECRET.encode(),value.encode(),hashlib.sha256).hexdigest()
def token(uid):
    payload=f'{uid}:{int(time.time())+12*3600}:{secrets.token_hex(12)}'
    return base64.urlsafe_b64encode(payload.encode()).decode()+'.'+sign(payload)
def identity(req):
    t=req.cookies.get('weather_session','')
    try:
        data,sig=t.split('.',1)
        payload=base64.urlsafe_b64decode(data).decode()
        uid,exp,_=payload.split(':',2)
        if int(exp)<time.time() or not hmac.compare_digest(sig,sign(payload)): return None
        with db() as c: row=c.execute('SELECT id,username,role FROM users WHERE id=? AND enabled=1',(int(uid),)).fetchone()
        return dict(row) if row else None
    except (ValueError,TypeError,UnicodeError): return None

def guard(req,admin=False):
    user=identity(req)
    if not user: raise HTTPException(401,'Log eerst in')
    if admin and user['role']!='admin': raise HTTPException(403,'Alleen voor beheerders')
    if req.method not in ('GET','HEAD'):
        origin=req.headers.get('origin')
        if origin:
            from urllib.parse import urlsplit
            if urlsplit(origin).netloc!=req.headers.get('host'): raise HTTPException(403,'Ongeldige origin')
        csrf=req.headers.get('x-csrf-token','')
        if not csrf or not hmac.compare_digest(csrf,sign(req.cookies.get('weather_session',''))):
            raise HTTPException(403,'Ongeldige CSRF token')
    return user

def can_access(c,user,sid):
    if user['role']=='admin': return True
    return bool(c.execute('SELECT 1 FROM user_stations WHERE user_id=? AND station_id=?',(user['id'],sid)).fetchone())

def station_guard(req,sid):
    user=guard(req)
    with db() as c:
        if not can_access(c,user,sid): raise HTTPException(403,'Geen toegang tot dit station')
    return user

def num(x):
    try: return float(x) if x is not None else None
    except (ValueError,TypeError): return None

def evaluate(c,sid,kind,value,limit,ts):
    row=c.execute('SELECT id FROM alerts WHERE station_id=? AND kind=? AND active=1',(sid,kind)).fetchone()
    exceeded=value is not None and value>=limit
    if exceeded and not row:
        c.execute('INSERT INTO alerts(station_id,kind,active,started,reading,limit_value) VALUES(?,?,1,?,?,?)',(sid,kind,ts,value,limit))
    elif not exceeded and row:
        c.execute('UPDATE alerts SET active=0,ended=? WHERE id=?',(ts,row['id']))

async def fetch_station(client,s):
    sid=s['id']
    try:
        key=crypto.decrypt(s['api_key']).decode()
        # AWEKAS keys are sometimes supplied already percent-encoded.
        response=await client.get('https://api.awekas.at/current.php',params={'key':unquote(key),'lng':'nl'})
        response.raise_for_status()
        obj=response.json()
        if obj.get('error'): raise ValueError('AWEKAS: '+str(obj['error'])[:150])
        current=obj.get('current')
        if not isinstance(current,dict): raise ValueError('Geen current-gegevens ontvangen')
        ts=int(current.get('datatimestamp') or time.time())
        if abs(ts-time.time())>86400*7: raise ValueError('Meetdatum buiten geldig bereik')
        values=[num(current.get(k)) for k in ('windspeed','gustspeed','winddirection','rainrate','precipitation','temperature','humidity','airpress_rel')]
        with db() as c:
            c.execute('INSERT OR IGNORE INTO readings(station_id,ts,wind,gust,direction,rainrate,precipitation,temp,humidity,pressure) VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,ts,*values))
            c.execute('UPDATE stations SET last_error=NULL WHERE id=?',(sid,))
            # Only evaluate fresh data; stale readings must not silently clear alarms.
            if time.time()-ts<600:
                evaluate(c,sid,'windstoot',values[1],s['wind_limit'],ts)
                evaluate(c,sid,'neerslag',values[3],s['rain_limit'],ts)
    except Exception as exc:
        logging.warning('Station %s: %s',sid,type(exc).__name__)
        with db() as c: c.execute('UPDATE stations SET last_error=? WHERE id=?',(str(exc)[:160],sid))

async def poll():
    async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
        while True:
            try:
                with db() as c: stations=c.execute("SELECT * FROM stations WHERE enabled=1 AND source='awekas'").fetchall()
                await asyncio.gather(*(fetch_station(client,s) for s in stations))
            except Exception: logging.exception('Polling fout')
            await asyncio.sleep(INTERVAL)

@asynccontextmanager
async def lifespan(app):
    setup()
    task=asyncio.create_task(poll())
    yield
    task.cancel()
    try: await task
    except asyncio.CancelledError: pass

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def headers(req,call_next):
    res=await call_next(req)
    res.headers['Cache-Control']='no-store'
    res.headers['X-Content-Type-Options']='nosniff'
    res.headers['X-Frame-Options']='DENY'
    res.headers['Referrer-Policy']='no-referrer'
    res.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
    return res

@app.get('/',response_class=HTMLResponse)
def home(): return Path(__file__).with_name('index.html').read_text()

class Login(BaseModel):
    username:str='admin'
    password:str
@app.post('/api/login')
def login(body:Login):
    with db() as c: user=c.execute('SELECT * FROM users WHERE username=? AND enabled=1',(body.username.strip().lower(),)).fetchone()
    if not user or not verify_password(body.password,user['password_hash']): raise HTTPException(401,'Onjuiste inloggegevens')
    t=token(user['id'])
    res=JSONResponse({'ok':True,'csrf':sign(t),'role':user['role'],'username':user['username'],'id':user['id']})
    res.set_cookie('weather_session',t,httponly=True,secure=SECURE,samesite='strict',max_age=43200)
    return res
@app.post('/api/logout')
def logout(req:Request):
    guard(req)
    res=JSONResponse({'ok':True});res.delete_cookie('weather_session');return res
@app.get('/api/me')
def me(req:Request):
    user=guard(req)
    return {'csrf':sign(req.cookies['weather_session']),**user}

class UserCreate(BaseModel):
    username:str=Field(min_length=3,max_length=60,pattern=r'^[a-zA-Z0-9_.-]+$')
    password:str=Field(min_length=12,max_length=256)
    role:str='viewer'
    station_ids:list[int]=Field(default_factory=list)

class UserUpdate(BaseModel):
    role:str='viewer'
    enabled:bool=True
    station_ids:list[int]=Field(default_factory=list)
    password:str|None=None

def validate_role(role):
    if role not in ('admin','viewer'): raise HTTPException(422,'Ongeldige rol')

def validate_stations(c,ids):
    if len(ids)>500: raise HTTPException(422,'Te veel stations')
    for sid in set(ids):
        if not c.execute('SELECT 1 FROM stations WHERE id=?',(sid,)).fetchone(): raise HTTPException(422,'Onbekend station')

def set_assignments(c,uid,ids):
    c.execute('DELETE FROM user_stations WHERE user_id=?',(uid,))
    c.executemany('INSERT INTO user_stations(user_id,station_id) VALUES(?,?)',[(uid,sid) for sid in set(ids)])

@app.get('/api/users')
def users(req:Request):
    guard(req,admin=True)
    with db() as c:
        result=[]
        for u in c.execute('SELECT id,username,role,enabled FROM users ORDER BY username').fetchall():
            ids=[r['station_id'] for r in c.execute('SELECT station_id FROM user_stations WHERE user_id=?',(u['id'],))]
            result.append({**dict(u),'station_ids':ids})
        return result

@app.post('/api/users')
def create_user(body:UserCreate,req:Request):
    guard(req,admin=True);validate_role(body.role)
    with db() as c:
        validate_stations(c,body.station_ids)
        try: cur=c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',(body.username.lower(),hash_password(body.password),body.role))
        except sqlite3.IntegrityError: raise HTTPException(409,'Gebruikersnaam bestaat al')
        set_assignments(c,cur.lastrowid,body.station_ids)
        return {'id':cur.lastrowid}

@app.put('/api/users/{uid}')
def update_user(uid:int,body:UserUpdate,req:Request):
    actor=guard(req,admin=True);validate_role(body.role)
    if body.password is not None and len(body.password)<12: raise HTTPException(422,'Wachtwoord minimaal 12 tekens')
    if uid==actor['id'] and (not body.enabled or body.role!='admin'): raise HTTPException(400,'Je kunt je eigen adminaccount niet uitschakelen')
    with db() as c:
        validate_stations(c,body.station_ids)
        if not c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone(): raise HTTPException(404,'Gebruiker niet gevonden')
        c.execute('UPDATE users SET role=?,enabled=? WHERE id=?',(body.role,int(body.enabled),uid))
        if body.password: c.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(body.password),uid))
        set_assignments(c,uid,body.station_ids)
    return {'ok':True}

@app.delete('/api/users/{uid}')
def delete_user(uid:int,req:Request):
    actor=guard(req,admin=True)
    if uid==actor['id']: raise HTTPException(400,'Je kunt je eigen account niet verwijderen')
    with db() as c:
        c.execute('DELETE FROM user_stations WHERE user_id=?',(uid,))
        c.execute('DELETE FROM users WHERE id=?',(uid,))
    return {'ok':True}

class Station(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    api_key:str=Field(min_length=10,max_length=1000)
    wind_limit:float=Field(default=50,gt=0,le=300)
    rain_limit:float=Field(default=10,gt=0,le=500)
@app.post('/api/stations')
def add(body:Station,req:Request):
    guard(req,admin=True)
    with db() as c:
        cur=c.execute('INSERT INTO stations(name,api_key,wind_limit,rain_limit) VALUES(?,?,?,?)',(body.name,crypto.encrypt(body.api_key.encode()),body.wind_limit,body.rain_limit))
        return {'id':cur.lastrowid}
class Limits(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    wind_limit:float=Field(gt=0,le=300)
    rain_limit:float=Field(gt=0,le=500)
    enabled:bool=True
@app.put('/api/stations/{sid}')
def update(sid:int,body:Limits,req:Request):
    guard(req,admin=True)
    with db() as c:
        cur=c.execute('UPDATE stations SET name=?,wind_limit=?,rain_limit=?,enabled=? WHERE id=?',(body.name,body.wind_limit,body.rain_limit,int(body.enabled),sid))
        if not cur.rowcount: raise HTTPException(404,'Station niet gevonden')
        return {'ok':True}
@app.delete('/api/stations/{sid}')
def delete(sid:int,req:Request):
    guard(req,admin=True)
    with db() as c:
        c.execute('DELETE FROM esp_devices WHERE station_id=?',(sid,))
        c.execute('DELETE FROM user_stations WHERE station_id=?',(sid,))
        c.execute('DELETE FROM alerts WHERE station_id=?',(sid,))
        c.execute('DELETE FROM readings WHERE station_id=?',(sid,))
        c.execute('DELETE FROM stations WHERE id=?',(sid,))
    return {'ok':True}
# ESP32 PoE / RS485: each device has a unique 256-bit credential, stored only as SHA-256.
# Ingestion is intentionally independent of browser cookie/CSRF authentication.
class ESPStation(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    wind_limit:float=Field(default=50,gt=0,le=300)
    rain_limit:float=Field(default=10,gt=0,le=500)

@app.post('/api/esp/stations')
def create_esp_station(body:ESPStation,req:Request):
    guard(req,admin=True)
    credential=secrets.token_urlsafe(32)
    digest=hashlib.sha256(credential.encode()).hexdigest()
    with db() as c:
        cur=c.execute("INSERT INTO stations(name,api_key,wind_limit,rain_limit,source) VALUES(?,?,?,?,?)",(body.name,crypto.encrypt(b''),body.wind_limit,body.rain_limit,'esp32'))
        c.execute('INSERT INTO esp_devices(station_id,token_hash) VALUES(?,?)',(cur.lastrowid,digest))
        return {'id':cur.lastrowid,'device_token':credential,'warning':'Bewaar de token nu; deze wordt niet opnieuw getoond.'}

@app.post('/api/esp/stations/{sid}/rotate')
def rotate_esp_token(sid:int,req:Request):
    guard(req,admin=True)
    credential=secrets.token_urlsafe(32)
    with db() as c:
        result=c.execute('UPDATE esp_devices SET token_hash=? WHERE station_id=?',(hashlib.sha256(credential.encode()).hexdigest(),sid))
        if not result.rowcount: raise HTTPException(404,'Geen ESP32-station')
    return {'device_token':credential,'warning':'De oude token werkt direct niet meer.'}

class ESPReading(BaseModel):
    wind:float=Field(ge=0,le=300,description='Windsnelheid in km/h')
    gust:float|None=Field(default=None,ge=0,le=350,description='Windstoot in km/h')
    direction:float|None=Field(default=None,ge=0,le=360,description='Meteorologische windrichting in graden')
    rainrate:float|None=Field(default=None,ge=0,le=500)
    precipitation:float|None=Field(default=None,ge=0,le=100000)
    temp:float|None=Field(default=None,ge=-80,le=80)
    humidity:float|None=Field(default=None,ge=0,le=100)
    pressure:float|None=Field(default=None,ge=700,le=1200)

@app.post('/api/esp/ingest/{sid}')
def esp_ingest(sid:int,body:ESPReading,req:Request):
    bearer=req.headers.get('authorization','')
    if not bearer.startswith('Bearer ') or len(bearer)>150: raise HTTPException(401,'Ongeldige device-token')
    candidate=hashlib.sha256(bearer[7:].encode()).hexdigest()
    with db() as c:
        station=c.execute("SELECT s.id,s.enabled,s.wind_limit,s.rain_limit,d.token_hash FROM stations s JOIN esp_devices d ON d.station_id=s.id WHERE s.id=? AND s.source='esp32'",(sid,)).fetchone()
        if not station or not hmac.compare_digest(candidate,station['token_hash']): raise HTTPException(401,'Ongeldige device-token')
        if not station['enabled']: raise HTTPException(403,'Station uitgeschakeld')
        ts=int(time.time())
        values=(body.wind,body.gust,body.direction,body.rainrate,body.precipitation,body.temp,body.humidity,body.pressure)
        c.execute('INSERT INTO readings(station_id,ts,wind,gust,direction,rainrate,precipitation,temp,humidity,pressure) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(station_id,ts) DO UPDATE SET wind=excluded.wind,gust=excluded.gust,direction=excluded.direction,rainrate=excluded.rainrate,precipitation=excluded.precipitation,temp=excluded.temp,humidity=excluded.humidity,pressure=excluded.pressure',(sid,ts,*values))
        c.execute('UPDATE stations SET last_error=NULL WHERE id=?',(sid,))
        evaluate(c,sid,'windstoot',body.gust,station['wind_limit'],ts)
        if body.rainrate is not None: evaluate(c,sid,'neerslag',body.rainrate,station['rain_limit'],ts)
    return {'ok':True,'received_at':ts}

@app.get('/api/stations')
def stations(req:Request):
    user=guard(req)
    with db() as c:
        result=[]
        for s in c.execute('SELECT id,name,wind_limit,rain_limit,enabled,last_error,source FROM stations ORDER BY id').fetchall():
            if not can_access(c,user,s['id']): continue
            latest=c.execute('SELECT ts,wind,gust,direction,rainrate,precipitation,temp,humidity,pressure FROM readings WHERE station_id=? ORDER BY ts DESC LIMIT 1',(s['id'],)).fetchone()
            result.append({**dict(s),'latest':dict(latest) if latest else None})
        return result
@app.get('/api/history/{sid}')
def history(sid:int,req:Request,hours:int=24):
    station_guard(req,sid)
    if hours not in (1,6,24,168): raise HTTPException(400,'Ongeldige periode')
    with db() as c:
        return [dict(r) for r in c.execute('SELECT ts,wind,gust,rainrate,precipitation,temp FROM readings WHERE station_id=? AND ts>=? ORDER BY ts LIMIT 1200',(sid,int(time.time())-hours*3600)).fetchall()]
@app.get('/api/alerts')
def alerts(req:Request):
    user=guard(req)
    with db() as c:
        return [dict(r) for r in c.execute('SELECT a.*,s.name FROM alerts a JOIN stations s ON s.id=a.station_id ORDER BY a.started DESC LIMIT 100').fetchall() if can_access(c,user,r['station_id'])]
@app.get('/api/export/{sid}')
def export(sid:int,req:Request,hours:int=24,unit:str='km/h'):
    station_guard(req,sid)
    if hours<1 or hours>720: raise HTTPException(400,'Ongeldige periode')
    factors={'km/h':1.0,'m/s':1/3.6,'kn':1/1.852,'mph':1/1.609344}
    if unit not in factors: raise HTTPException(400,'Ongeldige windeenheid')
    import csv,io
    from zoneinfo import ZoneInfo
    from fastapi.responses import Response
    with db() as c:
        rows=c.execute('SELECT ts,wind,gust,direction,rainrate,precipitation,temp,humidity,pressure FROM readings WHERE station_id=? AND ts>=? ORDER BY ts',(sid,int(time.time())-hours*3600)).fetchall()
    buf=io.StringIO();writer=csv.writer(buf,delimiter=';')
    writer.writerow(['Datum (Europe/Amsterdam)','Tijd (Europe/Amsterdam)','Tijdzone','unix_timestamp_utc',f'wind ({unit})',f'windstoot ({unit})','windrichting (graden)','regenintensiteit (mm/u)','neerslag (mm)','temperatuur (C)','luchtvochtigheid (%)','luchtdruk (hPa)'])
    for r in rows:
        dt=datetime.fromtimestamp(r['ts'],tz=ZoneInfo('Europe/Amsterdam'))
        def converted(value): return round(value*factors[unit],2) if value is not None else ''
        writer.writerow([dt.strftime('%d-%m-%Y'),dt.strftime('%H:%M:%S'),dt.strftime('%z'),r['ts'],converted(r['wind']),converted(r['gust']),r['direction'],r['rainrate'],r['precipitation'],r['temp'],r['humidity'],r['pressure']])
    return Response('\ufeff'+buf.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="station-{sid}-{unit.replace("/", "-")}.csv"'})
@app.get('/assets/{filename}')
def brand_asset(filename:str):
    from fastapi.responses import FileResponse
    allowed={'critical-connections-logo.jpg':'image/jpeg','logo-small.png':'image/png','favicon.png':'image/png'}
    if filename not in allowed: raise HTTPException(404,'Bestand niet gevonden')
    return FileResponse(Path(__file__).with_name('assets')/filename,media_type=allowed[filename])

@app.get('/static.js')
def js():
    from fastapi.responses import Response
    return Response(Path(__file__).with_name('static.js').read_text(),media_type='application/javascript')
