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
# 👑 DRIVE İÇİN GERİ GELDİLER 👑
from google.oauth2 import service_account
from googleapiclient.discovery import build 

import helpers
import fitz  # PyMuPDF

# =========================================================
# === 👑 PURE PYTHON PDF->TXT FONKSİYONU 👑 ===
# =========================================================
def pdf_to_txt_pure(pdf_path, txt_path):
    try:
        full_text = ""
        with fitz.open(pdf_path) as pdf_document:
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                full_text += page.get_text("text")
        
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print("Pure Python (fitz) ile PDF'den TXT'ye dönüştürme başarılı.")
    except Exception as e:
        print(f"Pure Python (fitz) PDF okuma hatası: {e}")
        raise e 

# =========================================================
# === AYARLAR VE BAĞLANTILAR ===
# =========================================================
KEY_FILE = "ders-program-e07f2-firebase-adminsdk-fbsvc-eff01c1173.json"
DATABASE_URL = "https://ders-program-e07f2-default-rtdb.europe-west1.firebasedatabase.app/"
# 👑 DRIVE AYARLARI GERİ GELDİ 👑
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
DRIVE_KEY_PATH = "" 
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

try:
    # Hem Firebase Hem Drive için Anahtar Yolu
    DRIVE_KEY_PATH = os.path.join(os.path.dirname(__file__), KEY_FILE)
    
    # Firebase Başlat
    if not firebase_admin._apps:
        cred = credentials.Certificate(DRIVE_KEY_PATH)
        firebase_admin.initialize_app(cred, {
            'databaseURL': DATABASE_URL
        })
        print("Firebase bağlantısı BAŞARILI!")
except Exception as e:
    if "already initialized" not in str(e):
        print(f"Firebase bağlantı HATASI: {e}")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kral_sarbay_cok_gizli_anahtar_12345'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


# =========================================================
# === BEYİN FONKSİYONLARI (Veri Çekme) ===
# =========================================================

def get_kral_selamlama():
    saat = datetime.datetime.now().hour
    if 5 <= saat < 12: return "Günaydın! ☀️"
    elif 12 <= saat < 18: return "İyi Günler! 😎"
    else: return "İyi Akşamlar! 🌙"

def get_yaklasan_sinavlar():
    yaklasan_sinavlar_raw = []
    try:
        sinav_verisi = db.reference('/sinavlar').get()
        today = datetime.datetime.now().date()
        
        if sinav_verisi and isinstance(sinav_verisi, list):
            for i, sinav in enumerate(sinav_verisi):
                try:
                    sinav_tarihi_str = sinav.get("tarih")
                    try:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%Y-%m-%d").date()
                    except ValueError:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%d.%m.%Y").date()
                    
                    kalan_gun = (sinav_tarihi - today).days
                    if kalan_gun >= 0:
                        yaklasan_sinavlar_raw.append({"id": i, "ad": sinav.get("ad"), "kalan_gun": kalan_gun})
                except Exception: continue
        elif sinav_verisi and isinstance(sinav_verisi, dict):
            for key, sinav in sinav_verisi.items():
                try:
                    sinav_tarihi_str = sinav.get("tarih")
                    try:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%Y-%m-%d").date()
                    except ValueError:
                        sinav_tarihi = datetime.datetime.strptime(sinav_tarihi_str, "%d.%m.%Y").date()
                    kalan_gun = (sinav_tarihi - today).days
                    if kalan_gun >= 0:
                        yaklasan_sinavlar_raw.append({"id": key, "ad": sinav.get("ad"), "kalan_gun": kalan_gun})
                except Exception: continue

        yaklasan_sinavlar_raw.sort(key=lambda x: x["kalan_gun"])
    except Exception as e: print(f"Firebase sınav hatası: {e}")
    return yaklasan_sinavlar_raw

def get_son_calismalar():
    son_calismalar_raw = []
    try:
        calisma_verisi = db.reference('/calisma_takibi').get()
        list_view = []
        if calisma_verisi and isinstance(calisma_verisi, list):
             list_view = [{"id": i, **v} for i, v in enumerate(calisma_verisi)]
        elif calisma_verisi and isinstance(calisma_verisi, dict):
            list_view = [{"id": k, **v} for k, v in calisma_verisi.items()]
            
        list_view.sort(key=lambda x: x.get('tarih', ''), reverse=True)

        for kayit in list_view[:5]:
            son_calismalar_raw.append({
                "id": kayit.get('id'),
                "text": f"{kayit.get('ders')} - {kayit.get('konu')} ({kayit.get('sure')} dk)"
            })
    except Exception as e: print(f"Firebase çalışma hatası: {e}")
    return son_calismalar_raw
    
