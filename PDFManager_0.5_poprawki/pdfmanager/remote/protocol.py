"""Shared public protocol. Client never contains an administrator private key."""
import base64,json,re
from datetime import datetime,timezone
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_MANIFEST=65536
MAX_INSTALLER=512*1024*1024

def canonical(payload):return json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def stamp():return datetime.now(timezone.utc).timestamp()
def sign(payload,key):return {'payload':payload,'signature':base64.b64encode(key.sign(canonical(payload))).decode()}
def public_key(pem):
    key=load_pem_public_key(pem.encode())
    if not isinstance(key,Ed25519PublicKey):raise ValueError('Wymagany jest klucz publiczny Ed25519.')
    return key

def origin(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:raise ValueError('Wymagany jest adres HTTPS bez danych logowania i fragmentu.')
    return parsed.hostname.lower(),parsed.port or 443

def config_check(data):
    if data.get('schema')!=1:raise ValueError('Nieznany format konfiguracji administratora.')
    public_key(data['public_key']);origin(data['base_url'])
    parsed=urlsplit(data['base_url'])
    if parsed.query:raise ValueError('Adres bazowy nie może zawierać parametrów.')
    if len(data.get('extra_ca_pem',''))>32768:raise ValueError('Certyfikat CA jest zbyt duży.')
    return {'schema':1,'public_key':data['public_key'],'base_url':data['base_url'].rstrip('/'),'extra_ca_pem':data.get('extra_ca_pem','')}

def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,4}\.\d{1,4}\.\d{1,4}',value):raise ValueError('Wersja musi mieć postać 0.8.0.')
    return tuple(map(int,value.split('.')))

def verify(envelope,pem,device,*,purpose='control',now=None):
    if not isinstance(envelope,dict) or set(envelope)!={'payload','signature'}:raise ValueError('Nieprawidłowa koperta polecenia.')
    payload=envelope['payload']
    if len(canonical(payload))>MAX_MANIFEST:raise ValueError('Polecenie jest zbyt duże.')
    public_key(pem).verify(base64.b64decode(envelope['signature'],validate=True),canonical(payload))
    if payload.get('schema')!=1 or payload.get('purpose')!=purpose or payload.get('device')!=device:raise ValueError('Polecenie nie jest przeznaczone dla tej instalacji.')
    current=stamp() if now is None else now
    issued=payload.get('issued');expires=payload.get('expires')
    if type(issued) not in (float,int) or type(expires) not in (float,int) or not issued<=current+300 or not current<expires or not 0<expires-issued<=90*86400:raise ValueError('Polecenie wygasło lub ma nieprawidłowy czas.')
    if purpose=='control':
        if type(payload.get('sequence')) is not int or payload['sequence']<1 or type(payload.get('blocked')) is not bool:raise ValueError('Nieprawidłowy numer polecenia lub stan blokady.')
        generation=payload.get('block_generation',payload['sequence'])
        if type(generation) is not int or not 0<=generation<=payload['sequence'] or (payload['blocked'] and generation<1):raise ValueError('Nieprawidłowa generacja blokady.')
        if len(str(payload.get('reason','')))>500:raise ValueError('Komunikat jest zbyt długi.')
        update=payload.get('update')
        if update:
            version(update['version']);origin(update['url'])
            if not re.fullmatch('[a-f0-9]{64}',update.get('sha256','')) or type(update.get('size')) is not int or not 1<=update['size']<=MAX_INSTALLER:raise ValueError('Nieprawidłowe dane aktualizacji.')
    elif purpose=='activation':
        if type(payload.get('days')) is not int or not 1<=payload['days']<=3650 or not re.fullmatch('[a-f0-9]{32}',payload.get('nonce','')):raise ValueError('Nieprawidłowy kod dostępu.')
    return payload

def activation_code(payload,key):
    encoded=base64.urlsafe_b64encode(canonical(sign(payload,key))).decode().rstrip('=')
    return 'PDMR1.'+encoded

def verify_activation(code,config,device,now=None):
    raw=code.strip().removeprefix('PDMR1.')
    if len(raw)>20000:raise ValueError('Kod jest zbyt długi.')
    envelope=json.loads(base64.b64decode(raw+'='*((-len(raw))%4),altchars=b'-_',validate=True))
    return verify(envelope,config['public_key'],device,purpose='activation',now=now)
