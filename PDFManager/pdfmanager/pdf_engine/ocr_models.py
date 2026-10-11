"""Verified on-demand OCR models from the official Apache-2.0 tessdata_fast tree."""
from pathlib import Path
import hashlib
import re
import subprocess
from urllib.request import urlopen
from PySide6.QtCore import QStandardPaths
from .io_utils import atomic_write_bytes

MODEL_COMMIT='87416418657359cb625c412a48b6e1d6d41c29bd'
# Git object identities from the pinned official tree, including Git blob framing.
MODEL_BLOBS={'eng':'bbef4675053b5b468cdb477053e28b1c698ba08e',
             'pol':'2382f568f0ce0c4c0a7f4380a291255514e5e97f',
             'ukr':'d02cf90b2911a3da66dac6ae380bcefb18dd7663'}


def model_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation))/'PDFManager'/'tessdata'


def verify_model(language: str, data: bytes) -> None:
    actual=hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
    if actual!=MODEL_BLOBS[language]:raise ValueError('Model OCR nie odpowiada przypiętej wersji oficjalnego repozytorium.')


def download_model(language: str) -> Path:
    if language not in MODEL_BLOBS:raise ValueError('Obsługiwane modele: eng, pol, ukr.')
    url=f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{MODEL_COMMIT}/{language}.traineddata'
    with urlopen(url,timeout=45) as response:
        data=response.read(32*1024*1024+1)
    if len(data)>32*1024*1024:raise ValueError('Model przekracza limit 32 MB.')
    verify_model(language,data)
    folder=model_dir();folder.mkdir(parents=True,exist_ok=True)
    path=folder/(language+'.traineddata');atomic_write_bytes(path,data)
    return path


def native_model_dir(executable: str) -> Path | None:
    proc=subprocess.run([executable,'--list-langs'],capture_output=True,text=True,timeout=20,check=True)
    match=re.search(r'in "([^"]+)"',proc.stdout)
    return Path(match.group(1)) if match else None
