import os
import datetime
import shutil 
import re 
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image

# --- Kütüphaneler ---
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
from google.oauth2 import service_account
from googleapiclient.discovery import build # 👑 DÜZELTİLDİ (googleapiclient)

import helpers
from flask import url_for 

import fitz  # PyMuPDF
import io

# =========================================================
# === 👑 KRAL DÜZELTMESİ (14.11.2025): YENİ PURE PYTHON PDF->TXT 👑 ===
# =========================================================
def pdf_to_txt_pure(pdf_path, txt_path):
    """
    Pure Python PDF'den metin çıkarma (PyMuPDF/fitz kullanarak).
    Poppler'a İHTİYACI YOKTUR. Bu yüzden her cihazda çalışır.
    """
    try:
        full_text = ""
        # PDF'i aç
        with fitz.open(pdf_path) as pdf_document:
            # Her sayfayı gez
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                # Sayfadaki metni al ve ekle
                full_text += page.get_text("text")
        
        # Tüm metni .txt dosyasına UTF-8 olarak yaz
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print("Pure Python (fitz) ile PDF'den TXT'ye dönüştürme başarılı.")
    except Exception as e:
        print(f"Pure Python (fitz) PDF okuma hatası: {e}")
        # Hatayı yeniden fırlat ki 'donusturme_merkezi_sayfasi' yakalayabilsin
        raise e 
# =========================================================
# === 👑 YENİ FONKSİYON BİTTİ 👑 ===
# =========================================================


# =========================================================
# === 👑 HARİCİ PROGRAM YOLU TANIMI (DOKUNMA) 👑 ===
# =========================================================
# Diğer helpers fonksiyonları (docx2txt vb.) Poppler/Tesseract
# gerektirebilir, bu yüzden bu kod kalsın.
POPPLER_BIN_PATH = None  # None ise otomatik PATH kullanılır.

if POPPLER_BIN_PATH and os.path.isdir(POPPLER_BIN_PATH):
    os.environ["PATH"] += os.pathsep + POPPLER_BIN_PATH
    print(f"Poppler yolu sisteme EKLENDİ: {POPPLER_BIN_PATH}")
# =========================================================


# --- AYARLAR VE BAĞLANTILAR ---
KEY_FILE = "ders-program-e07f2-firebase-adminsdk-fbsvc-eff01c1173.json"
DATABASE_URL = "https://ders-program-e07f2-default-rtdb.europe-west1.firebasedatabase.app/"
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
DRIVE_KEY_PATH = "" 
UPLOAD_FOLDER = 'uploads' # Yükleme klasörü
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

try:
    DRIVE_KEY_PATH = os.path.join(os.path.dirname(__file__), KEY_FILE)
    if not firebase_admin._apps:
        cred = credentials.Certificate(DRIVE_KEY_PATH)
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
        print("Firebase bağlantısı BAŞARILI!")
except Exception as e:
    if "already initialized" not in str(e):
        print(f"Firebase bağlantı HATASI: {e}")

# Flask Uygulamısını Başlat
app = Flask(__name__)
app.config['SECRET_KEY'] = 'kral_sarbay_cok_gizli_anahtar_12345'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# --- BEYİN FONKSİYONLARI (Veri Çekme) ---

def get_kral_selamlama():
    saat = datetime.datetime.now().hour
    if 5 <= saat < 12: return "Günaydın! ☀️"
    elif 12 <= saat < 18: return "İyi Günler! 😎"
    else: return "İyi Akşamlar! 🌙"

# =================================================================
# === 👑 KRAL DÜZELTMESİ: 'get_yaklasan_sinavlar' SİLME İÇİN GÜNCELLENDİ 👑 ===
# =================================================================
def get_yaklasan_sinavlar():
    yaklasan_sinavlar_raw = []
    try:
        sinav_verisi = db.reference('/sinavlar').get()
        today = datetime.datetime.now().date()
        
        if sinav_verisi and isinstance(sinav_verisi, list):
            # YENİ (PC) verisi (List)
            # 'i' artık Firebase'deki LİSTE index'i
            for i, sinav in enumerate(sinav_verisi):
                try:
                    sinav_tarihi_str = sinav.get("tarih")
                    try:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%Y-%m-%d").date()
                    except ValueError:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%d.%m.%Y").date()
                    
                    kalan_gun = (sinav_tarihi - today).days
                    if kalan_gun >= 0:
                        # 👑 ID olarak "index" veriyoruz (PC programı gibi)
                        yaklasan_sinavlar_raw.append({"id": i, "ad": sinav.get("ad"), "kalan_gun": kalan_gun})
                except Exception: continue
        
        elif sinav_verisi and isinstance(sinav_verisi, dict):
            # ESKİ (push) verisi (Dict)
            for key, sinav in sinav_verisi.items():
                try:
                    sinav_tarihi_str = sinav.get("tarih")
                    try:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%Y-%m-%d").date()
                    except ValueError:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%d.%m.%Y").date()
                    
                    kalan_gun = (sinav_tarihi - today).days
                    if kalan_gun >= 0:
                         # 👑 ID olarak Firebase KEY'ini ver
                        yaklasan_sinavlar_raw.append({"id": key, "ad": sinav.get("ad"), "kalan_gun": kalan_gun})
                except Exception: continue

        # Şimdi, ID'leri atadıktan SONRA sırala
        yaklasan_sinavlar_raw.sort(key=lambda x: x["kalan_gun"])

    except Exception as e: print(f"Firebase'den sınavlar çekılırken hata: {e}")
    return yaklasan_sinavlar_raw
# =================================================================
# === 👑 GÜNCELLEME BİTTİ 👑 ===
# =================================================================

# =================================================================
# === 👑 KRAL DÜZELTMESİ: 'get_son_calismalar' SİLME İÇİN GÜNCELLENDİ 👑 ===
# =================================================================
def get_son_calismalar():
    son_calismalar_raw = []
    try:
        calisma_verisi = db.reference('/calisma_takibi').get()
        
        list_view_with_ids = []
        if calisma_verisi and isinstance(calisma_verisi, list):
             # YENİ (PC) verisi (List)
             # 👑 ID olarak "index" veriyoruz (PC programı gibi)
             list_view_with_ids = [{"id": i, **v} for i, v in enumerate(calisma_verisi)]
             list_view_with_ids.sort(key=lambda x: x.get('tarih', ''), reverse=True)
            
        elif calisma_verisi and isinstance(calisma_verisi, dict):
            # ESKİ (push) verisi (Dict)
            # 👑 ID olarak Firebase KEY'ini ver
            list_view_with_ids = [{"id": k, **v} for k, v in calisma_verisi.items()]
            list_view_with_ids.sort(key=lambda x: x.get('tarih', ''), reverse=True)

        # === OKUMA KODU (DEĞİŞMEDİ, SADECE KAYNAK DEĞİŞTİ) ===
        for kayit in list_view_with_ids[:5]:
            son_calismalar_raw.append({
                "id": kayit.get('id'), # Artık 'silinemez' değil, gerçek ID/index
                "text": f"{kayit.get('ders')} - {kayit.get('konu')} ({kayit.get('sure')} dk)"
            })
                
    except Exception as e: print(f"Firebase'den çalışmalar çekılırken hata: {e}")
    return son_calismalar_raw
