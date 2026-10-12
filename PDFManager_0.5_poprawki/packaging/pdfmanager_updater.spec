# One-file trusted helper copied outside the installation during replacement.
from pathlib import Path
PROJECT_ROOT=Path(SPECPATH).parent
configuration=PROJECT_ROOT/'pdfmanager/resources/management.json'
data=[(str(configuration),'pdfmanager/resources')] if configuration.is_file() else []
a=Analysis([str(PROJECT_ROOT/'pdfmanager/remote/updater.py')],pathex=[str(PROJECT_ROOT)],binaries=[],datas=data,hiddenimports=[],hookspath=[],hooksconfig={},excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='PDFManagerUpdater',debug=False,strip=False,upx=False,console=False)
