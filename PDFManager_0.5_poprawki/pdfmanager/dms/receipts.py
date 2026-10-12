from pathlib import Path
from decimal import Decimal,InvalidOperation
from datetime import date
import csv,json,sqlite3
from .recovery import data_dir
from pdfmanager.security.cache import CacheCipher

class ReceiptStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else data_dir()/'receipts.sqlite3';self.path.parent.mkdir(parents=True,exist_ok=True)
        self.cipher=CacheCipher(self.path.parent)
        with sqlite3.connect(self.path) as db:db.execute('CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY,data TEXT NOT NULL)')
    def save(self,record,identifier=None):
        try:amount=Decimal(str(record['amount']).replace(',','.'))
        except (InvalidOperation,KeyError):raise ValueError('Podaj poprawną kwotę.')
        if not amount.is_finite() or amount<0 or amount>Decimal('999999999'):raise ValueError('Kwota jest poza zakresem.')
        date.fromisoformat(record['date']);record=dict(record,amount=str(amount.quantize(Decimal('.01'))))
        if not record.get('payee','').strip():raise ValueError('Podaj sprzedawcę.')
        data=self.cipher.encrypt(json.dumps(record,ensure_ascii=False))
        with sqlite3.connect(self.path) as db:
            if identifier:db.execute('UPDATE receipts SET data=? WHERE id=?',(data,identifier));return identifier
            return db.execute('INSERT INTO receipts(data) VALUES(?)',(data,)).lastrowid
    def all(self):
        with sqlite3.connect(self.path) as db:return [(i,json.loads(self.cipher.decrypt(data))) for i,data in db.execute('SELECT id,data FROM receipts ORDER BY id DESC')]
    def remove(self,identifier):
        with sqlite3.connect(self.path) as db:db.execute('PRAGMA secure_delete=ON');db.execute('DELETE FROM receipts WHERE id=?',(identifier,))
    def export(self,path):
        def safe(value):
            value=str(value)
            return "'"+value if value.lstrip(' \t\r\n\ufeff').startswith(('=','+','-','@')) else value
        with Path(path).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream,delimiter=';');writer.writerow(['Data','Sprzedawca','Kwota','Waluta','Kategoria','Płatność','Do zwrotu','Opis','Dokument'])
            for _,r in self.all():writer.writerow([safe(r.get(k,'')) for k in ('date','payee','amount','currency','category','payment','reimbursable','description','document')])