# =================================================================
# === 👑 GÜNCELLEME BİTTİ 👑 ===
# =================================================================
    
# =================================================================
# === 👑 KRAL DÜZELTMESİ: 'get_notlar' SİLME İÇİN GÜNCELLENDİ 👑 ===
# =================================================================
def get_notlar():
    not_listesi = []
    try:
        not_verisi = db.reference('/notlar').get()
        
        if not_verisi and isinstance(not_verisi, dict): 
            # ESKİ (push) verisi (Dict)
            for key, value in not_verisi.items():
                not_listesi.append({"id": key, "text": value.get("text", "Boş not")})
        
        elif not_verisi and isinstance(not_verisi, list):
            # YENİ (PC) verisi (List)
            for i, item in enumerate(not_verisi):
                if isinstance(item, dict):
                    # 👑 ID olarak "index" veriyoruz (PC programı gibi)
                    not_listesi.append({"id": i, "text": item.get("text", "Boş not")})
                else:
                    not_listesi.append({"id": i, "text": str(item)})
                
    except Exception as e: print(f"Firebase'den notlar çekılırken hata: {e}")
    return not_listesi
# =================================================================
# === 👑 GÜNCELLEME BİTTİ 👑 ===
# =================================================================

# =================================================================
# === 👑 KRAL DÜZELTMESİ: 'get_butun_calismalar' SİLME İÇİN GÜNCELLENDİ 👑 ===
# =================================================================
def get_butun_calismalar():
    butun_calismalar = []
    try:
        calisma_verisi = db.reference('/calisma_takibi').get()
        
        list_view_with_ids = []
        if calisma_verisi and isinstance(calisma_verisi, list):
            # YENİ (PC) verisi (List)
            list_view_with_ids = [{"id": i, **v} for i, v in enumerate(calisma_verisi)]
            
        elif calisma_verisi and isinstance(calisma_verisi, dict):
            # ESKİ (push) verisi (Dict)
            list_view_with_ids = [{"id": k, **v} for k, v in calisma_verisi.items()]
        
        list_view_with_ids.sort(key=lambda x: x.get('tarih', ''), reverse=True)
        
        for kayit in list_view_with_ids:
            butun_calismalar.append({
                "id": kayit.get('id'), # Gerçek ID/index
                "ders": kayit.get('ders', 'N/A'),
                "konu": kayit.get('konu', 'N/A'),
                "sure": kayit.get('sure', '0'),
                "tarih": kayit.get('tarih', 'Tarih Yok')
            })
                
    except Exception as e: 
        print(f"Firebase'den BÜTÜN çalışmalar çekilirken hata: {e}")
    return butun_calismalar
# =================================================================
# === 👑 GÜNCELLEME BİTTİ 👑 ===
# =================================================================

def natural_sort_key(s):
    ad = s.get('ad', str(s)) 
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('(\d+)', ad)]

def get_logo_path(item_name):
    logo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'logos')
    if not os.path.isdir(logo_dir): 
        print(f"HATA: Logo klasörü bulunamadı: {logo_dir}")
        return None
    clean_name = re.sub(r'^\d+\)|\d+\)', '', item_name).strip()
    search_names = [clean_name, item_name] 
    logo_files = {}
    for filename in os.listdir(logo_dir):
        name, ext = os.path.splitext(filename)
        logo_files[name.lower()] = filename
    for name_to_search in search_names:
        if not name_to_search: continue
        lower_name = name_to_search.lower()
        if lower_name in logo_files:
            original_filename = logo_files[lower_name]
            return url_for('static', filename='logos/' + original_filename)
    return None

def generate_app_link(app_name):
    app_map = {
        "Pakodemy": "pakodemy://app", "Derslig": "derslig://app", "Kunduz": "kunduz://app",
        "ChatGPT": "chatgpt://", "Gemini": "gemini://", "Copilot": "ms-copilot://", "DeepSeek": "deepseek://",
        "HIZ Kütüphanesi": "hizkutuphane://", "AnkaraVideoÇözüm": "ankaravideo://",
        "SonuçMobilKütüphanesi": "sonucmobil://", "TATSDijitalKitap": "tats://", 
    }
    return app_map.get(app_name, "#") 

# --- SAYFA YOLLARI (ROUTES) ---
@app.route('/')
def ana_sayfa():
    return render_template('ana_sayfa.html', 
                           selamlama_mesaji=get_kral_selamlama(), 
                           sinav_listesi=get_yaklasan_sinavlar(),
                           not_listesi=get_notlar(),
                           calisma_listesi=get_son_calismalar())

