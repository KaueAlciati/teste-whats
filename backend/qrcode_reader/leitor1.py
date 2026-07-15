import os
import cv2
import numpy as np
import re
from pyzbar.pyzbar import decode as pyzbar_decode
from pyzxing import BarCodeReader
from PIL import Image
import glob

def rotate_image(image, angle):
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h))

def decode_opencv(img_bgr):
    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(img_bgr)
    return data

def decode_pyzxing(img_path):
    reader = BarCodeReader()
    results = reader.decode(img_path)
    if not results:
        return None
    return results[0].get('parsed') or results[0].get('raw')

def apply_morphology(img, operation):
    kernel = np.ones((2, 2), np.uint8)
    if operation == "erode":
        return cv2.erode(img, kernel, iterations=1)
    elif operation == "dilate":
        return cv2.dilate(img, kernel, iterations=1)
    elif operation == "open":
        return cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel)
    elif operation == "close":
        return cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)
    return img

def decode_info_string(qr_url):
    if isinstance(qr_url, bytes):
        qr_url = qr_url.decode('utf-8')

    print(f"🔍 URL: {qr_url}")
    chave_match = re.search(r'(\d{44})', qr_url)
    if chave_match:
        chave = chave_match.group(1)
        print(f"🧾 Chave da NFC-e: {chave}")
        consulta_url = f"https://ww1.receita.fazenda.df.gov.br/DecVisualizador/Nfce/Captcha?Chave={chave}"
        print(f"🌐 URL de consulta: {consulta_url}")
    else:
        print("❌ Chave da nota não encontrada.")

def try_all_techniques(img_path, i):
    original_color = cv2.imread(img_path, cv2.IMREAD_COLOR)
    if original_color is None:
        print(f"❌ Não foi possível carregar a imagem: {img_path}")
        return

    original_gray = cv2.cvtColor(original_color, cv2.COLOR_BGR2GRAY)

    angles = [0, 90, 180, 270]
    thresholds = ["otsu", 50, 100, 150, 200]
    morphological_ops = [None, "erode", "dilate", "open", "close"]

    for angle in angles:
        rotated_color = rotate_image(original_color, angle)
        rotated_gray = rotate_image(original_gray, angle)

        for thresh_val in thresholds:
            gray_for_thresh = rotated_gray.copy()
            if thresh_val == "otsu":
                _, binarizada = cv2.threshold(gray_for_thresh, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                _, binarizada = cv2.threshold(gray_for_thresh, thresh_val, 255, cv2.THRESH_BINARY)

            for morph_op in morphological_ops:
                morphed = apply_morphology(binarizada, morph_op)
                final_bgr = cv2.cvtColor(morphed, cv2.COLOR_GRAY2BGR)

                data_opencv = decode_opencv(final_bgr)
                if data_opencv:
                    print(f"[OpenCV] ✅ angle={angle}, thresh={thresh_val}, morph={morph_op}")
                    print(data_opencv)
                    decode_info_string(data_opencv)
                    return

                results_pyzbar = pyzbar_decode(Image.fromarray(morphed))
                if results_pyzbar:
                    print(f"[pyzbar] ✅ angle={angle}, thresh={thresh_val}, morph={morph_op}")
                    for res in results_pyzbar:
                        qr_url = res.data.decode('utf-8')
                        print(qr_url)
                        decode_info_string(qr_url)
                    return

                temp_path = f"temp{i}.png"
                cv2.imwrite(temp_path, morphed)
                data_pyzxing = decode_pyzxing(temp_path)
                if data_pyzxing:
                    print(f"[pyzxing] ✅ angle={angle}, thresh={thresh_val}, morph={morph_op}")
                    print(data_pyzxing)
                    decode_info_string(data_pyzxing)
                    return

    print("🚫 Não foi possível decodificar o QR Code com nenhuma das heurísticas.")

def main():
    pasta = "E:/whatsapp_gastos_ai/backend/data"
    arquivos = glob.glob(f"{pasta}/*.jpeg")

    if not arquivos:
        print("❌ Nenhuma imagem JPEG encontrada na pasta 'data'.")
        return

    for caminho in arquivos:
        nome = os.path.basename(caminho)
        print(f"📂 Tentando: {nome}")
        try_all_techniques(caminho, nome.replace('.jpeg', ''))
        print("=" * 40)

if __name__ == "__main__":
    main()