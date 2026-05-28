# Chestny Znak DataMatrix PDF -> Final Correct GS1 CSV

Bu sürüm PDF içindeki DataMatrix'i ZXing ile okur.

ZXing şu formatı döndürürse:
(01)04695660284073(21)SERIAL(91)EE11(92)CRYPTOTAIL

Program bunu doğru ham GS1 formatına çevirir:
010469566028407321SERIAL<ASCII29>91EE11<ASCII29>92CRYPTOTAIL

online datamatrix creating  and control link https://barcode.tec-it.com/en/GS1DataMatrix
 sample data : 0104695660284073215C%:_z91EE1192c3XZzvLomCvCPQPycuCvGs50GStqsNXDCLhOJms/m1w=

Matbaa / TEC-IT CSV:
- tek kolon
- başlıksız
- parantezsiz
- gerçek ASCII 29 FNC1 ayırıcı karakterli

## Kurulum

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