def get_notlar():
    not_listesi = []
    try:
        not_verisi = db.reference('/notlar').get()
        if not_verisi and isinstance(not_verisi, dict): 
            for key, value in not_verisi.items():
                not_listesi.append({"id": key, "text": value.get("text", "Boş not")})
        elif not_verisi and isinstance(not_verisi, list):
            for i, item in enumerate(not_verisi):
                if isinstance(item, dict):
                    not_listesi.append({"id": i, "text": item.get("text", "Boş not")})
                else:
                    not_listesi.append({"id": i, "text": str(item)})
    except Exception as e: print(f"Firebase not hatası: {e}")
    return not_listesi

def get_butun_calismalar():
    butun_calismalar = []
    try:
        calisma_verisi = db.reference('/calisma_takibi').get()
        list_view = []
        if calisma_verisi and isinstance(calisma_verisi, list):
            list_view = [{"id": i, **v} for i, v in enumerate(calisma_verisi)]
        elif calisma_verisi and isinstance(calisma_verisi, dict):
            list_view = [{"id": k, **v} for k, v in calisma_verisi.items()]
        
        list_view.sort(key=lambda x: x.get('tarih', ''), reverse=True)
        
        for kayit in list_view:
            butun_calismalar.append({
                "id": kayit.get('id'),
                "ders": kayit.get('ders', 'N/A'),
                "konu": kayit.get('konu', 'N/A'),
                "sure": kayit.get('sure', '0'),
                "tarih": kayit.get('tarih', 'Tarih Yok')
            })
    except Exception as e: print(f"Bütün çalışmalar hatası: {e}")
    return butun_calismalar

def natural_sort_key(s):
    ad = s.get('ad', str(s)) 
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('(\d+)', ad)]

def get_logo_path(item_name):
    logo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'logos')
    if not os.path.isdir(logo_dir): return None
    clean_name = re.sub(r'^\d+\)|\d+\)', '', item_name).strip()
    search_names = [clean_name, item_name] 
    logo_files = {os.path.splitext(f)[0].lower(): f for f in os.listdir(logo_dir)}
    
    for name_to_search in search_names:
        if not name_to_search: continue
        if name_to_search.lower() in logo_files:
            return url_for('static', filename='logos/' + logo_files[name_to_search.lower()])
    return None

def generate_app_link(app_name):
    app_map = {
        "Pakodemy": "pakodemy://app", "Derslig": "derslig://app", "Kunduz": "kunduz://app",
        "ChatGPT": "chatgpt://", "Gemini": "gemini://", "Copilot": "ms-copilot://", "DeepSeek": "deepseek://",
        "HIZ Kütüphanesi": "hizkutuphane://", "AnkaraVideoÇözüm": "ankaravideo://",
        "SonuçMobilKütüphanesi": "sonucmobil://", "TATSDijitalKitap": "tats://", 
    }
    return app_map.get(app_name, "#") 

# =========================================================
# === 👑 SAYFA YOLLARI (ROUTES) 👑 ===
# =========================================================

@app.route('/')
def ana_sayfa():
    return render_template('ana_sayfa.html', 
                           selamlama_mesaji=get_kral_selamlama(), 
                           sinav_listesi=get_yaklasan_sinavlar(),
                           not_listesi=get_notlar(),
                           calisma_listesi=get_son_calismalar())

