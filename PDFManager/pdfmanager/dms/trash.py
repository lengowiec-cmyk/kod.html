"""Application trash with reversible restore; nothing is deleted permanently."""
from pathlib import Path
import json
import uuid
from .recovery import data_dir
from .files import transfer_file
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

class Trash:
    def __init__(self,root=None):self.root=Path(root) if root else data_dir()/'trash';self.root.mkdir(parents=True,exist_ok=True)
    def put(self,path):
        path=Path(path).resolve();folder=self.root/uuid.uuid4().hex;folder.mkdir()
        try:
            atomic_write_bytes(folder/'info.json',json.dumps({'source':str(path),'name':path.name},ensure_ascii=False).encode('utf-8'))
            transfer_file(path,folder/path.name,move=True)
        except Exception:
            # Keep any completed copy when source removal failed.
            if not (folder/path.name).exists():
                import shutil
                shutil.rmtree(folder)
            raise
        return folder
    def entries(self):
        result=[]
        for info in self.root.glob('*/info.json'):
            try:
                data=json.loads(info.read_text(encoding='utf-8'));item=info.parent/data['name']
                if item.is_file() and item.parent==info.parent:result.append((info.parent,Path(data['source']),item))
            except (ValueError,KeyError,OSError):continue
        return result
    def restore(self,folder,destination=None):
        entry=next(e for e in self.entries() if e[0]==Path(folder))
        target=Path(destination) if destination else entry[1]
        target.parent.mkdir(parents=True,exist_ok=True);transfer_file(entry[2],target,move=True)
        import shutil
        shutil.rmtree(entry[0]);return target
