
from pdfmanager.security.limits import pixmap as limited_pixmap

from pdfmanager.security.limits import safe_open
"""Additional local PDF workflows. Outputs never overwrite their source."""
from pathlib import Path
import pymupdf
from .io_utils import new_pdf_file, atomic_write_bytes


def _check_output(source: Path, output: Path) -> None:
    if Path(source).resolve() == Path(output).resolve():
        raise ValueError('Wybierz inny plik docelowy; oryginał zostanie zachowany.')


def search_text(source: Path, query: str) -> list[tuple[int, int]]:
    if not query.strip():
        return []
    with safe_open(source) as doc:
        return [(page.number, len(hits)) for page in doc if (hits := page.search_for(query))]


def export_images(source: Path, output_dir: Path, indices: list[int], dpi: int = 150, fmt: str = 'png') -> list[Path]:
    if fmt not in ('png', 'jpg') or not 72 <= dpi <= 600:
        raise ValueError('Nieprawidłowy format lub DPI (72–600).')
    if not indices:
        raise ValueError('Wybierz strony.')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [output_dir / f'{Path(source).stem}_page_{i + 1}.{fmt}' for i in indices]
    if len(set(outputs)) != len(outputs) or any(p.exists() for p in outputs):
        raise ValueError('Pliki docelowe już istnieją lub strony są powtórzone. Wybierz pusty folder.')
    with safe_open(source) as doc:
        if any(not 0 <= i < len(doc) for i in indices):
            raise ValueError('Nieprawidłowy numer strony.')
        for i, target in zip(indices, outputs):
            limited_pixmap(doc[i],dpi=dpi, colorspace=pymupdf.csRGB, alpha=False).save(target)
    return outputs


def stamp_document(source: Path, output: Path, text: str = '', page_numbers: bool = False) -> None:
    _check_output(source, output)
    if not text.strip() and not page_numbers:
        raise ValueError('Wpisz znak wodny lub włącz numerację.')
    font_path = Path(__file__).resolve().parent.parent / 'resources/fonts/DejaVuSans.ttf'
    font = pymupdf.Font(fontfile=str(font_path))
    with safe_open(source) as doc:
        for i, page in enumerate(doc):
            if text.strip():
                page.insert_font(fontname='watermark', fontfile=str(font_path))
                size = min(36, max(6, (page.rect.width - 40) / max(font.text_length(text, fontsize=1), 1)))
                width = font.text_length(text, fontsize=size)
                page.insert_text((max(10, (page.rect.width-width)/2), page.rect.height/2), text,
                                 fontname='watermark', fontsize=size, color=(.55,.55,.55), fill_opacity=.25)
            if page_numbers:
                label = f'{i+1} / {len(doc)}'
                width = pymupdf.get_text_length(label, fontsize=10)
                page.insert_text(((page.rect.width-width)/2, page.rect.height-18), label, fontsize=10)
        data = doc.tobytes(garbage=3, deflate=True)
    atomic_write_bytes(Path(output), data)


def flatten_document(source: Path, output: Path, dpi: int = 150) -> None:
    _check_output(source, output)
    if not 72 <= dpi <= 600:
        raise ValueError('DPI musi mieścić się w zakresie 72–600.')
    def build(out):
        with safe_open(source) as doc:
            for page in doc:
                pix = limited_pixmap(page,dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, annots=True)
                target = out.new_page(width=page.rect.width, height=page.rect.height)
                target.insert_image(target.rect, stream=pix.tobytes('png'))
    new_pdf_file(Path(output), build)

from pdfmanager.security.isolation import enable_module_isolation
ISOLATED_FUNCTIONS=['search_text', 'export_images', 'stamp_document', 'flatten_document']
enable_module_isolation(__name__,globals(),ISOLATED_FUNCTIONS)