# --- 👑 DERSLER SAYFASI (ESKİ DRIVE MODU) 👑 ---
@app.route('/dersler')
def dersler_sayfasi():
    ders_listesi = []
    try:
        # DRIVE BAĞLANTISI YAPILIYOR
        creds = service_account.Credentials.from_service_account_file(DRIVE_KEY_PATH, scopes=SCOPES)
        service = build('drive', 'v3', credentials=creds)
        
        # 'Dersler' klasörünü bul
        q_query = "name='Dersler' and mimeType='application/vnd.google-apps.folder'"
        results = service.files().list(q=q_query, fields="files(id, name)").execute()
        items = results.get('files', [])
        
        if not items:
            return render_template('dersler.html', dosya_listesi=[{"ad": "HATA: Drive'da 'Dersler' klasörü yok.", "link": "#"}])
        
        dersler_folder_id = items[0].get('id')
        
        # Klasörün içindekileri çek
        q_query_files = f"'{dersler_folder_id}' in parents and trashed=false"
        file_results = service.files().list(q=q_query_files, pageSize=50, fields="files(name, webViewLink, mimeType)").execute()
        files = file_results.get('files', [])
        
        if not files:
            return render_template('dersler.html', dosya_listesi=[{"ad": "Drive klasörü boş kral.", "link": "#"}])
        
        for file in files:
            link = file.get('webViewLink')
            mime_type = file.get('mimeType')
            file_name = file.get('name')
            # Google Doc ise önizleme linki yap
            if 'google-apps' in mime_type:
                link = link.replace('/edit?usp=drivesdk', '/preview?rm=minimal')
                link = link.replace('/edit', '/preview?rm=minimal')
            
            logo_path = get_logo_path(file_name)
            ders_listesi.append({"ad": file_name, "link": link, "logo": logo_path})
            
        ders_listesi.sort(key=natural_sort_key)
        return render_template('dersler.html', dosya_listesi=ders_listesi)
        
    except Exception as e:
        print(f"Drive hatası: {e}")
        return render_template('dersler.html', dosya_listesi=[{"ad": f"HATA: {e}", "link": "#"}])


# --- 👑 YENİ SAYFALAR (KLASÖRDEN OKUR) 👑 ---
@app.route('/ahlak-metinleri')
def ahlak_sayfasi():
    klasor_yolu = os.path.join(app.root_path, 'static', 'ahlak')
    dosyalar = []
    if os.path.exists(klasor_yolu):
        dosyalar = [f for f in os.listdir(klasor_yolu) if os.path.isfile(os.path.join(klasor_yolu, f)) and not f.startswith('.')]
    dosyalar.sort()
    return render_template('ahlak.html', dosya_listesi=dosyalar, baslik="Ahlak Metinleri")

@app.route('/peygamberimizin-hayati')
def peygamber_sayfasi():
    klasor_yolu = os.path.join(app.root_path, 'static', 'peygamber')
    dosyalar = []
    if os.path.exists(klasor_yolu):
        dosyalar = [f for f in os.listdir(klasor_yolu) if os.path.isfile(os.path.join(klasor_yolu, f)) and not f.startswith('.')]
    dosyalar.sort()
    return render_template('peygamber.html', dosya_listesi=dosyalar, baslik="Peygamberimizin Hayatı")

@app.route('/proje-tasarimi')
def proje_sayfasi():
    klasor_yolu = os.path.join(app.root_path, 'static', 'proje')
    dosyalar = []
    if os.path.exists(klasor_yolu):
        dosyalar = [f for f in os.listdir(klasor_yolu) if os.path.isfile(os.path.join(klasor_yolu, f)) and not f.startswith('.')]
    dosyalar.sort()
    return render_template('proje.html', dosya_listesi=dosyalar, baslik="Proje Tasarımı")

