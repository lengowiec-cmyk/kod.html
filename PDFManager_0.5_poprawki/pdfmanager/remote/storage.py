from pathlib import Path
import json,uuid,sys
from pdfmanager.dms.recovery import data_dir
from pdfmanager.licensing import secure_storage
from pdfmanager.remote.protocol import config_check

def factory_path():
    if getattr(sys,'frozen',False):
        root=Path(sys.executable).resolve().parent
        if root.name=='CLI':root=root.parent
        path=root/'management.json'
        if path.exists():return path,True
    return Path(__file__).resolve().parents[1]/'resources'/'management.json',False

def load_config(*,factory=None,folder=None):
    """Bootstrap from owner's package once; pin authority in local DPAPI storage.

    A copied update helper uses the saved pairing without a sidecar in its temp dir.
    The initial package is the trust boundary and must come from the owner.
    """
    from pdfmanager.security.cache import CacheCipher
    from pdfmanager.remote.deployment import verify_factory
    from pdfmanager.remote.shared import is_link
    from pdfmanager.pdf_engine.io_utils import atomic_write_bytes
    path,signed=(Path(factory),True) if factory is not None else factory_path()
    folder=Path(folder) if folder is not None else data_dir()/'management'
    saved=folder/'paired-config.enc'
    if not saved.exists() and not path.exists():return None
    with RemoteState(folder)._lock():
        cipher=CacheCipher(folder);previous=None
        if is_link(saved) or is_link(path):raise ValueError('Konfiguracja połączenia nie może być odsyłaczem.')
        if saved.exists():
            if saved.stat().st_size>150000:raise ValueError('Zapisana konfiguracja jest zbyt duża.')
            previous=config_check(json.loads(cipher.decrypt(saved.read_text(encoding='utf-8'))))
        if not path.exists():return previous
        with path.open('rb') as stream:raw=stream.read(65537)
        if len(raw)>65536:raise ValueError('Konfiguracja administratora jest zbyt duża.')
        data=json.loads(raw)
        config=verify_factory(data) if signed or 'payload' in data else config_check(data)
        if previous and previous['public_key']!=config['public_key']:raise ValueError('Próba zmiany właściciela połączenia została zablokowana.')
        if previous!=config:atomic_write_bytes(saved,cipher.encrypt(json.dumps(config)).encode())
        return config

class RemoteState:
    def __init__(self,folder=None):
        self.folder=Path(folder or data_dir()/'management');self.folder.mkdir(parents=True,exist_ok=True)
        self.registry=r'Software\PDFManager\Management'
    def _lock(self):
        from contextlib import contextmanager
        import os,time
        @contextmanager
        def lock():
            with (self.folder/'state.lock').open('a+b') as stream:
                if stream.seek(0,2)==0:stream.write(b'0');stream.flush()
                deadline=time.monotonic()+5
                while True:
                    try:
                        if os.name=='nt':
                            import msvcrt
                            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                        else:
                            import fcntl
                            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic()>deadline:raise TimeoutError('Stan połączenia jest aktualizowany przez drugi proces.')
                        time.sleep(.01)
                try:yield
                finally:
                    if os.name=='nt':stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                    else:fcntl.flock(stream,fcntl.LOCK_UN)
        return lock()
    def _read(self):
        records=secure_storage.read_dual(self.registry,'state',self.folder/'state.dat')
        if not records:return {'sequence':0,'blocked':False,'released':0,'device':str(uuid.uuid4())}
        state=max(records,key=lambda r:r.get('sequence',0)).copy();state['released']=max(r.get('released',0) for r in records)
        return state
    def read(self):
        with self._lock():return self._read()
    def _write(self,state):secure_storage.write_dual(self.registry,'state',self.folder/'state.dat',state)
    def device(self):
        with self._lock():
            state=self._read();self._write(state);return state['device']
    def apply(self,payload):
        with self._lock():
            state=self._read()
            if payload['sequence']<=state['sequence']:return False
            state.update(sequence=payload['sequence'],blocked=payload['blocked'],reason=payload.get('reason',''),issued=payload['issued'])
            if payload['blocked']:state['block_sequence']=payload.get('block_generation',payload['sequence'])
            self._write(state);return True
    def blocked(self):
        state=self.read();return state.get('blocked',False) and state.get('block_sequence',0)>state.get('released',0)
    def release(self):
        with self._lock():
            state=self._read();state['released']=max(state.get('released',0),state.get('block_sequence',0));self._write(state)
