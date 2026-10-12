from PyInstaller.utils.hooks import collect_submodules
# Console companion: GUI --noconsole builds cannot display headless help/output.
from pathlib import Path
PROJECT_ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(PROJECT_ROOT / 'pdfmanager' / 'cli.py')],
    pathex=[str(PROJECT_ROOT)], binaries=[],
    datas=[(str(PROJECT_ROOT / 'third_party' / 'ZXing_CPP_LICENSE.txt'), 'third_party'),(str(PROJECT_ROOT / 'pdfmanager' / 'licensing' / 'public_key.pem'), 'pdfmanager/licensing')],
    hiddenimports=['pyhanko.sign.validation', 'pyhanko.sign.signers','zxingcpp']+collect_submodules('pdfmanager.pdf_engine')+collect_submodules('pdfmanager.security'),
    hookspath=[], hooksconfig={}, excludes=[], noarchive=False,
)
fonts = Tree(str(PROJECT_ROOT / 'pdfmanager' / 'resources' / 'fonts'), prefix='pdfmanager/resources/fonts')
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PDFManagerCLI',
          debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, fonts, strip=False, upx=False, name='PDFManagerCLI')
