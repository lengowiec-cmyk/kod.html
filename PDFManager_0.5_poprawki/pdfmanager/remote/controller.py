"""Qt controller: background checks, embedded enrollment and safe-exit updates."""
from pathlib import Path
import json,sys,os,shutil
from PySide6.QtCore import QObject,QTimer
from PySide6.QtWidgets import QMessageBox
from pdfmanager.remote.storage import load_config,RemoteState
from pdfmanager.remote.client import ControlClient
from pdfmanager.dms.recovery import data_dir
from pdfmanager.ui.background_job import Worker
from pdfmanager.pdf_engine.io_utils import atomic_write_bytes

class RemoteController(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.busy=False;self.pending=None;self.closing=False;self.helper_started=False
        self.timer=QTimer(self);self.timer.setInterval(60000);self.timer.timeout.connect(self.check);self.timer.start()
        QTimer.singleShot(1000,self.check)
    def check(self):
        if self.busy or self.closing:return
        try:config=load_config()
        except Exception as exc:self.window.statusBar().showMessage('Konfiguracja administratora: '+str(exc),10000);return
        if not config:return
        self.busy=True
        def work():
            client=ControlClient(config);envelope=client.poll()
            path=client.download(envelope,data_dir()/'updates') if envelope else None
            return envelope,str(path) if path else None
        self.worker=Worker(work,self);self.worker.succeeded.connect(self.received)
        self.worker.failed.connect(lambda error:self.window.statusBar().showMessage('Połączenie administracyjne: '+error,10000))
        self.worker.finished.connect(lambda:setattr(self,'busy',False));self.worker.finished.connect(self.worker.deleteLater);self.worker.start()
    def received(self,result):
        envelope,path=result
        if envelope and not path:self.pending=None
        if path:
            self.pending={'envelope':envelope,'installer':path}
            self.window.statusBar().showMessage('Podpisana aktualizacja pobrana. Zostanie zainstalowana po zwykłym zamknięciu programu.',15000)
        if RemoteState().blocked():QTimer.singleShot(0,self.window._enforce_license_block)
    def prepare_close(self,event):
        self.closing=True;self.timer.stop()
        if self.busy:
            self.worker.control.cancelled.set();event.ignore()
            if not getattr(self,'wait_close',False):self.wait_close=True;self.worker.finished.connect(self.window.close)
            return False
        return True
    def finish_close(self):
        if not self.pending or self.helper_started:return
        if sys.platform!='win32' or not getattr(sys,'frozen',False):return
        root=Path(sys.executable).resolve().parent;helper=root/'PDFManagerUpdater.exe'
        if not helper.is_file():return
        import tempfile,subprocess
        folder=Path(tempfile.mkdtemp(prefix='helper-',dir=data_dir()/'updates'));copy=folder/'PDFManagerUpdater.exe';shutil.copy2(helper,copy)
        plan={**self.pending,'root':str(root),'pid':os.getpid()};path=folder/'plan.json';atomic_write_bytes(path,json.dumps(plan,ensure_ascii=False).encode())
        subprocess.Popen([str(copy),str(path)],cwd=str(folder));self.helper_started=True
