"""Cooperative cancellation: never interrupts an atomic document commit."""
from threading import Event, local
import subprocess
import time
_state=local()
class Cancelled(Exception):pass
class JobControl:
    def __init__(self,report=None):self.cancelled=Event();self.report=report or (lambda done,total,label:None)
    def checkpoint(self,done=0,total=0,label=''):
        if self.cancelled.is_set():raise Cancelled('Operacja anulowana. Ukończone pliki pozostają zapisane.')
        self.report(done,total,label)

def checkpoint(done=0,total=0,label=''):
    control=getattr(_state,'control',None)
    if control:control.checkpoint(done,total,label)

def execute(function,control):
    _state.control=control
    try:return function()
    finally:_state.control=None

def run_process(command,timeout=180,env=None):
    # communicate with short timeouts drains pipes while allowing cancellation.
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    deadline=time.monotonic()+timeout
    try:
        while True:
            checkpoint()
            try:
                out,err=proc.communicate(timeout=.2)
                return subprocess.CompletedProcess(command,proc.returncode,out,err)
            except subprocess.TimeoutExpired:
                if time.monotonic()>deadline:raise TimeoutError('Przekroczono czas OCR.')
    finally:
        if proc.poll() is None:proc.kill();proc.communicate()