# --- DİĞER SAYFALAR ---
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
            if ders and konu and sure > 0:
                mevcut_calismalar = db.reference('/calisma_takibi').get()
                if not isinstance(mevcut_calismalar, list): mevcut_calismalar = [] 
                yeni_kayit = {
                    "ders": ders, "konu": konu, "sure": sure,
                    "tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "kaynak": "TELEFON"
                }
                mevcut_calismalar.append(yeni_kayit)
                db.reference('/calisma_takibi').set(mevcut_calismalar)
        except Exception as e: print(f"Çalışma ekleme hatası: {e}")
        return redirect(url_for('calisma_takibi_sayfasi'))
    
    butun_calismalar = get_butun_calismalar() 
    calisma_data_agaci = scan_calisma_klasoru()
    return render_template('calisma_takibi.html', calisma_listesi=butun_calismalar, calisma_data_agaci=calisma_data_agaci)

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
                img = Image.open(in_path).convert('RGB')
                img.save(out_path)
            elif operation == 'jpg2png':
                out_path = helpers.safe_out_path(in_path, ".png")
                img = Image.open(in_path)
                img.save(out_path)
            elif operation == 'pdf2txt': 
                out_path = helpers.safe_out_path(in_path, ".txt")
                pdf_to_txt_pure(in_path, out_path)
            elif operation == 'txt2pdf': out_path = helpers.safe_out_path(in_path, ".pdf"); helpers.txt_to_pdf(in_path, out_path)
            elif operation == 'docx2txt': out_path = helpers.safe_out_path(in_path, ".txt"); helpers.docx_to_txt(in_path, out_path)
            elif operation == 'txt2docx': out_path = helpers.safe_out_path(in_path, ".docx"); helpers.txt_to_docx(in_path, out_path)
            elif operation == 'excel2docx': out_path = helpers.safe_out_path(in_path, ".docx"); helpers.excel_to_docx(in_path, out_path)
            elif operation == 'excel2txt': out_path = helpers.safe_out_path(in_path, ".txt"); helpers.excel_to_txt(in_path, out_path)
            elif operation == 'pptx2ppsx': out_path = helpers.safe_out_path(in_path, ".ppsx"); shutil.copy(in_path, out_path) 
            elif operation == 'ppsx2pptx': out_path = helpers.safe_out_path(in_path, ".pptx"); shutil.copy(in_path, out_path)
            else: return render_template('donusturme_merkezi.html', hata="Geçersiz işlem!")

            out_filename = os.path.basename(out_path); out_dir = os.path.dirname(out_path)
            return send_from_directory(out_dir, out_filename, as_attachment=True)
        except Exception as e:
            return render_template('donusturme_merkezi.html', hata=f"Hata: {e}")
    return render_template('donusturme_merkezi.html', hata=None)

# --- EKLEME/SİLME FONKSİYONLARI ---
@app.route('/ekle-not', methods=['POST'])
def ekle_not():
    if request.method == 'POST':
        try:
            not_text = request.form['not_text']
            if not_text:
                mevcut_notlar = db.reference('/notlar').get()
                data_list = list(mevcut_notlar.values()) if isinstance(mevcut_notlar, dict) else (mevcut_notlar if isinstance(mevcut_notlar, list) else [])
                yeni_not = { "text": f"TELEFON: {not_text}", "tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M") } 
                data_list.append(yeni_not)
                db.reference('/notlar').set(data_list)
        except Exception as e: print(f"Not ekleme hatası: {e}")
    return redirect(url_for('ana_sayfa'))

@app.route('/ekle-sinav', methods=['POST'])
def ekle_sinav():
    if request.method == 'POST':
        try:
            sinav_adi = request.form['sinav_adi']
            if sinav_adi in ['Diger', 'Diğer']: sinav_adi = request.form.get('sinav_adi_manual', 'Diğer Sınav')
            sinav_tarihi = request.form['sinav_tarihi']
            if sinav_adi and sinav_tarihi:
                mevcut_sinavlar = db.reference('/sinavlar').get()
                if not isinstance(mevcut_sinavlar, list): mevcut_sinavlar = [] 
                yeni_sinav = { "ad": sinav_adi, "tarih": sinav_tarihi, "kaynak": "TELEFON" }
                mevcut_sinavlar.append(yeni_sinav)
                db.reference('/sinavlar').set(mevcut_sinavlar)
        except Exception as e: print(f"Sınav ekleme hatası: {e}")
    return redirect(url_for('ana_sayfa'))

@app.route('/sil-not/<not_id>', methods=['GET'])
def sil_not(not_id):
    try:
        index_to_delete = int(not_id)
        mevcut_notlar = db.reference('/notlar').get()
        if isinstance(mevcut_notlar, list) and 0 <= index_to_delete < len(mevcut_notlar):
            del mevcut_notlar[index_to_delete]
            db.reference('/notlar').set(mevcut_notlar)
    except ValueError:
        try: db.reference(f'/notlar/{not_id}').delete()
        except: pass
    except: pass
    return redirect(url_for('ana_sayfa'))

@app.route('/sil-calisma/<calisma_id>', methods=['GET'])
def sil_calisma(calisma_id):
    try:
        index_to_delete = int(calisma_id)
        mevcut_calismalar = db.reference('/calisma_takibi').get()
        if isinstance(mevcut_calismalar, list) and 0 <= index_to_delete < len(mevcut_calismalar):
            del mevcut_calismalar[index_to_delete]
            db.reference('/calisma_takibi').set(mevcut_calismalar)
    except ValueError:
        try: db.reference(f'/calisma_takibi/{calisma_id}').delete()
        except: pass
    except: pass
    return redirect(url_for('calisma_takibi_sayfasi'))