@app.route('/dersler')
def dersler_sayfasi():
    ders_listesi = []
    try:
        creds = service_account.Credentials.from_service_account_file(DRIVE_KEY_PATH, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        q_query = "name='Dersler' and mimeType='application/vnd.google-apps.folder'"
        results = service.files().list(q=q_query, fields="files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            return render_template('dersler.html', dosya_listesi=[{"ad": "HATA: 'Dersler' klasörü bulunamadı veya paylaşılmadı.", "link": "#"}])
        dersler_folder_id = items[0].get('id')
        q_query_files = f"'{dersler_folder_id}' in parents and trashed=false"
        file_results = service.files().list(q=q_query_files, pageSize=50, fields="files(name, webViewLink, mimeType)").execute()
        files = file_results.get('files', [])
        if not files:
            return render_template('dersler.html', dosya_listesi=[{"ad": "Bu klasör (şimtilik) boş.", "link": "#"}])
        for file in files:
            link = file.get('webViewLink')
            mime_type = file.get('mimeType')
            file_name = file.get('name')
            if 'google-apps' in mime_type:
                link = link.replace('/edit?usp=drivesdk', '/preview?rm=minimal')
                link = link.replace('/edit', '/preview?rm=minimal')
            logo_path = get_logo_path(file_name)
            ders_listesi.append({"ad": file_name, "link": link, "logo": logo_path})
        ders_listesi.sort(key=natural_sort_key)
        return render_template('dersler.html', dosya_listesi=ders_listesi)
    except Exception as e:
        print(f"Google Drive'dan dosyalar çekılırken hata: {e}")
        return render_template('dersler.html', dosya_listesi=[{"ad": f"HATA: {e}", "link": "#"}])

@app.route('/dershaneler')
def dershaneler_sayfasi():
    dershaneler = [{"ad": "Pakodemy"}, {"ad": "Derslig"}, {"ad": "Kunduz"}]
    for d in dershaneler:
        d['logo'] = get_logo_path(d['ad']) 
        d['link'] = generate_app_link(d['ad']) 
    return render_template('dershaneler.html', dershane_listesi=dershaneler)

@app.route('/yapay-zeka')
def yapay_zeka_sayfasi():
    ai_servisleri = [{"ad": "ChatGPT"}, {"ad": "Gemini"}, {"ad": "DeepSeek"}, {"ad": "Copilot"}]
    for ai in ai_servisleri:
        ai['logo'] = get_logo_path(ai['ad'])
        ai['link'] = generate_app_link(ai['ad']) 
    return render_template('yapay_zeka.html', ai_listesi=ai_servisleri)

@app.route('/test-kitaplari')
def test_kitaplari_sayfasi():
    kitaplar = [{"ad": "HIZ Kütüphanesi"}, {"ad": "AnkaraVideoÇözüm"}, {"ad": "SonuçMobilKütüphanesi"}, {"ad": "TATSDijitalKitap"}]
    for kitap in kitaplar:
        kitap['logo'] = get_logo_path(kitap['ad'])
        kitap['link'] = generate_app_link(kitap['ad']) 
    return render_template('test_kitaplari.html', kitap_listesi=kitaplar)

@app.route('/calisma-takibi', methods=['GET', 'POST']) 
def calisma_takibi_sayfasi():
    if request.method == 'POST':
        try:
            ders = request.form['ders_adi']
            konu = request.form['konu_adi']
            sure = int(request.form['sure_dk'])
            if not ders or not konu or sure <= 0:
                pass 
            else:
                mevcut_calismalar = db.reference('/calisma_takibi').get()
                if not isinstance(mevcut_calismalar, list):
                    mevcut_calismalar = [] 
                yeni_kayit = {
                    "ders": ders, "konu": konu, "sure": sure,
                    "tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "kaynak": "TELEFON"
                }
                mevcut_calismalar.append(yeni_kayit)
                db.reference('/calisma_takibi').set(mevcut_calismalar)
                print("Web'den yeni çalışma (PC UYUMLU - SET) Firebase'e eklendi!")
        except Exception as e:
            print(f"Firebase'e PC UYUMLU ÇALIŞMA YAZMA hatası: {e}")
        return redirect(url_for('calisma_takibi_sayfasi'))
    
    butun_calismalar = get_butun_calismalar() 
    calisma_data_agaci = scan_calisma_klasoru()
    return render_template('calisma_takibi.html', 
                           calisma_listesi=butun_calismalar, 
                           calisma_data_agaci=calisma_data_agaci)

@app.route('/donusturme-merkezi', methods=['GET', 'POST'])
def donusturme_merkezi_sayfasi():
    if request.method == 'POST':
        try:
            if 'file' not in request.files: return render_template('donusturme_merkezi.html', hata="Dosya seçilmedi!")
            file = request.files['file']
            operation = request.form['operation']
            if file.filename == '': return render_template('donusturme_merkezi.html', hata="Dosya seçilmedi!")
            filename = secure_filename(file.filename)
            in_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(in_path)
            out_path = ""
            if operation == 'png2jpg':
                out_path = helpers.safe_out_path(in_path, ".jpg")
                img = Image.open(in_path)
                if img.mode == 'RGBA' or 'A' in img.info.get('transparency', ''):
                    img = img.convert('RGB')
                img.save(out_path)
            elif operation == 'jpg2png':
                out_path = helpers.safe_out_path(in_path, ".png")
                img = Image.open(in_path)
                img.save(out_path)
            elif operation in ['txt2pdf', 'pdf2txt', 'docx2txt', 'txt2docx', 'excel2docx', 'excel2txt', 'pptx2ppsx', 'ppsx2pptx']:
                try:
                    if operation == 'txt2pdf': out_path = helpers.safe_out_path(in_path, ".pdf"); helpers.txt_to_pdf(in_path, out_path)
                    
                    # === 👑👑👑 KRAL DÜZELTMESİ (14.11.2025) 👑👑👑 ===
                    # Poppler gerektiren 'helpers.pdf_to_txt' yerine 
                    # Poppler GEREKTİRMEYEN 'pdf_to_txt_pure' (fitz) kullanılıyor.
                    elif operation == 'pdf2txt': 
                        out_path = helpers.safe_out_path(in_path, ".txt")
                        pdf_to_txt_pure(in_path, out_path) # <--- HATA BURADAYDI, DÜZELTİLDİ
                    # === 👑👑👑 DÜZELTME BİTTİ 👑👑👑 ===
                    
                    elif operation == 'docx2txt': out_path = helpers.safe_out_path(in_path, ".txt"); helpers.docx_to_txt(in_path, out_path)
                    elif operation == 'txt2docx': out_path = helpers.safe_out_path(in_path, ".docx"); helpers.txt_to_docx(in_path, out_path)
                    elif operation == 'excel2docx': out_path = helpers.safe_out_path(in_path, ".docx"); helpers.excel_to_docx(in_path, out_path)
                    elif operation == 'excel2txt': out_path = helpers.safe_out_path(in_path, ".txt"); helpers.excel_to_txt(in_path, out_path)
                    elif operation == 'pptx2ppsx': out_path = helpers.safe_out_path(in_path, ".ppsx"); shutil.copy(in_path, out_path) 
                    elif operation == 'ppsx2pptx': out_path = helpers.safe_out_path(in_path, ".pptx"); shutil.copy(in_path, out_path)
                except Exception as doc_error:
                    # Hatayı daha net göstermek için 'doc_error'u yazdır
                    error_msg = f"Doküman dönüştürme hatası: {doc_error}. Lütfen Poppler/Tesseract programlarının kurulu olduğundan emin olun."
                    print(f"KRİTİK HATA: {error_msg}")
                    return render_template('donusturme_merkezi.html', hata=error_msg)
            else: return render_template('donusturme_merkezi.html', hata="Geçersiz işlem seçildi!")
            out_filename = os.path.basename(out_path); out_dir = os.path.dirname(out_path)
            return send_from_directory(out_dir, out_filename, as_attachment=True)
        except Exception as e:
            print(f"Dönüştürme hatası: {e}")
            return render_template('donusturme_merkezi.html', hata=f"Dönüştürme hatası: {e}")
    return render_template('donusturme_merkezi.html', hata=None)

# --- YENİ EKLEME FONKSİYONLARI ---
@app.route('/ekle-not', methods=['POST'])
def ekle_not():
    if request.method == 'POST':
        try:
            not_text = request.form['not_text']
            if not_text:
                mevcut_notlar = db.reference('/notlar').get()
                data_list = []
                if isinstance(mevcut_notlar, dict): data_list = list(mevcut_notlar.values())
                elif isinstance(mevcut_notlar, list): data_list = mevcut_notlar
                yeni_not = { "text": f"TELEFON: {not_text}", "tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M") } 
                data_list.append(yeni_not)
                db.reference('/notlar').set(data_list)
                print("Web'den yeni not (PC UYUMLU - SET) Firebase'e eklendi!")
        except Exception as e:
            print(f"Firebase'e PC UYUMLU NOT YAZMA hatası: {e}")
    return redirect(url_for('ana_sayfa'))

@app.route('/ekle-sinav', methods=['POST'])
def ekle_sinav():
    if request.method == 'POST':
        try:
            sinav_adi = request.form['sinav_adi']
            sinav_tarihi = request.form['sinav_tarihi']
            if sinav_adi == 'Diger' or sinav_adi == 'Diğer':
                sinav_adi = request.form.get('sinav_adi_manual', 'Diğer Sınav')
            if sinav_adi and sinav_tarihi:
                mevcut_sinavlar = db.reference('/sinavlar').get()
                if not isinstance(mevcut_sinavlar, list):
                    mevcut_sinavlar = [] 
                yeni_sinav = { "ad": sinav_adi, "tarih": sinav_tarihi, "kaynak": "TELEFON" }
                mevcut_sinavlar.append(yeni_sinav)
                db.reference('/sinavlar').set(mevcut_sinavlar)
                print("Web'den yeni sınav (PC UYUMLU - SET) Firebase'e eklendi!")
        except Exception as e:
            print(f"Firebase'e PC UYUMLU SINAV YAZMA hatası: {e}")
    return redirect(url_for('ana_sayfa'))

# =================================================================
# === 👑 KRAL DÜZELTMESİ: YENİ SİLME FONKSİYONLARI 👑 ===
# =================================================================

# PC uyumlu (LİSTE) ve Eski (DICT) verileri silen FİNAL fonksiyonlar
# Gelen ID'nin sayı (index) mı yoksa string (key) mi olduğuna bakarlar.

@app.route('/sil-not/<not_id>', methods=['GET'])
def sil_not(not_id):
    try:
        # 1. Gelen ID'yi index olarak dene
        index_to_delete = int(not_id)
        
        # 2. LİSTEYİ OKU
        mevcut_notlar = db.reference('/notlar').get()
        
        # 3. Veri LİSTE ise ve index geçerliyse, SİL
        if isinstance(mevcut_notlar, list) and 0 <= index_to_delete < len(mevcut_notlar):
            del mevcut_notlar[index_to_delete]
            
            # 4. YENİ LİSTEYİ YAZ (SET)
            db.reference('/notlar').set(mevcut_notlar)
            print(f"Not (Index: {index_to_delete}) başarıyla silindi (PC UYUMLU).")
        else:
            print(f"UYARI: Silinecek not (Index: {index_to_delete}) LİSTE içinde bulunamadı.")

    except ValueError:
        # Hata: Gelen ID '-Mxyz...' gibi bir string (sayı değil), bu ESKİ formattır
        try:
            db.reference(f'/notlar/{not_id}').delete()
            print(f"Eski format (DICT) not (ID: {not_id}) silindi.")
        except Exception as e2:
            print(f"Eski format not silme de başarısız: {e2}")
    except Exception as e:
        print(f"Not silinirken HATA: {e}")
        
    return redirect(url_for('ana_sayfa'))


@app.route('/sil-calisma/<calisma_id>', methods=['GET'])
def sil_calisma(calisma_id):
    try:
        # 1. Gelen ID'yi index olarak dene
        index_to_delete = int(calisma_id)
        
        # 2. LİSTEYİ OKU
        mevcut_calismalar = db.reference('/calisma_takibi').get()
        
        # 3. Veri LİSTE ise ve index geçerliyse, SİL
        if isinstance(mevcut_calismalar, list) and 0 <= index_to_delete < len(mevcut_calismalar):
            del mevcut_calismalar[index_to_delete]
            
            # 4. YENİ LİSTEYİ YAZ (SET)
            db.reference('/calisma_takibi').set(mevcut_calismalar)
            print(f"Çalışma (Index: {index_to_delete}) başarıyla silindi (PC UYUMLU).")
        else:
            print(f"UYARI: Silinecek çalışma (Index: {index_to_delete}) LİSTE içinde bulunamadı.")

    except ValueError:
        # Hata: Gelen ID '-Mxyz...' gibi bir string (sayı değil), bu ESKİ formattır
        try:
            db.reference(f'/calisma_takibi/{calisma_id}').delete()
            print(f"Eski format (DICT) çalışma (ID: {calisma_id}) silindi.")
        except Exception as e2:
            print(f"Eski format çalışma silme de başarısız: {e2}")
    except Exception as e:
        print(f"Çalışma silinirken HATA: {e}")
        
    return redirect(url_for('calisma_takibi_sayfasi'))


@app.route('/sil-sinav/<sinav_id>', methods=['GET'])
def sil_sinav(sinav_id):
    try:
        # 1. Gelen ID'yi index olarak dene
        index_to_delete = int(sinav_id)
        
        # 2. LİSTEYİ OKU
        mevcut_sinavlar = db.reference('/sinavlar').get()
        
        # 3. Veri LİSTE ise ve index geçerliyse, SİL
        if isinstance(mevcut_sinavlar, list) and 0 <= index_to_delete < len(mevcut_sinavlar):
            del mevcut_sinavlar[index_to_delete]
            
            # 4. YENİ LİSTEYİ YAZ (SET)
            db.reference('/sinavlar').set(mevcut_sinavlar)
            print(f"Sınav (Index: {index_to_delete}) başarıyla silindi (PC UYUMLU).")
        else:
            print(f"UYARI: Silinecek sınav (Index: {index_to_delete}) LİSTE içinde bulunamadı.")

    except ValueError:
        # Hata: Gelen ID '-Mxyz...' gibi bir string (sayı değil), bu ESKİ formattır
        try:
            db.reference(f'/sinavlar/{sinav_id}').delete()
            print(f"Eski format (DICT) sınav (ID: {sinav_id}) silindi.")
        except Exception as e2:
            print(f"Eski format sınav silme de başarısız: {e2}")
    except Exception as e:
        print(f"Sınav silinirken HATA: {e}")
    
    return redirect(url_for('ana_sayfa'))

# =================================================================
# === 👑 SİLME FONKSİYONLARI BİTTİ 👑 ===
# =================================================================

@app.route('/TEMIZLE_ESKI_VERILERI_TEHLIKELI')
def temizle_eski_verileri():
    try:
        # PC programı LİSTE beklediği için en güvenli temizleme
        # oraya boş bir LİSTE set etmektir.
        db.reference('/notlar').set([])
        db.reference('/sinavlar').set([])
        db.reference('/calisma_takibi').set([])
        print("KRİTİK UYARI: TÜM VERİLER SIFIRLANDI (PC UYUMLU LİSTE FORMATINDA).")
    except Exception as e:
        print(f"TEMİZLEME SIRASINDA HATA: {e}")
    return redirect(url_for('ana_sayfa'))

# -----------------------------------------------------------------
# --- 👑 MUCK GİBİ KOD (PDF TARAYICI + SENKRONİZASYON) 👑 ---
# -----------------------------------------------------------------

# ==================================================================
# === 👑 KRAL DÜZELTMESİ (FİNAL FİNAL): ÇİFT FORMATLI PDF OKUMA 👑 ===
# ==================================================================
def process_pdf_text(pdf_file_stream):
    """ 
    PDF'i okur.
    HEM '...yap' (ödev) arar.
    HEM 'SINAV: ...' (tek satır sınav) arar.
    HEM DE 'SINAV' (başlık) ve altındaki 'Matematik ...' (çoklu satır sınav) arar.
    """
    homeworks = []
    exams = [] # Sınavlar için yeni liste
    
    try:
        pdf_document = fitz.open(stream=pdf_file_stream, filetype="pdf")
        full_text = ""
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            full_text += page.get_text("text")
            
        lines = full_text.split('\n')
        
        # === 👑 KRAL GÜNCELLEMESİ: Multi-line Sınav Taraması 👑 ===
        found_sinav_header = False 
        # === 👑 Güncelleme Bitti 👑 ===

        for line in lines:
            trimmed_line = line.strip() 
            if not trimmed_line: # Boş satırları atla
                continue

            # 1. KURAL: Ödevler (sonu "yap" ile bitenler)
            if trimmed_line.endswith('yap') or trimmed_line.endswith('yap.'):
                homeworks.append(trimmed_line)
                found_sinav_header = False # Ödevse, sınav başlığı değildir
            
            # === 👑 KRAL GÜNCELLEMESİ: YENİ 2. KURAL (Multi-line) 👑 ===
            # Eğer bir önceki satır "SINAV" ise, bu satırı işle
            elif found_sinav_header:
                # Bu satır "Matematik 14.11.2025" olmalı
                # Tarihi (GG.AA.YYYY) formatında bul
                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', trimmed_line)
                exam_name = trimmed_line
                exam_date = "Tarih Belirtilmemiş"

                if date_match:
                    exam_date_raw = date_match.group(1) # Bu '14.11.2025'
                    # === 👑 KRAL DÜZELTMESİ: Tarihi PC formatına (YYYY-AA-GG) çevir 👑 ===
                    try:
                        dt_obj = datetime.datetime.strptime(exam_date_raw, "%d.%m.%Y")
                        exam_date = dt_obj.strftime("%Y-%m-%d") # '2025-11-14' oldu
                    except ValueError:
                        exam_date = exam_date_raw # Çeviremezse, 'Belirsiz' olmasın diye ham halini yaz
                    # === 👑 Düzeltme Bitti 👑 ===
                    exam_name = trimmed_line.replace(date_match.group(1), '').strip()

                if exam_name: # Boş satırları eklemesin
                    exams.append({"ad": exam_name, "tarih": exam_date})
                
                found_sinav_header = False # Başlığı işledik, sıfırla

            # Eğer satır tam olarak "SINAV" ise, bir sonraki satırın sınav detayı olduğunu işaretle
            elif trimmed_line.upper() == 'SINAV': # Büyük/küçük harf duyarsız
                found_sinav_header = True
                # Bu satırı geç, bir sonrakine bak
                continue 
            # === 👑 Yeni Kural Bitti 👑 ===

            # 3. KURAL: ESKİ (Single-line "SINAV:") formatı
            elif trimmed_line.upper().startswith('SINAV:'):
                try:
                    # 'SINAV:' kelimesini (büyük/küçük) at
                    text_after_sinav = re.split(r'SINAV:', trimmed_line, flags=re.IGNORECASE)[1].strip()
                    
                    # Varsayılan değerleri ayarla
                    exam_name = text_after_sinav # Önce hepsini isim san
                    exam_date = "Tarih Belirtilmemiş"
                    date_found = False # Tarihi bulduk mu?

                    # 1. DENEME: YYYY-AA-GG formatını ara (PC formatı)
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text_after_sinav)
                    if date_match:
                        exam_date = date_match.group(1)
                        exam_name = text_after_sinav.replace(exam_date, '').strip()
                        date_found = True
                    
                    # 2. DENEME: GG.AA.YYYY formatını ara (PDF formatı)
                    if not date_found:
                        date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', text_after_sinav)
                        if date_match:
                            exam_date_raw = date_match.group(1) # '16.11.2025'
                            # PC formatına çevir
                            try:
                                dt_obj = datetime.datetime.strptime(exam_date_raw, "%d.%m.%Y")
                                exam_date = dt_obj.strftime("%Y-%m-%d") # '2025-11-16'
                            except ValueError:
                                exam_date = exam_date_raw # Çeviremezse ham halini yaz
                            
                            # Adı temizle
                            exam_name = text_after_sinav.replace(exam_date_raw, '').strip()
                            date_found = True

                    # 3. DENEME: GG-AA-YYYY formatını ara (SENİN FORMATIN)
                    if not date_found:
                        date_match = re.search(r'(\d{2}-\d{2}-\d{4})', text_after_sinav) 
                        if date_match:
                            exam_date_raw = date_match.group(1) # '15-11-2025'
                            try:
                                # Bunu da YYYY-MM-DD formatına çevir
                                dt_obj = datetime.datetime.strptime(exam_date_raw, "%d-%m-%Y") 
                                exam_date = dt_obj.strftime("%Y-%m-%d") # '2025-11-15'
                            except ValueError:
                                exam_date = exam_date_raw # Çeviremezse ham halini yaz
                            
                            # Adı temizle
                            exam_name = text_after_sinav.replace(exam_date_raw, '').strip()
                            date_found = True
                    # === 👑👑👑 DÜZELTME BİTTİ 👑👑👑 ===

                    # İsimde kalmış olabilecek "Tarih:" kelimesini temizle
                    exam_name = re.sub(r'Tarih:', '', exam_name, flags=re.IGNORECASE).strip()
                    exam_name = re.sub(r'TARİH:', '', exam_name, flags=re.IGNORECASE).strip()

                    if exam_name: 
                        exams.append({"ad": exam_name, "tarih": exam_date})
                        
                except Exception as e:
                    print(f"Sınav satırı formatı okunamadı: {trimmed_line}, Hata: {e}")
                
                found_sinav_header = False # Bu da bir sınavdı, başlığı sıfırla
            
            else:
                # Bu satır alakasız bir şey, başlığı sıfırla
                found_sinav_header = False

    except Exception as e:
        print(f"PDF OKUMA HATASI: {e}")
        return [], [], f"PDF işlenirken bir hata oluştu: {e}"
    
    # Artık 2 liste, 1 hata mesajı döndürür
    return homeworks, exams, None 
