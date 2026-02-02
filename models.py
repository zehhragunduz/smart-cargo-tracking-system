from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Kullanici(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    sifre = db.Column(db.String(150), nullable=False)
    rol = db.Column(db.String(50), nullable=False)

class Kargo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    takip_no = db.Column(db.String(150), nullable=False, unique=True)
    gonderen_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    alici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    durum = db.Column(db.String(150), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)

class Iade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kargo_id = db.Column(db.Integer, db.ForeignKey('kargo.id'), nullable=False)
    sebep = db.Column(db.String(250), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'Messages'
    
    MessageID = db.Column(db.Integer, primary_key=True)
    SenderID = db.Column(db.Integer, nullable=False)
    ReceiverID = db.Column(db.Integer, nullable=False)
    MessageText = db.Column(db.String, nullable=False)
    SentAt = db.Column(db.DateTime, default=datetime.utcnow)
    IsRead = db.Column(db.Boolean, default=False)

    def __init__(self, SenderID, ReceiverID, MessageText):
        self.SenderID = SenderID
        self.ReceiverID = ReceiverID
        self.MessageText = MessageText

    

   