@app.route('/sil-sinav/<sinav_id>', methods=['GET'])
def sil_sinav(sinav_id):
    try:
        index_to_delete = int(sinav_id)
        mevcut_sinavlar = db.reference('/sinavlar').get()
        if isinstance(mevcut_sinavlar, list) and 0 <= index_to_delete < len(mevcut_sinavlar):
            del mevcut_sinavlar[index_to_delete]
            db.reference('/sinavlar').set(mevcut_sinavlar)
    except ValueError:
        try: db.reference(f'/sinavlar/{sinav_id}').delete()
        except: pass
    except: pass
    return redirect(url_for('ana_sayfa'))

@app.route('/TEMIZLE_ESKI_VERILERI_TEHLIKELI')
def temizle_eski_verileri():
    try:
        db.reference('/notlar').set([])
        db.reference('/sinavlar').set([])
        db.reference('/calisma_takibi').set([])
    except: pass
    return redirect(url_for('ana_sayfa'))

# =========================================================
# === PDF TARAYICI VE İŞLEME ===
# =========================================================
def process_pdf_text(pdf_file_stream):
    homeworks = []
    exams = []
    try:
        pdf_document = fitz.open(stream=pdf_file_stream, filetype="pdf")
        full_text = ""
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            full_text += page.get_text("text")
            
        lines = full_text.split('\n')
        found_sinav_header = False 

        for line in lines:
            trimmed_line = line.strip() 
            if not trimmed_line: continue

            if trimmed_line.endswith('yap') or trimmed_line.endswith('yap.'):
                homeworks.append(trimmed_line)
                found_sinav_header = False 
            
            elif found_sinav_header:
                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', trimmed_line)
                exam_name = trimmed_line
                exam_date = "Tarih Belirtilmemiş"
                if date_match:
                    exam_date_raw = date_match.group(1)
                    try:
                        dt_obj = datetime.datetime.strptime(exam_date_raw, "%d.%m.%Y")
                        exam_date = dt_obj.strftime("%Y-%m-%d")
                    except: exam_date = exam_date_raw
                    exam_name = trimmed_line.replace(date_match.group(1), '').strip()
                if exam_name: exams.append({"ad": exam_name, "tarih": exam_date})
                found_sinav_header = False 

            elif trimmed_line.upper() == 'SINAV':
                found_sinav_header = True
                continue 

            elif trimmed_line.upper().startswith('SINAV:'):
                try:
                    text_after_sinav = re.split(r'SINAV:', trimmed_line, flags=re.IGNORECASE)[1].strip()
                    exam_name = text_after_sinav
                    exam_date = "Tarih Belirtilmemiş"
                    date_found = False
                    
                    # Tarih formatlarını dene
                    patterns = [r'(\d{4}-\d{2}-\d{2})', r'(\d{2}\.\d{2}\.\d{4})', r'(\d{2}-\d{2}-\d{4})']
                    for pat in patterns:
                        if date_found: break
                        match = re.search(pat, text_after_sinav)
                        if match:
                            date_raw = match.group(1)
                            # Tarihi standartlaştır
                            try:
                                if '-' in date_raw and len(date_raw.split('-')[0]) == 4: # YYYY-MM-DD
                                    exam_date = date_raw
                                elif '.' in date_raw: # DD.MM.YYYY
                                    exam_date = datetime.datetime.strptime(date_raw, "%d.%m.%Y").strftime("%Y-%m-%d")
                                elif '-' in date_raw: # DD-MM-YYYY
                                    exam_date = datetime.datetime.strptime(date_raw, "%d-%m-%Y").strftime("%Y-%m-%d")
                            except: exam_date = date_raw
                            
                            exam_name = text_after_sinav.replace(date_raw, '').strip()
                            date_found = True

                    exam_name = re.sub(r'Tarih:', '', exam_name, flags=re.IGNORECASE).strip()
                    if exam_name: exams.append({"ad": exam_name, "tarih": exam_date})
                except: pass
                found_sinav_header = False 
            else:
                found_sinav_header = False
    except Exception as e: return [], [], f"PDF Hata: {e}"
    return homeworks, exams, None 

