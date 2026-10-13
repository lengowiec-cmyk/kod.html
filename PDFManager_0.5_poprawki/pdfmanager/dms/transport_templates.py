"""Original PL/EN/UK transport templates, separate from interface language."""
LANGUAGES=('pl','en','uk')
ROWS=[
('verified','ZWERYFIKOWANO','VERIFIED','ПЕРЕВІРЕНО'),
('correction','DO POPRAWY','CORRECTION REQUIRED','ПОТРЕБУЄ ВИПРАВЛЕННЯ'),
('signature','BRAK PODPISU','SIGNATURE MISSING','ВІДСУТНІЙ ПІДПИС'),
('complete','DOKUMENT KOMPLETNY','DOCUMENT COMPLETE','ДОКУМЕНТ ПОВНИЙ'),
('copy','KOPIA','COPY','КОПІЯ'),
('paid','OPŁACONO','PAID','СПЛАЧЕНО'),
('received','OTRZYMANO','RECEIVED','ОТРИМАНО'),
('delivery','POTWIERDZENIE DOSTAWY','PROOF OF DELIVERY','ПІДТВЕРДЖЕННЯ ДОСТАВКИ'),
('cmr','CMR OTRZYMANO','CMR RECEIVED','CMR ОТРИМАНО'),
('pod','POD OTRZYMANO','POD RECEIVED','POD ОТРИМАНО'),
('awb','AWB SPRAWDZONO','AWB CHECKED','AWB ПЕРЕВІРЕНО'),
('hawb','HAWB SPRAWDZONO','HAWB CHECKED','HAWB ПЕРЕВІРЕНО'),
('mawb','MAWB SPRAWDZONO','MAWB CHECKED','MAWB ПЕРЕВІРЕНО'),
('customs','DOKUMENTY CELNE OTRZYMANO','CUSTOMS DOCUMENTS RECEIVED','МИТНІ ДОКУМЕНТИ ОТРИМАНО'),
('invoice','FAKTURA SPRAWDZONA','INVOICE CHECKED','РАХУНОК ПЕРЕВІРЕНО'),
('pending','OCZEKUJE NA WERYFIKACJĘ','AWAITING VERIFICATION','ОЧІКУЄ НА ПЕРЕВІРКУ'),
('received_docs','Odbiór dokumentów','Documents received','Отримання документів',
 'Potwierdzamy otrzymanie dokumentów do zlecenia {zlecenie}. Kontrahent: {kontrahent}.',
 'We confirm receipt of the documents for order {zlecenie}. Customer: {kontrahent}.',
 'Підтверджуємо отримання документів до замовлення {zlecenie}. Контрагент: {kontrahent}.'),
('missing_signature','Uzupełnienie podpisu','Missing signature request','Запит щодо відсутнього підпису',
 'Prosimy o uzupełnienie podpisu i daty odbioru oraz przesłanie czytelnej kopii dokumentu.',
 'Please add the signature and delivery date and send a legible copy of the document.',
 'Просимо додати підпис і дату отримання та надіслати розбірливу копію документа.'),
('road_docs','Dokumenty drogowe','Road transport documents','Документи автомобільного перевезення',
 'Zlecenie {zlecenie}: prosimy o przesłanie podpisanego CMR i potwierdzenia dostawy POD.',
 'Order {zlecenie}: please send the signed CMR and proof of delivery (POD).',
 'Замовлення {zlecenie}: просимо надіслати підписаний CMR і підтвердження доставки POD.'),
('air_docs','Dokumenty lotnicze','Air freight documents','Документи авіаперевезення',
 'Zlecenie {zlecenie}: prosimy o przesłanie AWB, faktury handlowej i listy pakunkowej. AWB: {awb}. HAWB: {hawb}. MAWB: {mawb}.',
 'Order {zlecenie}: please send the AWB, commercial invoice and packing list. AWB: {awb}. HAWB: {hawb}. MAWB: {mawb}.',
 'Замовлення {zlecenie}: просимо надіслати AWB, комерційний рахунок та пакувальний лист. AWB: {awb}. HAWB: {hawb}. MAWB: {mawb}.'),
('shipment','Dane przesyłki','Shipment details','Дані відправлення',
 'Zlecenie: {zlecenie}\nTrasa: {trasa}\nPrzewoźnik: {przewoznik}\nLiczba sztuk: {sztuki}\nMasa: {masa}\nAWB: {awb}',
 'Order: {zlecenie}\nRoute: {trasa}\nCarrier: {przewoznik}\nPieces: {sztuki}\nWeight: {masa}\nAWB: {awb}',
 'Замовлення: {zlecenie}\nМаршрут: {trasa}\nПеревізник: {przewoznik}\nКількість місць: {sztuki}\nМаса: {masa}\nAWB: {awb}'),
('remark','Uwagi do przesyłki','Shipment remarks','Зауваження до відправлення',
 'Uwagi do zlecenia {zlecenie}: {uwagi}\n{data} {godzina} — {pracownik}',
 'Remarks for order {zlecenie}: {uwagi}\n{data} {godzina} — {pracownik}',
 'Зауваження до замовлення {zlecenie}: {uwagi}\n{data} {godzina} — {pracownik}'),
('driver','Instrukcja po rozładunku','After-unloading instructions','Інструкція після розвантаження',
 'Po rozładunku prosimy o przesłanie czytelnego skanu wszystkich stron podpisanego CMR. Zlecenie: {zlecenie}.',
 'After unloading, please send a legible scan of all pages of the signed CMR. Order: {zlecenie}.',
 'Після розвантаження просимо надіслати розбірливий скан усіх сторінок підписаного CMR. Замовлення: {zlecenie}.'),
]

def templates(language,kind='stamps'):
    if language not in LANGUAGES or kind not in ('stamps','snippets'):raise ValueError('Nieprawidłowy język lub rodzaj wzorów.')
    i=LANGUAGES.index(language)+1
    return [{'id':row[0],'label':row[i],'text':row[i] if len(row)==4 else row[i+3]} for row in ROWS if (len(row)==4)==(kind=='stamps')]

ORDER_PROFILES={
 'road':{'folders':['01 Order','02 CMR','03 POD','04 Invoice','05 Correspondence'],'required':['Podpisany CMR','POD','Faktura'],'destinations':{'Podpisany CMR':'02 CMR','POD':'03 POD','Faktura':'04 Invoice'}},
 'air':{'folders':['01 Order','02 AWB','03 HAWB','04 MAWB','05 Commercial invoice','06 Packing list','07 Customs','08 POD','09 Correspondence'],'required':['AWB','Faktura handlowa','Lista pakunkowa','POD'],'destinations':{'AWB':'02 AWB','HAWB':'03 HAWB','MAWB':'04 MAWB','Faktura handlowa':'05 Commercial invoice','Lista pakunkowa':'06 Packing list','Dokumenty celne':'07 Customs','POD':'08 POD'}},
}
