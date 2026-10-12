"""Worker progress and cooperative cancellation without terminating threads."""
from PySide6.QtCore import QThread,Signal,QTimer,Qt
from PySide6.QtWidgets import QProgressDialog,QMessageBox
from pdfmanager.dms.jobs import JobControl,execute,Cancelled

class Worker(QThread):
    succeeded=Signal(object);failed=Signal(str);progress=Signal(int,int,str);cancelled=Signal()
    def __init__(self,function,parent):
        super().__init__(parent);self.function=function;self.control=JobControl(self.progress.emit)
    def run(self):
        try:self.succeeded.emit(execute(self.function,self.control))
        except Cancelled:self.cancelled.emit()
        except Exception as exc:self.failed.emit(str(exc))

class BusyDialog(QProgressDialog):
    def reject(self):self.cancel()
    def closeEvent(self,event):self.cancel();event.ignore()

def run_job(parent,title,function,on_success=None):
    dialog=BusyDialog(title,'Anuluj',0,0,parent);dialog.setWindowTitle(title)
    dialog.setAutoClose(False);dialog.setAutoReset(False);dialog.setWindowModality(Qt.ApplicationModal)
    worker=Worker(function,parent);outcome={}
    def cancel():
        worker.control.cancelled.set();dialog.setLabelText('Anulowanie po zakończeniu bieżącego kroku…');dialog.setCancelButton(None)
        dialog.show()
    dialog.canceled.connect(cancel)
    def progress(done,total,label):
        if total:dialog.setRange(0,total);dialog.setValue(done)
        if label:dialog.setLabelText(label)
    worker.progress.connect(progress)
    worker.succeeded.connect(lambda result:outcome.update(result=result))
    worker.failed.connect(lambda error:outcome.update(error=error))
    worker.cancelled.connect(lambda:outcome.update(cancelled=True))
    worker.finished.connect(dialog.accept);QTimer.singleShot(0,worker.start)
    while not worker.isFinished():dialog.exec()
    worker.wait();worker.deleteLater();dialog.deleteLater()
    if 'error' in outcome:QMessageBox.critical(parent,title,outcome['error']);return
    if outcome.get('cancelled'):
        parent.window().statusBar().showMessage('Operacja anulowana; ukończone pliki pozostają zapisane.',5000) if hasattr(parent.window(),'statusBar') else None
        return
    if on_success:on_success(outcome.get('result'))