# ==================================================================
# === 👑 PDF OKUMA DÜZELTMESİ BİTTİ 👑 ===
# ==================================================================


# =================================================================
# === 👑 KRAL DÜZELTMESİ (FİNAL SÜRÜM): AKILLI TARAYICI 👑 ===
# =================================================================
@app.route('/akilli-tarayici', methods=['GET', 'POST'])
def akilli_tarayici_sayfasi():
    
    kayit_basarili_not = False
    kayit_basarili_sinav = False
    homeworks_result = [] 
    exams_result = [] # Sınavlar için yeni liste
    error_message = None 

    if request.method == 'POST':
        # === 👑 KRAL İSTEĞİ: YENİ RESİM -> PDF DÖNÜŞTÜRÜCÜ KONTROLÜ 👑 ===
        # Form 'form_type' alanı gönderiyorsa, bu yeni formdur
        form_type = request.form.get('form_type')
        
        # 1. YENİ FORMSA (RESİMDEN PDF'E)
        if form_type == 'image_to_pdf':
            try:
                if 'resim_dosyalari' not in request.files:
                    error_msg = "Resim dosyası seçilmedi."
                    return render_template('akilli_tarayici.html', error=error_msg, homeworks=None, exams=None, kaydedildi_not=False, kaydedildi_sinav=False)
                
                files = request.files.getlist('resim_dosyalari')
                
                if not files or files[0].filename == '':
                    error_msg = "Resim dosyası seçilmedi."
                    return render_template('akilli_tarayici.html', error=error_msg, homeworks=None, exams=None, kaydedildi_not=False, kaydedildi_sinav=False)

                image_list = []
                allowed_extensions = {'.png', '.jpg', '.jpeg'}

                for file in files:
                    filename = secure_filename(file.filename)
                    file_ext = os.path.splitext(filename)[1].lower()
                    
                    if file_ext in allowed_extensions:
                        try:
                            img = Image.open(file.stream).convert('RGB')
                            image_list.append(img)
                        except Exception as e:
                            print(f"Resim dosyası açılamadı ({filename}): {e}")
                    
                if not image_list:
                    error_msg = "Hata: Geçerli bir PNG veya JPG dosyası bulunamadı."
                    return render_template('akilli_tarayici.html', error=error_msg, homeworks=None, exams=None, kaydedildi_not=False, kaydedildi_sinav=False)

                first_image = image_list[0]
                other_images = image_list[1:]
                out_filename = f"resimden_pdf_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                out_path = os.path.join(app.config['UPLOAD_FOLDER'], out_filename)
                first_image.save(out_path, save_all=True, append_images=other_images, resolution=100.0)
                
                print(f"{len(image_list)} adet resim PDF'e dönüştürüldü: {out_filename}")
                
                return send_from_directory(app.config['UPLOAD_FOLDER'], out_filename, as_attachment=True)

            except Exception as e:
                print(f"Resimden PDF'e dönüştürme hatası: {e}")
                error_msg = f"Dönüştürme sırasında bir hata oluştu: {e}"
                return render_template('akilli_tarayici.html', error=error_msg, homeworks=None, exams=None, kaydedildi_not=False, kaydedildi_sinav=False)
        
        # 2. ESKİ FORMSA (PDF TARAYICI)
        elif form_type == 'pdf_scanner':
            if 'file' not in request.files or request.files['file'].filename == '':
                error_message = "Dosya seçilmedi. Lütfen bir PDF dosyası yükleyin."
                return render_template('akilli_tarayici.html', homeworks=None, exams=None, error=error_message, kaydedildi_not=False, kaydedildi_sinav=False)
            
            file = request.files['file']
            scan_type = request.form.get('scan_type', 'odevler') 

            if file and file.filename.endswith('.pdf'):
                try:
                    pdf_stream = file.read()
                    homeworks_result, exams_result, error_message = process_pdf_text(pdf_stream)
                    
                    if error_message:
                         return render_template('akilli_tarayici.html', homeworks=None, exams=None, error=error_message, kaydedildi_not=False, kaydedildi_sinav=False)

                    if scan_type == 'odevler':
                        if homeworks_result: 
                            print(f"Akıllı Tarayıcı {len(homeworks_result)} adet ödev buldu. Kaydediliyor...")
                            try:
                                mevcut_notlar = db.reference('/notlar').get()
                                data_list = []
                                if isinstance(mevcut_notlar, dict): data_list = list(mevcut_notlar.values())
                                elif isinstance(mevcut_notlar, list): data_list = mevcut_notlar
                                for hw_text in homeworks_result:
                                    data_list.append({
                                        "text": f"PDF Tarayıcı: {hw_text}",
                                        "tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                                    }) 
                                db.reference('/notlar').set(data_list)
                                kayit_basarili_not = True
                                print("Not Senkronizasyonu (PC UYUMLU SET) tamamlandı!")
                            except Exception as e:
                                print(f"NOT SENKRONİZASYON HATASI (SET): {e}")
                                error_message = f"Notlar kaydedilirken bir veritabanı hatası oluştu: {e}"
                        elif exams_result: 
                            error_message = "Bu PDF'te ödev bulunamadı, ancak sınav(lar) bulundu. Lütfen 'Sadece Sınavları Tara' seçeneğini seçip tekrar deneyin."
                        else: 
                             error_message = "Bu PDF'te '...yap' ile biten bir ödev bulunamadı."

                    elif scan_type == 'sinavlar':
                        if exams_result: 
                            print(f"Akıllı Tarayıcı {len(exams_result)} adet sınav buldu. Kaydediliyor...")
                            try:
                                mevcut_sinavlar = db.reference('/sinavlar').get()
                                if not isinstance(mevcut_sinavlar, list):
                                    mevcut_sinavlar = []
                                for ex in exams_result:
                                    mevcut_sinavlar.append({
                                        "ad": ex['ad'], 
                                        "tarih": ex['tarih'], 
                                        "kaynak": "PDF Tarayıcı" 
                                    })
                                db.reference('/sinavlar').set(mevcut_sinavlar)
                                kayit_basarili_sinav = True
                                print("Sınav Senkronizasyonu (PC UYUMLU SET) tamamlandı!")
                            except Exception as e:
                                print(f"SINAV SENKRONİZASYON HATASI (SET): {e}")
                                error_message = f"Sınavlar kaydedilirken bir veritabanı hatası oluştu: {e}"
                        elif homeworks_result: 
                            error_message = "Bu PDF'te sınav bulunamadı, ancak '...yap' ile biten ödevler bulundu. Lütfen 'Sadece Ödevleri Tara' seçeneğini seçip tekrar deneyin."
                        else: 
                            error_message = "Bu PDF'te 'SINAV' başlığı veya 'SINAV:' ile başlayan bir içerik bulunamadı."
                    
                except Exception as e:
                    print(f"PDF İŞLEME KRİTİK HATASI: {e}")
                    error_message = f"PDF işlenirken kritik bir hata oluştu: {e}"
            else:
                 error_message = "Hata: Lütfen sadece .pdf uzantılı bir dosya yükleyin."
                 
            return render_template('akilli_tarayici.html', 
                                   homeworks=homeworks_result,
                                   exams=exams_result,
                                   kaydedildi_not=kayit_basarili_not,
                                   kaydedildi_sinav=kayit_basarili_sinav,
                                   error=error_message)
        
        else:
            # Eğer form_type gelmemişse, eski bir formdandır, hata ver
            error_message = "Form hatası: Lütfen sayfayı yenileyin."
            return render_template('akilli_tarayici.html', error=error_message, homeworks=None, exams=None, kaydedildi_not=False, kaydedildi_sinav=False)

    # Eğer sayfa ilk kez açılıyorsa (GET)
    return render_template('akilli_tarayici.html', homeworks=None, exams=None, error=None, kaydedildi_not=False, kaydedildi_sinav=False)
# ----------------------------------------------------
# --- PDF TARAYICI BİTİŞ ---
# ----------------------------------------------------


# =================================================================
# === 👑 KRAL İSTEĞİ: YENİ RESİM -> PDF DÖNÜŞTÜRÜCÜ (ESKİ YOL) 👑 ===
# =================================================================
@app.route('/cevir-resimden-pdf-ye', methods=['POST'])
def cevir_resimden_pdf_ye():
    
    # Hata mesajı için varsayılan değişkenleri ayarla (template çökmesin diye)
    default_template_vars = {
        "homeworks": None, "exams": None, 
        "kaydedildi_not": False, "kaydedildi_sinav": False
    }

    try:
        if 'resim_dosyalari' not in request.files:
            error_msg = "Resim dosyası seçilmedi."
            return render_template('akilli_tarayici.html', error=error_msg, **default_template_vars)
        
        files = request.files.getlist('resim_dosyalari')
        
        if not files or files[0].filename == '':
            error_msg = "Resim dosyası seçilmedi."
            return render_template('akilli_tarayici.html', error=error_msg, **default_template_vars)

        image_list = []
        allowed_extensions = {'.png', '.jpg', '.jpeg'}

        for file in files:
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()
            
            if file_ext in allowed_extensions:
                try:
                    # Görüntüyü 'RGB'ye dönüştürerek kaydetme sorunlarını (örn. RGBA, P) engelle
                    img = Image.open(file.stream).convert('RGB')
                    image_list.append(img)
                except Exception as e:
                    print(f"Resim dosyası açılamadı ({filename}): {e}")
                    # Bu dosyayı atla
            
        if not image_list:
            error_msg = "Hata: Geçerli bir PNG veya JPG dosyası bulunamadı."
            return render_template('akilli_tarayici.html', error=error_msg, **default_template_vars)

        # PDF'i hazırla
        first_image = image_list[0]
        other_images = image_list[1:]
        
        out_filename = f"resimden_pdf_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        out_path = os.path.join(app.config['UPLOAD_FOLDER'], out_filename)

        # İlk resmi kaydet, diğerlerini ona ekle
        first_image.save(out_path, save_all=True, append_images=other_images, resolution=100.0)
        
        print(f"{len(image_list)} adet resim PDF'e dönüştürüldü: {out_filename}")
        
        # Kullanıcıya PDF'i yolla
        return send_from_directory(app.config['UPLOAD_FOLDER'], out_filename, as_attachment=True)

    except Exception as e:
        print(f"Resimden PDF'e dönüştürme hatası: {e}")
        error_msg = f"Dönüştürme sırasında bir hata oluştu: {e}"
        return render_template('akilli_tarayici.html', error=error_msg, **default_template_vars)
# =================================================================
# === 👑 DÖNÜŞTÜRÜCÜ BİTTİ 👑 ===
# =================================================================


# -----------------------------------------------------------------
# --- 👑 KRAL İSTEĞİ: HIZLI EKLE KÜTÜPHANESİ BEYNİ 👑 ---
# -----------------------------------------------------------------

def scan_sinavlar_klasoru():
    """ 'Sınavlar' klasörünü tarar ve bir dict döndürür. """
    sinavlar_data = {}
    base_path = os.path.join(app.root_path, 'Sınavlar')
    
    if not os.path.isdir(base_path):
        print("HATA: 'Sınavlar' klasörü ana dizinde bulunamadı.")
        return {"Hata": ["'Sınavlar' klasörü bulunamadı."]}

    try:
        for bolum_adi in os.listdir(base_path):
            bolum_path = os.path.join(base_path, bolum_adi)
            if os.path.isdir(bolum_path):
                ders_listesi = []
                for ders_adi in os.listdir(bolum_path):
                    if os.path.isdir(os.path.join(bolum_path, ders_adi)):
                        ders_listesi.append(ders_adi)
                ders_listesi.sort() 
                sinavlar_data[bolum_adi] = ders_listesi
                
    except Exception as e:
        print(f"Sınavlar klasörü okunurken hata: {e}")
        return {"Hata": [f"Klasör okunurken hata: {e}"]}
        
    return sinavlar_data

# =================================================================
# === 👑 KRAL DÜZELTMESİ (FİNAL SÜRÜM): HIZLI EKLE AĞACI 👑 ===
# =================================================================
def scan_calisma_klasoru():
    """ 
    'ÇALIŞMA' (HEPSİ BÜYÜK) klasörünü tarar ve iç içe bir dict döndürür.
    Bozuk olan 'os.walk' mantığı yerine 3 seviyeli 'os.listdir' mantığı eklendi.
    Bu kod senin klasör yapınla (Bölüm -> Ders -> Konu.txt) %100 uyumlu.
    """
    calisma_data = {}
    
    # 1. 'ÇALIŞMA' (büyük harf) klasörünü ara
    base_path = os.path.join(app.root_path, 'ÇALIŞMA') 
    
    # 2. Hata Kontrolü: Klasör yoksa, HTML'e hata yolla
    if not os.path.isdir(base_path):
        print(f"HATA: 'ÇALIŞMA' klasörü ana dizinde bulunamadı: {base_path}")
        return {"Hata": ["'ÇALIŞMA' klasörü ana dizinde bulunamadı."]}

    try:
        # 3. Klasörün *içinden* başla (Bölüm seviyesi)
        # Örn: '1)Sözel', '2)Sayısal'
        # Güvenlik için gizli/sistem dosyalarını atla
        bolum_listesi = [b for b in os.listdir(base_path) if not b.startswith('.')]
        for bolum_adi in sorted(bolum_listesi):
            bolum_path = os.path.join(base_path, bolum_adi)
            
            # Sadece klasör olanları al
            if os.path.isdir(bolum_path):
                calisma_data[bolum_adi] = {} # {'1)Sözel': {}}
                
                # 4. Bölümün *içine* gir (Ders seviyesi)
                # Örn: '1)Türk Dili ve Edebiyatı'
                ders_listesi = [d for d in os.listdir(bolum_path) if not d.startswith('.')]
                for ders_adi in sorted(ders_listesi):
                    ders_path = os.path.join(bolum_path, ders_adi)
                    
                    # Sadece klasör olanları al
                    if os.path.isdir(ders_path):
                        calisma_data[bolum_adi][ders_adi] = [] # {'1)Sözel': {'1)Türk Dili...': []}}
                        
                        # 5. Dersin *içine* gir (Konu seviyesi)
                        # Örn: '1.Ünite Sözün İnceliği.txt'
                        konu_listesi = [k for k in os.listdir(ders_path) if not k.startswith('.')]
                        for konu_dosyasi in sorted(konu_listesi):
                            konu_path = os.path.join(ders_path, konu_dosyasi)
                            
                            # Sadece .txt olanları al
                            if os.path.isfile(konu_path) and konu_dosyasi.lower().endswith('.txt'):
                                # .txt uzantısını kaldır
                                konu_adi = os.path.splitext(konu_dosyasi)[0] 
                                calisma_data[bolum_adi][ders_adi].append(konu_adi)
                        
                        # Eğer dersin içi boşsa (txt yoksa), o dersi listeden sil
                        if not calisma_data[bolum_adi][ders_adi]:
                            del calisma_data[bolum_adi][ders_adi]

                # Eğer bölümün içi boşsa (ders klasörü yoksa), o bölümü sil
                if not calisma_data[bolum_adi]:
                    del calisma_data[bolum_adi]

    except Exception as e:
        print(f"ÇALIŞMA klasörü okunurken hata: {e}")
        return {"Hata": [f"Klasör okunurken hata: {e}"]}
    
    # 6. Doldurulmuş veriyi yolla
    if not calisma_data:
        print("Bilgi: 'ÇALIŞMA' klasörü bulundu ama içinde (Bölüm/Ders/Konu.txt) yapısında içerik yok.")
    
    return calisma_data
# =================================================================
# === 👑 HIZLI EKLE AĞACI DÜZELTMESİ BİTTİ 👑 ===
# =================================================================


@app.route('/hizli-ekle')
def hizli_ekle_sayfasi():
    sinavlar_data = scan_sinavlar_klasoru()
    calisma_data = scan_calisma_klasoru()
    
    return render_template('hizli-ekle.html', 
                           sinavlar_data=sinavlar_data, 
                           calisma_data=calisma_data)
# ----------------------------------------------------
# --- HIZLI EKLE KÜTÜPHANESİ BİTİŞ ---
# ----------------------------------------------------


# -----------------------------------------------------------------
# --- 👑 KRAL İSTEĞİ: SINAV COMBOBOX BEYNİ 👑 ---
# -----------------------------------------------------------------

def scan_tum_dersleri():
    """ 
    👑 KRAL GÜNCELLEMESİ (14.11.2025): 
    Ders listesi artık klasörden taranmıyor!
    Kralın isteği üzerine alfabetik olarak SABİT LİSTE kullanılıyor.
    (İngilizce'deki yazım hatasını da düzelttim kral 🫡)
    """
    
    # Senin verdiğin, alfabetik sıraya dizilmiş tam liste:
    dersler = [
        "Almanca",
        "Biyoloji",
        "Coğrafya",
        "Din Kültürü",
        "Edebiyat",
        "Fizik",
        "İngilizce",
        "Kimya",
        "Matematik",
        "Peygamberimizin Hayatı",
        "Proje",
        "Sağlık",
        "Tarih"
    ]
    
    # Liste zaten alfabetik olduğu için .sort() çağırmaya gerek yok.
    return dersler

@app.context_processor
def inject_dersler():
    """ Bu SİHİRLİ kod, ders listesini TÜM HTML SAYFALARINA yollar. """
    tum_dersler = scan_tum_dersleri()
    return dict(global_ders_listesi=tum_dersler) 

# --- 👑 COMBOBOX BEYNİ BİTTİ 👑 ---


if __name__ == '__main__':
    app.run(debug=True)