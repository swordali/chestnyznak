import io
import re
import fitz  # PyMuPDF
import zxingcpp
import pandas as pd
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance

GS = chr(29)


def pdf_to_images(pdf_bytes, zoom=5):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        pages.append((page_index + 1, img))

    return pages


def make_attempt_images(img):
    w, h = img.size

    crops = [
        img,
        img.crop((int(w * 0.10), int(h * 0.10), int(w * 0.90), int(h * 0.75))),
        img.crop((int(w * 0.14), int(h * 0.14), int(w * 0.86), int(h * 0.65))),
        img.crop((int(w * 0.18), int(h * 0.18), int(w * 0.82), int(h * 0.58))),
    ]

    attempts = []

    for crop in crops:
        gray = ImageOps.grayscale(crop)
        attempts.append(gray)

        contrast = ImageEnhance.Contrast(gray).enhance(2.0)
        attempts.append(contrast)

        bw = contrast.point(lambda p: 255 if p > 150 else 0)
        attempts.append(bw)

        big = bw.resize((bw.width * 2, bw.height * 2), Image.Resampling.NEAREST)
        attempts.append(big)

    return attempts


def decode_datamatrix_zxing(pil_img):
    found = []

    for attempt_img in make_attempt_images(pil_img):
        try:
            results = zxingcpp.read_barcodes(
                attempt_img,
                formats=zxingcpp.BarcodeFormat.DataMatrix,
                try_rotate=True,
                try_downscale=True
            )
        except TypeError:
            results = zxingcpp.read_barcodes(attempt_img)

        for r in results:
            text = getattr(r, "text", "")

            if text and text not in found:
                found.append(text)

        if found:
            break

    return found


def normalize_input(raw):
    raw = raw.replace("\r", "")
    raw = raw.replace("\n", "")
    raw = raw.strip()

    if raw.startswith("]d2"):
        raw = raw[3:]

    raw = raw.replace("<GS>", GS)
    raw = raw.replace("\\x1d", GS)

    return raw


def parse_gs1(raw):
    """
    İki formatı da destekler:

    1) ZXing human-readable:
       (01)04695660284073(21)SERIAL(91)EE11(92)CRYPTOTAIL

    2) Ham GS1:
       010469566028407321SERIAL<ASCII29>91EE11<ASCII29>92CRYPTOTAIL

    Çıktıda correct_gs1 her zaman ham GS1/FNC1 formatıdır.
    """
    s = normalize_input(raw)

    result = {
        "gtin_01": "",
        "serial_21": "",
        "crypto_91": "",
        "crypto_92": "",
        "decoded_visible": s.replace(GS, "<GS>"),
        "correct_gs1": "",
    }

    # FORMAT 1: (01)...(21)...(91)...(92)...
    if "(01)" in s and "(21)" in s:
        gtin = re.search(r"\(01\)(\d{14})", s)
        serial = re.search(r"\(21\)(.*?)(?=\(91\)|\(92\)|$)", s)
        crypto91 = re.search(r"\(91\)(.*?)(?=\(92\)|$)", s)
        crypto92 = re.search(r"\(92\)(.*)$", s)

        if gtin:
            result["gtin_01"] = gtin.group(1)
        if serial:
            result["serial_21"] = serial.group(1)
        if crypto91:
            result["crypto_91"] = crypto91.group(1)
        if crypto92:
            result["crypto_92"] = crypto92.group(1)

        result["correct_gs1"] = build_correct_gs1(result)
        return result

    # FORMAT 2: raw GS1
    pos = 0

    while pos < len(s):
        ai = s[pos:pos + 2]

        if ai == "01":
            result["gtin_01"] = s[pos + 2:pos + 16]
            pos += 16

        elif ai == "21":
            start = pos + 2
            next_gs = s.find(GS, start)

            if next_gs != -1:
                result["serial_21"] = s[start:next_gs]
                pos = next_gs + 1
            else:
                next_91 = s.find("91", start)
                if next_91 != -1:
                    result["serial_21"] = s[start:next_91]
                    pos = next_91
                else:
                    result["serial_21"] = s[start:]
                    pos = len(s)

        elif ai == "91":
            start = pos + 2
            next_gs = s.find(GS, start)

            if next_gs != -1:
                result["crypto_91"] = s[start:next_gs]
                pos = next_gs + 1
            else:
                next_92 = s.find("92", start)
                if next_92 != -1:
                    result["crypto_91"] = s[start:next_92]
                    pos = next_92
                else:
                    result["crypto_91"] = s[start:]
                    pos = len(s)

        elif ai == "92":
            result["crypto_92"] = s[pos + 2:]
            pos = len(s)

        else:
            pos += 1

    result["correct_gs1"] = build_correct_gs1(result)
    return result


