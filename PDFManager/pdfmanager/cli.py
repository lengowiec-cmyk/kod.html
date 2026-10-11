"""Local headless document workflows with useful exit codes."""
from pathlib import Path
import argparse
import sys
import getpass
from pdfmanager.pdf_engine import workflows as ops
from pdfmanager.pdf_engine.extended_ops import export_images,flatten_document,stamp_document
from pdfmanager.pdf_engine import page_ops


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog='PDFManager',description='Lokalne operacje PDF. Oryginały pozostają niezmienione.')
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('merge');p.add_argument('output',type=Path);p.add_argument('inputs',type=Path,nargs='+')
    p=commands.add_parser('extract-pages');p.add_argument('input',type=Path);p.add_argument('pages');p.add_argument('output',type=Path)
    p=commands.add_parser('split');p.add_argument('input',type=Path);p.add_argument('output_dir',type=Path)
    p=commands.add_parser('decrypt');p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--password-stdin',action='store_true')
    p=commands.add_parser('to-image');p.add_argument('input',type=Path);p.add_argument('output_dir',type=Path);p.add_argument('--pages',default='*');p.add_argument('--dpi',type=int,default=150);p.add_argument('--format',choices=['png','jpg'],default='png')
    p=commands.add_parser('flatten');p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--dpi',type=int,default=150)
    p=commands.add_parser('ocr');p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--lang',default='eng');p.add_argument('--text',action='store_true');p.add_argument('--dpi',type=int,default=200)
    p=commands.add_parser('text');p.add_argument('input',type=Path);p.add_argument('output',type=Path)
    p=commands.add_parser('batch-resave');p.add_argument('input_dir',type=Path);p.add_argument('output_dir',type=Path)
    p=commands.add_parser('print');p.add_argument('input',type=Path);p.add_argument('--printer');p.add_argument('--output',type=Path);p.add_argument('--pages',default='*');p.add_argument('--copies',type=int,default=1)
    p=commands.add_parser('watermark');p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--text',default='');p.add_argument('--numbers',action='store_true')
    args=parser.parse_args(argv)
    from PySide6.QtCore import QCoreApplication
    if args.command=='print':
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication(['PDFManager'])
    else:
        app=QCoreApplication.instance() or QCoreApplication(['PDFManager'])
    app.setOrganizationName('PDFManager');app.setApplicationName('PDFManager')
    try:
        from pdfmanager.licensing.license_manager import get_default_license_manager
        if get_default_license_manager().get_status().is_blocked:
            raise ops.WorkflowError('Licencja wymaga aktywacji w interfejsie aplikacji.')
        cmd=args.command
        if cmd=='merge':ops.merge_inputs(args.inputs,args.output)
        elif cmd=='extract-pages':
            ops._check_output(args.input,args.output)
            with ops.open_pdf(args.input) as doc:indices=ops.parse_pages(args.pages,len(doc))
            page_ops.extract_pages(args.input,indices,args.output)
        elif cmd=='split':
            args.output_dir.mkdir(parents=True,exist_ok=True)
            with ops.open_pdf(args.input) as doc:count=len(doc)
            targets=[args.output_dir/f'{args.input.stem}_part{i+1}.pdf' for i in range(count)]
            if any(p.exists() for p in targets):raise ops.WorkflowError('Wybierz pusty folder docelowy.')
            page_ops.split_at(args.input,list(range(count-1)),args.output_dir,args.input.stem)
        elif cmd=='decrypt':
            password=sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('Hasło PDF: ')
            ops.resave(args.input,args.output,password=password)
        elif cmd=='to-image':
            with ops.open_pdf(args.input) as doc:indices=ops.parse_pages(args.pages,len(doc))
            export_images(args.input,args.output_dir,indices,args.dpi,args.format)
        elif cmd=='flatten':flatten_document(args.input,args.output,args.dpi)
        elif cmd=='ocr':ops.ocr_document(args.input,args.output,args.lang,args.dpi,args.text)
        elif cmd=='text':ops.export_text(args.input,args.output)
        elif cmd=='print':
            from PySide6.QtPrintSupport import QPrinter,QPrinterInfo
            from pdfmanager.ui.printing import paint_document
            if not 1<=args.copies<=999:raise ops.WorkflowError('Liczba kopii: 1–999.')
            printer=QPrinter(QPrinter.PrinterMode.HighResolution)
            if args.output:
                ops._check_output(args.input,args.output)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat);printer.setOutputFileName(str(args.output))
            elif args.printer:
                if args.printer not in QPrinterInfo.availablePrinterNames():raise ops.WorkflowError('Nie znaleziono drukarki.')
                printer.setPrinterName(args.printer)
            elif not QPrinterInfo.defaultPrinterName():raise ops.WorkflowError('Brak drukarki domyślnej. Wybierz --printer lub --output.')
            printer.setCopyCount(args.copies)
            with ops.open_pdf(args.input) as doc:indices=ops.parse_pages(args.pages,len(doc))
            paint_document(printer,args.input,indices)
        elif cmd=='watermark':stamp_document(args.input,args.output,args.text,args.numbers)
        elif cmd=='batch-resave':
            results=ops.batch_resave(args.input_dir,args.output_dir)
            if any(status!='OK' for _,status in results):
                print('Część plików nie została przetworzona. Zobacz report.csv.',file=sys.stderr);return 2
    except Exception as exc:
        print(f'Błąd: {exc}',file=sys.stderr);return 1
    print('OK');return 0


if __name__=='__main__':raise SystemExit(main())
