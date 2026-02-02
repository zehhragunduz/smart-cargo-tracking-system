from flask import Flask, render_template, redirect, url_for, flash, request, session,jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
import pyodbc
import os
from datetime import datetime 
from models import db, Kullanici, Kargo, Iade, Message

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///kargopro.db'
app.config['SECRET_KEY'] = 'your_secret_key'

db.init_app(app)

# Flask-Admin kurulumu
admin = Admin(app, name='Kargo Takip Admin', template_mode='bootstrap3')
admin.add_view(ModelView(Kullanici, db.session))
admin.add_view(ModelView(Kargo, db.session))
admin.add_view(ModelView(Iade, db.session))

# MSSQL veritabanı bağlantısı
conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DESKTOP-ILTS1VM;"
    "DATABASE=kargopro;"
    "Trusted_Connection=yes;"
)
current_time = datetime.now()
with app.app_context():
    db.create_all()

    
def row_to_dict(row):
    """Row nesnesini sözlüğe dönüştürür."""
    return {col[0]: row[i] for i, col in enumerate(row.cursor_description)}






# Giriş sayfası
@app.route('/')
def intro():
    return render_template('intro.html')

@app.route('/home')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        kullanici_adi = request.form['kullanici_adi']
        email = request.form['email']
        sifre = request.form['sifre']
        rol = request.form['rol']

        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Kullanici (KullaniciAdi, Email, Sifre, Rol)
                VALUES (?, ?, ?, ?)
            """, kullanici_adi, email, sifre, rol)
            conn.commit()
            conn.close()
            flash('Kayıt başarılı! Giriş yapabilirsiniz.', 'success')
            return redirect(url_for('login'))
        except pyodbc.IntegrityError as e:
            if '23000' in str(e):
                flash('Girmiş olduğunuz bilgiler sisteme kayıtlı.', 'danger')
            else:
                flash('Bir hata oluştu. Lütfen tekrar deneyin.', 'danger')
            conn.close()
    return render_template('register.html')

# Giriş işlemi
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        sifre = request.form['sifre']

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Kullanıcıyı e-posta ile arayın
        cursor.execute("SELECT * FROM Kullanici WHERE Email = ?", email)
        user = cursor.fetchone()
        
        if user:
            # Kullanıcı bulundu, şimdi şifre kontrolü yapalım
            cursor.execute("SELECT * FROM Kullanici WHERE Email = ? AND Sifre = ?", email, sifre)
            user_with_correct_password = cursor.fetchone()
            conn.close()
            
            if user_with_correct_password:
                session['user_id'] = user_with_correct_password.KullaniciID
                session['rol'] = user_with_correct_password.Rol
                flash('Başarıyla giriş yapıldı.', 'success')
                if user_with_correct_password.Rol == 'Gönderici':
                    return redirect(url_for('sender_dashboard'))
                elif user_with_correct_password.Rol == 'Alıcı':
                    return redirect(url_for('user_dashboard'))
                elif user_with_correct_password.Rol == 'Admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    flash('Geçersiz rol!', 'danger')
                    return redirect(url_for('login'))
            else:
                # Kullanıcı bulundu ancak şifre yanlış
                flash('Girdiğiniz bilgiler yanlış.', 'danger')
                return redirect(url_for('login'))
        else:
            # Kullanıcı bulunamadı
            flash('Sisteme kayıtlı değilsiniz.', 'danger')
            conn.close()
            return redirect(url_for('login'))

    return render_template('login.html')

# Çıkış işlemi
@app.route('/logout')
def logout():
    session.clear()
    flash('Başarıyla çıkış yapıldı.', 'success')
    return redirect(url_for('login'))

# Kullanıcı paneli
@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    # Kullanıcının mesajlaştığı kullanıcıları getir
    cursor.execute("""
        SELECT DISTINCT K.KullaniciID, K.KullaniciAdi
        FROM Messages M
        JOIN Kullanici K ON M.SenderID = K.KullaniciID OR M.ReceiverID = K.KullaniciID
        WHERE (M.SenderID = ? OR M.ReceiverID = ?) AND K.KullaniciID != ?
    """, user_id, user_id, user_id)
    kullanicilar = cursor.fetchall()

    # Kullanıcının kargolarını getir
    cursor.execute("""
        SELECT * FROM Kargo WHERE AliciID = ?
    """, user_id)
    kargolar = cursor.fetchall()

    conn.close()
    return render_template('user_dashboard.html', kullanicilar=kullanicilar, kargolar=kargolar)




@app.route('/sender_dashboard', methods=['GET', 'POST'])
def sender_dashboard():
    # Kullanıcı oturumu kontrolü
    if 'user_id' not in session or session['rol'] != 'Gönderici':
        return redirect(url_for('login'))
    
    GonderiID = session['user_id']  # Gönderici ID

    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        print("Veritabanı bağlantısı başarılı")

        # POST isteği: Yeni kargo gönderme işlemi
        if request.method == 'POST':
            if 'alici_email' in request.form:
                try:
                    alici_email = request.form['alici_email']
                    gonderi_adres = request.form['alici_adres']
                    kargo_agirligi = request.form['kargo_agirligi']

                    # Kargo ağırlığını kontrol et ve fiyat hesapla
                    if not kargo_agirligi or not kargo_agirligi.isdigit():
                        flash('Geçersiz kargo ağırlığı!', 'danger')
                        return redirect(url_for('sender_dashboard'))
                    
                    kargo_fiyati = (float(kargo_agirligi) / 0.2) * 10

                    # Alıcı bilgilerini al
                    cursor.execute("SELECT KullaniciID, KullaniciAdi, GonderiAdres FROM Kullanici WHERE Email = ?", (alici_email))
                    alici = cursor.fetchone()
                    if not alici:
                        flash('Alıcı bulunamadı!', 'danger')
                        return redirect(url_for('sender_dashboard'))
                    
                    alici_id = alici[0]  # KullaniciID sütunu
                    alici_adi = alici[1]  # KullaniciAdi sütunu
                    gonderi_adres = alici[2]  # GonderiAdres sütun


                    # Alıcı adresini güncelle
                    cursor.execute("UPDATE Kullanici SET GonderiAdres = ? WHERE KullaniciID = ?", gonderi_adres, alici_id)
                    conn.commit()

                    # Kargo bilgilerini ekle
                    cursor.execute("""
                        INSERT INTO Kargo (GondericiID, AliciID, KargoAgirligi, KargoFiyati, KargoDurumu, GonderiAdres)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, GonderiID, alici_id, kargo_agirligi, kargo_fiyati, 'Gönderildi', gonderi_adres)
                    conn.commit()

                    # Eklenen kargo ID'sini al
                    kargo_id = cursor.execute("SELECT @@IDENTITY").fetchval()

                    # KargoDurum tablosuna bilgi ekle
                    cursor.execute("""
                        INSERT INTO KargoDurum (KargoID, VerilmeTarihi, Durum)
                        VALUES (?, ?, ?)
                    """, kargo_id, datetime.datetime.now(), 'Gönderildi')
                    conn.commit()

                    flash('Kargo başarıyla gönderildi!', 'success')
                    return redirect(url_for('sender_dashboard'))

                except Exception as e:
                    flash(f'Hata: {str(e)}', 'danger')
                    conn.rollback()
                    return redirect(url_for('sender_dashboard'))
        
        # GET isteği: Göndericiye gelen ve gönderici tarafından gönderilen mesajları getir
        cursor.execute("""
            SELECT DISTINCT K.KullaniciID, K.KullaniciAdi
            FROM Messages M
            JOIN Kullanici K ON M.SenderID = K.KullaniciID OR M.ReceiverID = K.KullaniciID
            WHERE (M.SenderID = ? OR M.ReceiverID = ?) AND K.KullaniciID != ?
        """, GonderiID, GonderiID, GonderiID)
        kullanicilar = cursor.fetchall()
        print("Mesajlar başarıyla alındı")

        # Göndericinin kargolarını getir
        cursor.execute("""
            SELECT 
                Kargo.*, 
                Gonderici.KullaniciAdi AS GondericiAdi, 
                Alici.KullaniciAdi AS AliciAdi, 
                KargoDurum.VerilmeTarihi
            FROM Kargo 
            JOIN Kullanici AS Gonderici ON Kargo.GondericiID = Gonderici.KullaniciID 
            JOIN Kullanici AS Alici ON Kargo.AliciID = Alici.KullaniciID 
            LEFT JOIN KargoDurum ON Kargo.KargoID = KargoDurum.KargoID
            WHERE GondericiID = ?
        """, GonderiID)
        kargolar = cursor.fetchall()
        print("Kargolar başarıyla alındı")

    except pyodbc.Error as e:
        # Veritabanı hatalarını yakala
        error_message = f"Veritabanı Hatası: {str(e)}"
        print(error_message)
        flash(error_message, "danger")
        return redirect(url_for('login'))
    except Exception as e:
        # Diğer hataları yakala
        error_message = f"Hata: {str(e)}"
        print(error_message)
        flash(error_message, "danger")
        return redirect(url_for('login'))
    finally:
        if 'conn' in locals():
            conn.close()
            print("Veritabanı bağlantısı kapatıldı")

    kargo_icon = {
        'Teslim Edildi': 'fa-check-circle',
        'Yolda': 'fa-truck',
        'Hazırlanıyor': 'fa-box-open',
        # Diğer durumlar ve ikonlar
    }
    return render_template('sender_dashboard.html', kargolar=kargolar, kullanicilar=kullanicilar, kargo_icon=kargo_icon)




       


            
        



