"""Owner prepares a complete employee ZIP with a signed, pre-bound config."""
from pathlib import Path
import json,uuid,os,secrets,zipfile
from cryptography.hazmat.primitives import serialization
from pdfmanager.remote.protocol import sign,canonical,config_check,version
from pdfmanager.remote.shared import MARKER,check_signature,verify_folder,is_link,scoped_target
from pdfmanager.remote import APP_VERSION
from pdfmanager.security.cache import CacheCipher
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

SETTINGS='simple-connection.json'

def automatic_unlock(workspace):
    cipher=CacheCipher(workspace.folder);credential=workspace.folder/'automatic-key.enc'
    if credential.exists():password=cipher.decrypt(credential.read_text(encoding='utf-8'))
    else:
        if (workspace.folder/'management-signing.pem').exists():raise ValueError('Istniejący klucz wymaga jednorazowego odblokowania hasłem w ustawieniach zaawansowanych.')
        password=secrets.token_urlsafe(48)
    workspace.unlock(password)
    if not credential.exists():atomic_write_bytes(credential,cipher.encrypt(password).encode())
    return password

def remember_password(workspace,password):
    cipher=CacheCipher(workspace.folder);atomic_write_bytes(workspace.folder/'automatic-key.enc',cipher.encrypt(password).encode())

def attach_shared_folder(workspace,parent=None):
    if not workspace.key:raise ValueError('Program matka nie ma odblokowanego klucza.')
    settings=workspace.folder/SETTINGS
    saved=json.loads(settings.read_text()) if settings.exists() else {}
    identity=saved.get('workspace') or str(uuid.uuid4())
    if parent is None:
        if not saved.get('folder'):raise ValueError('Wybierz wspólny folder Google Drive.')
        folder=Path(saved['folder'])
        if not folder.is_dir():raise OSError('Wspólny folder jest niedostępny. Uruchom Google Drive i ponów.')
    else:
        parent=Path(parent)
        if not parent.is_dir():raise ValueError('Wybierz istniejący wspólny folder.')
        folder=parent/('PDFManager-Polaczenie-'+identity[:8])
        if is_link(folder) or folder.resolve().parent!=parent.resolve():raise ValueError('Nieprawidłowy folder połączenia. Nic nie zapisano.')
        folder.mkdir(exist_ok=True)
    if is_link(folder):raise ValueError('Folder połączenia nie może być odsyłaczem.')
    if not (folder/MARKER).exists() and any(folder.iterdir()):raise ValueError('Folder nie jest pusty i nie ma znacznika połączenia. Niczego nie nadpisano.')
    pem=workspace.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    config=config_check({'schema':1,'public_key':pem,'transport':'shared_folder','base_url':'pdm-share://'+identity,'folder_hint':str(folder.resolve())})
    if (folder/MARKER).exists() and not verify_folder(folder,config):raise ValueError('Ten folder należy do innego połączenia. Nie nadpisano go.')
    if is_link(folder/MARKER):raise ValueError('Nieprawidłowy znacznik kanału.')
    for name in ('control','updates','hello'):
        path=folder/name
        if is_link(path) or path.resolve().parent!=folder.resolve():raise ValueError('Nieprawidłowy katalog kanału.')
        path.mkdir(exist_ok=True)
    marker={'schema':1,'purpose':'shared-root','workspace':identity,'public_key':pem}
    atomic_write_bytes(folder/MARKER,canonical(sign(marker,workspace.key)))
    atomic_write_bytes(settings,canonical({'workspace':identity,'folder':str(folder.resolve())}))
    workspace.web=folder;return config

