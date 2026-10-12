"""Encrypted durable outbox and non-overwriting Drive versions.

Reservations are advisory; Google Drive appProperties do not provide an atomic
mutex. Version publication creates a new file, never overwrites the original.
"""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json, uuid, tempfile
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from pdfmanager.drive.api_client import DriveFile, DriveApiError, DriveConflictError, DRIVE_FIELDS, PDF_MIME_TYPE, _parse_file
from pdfmanager.dms.recovery import data_dir
from pdfmanager.security.cache import CacheCipher, crypt_file
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

LEASE_KEY='pdfmanagerReservation'

def now():return datetime.now(timezone.utc)
def quote(value):return str(value).replace('\\','\\\\').replace("'","\\'")

class TeamDrive:
    def __init__(self,client):self.client=client;self.service=client._service
    def reservation(self,file_id):
        data=self.service.files().get(fileId=file_id,fields='appProperties',supportsAllDrives=True).execute()
        try:
            item=json.loads(data.get('appProperties',{}).get(LEASE_KEY,'{}'))
            if item and float(item['e'])>now().timestamp():return {'owner':item['o'],'token':item['t'],'until':datetime.fromtimestamp(item['e'],timezone.utc).isoformat()}
        except (ValueError,KeyError,TypeError):pass
        return None
    def reserve(self,file_id,owner,token):
        current=self.reservation(file_id)
        if current and current.get('token')!=token:raise DriveApiError(f"Dokument edytuje {current.get('owner','inny pracownik')} do {current.get('until')}.")
        # Keep the property below Drive's 124-byte key+value limit.
        item={'o':owner[:24],'t':token,'e':int((now()+timedelta(minutes=15)).timestamp())}
        payload=json.dumps(item,separators=(',',':'),ensure_ascii=False)
        while len((LEASE_KEY+payload).encode())>124 and item['o']:
            item['o']=item['o'][:-1];payload=json.dumps(item,separators=(',',':'),ensure_ascii=False)
        if not item['o']:raise ValueError('Nieprawidłowa rezerwacja.')
        self.service.files().update(fileId=file_id,body={'appProperties':{LEASE_KEY:payload}},fields='id',supportsAllDrives=True).execute()
        verified=self.reservation(file_id)
        if not verified or verified.get('token')!=token:raise DriveApiError('Rezerwacja została zmieniona. Otwórz dokument ponownie.')
        return verified
    def release(self,file_id,token):
        current=self.reservation(file_id)
        if current and current.get('token')==token:self.service.files().update(fileId=file_id,body={'appProperties':{LEASE_KEY:None}},fields='id',supportsAllDrives=True).execute()
    def versions(self,file_id):
        files=[];token=None
        for _ in range(50):
            kwargs={'q':f"appProperties has {{ key='pdfmanagerOrigin' and value='{quote(file_id)}' }} and trashed=false",'fields':f'nextPageToken,files({DRIVE_FIELDS},appProperties,lastModifyingUser(displayName))','pageSize':100,'orderBy':'createdTime desc','supportsAllDrives':True,'includeItemsFromAllDrives':True}
            if token:kwargs['pageToken']=token
            data=self.service.files().list(**kwargs).execute();files.extend(data.get('files',[]));token=data.get('nextPageToken')
            if not token:return files
        raise DriveApiError('Historia przekracza limit 5000 wersji.')
    def revisions(self,file_id):
        result=self.service.revisions().list(fileId=file_id,fields='revisions(id,modifiedTime,lastModifyingUser(displayName),size)',pageSize=1000).execute()
        return result.get('revisions',[])
    def download_revision(self,file_id,revision_id,path):
        from pdfmanager.drive.api_client import download_request
        request=self.service.revisions().get(fileId=file_id,revisionId=revision_id,alt='media')
        download_request(request,path)
    def publish(self,path,baseline,owner,job_id):
        # A retry first locates a previous create, so a lost HTTP response does
        # not create a duplicate on the next attempt. No automatic transport retries.
        q=f"appProperties has {{ key='pdfmanagerJob' and value='{quote(job_id)}' }} and trashed=false"
        found=self.service.files().list(q=q,fields=f'files({DRIVE_FIELDS})',pageSize=2,supportsAllDrives=True,includeItemsFromAllDrives=True).execute().get('files',[])
        if found:return _parse_file(found[0])
        current=self.client.get_metadata(baseline.id)
        changed=(current.md5_checksum!=baseline.md5_checksum) if current.md5_checksum and baseline.md5_checksum else current.modified_time!=baseline.modified_time
        if changed:raise DriveConflictError(baseline.id,current)
        stamp=now().strftime('%Y%m%d-%H%M%S')
        from pdfmanager.dms.transport import component
        name=f'{component(Path(baseline.name).stem)}_wersja_{stamp}_{component(owner)}_{job_id[:8]}.pdf'
        body={'name':name,'appProperties':{'pdfmanagerOrigin':baseline.id,'pdfmanagerJob':job_id,'pdfmanagerOwner':owner[:40]}}
        if baseline.parents:body['parents']=[baseline.parents[0]]
        media=MediaFileUpload(str(path),mimetype=PDF_MIME_TYPE,resumable=True)
        try:data=self.service.files().create(body=body,media_body=media,fields=DRIVE_FIELDS,supportsAllDrives=True).execute()
        except HttpError as exc:raise DriveApiError('Wysyłanie nie zostało potwierdzone. Kolejka zachowa kopię i sprawdzi ponownie przed ponowieniem.') from exc
        return _parse_file(data)

