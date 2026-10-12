from pathlib import Path
import json,uuid
from pdfmanager.dms.recovery import data_dir
from pdfmanager.licensing import secure_storage
from pdfmanager.remote.protocol import config_check

def load_config():
    installed=Path(__file__).resolve().parents[1]/'resources'/'management.json'
    path=installed
    if not path.is_file():return None
    if path.stat().st_size>65536:raise ValueError('Konfiguracja administratora jest zbyt duża.')
    return config_check(json.loads(path.read_text(encoding='utf-8')))

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