@app.route('/akilli-tarayici', methods=['GET', 'POST'])
def akilli_tarayici_sayfasi():
    homeworks = None
    exams = None
    error = None
    saved_not = False
    saved_sinav = False
    
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        
        if form_type == 'image_to_pdf':
            # Resimden PDF Çevirme
            try:
                files = request.files.getlist('resim_dosyalari')
                if not files or not files[0].filename:
                    error = "Dosya seçilmedi."
                else:
                    images = []
                    for f in files:
                        if f.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                            images.append(Image.open(f.stream).convert('RGB'))
                    if images:
                        out_name = f"resim_pdf_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
                        out_path = os.path.join(app.config['UPLOAD_FOLDER'], out_name)
                        images[0].save(out_path, save_all=True, append_images=images[1:])
                        return send_from_directory(app.config['UPLOAD_FOLDER'], out_name, as_attachment=True)
                    else: error = "Geçerli resim bulunamadı."
            except Exception as e: error = f"Hata: {e}"

        elif form_type == 'pdf_scanner':
            # PDF Tarama
            if 'file' not in request.files: error = "Dosya yok."
            else:
                f = request.files['file']
                if f.filename == '': error = "Dosya seçilmedi."
                elif not f.filename.endswith('.pdf'): error = "Sadece PDF!"
                else:
                    scan_type = request.form.get('scan_type', 'odevler')
                    hws, exs, err = process_pdf_text(f.read())
                    if err: error = err
                    else:
                        homeworks = hws
                        exams = exs
                        if scan_type == 'odevler' and hws:
                            # Notlara kaydet
                            mevcut = db.reference('/notlar').get()
                            data = list(mevcut.values()) if isinstance(mevcut, dict) else (mevcut if isinstance(mevcut, list) else [])
                            for h in hws:
                                data.append({"text": f"PDF: {h}", "tarih": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
                            db.reference('/notlar').set(data)
                            saved_not = True
                        elif scan_type == 'sinavlar' and exs:
                            # Sınavlara kaydet
                            mevcut = db.reference('/sinavlar').get()
                            if not isinstance(mevcut, list): mevcut = []
                            for ex in exs:
                                mevcut.append({"ad": ex['ad'], "tarih": ex['tarih'], "kaynak": "PDF"})
                            db.reference('/sinavlar').set(mevcut)
                            saved_sinav = True
                            
    return render_template('akilli_tarayici.html', homeworks=homeworks, exams=exams, error=error, kaydedildi_not=saved_not, kaydedildi_sinav=saved_sinav)

@app.route('/cevir-resimden-pdf-ye', methods=['POST'])
def cevir_resimden_pdf_ye():
    # Eski yol desteği
    return akilli_tarayici_sayfasi()

# =========================================================
# === KLASÖR TARAMA (HIZLI EKLE) ===
# =========================================================
def scan_sinavlar_klasoru():
    data = {}
    path = os.path.join(app.root_path, 'Sınavlar')
    if os.path.isdir(path):
        for bolum in os.listdir(path):
            b_path = os.path.join(path, bolum)
            if os.path.isdir(b_path):
                dersler = [d for d in os.listdir(b_path) if os.path.isdir(os.path.join(b_path, d))]
                dersler.sort()
                data[bolum] = dersler
    return data

def scan_calisma_klasoru():
    data = {}
    path = os.path.join(app.root_path, 'ÇALIŞMA')
    if os.path.isdir(path):
        for bolum in sorted([b for b in os.listdir(path) if not b.startswith('.')]):
            b_path = os.path.join(path, bolum)
            if os.path.isdir(b_path):
                data[bolum] = {}
                for ders in sorted([d for d in os.listdir(b_path) if not d.startswith('.')]):
                    d_path = os.path.join(b_path, ders)
                    if os.path.isdir(d_path):
                        konular = [os.path.splitext(k)[0] for k in os.listdir(d_path) if k.endswith('.txt')]
                        if konular: data[bolum][ders] = sorted(konular)
                if not data[bolum]: del data[bolum]
    return data

@app.route('/hizli-ekle')
def hizli_ekle_sayfasi():
    return render_template('hizli-ekle.html', sinavlar_data=scan_sinavlar_klasoru(), calisma_data=scan_calisma_klasoru())

@app.context_processor
def inject_dersler():
    dersler = ["Almanca", "Biyoloji", "Coğrafya", "Din Kültürü", "Edebiyat", "Fizik", "İngilizce", "Kimya", "Matematik", "Peygamberimizin Hayatı", "Proje", "Sağlık", "Tarih"]
    return dict(global_ders_listesi=dersler) 

if __name__ == '__main__':
    app.run(debug=True)