@app.route('/get_messages/<int:user_id>', methods=['GET'])
def get_messages(user_id):
    messages = Message.query.filter(
        (Message.SenderID == session['user_id']) & (Message.ReceiverID == user_id) |
        (Message.SenderID == user_id) & (Message.ReceiverID == session['user_id'])
    ).order_by(Message.SentAt.asc()).all()
    return jsonify([{'id': msg.MessageID, 'content': msg.MessageText, 'timestamp': msg.SentAt} for msg in messages])

@app.route('/contact_admin', methods=['POST'])
def contact_admin():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    contact_message = request.form['contact_message']

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Feedback (UserID, FeedbackText, SentAt)
        VALUES (?, ?, ?)
    """, user_id, contact_message, datetime.now())
    conn.commit()
    conn.close()

    flash('Mesajınız gönderildi!', 'success')
    return redirect(url_for('sender_dashboard'))

@app.route('/uye_bilgileri', methods=['GET', 'POST'])
def uye_bilgileri():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    kullanici_rol = session['rol']
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    if request.method == 'POST':
        kullanici_adi = request.form['kullanici_adi']
        email = request.form['email']
        
        if kullanici_rol == 'Alıcı':
            gonderi_adres = request.form['gonderi_adres']
            cursor.execute("""
                UPDATE Kullanici SET KullaniciAdi = ?, Email = ?, GonderiAdres = ? WHERE KullaniciID = ?
            """, kullanici_adi, email, gonderi_adres, user_id)
        else:
            cursor.execute("""
                UPDATE Kullanici SET KullaniciAdi = ?, Email = ? WHERE KullaniciID = ?
            """, kullanici_adi, email, user_id)
        
        conn.commit()
        flash('Bilgiler başarıyla güncellendi!', 'success')
        return redirect(url_for('uye_bilgileri'))

    cursor.execute("SELECT KullaniciAdi, Email, GonderiAdres FROM Kullanici WHERE KullaniciID = ?", user_id)
    kullanici = cursor.fetchone()
    conn.close()
    return render_template('uye_bilgileri.html', kullanici=kullanici, kullanici_rol=kullanici_rol)





@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    feedback_text = request.form['feedback_text']

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Feedback (UserID, FeedbackText, SentAt)
        VALUES (?, ?, ?)
    """, user_id, feedback_text, datetime.datetime.now())
    conn.commit()
    conn.close()

    flash('Geri bildiriminiz gönderildi!', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['rol'] != 'Admin':
        return redirect(url_for('login'))

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM Kargo WHERE KargoDurumu IN ('Hazırlanıyor', 'Yolda')")
    aktif_kargo_sayisi = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Kargo WHERE KargoDurumu = 'Teslim Edildi'")
    teslim_edilmis_kargo_sayisi = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Kargo WHERE KargoDurumu = 'Yolda'")
    gonderilmis_kargo_sayisi = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Kargo WHERE KargoDurumu = 'İade Edildi'")
    iade_edilmis_kargo_sayisi = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Kargo")
    toplam_kargo_sayisi = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Kullanici")
    toplam_kullanici_sayisi = cursor.fetchone()[0]

    # Kullanıcılar arası mesajlar
    cursor.execute("""
        SELECT M.MessageID, M.MessageText, M.SentAt, 
               K1.KullaniciAdi AS SenderName, 
               K2.KullaniciAdi AS ReceiverName 
        FROM Messages M
        JOIN Kullanici K1 ON M.SenderID = K1.KullaniciID
        JOIN Kullanici K2 ON M.ReceiverID = K2.KullaniciID
        WHERE M.ReceiverID != 1 -- Admin ID'si 1 varsayıldı
        ORDER BY M.SentAt DESC
    """)
    kullanici_mesajlari = cursor.fetchall()

    # Şikayet ve talepler (admin'e gönderilen mesajlar)
    cursor.execute("""
        SELECT F.FeedbackID, F.FeedbackText, F.SentAt, K.KullaniciAdi AS SenderName
        FROM Feedback F
        JOIN Kullanici K ON F.UserID = K.KullaniciID
        ORDER BY F.SentAt DESC
    """)
    sikayet_talep_mesajlari = cursor.fetchall()

    cursor.execute("""
        SELECT Kargo.*, Gonderici.KullaniciAdi AS GondericiAdi, Alici.KullaniciAdi AS AliciAdi
        FROM Kargo
        JOIN Kullanici AS Gonderici ON Kargo.GondericiID = Gonderici.KullaniciID
        JOIN Kullanici AS Alici ON Kargo.AliciID = Alici.KullaniciID
    """)
    kargolar = cursor.fetchall()

    cursor.execute("SELECT * FROM Kullanici")
    kullanicilar = cursor.fetchall()

    conn.close()

    return render_template('admin_dashboard.html', 
                           aktif_kargo_sayisi=aktif_kargo_sayisi,
                           teslim_edilmis_kargo_sayisi=teslim_edilmis_kargo_sayisi,
                           gonderilmis_kargo_sayisi=gonderilmis_kargo_sayisi,
                           iade_edilmis_kargo_sayisi=iade_edilmis_kargo_sayisi,
                           toplam_kargo_sayisi=toplam_kargo_sayisi,
                           toplam_kullanici_sayisi=toplam_kullanici_sayisi,
                           kullanici_mesajlari=kullanici_mesajlari,
                           sikayet_talep_mesajlari=sikayet_talep_mesajlari,
                           kargolar=kargolar,
                           kullanicilar=kullanicilar)

@app.route('/kargo/<int:kargo_id>', methods=['GET', 'POST'])
def kargo_detay(kargo_id):
    user_role = session.get('rol')
    
    if request.method == 'POST' and user_role == 'Gönderici':
        yeni_durum = request.form.get('kargo_durumu')
        teslim_alan = request.form.get('teslim_alan')
        lat = request.form.get('lat', type=float)
        lng = request.form.get('lng', type=float)

        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        if yeni_durum and lat is not None and lng is not None:
            # Kargo durumu "Teslim Edildi" ise VerilmeTarihi'ni güncelle
            if yeni_durum == 'Teslim Edildi' and teslim_alan:
                verilme_tarihi = datetime.now()
                cursor.execute("""
                    UPDATE Kargo SET KargoDurumu = ?, lat = ?, lng = ?,  TeslimAlan = ? WHERE KargoID = ?
                """, yeni_durum, lat, lng, teslim_alan, kargo_id)
                cursor.execute("""
                    MERGE INTO KargoDurum AS target
                    USING (SELECT ? AS KargoID, ? AS VerilmeTarihi, ? AS Durum) AS source
                    ON (target.KargoID = source.KargoID)
                    WHEN MATCHED THEN
                        UPDATE SET VerilmeTarihi = source.VerilmeTarihi, Durum = source.Durum
                    WHEN NOT MATCHED THEN
                        INSERT (KargoID, VerilmeTarihi, Durum)
                        VALUES (source.KargoID, source.VerilmeTarihi, source.Durum);
                """, kargo_id, verilme_tarihi, yeni_durum)
            else:
                cursor.execute("""
                    UPDATE Kargo SET KargoDurumu = ?, lat = ?, lng = ? WHERE KargoID = ?
                """, yeni_durum, lat, lng, kargo_id)
            conn.commit()
            flash('Kargo durumu ve konumu güncellendi!', 'success')
        conn.close()

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Kargo.*, Gonderici.KullaniciAdi AS GondericiAdi, Alici.KullaniciAdi AS AliciAdi, KargoDurum.VerilmeTarihi
        FROM Kargo 
        JOIN Kullanici AS Gonderici ON Kargo.GondericiID = Gonderici.KullaniciID 
        JOIN Kullanici AS Alici ON Kargo.AliciID = Alici.KullaniciID
        LEFT JOIN KargoDurum ON Kargo.KargoID = KargoDurum.KargoID
        WHERE Kargo.KargoID = ?
    """, kargo_id)
    kargo = cursor.fetchone()
    conn.close()
    
    if not kargo:
        flash('Kargo bulunamadı!', 'danger')
        return redirect(url_for('sender_dashboard'))

    api_key = "AIzaSyDRYO8_9Qjcq9PSoc6anJonGEWExE-dxQo"  # Google Maps API anahtarınızı buraya ekleyin

    if user_role == 'Gönderici':
        return render_template('kargo_detay_sender.html', kargo=kargo, api_key=api_key)
    elif user_role == 'Alıcı':
        return render_template('kargo_detay_receiver.html', kargo=kargo, api_key=api_key)
    else:
        return redirect(url_for('login'))

# İade işlemi
@app.route('/iade/<int:kargo_id>', methods=['GET', 'POST'])
def iade(kargo_id):
    if request.method == 'POST':
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Kargo bilgilerini al
        cursor.execute("SELECT KargoAgirligi FROM Kargo WHERE KargoID = ?", kargo_id)
        kargo = cursor.fetchone()

        if kargo:
            kargo_agirligi = kargo.KargoAgirligi
            iade_fiyati = (kargo_agirligi / 0.1) * 10  # Her 0.1 kg başına 10 TL

            # İade bilgilerini ekle ve kargo durumunu güncelle
            cursor.execute("""
                INSERT INTO Iade (KargoID, IadeDurumu, IadeFiyati)
                VALUES (?, ?, ?)
            """, kargo_id, 'İade Edildi', iade_fiyati)
            cursor.execute("""
                UPDATE Kargo SET KargoDurumu = 'İade Edildi' WHERE KargoID = ?
            """, kargo_id)
            conn.commit()
            conn.close()

            flash(f'Kargo iade edildi! İade ücreti: {iade_fiyati} TL', 'success')
            return redirect(url_for('sender_dashboard'))
        else:
            flash('Kargo bulunamadı!', 'danger')
            conn.close()
            return redirect(url_for('sender_dashboard'))
    
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Kargo WHERE KargoID = ?", kargo_id)
    kargo = cursor.fetchone()
    conn.close()
    return render_template('iade.html', kargo=kargo)

@app.route('/get_inbox', methods=['GET'])
def get_inbox():
    user_id = session.get('user_id')

    # Kullanıcının gelen mesajlarını al
    messages = Message.query.filter_by(receiver_id=user_id).all()
    inbox = []

    for message in messages:
        inbox.append({
            'username': message.sender.username,
            'messages': [{
                'sender': message.sender.username,
                'content': message.content,
                'timestamp': message.timestamp
            }]
        })

    return jsonify(inbox)


# Yeni route: Kargoyu teslim et
@app.route('/teslim_et/<int:kargo_id>', methods=['POST'])
def teslim_et(kargo_id):
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()

        # Şu anki zamanı al
        verilme_tarihi = datetime.datetime.now()

        # Kargo durumunu güncelle ve verilme tarihini ekle
        cursor.execute("""
            UPDATE Kargo 
            SET KargoDurumu = 'Teslim Edildi', VerilmeTarihi = ? 
            WHERE KargoID = ?
        """, verilme_tarihi, kargo_id)
        conn.commit()
        conn.close()

        flash('Kargo başarıyla teslim edildi!', 'success')
    except pyodbc.Error as e:
        flash('Veritabanı hatası: ' + str(e), 'danger')
    
    return redirect(url_for('sender_dashboard'))

@app.route('/get_users', methods=['GET'])
def get_users():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    cursor.execute("SELECT KullaniciID, KullaniciAdi FROM Kullanici")
    users = cursor.fetchall()
    conn.close()

    return jsonify([{'id': user.KullaniciID, 'username': user.KullaniciAdi} for user in users])

import traceback


@app.route('/send_message', methods=['POST'])
def send_message():
    sender_id = request.form['sender_id']
    receiver_name = request.form['receiver_name']
    content = request.form['content']

    # Mesajı veritabanına kaydetme
    message = Message(sender_id=sender_id, receiver_name=receiver_name, content=content)
    db.session.add(message)
    db.session.commit()

    return jsonify({'success': True})


@app.route('/user_messages', methods=['GET'])
def user_messages():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized access'}), 401

    user_id = session['user_id']
    
    # Kullanıcının gönderdiği veya aldığı mesajları sorgula
    messages = Message.query.filter(
        (Message.SenderID == user_id) | (Message.ReceiverID == user_id)
    ).order_by(Message.SentAt.asc()).all()

    # Mesajları JSON formatında döndür
    return jsonify([{
        'id': msg.MessageID,
        'content': msg.MessageText,
        'timestamp': msg.SentAt,
        'sender_id': msg.SenderID,
        'receiver_id': msg.ReceiverID
    } for msg in messages])

@app.route('/inbox')
def inbox():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    messages = Message.query.filter_by(ReceiverID=user_id).order_by(Message.SentAt.desc()).all()

    # Gönderen adlarını çek
    for message in messages:
        sender = Kullanici.query.get(message.SenderID)
        message.sender_name = sender.kullanici_adi if sender else "Bilinmiyor"

    return render_template('user_dashboard.html', messages=messages)

if __name__ == '__main__':
    app.run(debug=True)