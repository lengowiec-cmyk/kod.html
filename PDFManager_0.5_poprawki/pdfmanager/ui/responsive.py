"""Wait for bounded work without blocking Qt's event loop or editing reentrantly."""
from PySide6.QtCore import QThread,QEventLoop,Qt
from PySide6.QtWidgets import QApplication
from pdfmanager.ui.background_job import Worker,BusyDialog

_busy=0
def busy():return bool(_busy)

def run(function,parent=None,title='Przetwarzanie dokumentu…'):
    app=QApplication.instance()
    if not isinstance(app,QApplication) or QThread.currentThread()!=app.thread():return function()
    if busy():raise RuntimeError('Trwa inna operacja na dokumencie. Poczekaj na jej zakończenie.')
    global _busy
    _busy+=1
    parent=parent or app.activeWindow()
    dialog=BusyDialog(title,'Anuluj',0,0,parent);dialog.setWindowTitle(title)
    dialog.setAutoClose(False);dialog.setAutoReset(False);dialog.setWindowModality(Qt.ApplicationModal)
    loop=QEventLoop();outcome={}
    def work():
        try:return True,function()
        except Exception as exc:return False,exc
    worker=Worker(work,parent or dialog)
    worker.succeeded.connect(lambda value:outcome.update(value=value))
    worker.finished.connect(loop.quit)
    def cancel():
        worker.control.cancelled.set();dialog.setLabelText('Anulowanie po zakończeniu bezpiecznego kroku…');dialog.setCancelButton(None);dialog.show()
    dialog.canceled.connect(cancel)
    try:
        dialog.show();worker.start();loop.exec();worker.wait()
        ok,value=outcome['value']
        if not ok:raise value
        return value
    finally:
        dialog.hide();dialog.deleteLater();worker.deleteLater();_busy-=1

# A collection of open tabs must not launch one native renderer per tab.
from threading import BoundedSemaphore
_preview_slot=BoundedSemaphore(1)
def preview_work(function):
    from pdfmanager.dms.jobs import checkpoint
    while not _preview_slot.acquire(timeout=.1):checkpoint()
    try:checkpoint();return function()
    finally:_preview_slot.release()
