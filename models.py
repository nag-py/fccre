from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Contact(db.Model):
    __tablename__ = 'contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    nom_prenom = db.Column(db.String(100), nullable=False)
    telephone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    origine = db.Column(db.String(50))
    
    # Adresse
    rue = db.Column(db.String(100))
    numero = db.Column(db.String(10))
    etage_boite = db.Column(db.String(10))
    
    # Zones (stockées comme chaîne séparée par des virgules)
    zones = db.Column(db.String(100))
    
    # Logement
    statut = db.Column(db.String(50))
    futur = db.Column(db.Boolean, default=False)
    type_bien = db.Column(db.String(50))
    copropriete = db.Column(db.String(10))
    nb_unites = db.Column(db.Integer)
    total_unites = db.Column(db.Integer)
    
    # Situation personnelle
    revenus = db.Column(db.String(50))
    composition_familiale = db.Column(db.String(50))
    famille_nombreuse = db.Column(db.Boolean, default=False)
    fracture_numerique = db.Column(db.Boolean, default=False)
    
    # Demande et travaux
    demande_initiale = db.Column(db.String(50))
    thematiques = db.Column(db.String(200))  # séparés par des virgules
    type_travaux = db.Column(db.String(200))  # séparés par des virgules
    primes_introduites = db.Column(db.String(200))  # séparés par des virgules
    
    # Dates de création et modification
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    date_modification = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    historique_contacts = db.relationship('HistoriqueContact', backref='contact', lazy=True, cascade="all, delete-orphan")
    
    def get_date_premier_contact(self):
        """Retourne la date du premier contact de l'historique."""
        if not self.historique_contacts:
            return None
        return min(contact.date for contact in self.historique_contacts)
    
    def get_date_dernier_contact(self):
        """Retourne la date du dernier contact de l'historique."""
        if not self.historique_contacts:
            return None
        return max(contact.date for contact in self.historique_contacts)


class HistoriqueContact(db.Model):
    __tablename__ = 'historique_contacts'
    
    id = db.Column(db.Integer, primary_key=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    type_contact = db.Column(db.String(50), nullable=False)
    interventions = db.Column(db.String(200))  # séparés par des virgules
    commentaire = db.Column(db.Text)
    
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    # Relation avec fichiers - configurée du bon côté
    fichiers = db.relationship('FichierHistorique',
                             backref='historique',
                             lazy=True,
                             cascade='all, delete-orphan')
# La relation est déjà définie par le backref ci-dessus

# Dans models.py
class FichierHistorique(db.Model):
    __tablename__ = 'fichiers_historique'

    id = db.Column(db.Integer, primary_key=True)
    historique_id = db.Column(db.Integer, db.ForeignKey('historique_contacts.id'), nullable=False)
    nom_fichier = db.Column(db.String(255), nullable=False)
    chemin_fichier = db.Column(db.String(255), nullable=False)
    type_fichier = db.Column(db.String(100))
    date_upload = db.Column(db.DateTime, default=datetime.utcnow)

    # Relation avec l'historique
