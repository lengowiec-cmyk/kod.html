"""Identify a complete, pairing-capable Windows build for the owner's packager."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pdfmanager.remote import APP_VERSION

def main():
    folder=ROOT/'dist'/'PDFManager'
    for name in ('PDFManager.exe','PDFManagerUpdater.exe','CLI/PDFManagerCLI.exe'):
        if not (folder/name).is_file():raise FileNotFoundError(name)
    (folder/'PDFManager-build.json').write_text(json.dumps({'schema':1,'platform':'windows','version':APP_VERSION}),encoding='utf-8')

if __name__=='__main__':main()