class Outbox:
    def __init__(self,folder=None):
        self.folder=Path(folder or data_dir()/'drive_outbox');self.folder.mkdir(parents=True,exist_ok=True)
        self.cipher=CacheCipher(self.folder)
    def items(self):
        items=[]
        for p in sorted(self.folder.glob('*.json')):
            if p.stat().st_size>100000:raise ValueError('Nieprawidłowy wpis kolejki.')
            item=json.loads(self.cipher.decrypt(p.read_text()));item['job']=p.stem;items.append(item)
        return items
    def write(self,job,item):
        if not uuid.UUID(job):raise ValueError('Nieprawidłowe zadanie.')
        atomic_write_bytes(self.folder/f'{job}.json',self.cipher.encrypt(json.dumps(item,ensure_ascii=False)).encode())
    def enqueue(self,path,baseline,owner,account=''):
        if not account:raise ValueError('Nie potwierdzono konta Google. Połącz się z Drive przed dodaniem do kolejki.')
        if not owner.strip():raise ValueError('Uzupełnij nazwę pracownika.')
        job=str(uuid.uuid4());crypt_file(path,self.folder/f'{job}.pdm')
        item={'baseline':asdict(baseline),'owner':owner,'account':account,'state':'Oczekuje na wysłanie','created':now().isoformat(),'error':''}
        self.write(job,item);return job
    def process(self,team,account):
        with self._lock():return self._process(team,account)
    def _lock(self):
        from contextlib import contextmanager
        @contextmanager
        def lock():
            with (self.folder/'outbox.lock').open('a+b') as stream:
                if __import__('os').name=='nt':
                    import msvcrt
                    stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                try:yield
                finally:
                    if __import__('os').name=='nt':stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                    else:fcntl.flock(stream,fcntl.LOCK_UN)
        return lock()
    def _process(self,team,account):
        outcomes=[]
        for item in self.items():
            from pdfmanager.dms.jobs import checkpoint
            checkpoint()
            if item['state']=='Zapisano na Google Drive' or item['state']=='Konflikt':continue
            if not account or item.get('account')!=account:continue
            job=item.pop('job');baseline=DriveFile(**{**item['baseline'],'parents':tuple(item['baseline']['parents'])})
            try:
                with tempfile.TemporaryDirectory(prefix='pdfmanager-outbox-') as temp:
                    path=Path(temp)/'document.pdf';crypt_file(self.folder/f'{job}.pdm',path,decrypt=True)
                    result=team.publish(path,baseline,item['owner'],job)
                item.update(state='Zapisano na Google Drive',result=asdict(result),error='')
            except DriveConflictError as exc:item.update(state='Konflikt',error=str(exc))
            except Exception as exc:item.update(state='Oczekuje na wysłanie',error=str(exc)[:1000])
            self.write(job,item);outcomes.append({'job':job,**item})
        return outcomes
    def remove(self,job):
        uuid.UUID(job)
        with self._lock():
            (self.folder/f'{job}.json').unlink(missing_ok=True);(self.folder/f'{job}.pdm').unlink(missing_ok=True)
    def recover(self,job,target):
        uuid.UUID(job)
        if Path(target).exists():raise FileExistsError('Plik wynikowy już istnieje.')
        crypt_file(self.folder/f'{job}.pdm',target,decrypt=True)