def ingest_hellos(workspace):
    folder=workspace.web/'hello'
    if not folder.is_dir():return 0
    scoped_target(workspace.web,'hello','check.json')
    accepted=0
    with workspace.lock:
        devices=workspace.devices()
        for index,path in enumerate(folder.glob('*.json')):
            if index>=1000:break
            try:
                if is_link(path):continue
                with path.open('rb') as stream:raw=stream.read(2049)
                if len(raw)>2048:continue
                item=json.loads(raw);device=str(uuid.UUID(item['device']));version(item['version'])
                if path.stem!=device:continue
                if device not in devices:
                    if len(devices)>=1000:break
                    devices[device]={'label':'Komputer '+device[:8],'sequence':0,'blocked':False}
                row=devices[device];row.update(version=item['version'],last_seen=item.get('seen',''));accepted+=1
            except (OSError,ValueError,KeyError,TypeError):continue
        workspace.save_devices(devices)
        for device,row in devices.items():
            target=scoped_target(workspace.web,'control',device+'.json')
            if row['sequence']==0 and not target.exists():workspace.command(device,False)
    return accepted

def factory_envelope(config,key):return sign({'schema':1,'purpose':'deployment','config':config_check(config)},key)
def verify_factory(envelope):
    payload=envelope['payload'];config=config_check(payload['config']);check_signature(envelope,config['public_key'],'deployment');return config

def prepare_package(source,destination,config,key):
    """Never writes inside the supplied build; packages a fresh, complete copy."""
    source=Path(source).resolve();destination=Path(destination)
    if destination.exists():raise FileExistsError('Paczka już istnieje. Wybierz nową nazwę.')
    if destination.resolve().is_relative_to(source):raise ValueError('Zapisz paczkę poza folderem aplikacji.')
    manifest=source/'PDFManager-build.json'
    if not manifest.is_file() or manifest.stat().st_size>4096:raise ValueError('Wybierz folder dist/PDFManager zbudowany skryptem wersji 0.9 lub nowszej.')
    data=json.loads(manifest.read_text())
    if data.get('schema')!=1 or data.get('platform')!='windows':raise ValueError('Nieprawidłowa informacja o kompilacji Windows.')
    if version(data['version'])<(0,9,0):raise ValueError('Ten program nie obsługuje przygotowanego połączenia.')
    for name in ('PDFManager.exe','PDFManagerUpdater.exe','CLI/PDFManagerCLI.exe'):
        path=source/name
        if not path.is_file():raise ValueError('Brakuje '+name+' — zbuduj pełny folder programu.')
        with path.open('rb') as stream:
            if stream.read(2)!=b'MZ':raise ValueError('Nieprawidłowy plik Windows '+name)
    envelope=factory_envelope(config,key)
    verify_factory(envelope)
    import tempfile
    fd,tempname=tempfile.mkstemp(prefix='PDFManager-paczka-',suffix='.zip',dir=destination.parent);os.close(fd);temporary=Path(tempname)
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in source.rglob('*'):
                from pdfmanager.dms.jobs import checkpoint
                checkpoint()
                if is_link(path) or not path.resolve().is_relative_to(source):raise ValueError('Folder programu zawiera odsyłacz.')
                if not path.is_file():continue
                relative=path.relative_to(source)
                if relative.as_posix()=='management.json':continue
                if path.name.lower() in ('management-signing.pem','automatic-key.enc','cache-key.bin','devices.json','simple-connection.json','paired-config.enc','state.dat') or path.suffix.lower() in ('.pfx','.p12','.key'):raise ValueError('W folderze programu znaleziono prywatny plik. Nie utworzono paczki.')
                if path.suffix.lower()=='.pem' and b'PRIVATE KEY' in path.read_bytes():raise ValueError('Nie można wysłać klucza prywatnego.')
                archive.write(path,Path('PDFManager')/relative)
            archive.writestr('PDFManager/management.json',canonical(envelope))
            archive.writestr('URUCHOMIENIE.txt','Rozpakuj cały folder PDFManager na lokalnym dysku komputera i uruchom PDFManager.exe.\nPołączenie z firmą jest już przygotowane. Nie wpisuj kodu parowania.\nGoogle Drive musi synchronizować firmowy folder, do którego masz dostęp.\nNie przenoś samego EXE bez pozostałych plików. Nie uruchamiaj programu ze współdzielonego folderu Drive.\nDokumenty trzymaj oddzielnie od folderu programu.\n')
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip():raise ValueError('Paczka nie przeszła kontroli integralności.')
        temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
    return destination
