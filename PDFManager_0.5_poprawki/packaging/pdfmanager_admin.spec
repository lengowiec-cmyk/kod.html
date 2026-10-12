# Separate owner's program; never included in the employee installer.
from pathlib import Path
PROJECT_ROOT = Path(SPECPATH).parent
a = Analysis([str(PROJECT_ROOT / 'pdfmanager/remote/admin_app.py')], pathex=[str(PROJECT_ROOT)], binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={}, excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='PDFManagerAdmin', debug=False, strip=False, upx=False, console=False)