def build_correct_gs1(parsed):
    gtin = parsed.get("gtin_01", "")
    serial = parsed.get("serial_21", "")
    crypto91 = parsed.get("crypto_91", "")
    crypto92 = parsed.get("crypto_92", "")

    if not gtin or not serial:
        return ""

    if crypto91 or crypto92:
        return f"01{gtin}21{serial}{GS}91{crypto91}{GS}92{crypto92}"

    return f"01{gtin}21{serial}"


def main():
    st.set_page_config(
        page_title="Chestny Znak DataMatrix PDF → Final GS1 CSV",
        layout="wide"
    )

    st.title("Chestny Znak DataMatrix PDF → Final GS1 CSV")

    st.write(
        "PDF içindeki DataMatrix kodlarını okur. "
        "ZXing parantezli format döndürse bile doğru ham GS1/FNC1 CSV üretir. www.chestnyznak.com.tr"
    )

    uploaded_file = st.file_uploader("DataMatrix içeren PDF yükle", type=["pdf"])

    if not uploaded_file:
        st.info("PDF dosyasını yükleyin.")
        st.stop()

    zoom = st.slider("PDF görüntü kalitesi", min_value=3, max_value=8, value=5)

    csv_mode = st.radio(
        "CSV çıktısı",
        [
            "Matbaa / TEC-IT için tek kolon başlıksız",
            "Kontrol için detaylı CSV"
        ],
        index=0
    )

    pdf_bytes = uploaded_file.read()
    rows = []

    with st.spinner("PDF içindeki DataMatrix kodları okunuyor..."):
        pages = pdf_to_images(pdf_bytes, zoom=zoom)
        progress = st.progress(0)

        for i, (page_no, img) in enumerate(pages, start=1):
            decoded_values = decode_datamatrix_zxing(img)

            if not decoded_values:
                rows.append({
                    "page": page_no,
                    "status": "NOT_FOUND",
                    "gtin_01": "",
                    "serial_21": "",
                    "crypto_91": "",
                    "crypto_92": "",
                    "decoded_visible": "",
                    "correct_visible": "",
                    "correct_gs1": "",
                })
            else:
                for raw in decoded_values:
                    parsed = parse_gs1(raw)
                    parsed["page"] = page_no
                    parsed["status"] = "OK" if parsed["correct_gs1"] else "PARSE_ERROR"
                    parsed["correct_visible"] = parsed["correct_gs1"].replace(GS, "<GS>")
                    rows.append(parsed)

            progress.progress(i / len(pages))

    df = pd.DataFrame(rows)

    show_columns = [
        "page",
        "status",
        "gtin_01",
        "serial_21",
        "crypto_91",
        "crypto_92",
        "decoded_visible",
        "correct_visible",
    ]

    st.subheader("Kontrol tablosu")
    st.dataframe(df[show_columns], use_container_width=True)

    ok_count = int((df["status"] == "OK").sum())
    parse_error_count = int((df["status"] == "PARSE_ERROR").sum())
    not_found_count = int((df["status"] == "NOT_FOUND").sum())

    st.write(
        f"OK: {ok_count} | PARSE_ERROR: {parse_error_count} | "
        f"NOT_FOUND: {not_found_count} | Toplam: {len(df)}"
    )

    if csv_mode.startswith("Matbaa"):
        out = df[df["status"] == "OK"][["correct_gs1"]].copy()

        csv_data = out.to_csv(
            index=False,
            header=False,
            encoding="utf-8-sig"
        ).encode("utf-8-sig")

        file_name = "correct_gs1_for_datamatrix.csv"

    else:
        out = df[show_columns].copy()

        csv_data = out.to_csv(
            index=False,
            encoding="utf-8-sig"
        ).encode("utf-8")

        file_name = "gs1_codes_check.csv"

    st.download_button(
        "CSV indir",
        csv_data,
        file_name=file_name,
        mime="text/csv"
    )

    st.caption(
        "Önemli: Matbaa/TEC-IT CSV içinde <GS> yazısı yoktur. "
        "Gerçek ASCII 29/FNC1 ayırıcı karakteri vardır."
    )


if __name__ == "__main__":
    main()
