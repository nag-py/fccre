from flask import Flask, render_template, request, redirect, url_for, flash, send_file, current_app
from sqlalchemy import func, extract
from models import db, Contact, HistoriqueContact, FichierHistorique, Feedback
import os
from datetime import datetime, time
from werkzeug.utils import secure_filename
import json
import subprocess

def get_db_last_update():
    try:
        db_path = os.path.join(current_app.instance_path, 'renovation.db')
        if not os.path.exists(db_path):
            current_app.logger.warning(f"Fichier DB non trouvé: {db_path}")
            return "Date inconnue"
            
        # Double méthode de vérification
        try:
            # Méthode 1: commande stat
            result = subprocess.run(['stat', '-c', '%y', db_path], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            current_app.logger.warning(f"Erreur avec stat: {str(e)}")
            
        # Méthode 2: fallback avec os.path
        timestamp = os.path.getmtime(db_path)
        return datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y à %H:%M')
        
    except Exception as e:
        current_app.logger.error(f"Erreur grave: {str(e)}")
        return "Date inconnue"



# Définir le dossier d'upload
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'gif'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # Limite à 16 MB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///renovation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'votre_cle_secrete'

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# S'assurer que le dossier d'upload existe
db.init_app(app)

with app.app_context():
    # Créer le dossier d'upload s'il n'existe pas
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    
    # Créer les tables de la base de données
    db.create_all()


@app.route('/')
def index():
    search_term = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'date_modification')
    order = request.args.get('order', 'desc')

    sort_column = {
        'rue': Contact.rue,
        'date_creation': Contact.date_creation,
        'date_modification': Contact.date_modification,
    }.get(sort_by, Contact.date_modification)

    # Base de requête
    query = Contact.query

    # Appliquer le filtre si un terme de recherche est fourni
    if search_term:
        like_term = f"%{search_term}%"
        query = query.filter(
            db.or_(
                Contact.rue.ilike(like_term),
                Contact.telephone.ilike(like_term),
                Contact.nom_prenom.ilike(like_term),
                Contact.email.ilike(like_term)
            )
        )

    # Appliquer le tri
    if order == 'asc':
        contacts = query.order_by(sort_column.asc()).all()
    else:
        contacts = query.order_by(sort_column.desc()).all()


    # ---------- STATISTIQUES (1ère colonne) ----------
    annee = 2025

    # 1. Fiches ouvertes en 2025
    fiches_ouvertes_2025 = Contact.query.filter(extract('year', Contact.date_creation) == annee).count()

    # 2. Fiches réouvertes : créées avant 2025 mais modifiées en 2025
    fiches_reouvertes_2025 = Contact.query.filter(
        extract('year', Contact.date_creation) < annee,
        extract('year', Contact.date_modification) == annee
    ).count()

    # 3. Contacts "A..." en 2025
    contacts_A_2025 = HistoriqueContact.query.filter(
        HistoriqueContact.type_contact.ilike('A%'),
        extract('year', HistoriqueContact.date) == annee
    ).count()

    # 4. Contacts "P..." en 2025
    contacts_P_2025 = HistoriqueContact.query.filter(
        HistoriqueContact.type_contact.ilike('P%'),
        extract('year', HistoriqueContact.date) == annee
    ).count()

    # 5. Top 3 type_contact
    top_type_contacts = (
        db.session.query(HistoriqueContact.type_contact, func.count().label('total'))
        .group_by(HistoriqueContact.type_contact)
        .order_by(func.count().desc())
        .limit(3)
        .all()
    )

    # 6. Nombre d'interventions en 2025
    
    all_interventions_2025 = (
    db.session.query(HistoriqueContact.interventions)
    .filter(
        HistoriqueContact.interventions != '',
        extract('year', HistoriqueContact.date) == annee
    )
    .all())

    interventions_2025 = sum(
    len(interv[0].split(',')) for interv in all_interventions_2025 if interv[0])


    # 7. Top 3 interventions (chaîne à virgules à éclater manuellement)
    all_interventions = (
        db.session.query(HistoriqueContact.interventions)
        .filter(HistoriqueContact.interventions != '')
        .all()
    )

    from collections import Counter
    interventions_counter = Counter()
    for ligne in all_interventions:
        for item in ligne[0].split(','):
            interventions_counter[item.strip()] += 1
    top_interventions = interventions_counter.most_common(3)

# ---------- COLONNE 2 ----------
    contacts_2025 = Contact.query.filter(extract('year', Contact.date_modification) == annee)

    # 1. Top 3 demandes initiales
    top_demandes = (
        contacts_2025
        .with_entities(Contact.demande_initiale, func.count().label('total'))
        .filter(Contact.demande_initiale != None, Contact.demande_initiale != '')
        .group_by(Contact.demande_initiale)
        .order_by(func.count().desc())
        .limit(3)
        .all()
    )

    # 2. Top 3 thématiques (chaînes à virgules)
    from collections import Counter

    thematique_counter = Counter()
    for c in contacts_2025.filter(Contact.thematiques != None).all():
        for t in c.thematiques.split(','):
            thematique_counter[t.strip()] += 1
    top_thematiques = thematique_counter.most_common(3)

    # 3. Top 3 types de travaux (chaînes à virgules)
    travaux_counter = Counter()
    for c in contacts_2025.filter(Contact.type_travaux != None).all():
        for t in c.type_travaux.split(','):
            travaux_counter[t.strip()] += 1
    top_travaux = travaux_counter.most_common(3)

    # ---------- COLONNE 3 ----------
    # 4. Top 4 statuts
    top_statuts = (
        contacts_2025
        .with_entities(Contact.statut, func.count().label('total'))
        .filter(Contact.statut != None, Contact.statut != '')
        .group_by(Contact.statut)
        .order_by(func.count().desc())
        .limit(4)
        .all()
    )

    # 5. Nombre de copropriétaires
    nb_copro = contacts_2025.filter(Contact.copropriete.ilike('oui')).count()

    # 6. Fracture numérique
    nb_fracture = contacts_2025.filter(Contact.fracture_numerique == True).count()

    # 7. Répartition des fiches par nombre d'interventions
    bins = {
        '1 intervention': 0,
        '2–5': 0,
        '6–10': 0,
        '11–15': 0,
        '16–20': 0,
        '21+': 0
    }

    for contact in contacts_2025.all():
        n = len(contact.historique_contacts)
        if n == 1:
            bins['1 intervention'] += 1
        elif 2 <= n <= 5:
            bins['2–5'] += 1
        elif 6 <= n <= 10:
            bins['6–10'] += 1
        elif 11 <= n <= 15:
            bins['11–15'] += 1
        elif 16 <= n <= 20:
            bins['16–20'] += 1
        elif n >= 21:
            bins['21+'] += 1


    return render_template(
        'liste_contacts.html',
        contacts=contacts,
        last_db_update=get_db_last_update(),
        stats={
            # colonne 1 (déjà présent)
            'fiches_ouvertes_2025': fiches_ouvertes_2025,
            'fiches_reouvertes_2025': fiches_reouvertes_2025,
            'contacts_A_2025': contacts_A_2025,
            'contacts_P_2025': contacts_P_2025,
            'top_type_contacts': top_type_contacts,
            'interventions_2025': interventions_2025,
            'top_interventions': top_interventions,

            # colonne 2
            'top_demandes': top_demandes,
            'top_thematiques': top_thematiques,
            'top_travaux': top_travaux,

            # colonne 3
            'top_statuts': top_statuts,
            'nb_copro': nb_copro,
            'nb_fracture': nb_fracture,
            'bins_interventions': bins,
        }
    )





@app.route('/contact/nouveau', methods=['GET', 'POST'])
def nouveau_contact():
    """Page de création d'un nouveau contact"""
        # Charger la liste des rues depuis le fichier JSON
    with open('rues.json', 'r', encoding='utf-8') as f:
        rues = json.load(f)
    if request.method == 'POST':
        # Récupération des données du formulaire
        contact = Contact(
            nom_prenom=request.form.get('nom_prenom', ''),
            telephone=request.form.get('telephone', ''),
            email=request.form.get('email', ''),
            origine=request.form.get('origine', ''),
            rue=request.form.get('rue', ''),
            numero=request.form.get('numero', ''),
            etage_boite=request.form.get('etage_boite', ''),
            zones=','.join(request.form.getlist('zones')) if request.form.getlist('zones') else '',
            statut=request.form.get('statut', ''),
            futur='futur' in request.form,
            type_bien=request.form.get('type_bien', ''),
            copropriete=','.join(request.form.getlist('copropriete')) if request.form.getlist('copropriete') else '',
            nb_unites=request.form.get('nb_unites', 0) if request.form.get('nb_unites') else 0,
            total_unites=request.form.get('total_unites', 0) if request.form.get('total_unites') else 0,
            revenus=request.form.get('revenus', ''),
            composition_familiale=request.form.get('composition_familiale', ''),
            famille_nombreuse='famille_nombreuse' in request.form,
            fracture_numerique='fracture_numerique' in request.form,
            demande_initiale=request.form.get('demande_initiale', ''),
            thematiques=','.join(request.form.getlist('thematiques')) if request.form.getlist('thematiques') else '',
            type_travaux=','.join(request.form.getlist('type_travaux')) if request.form.getlist('type_travaux') else '',
            primes_introduites=','.join(request.form.getlist('primes_introduites')) if request.form.getlist('primes_introduites') else ''
        )
        
        db.session.add(contact)
        db.session.commit()
        
        # Gestion de l'historique des contacts si des données sont présentes
        date_contact = request.form.get('date_contact')
        type_contact = request.form.get('type_contact')
        
        if date_contact and type_contact:
            historique = HistoriqueContact(
                contact_id=contact.id,
                date=datetime.strptime(date_contact, '%Y-%m-%d').date(),
                type_contact=type_contact,
                interventions=','.join(request.form.getlist('interventions')) if request.form.getlist('interventions') else '',
                commentaire=request.form.get('commentaire', '')
            )
            db.session.add(historique)
            db.session.commit()
            # Traitement des fichiers
            if 'fichiers' in request.files:
                fichiers = request.files.getlist('fichiers')
                for fichier in fichiers:
                    if fichier and fichier.filename != '' and allowed_file(fichier.filename):
                        filename = secure_filename(fichier.filename)
                        # Créer un sous-dossier pour ce contact s'il n'existe pas
                        contact_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(contact.id))
                        if not os.path.exists(contact_folder):
                            os.makedirs(contact_folder)

                        # Chemin complet du fichier
                        filepath = os.path.join(contact_folder, filename)
                        fichier.save(filepath)

                        # Enregistrer dans la base de données
                        db_fichier = FichierHistorique(
                            historique_id=historique.id,
                            nom_fichier=filename,
                            chemin_fichier=os.path.join(str(contact.id), filename),
                            type_fichier=fichier.content_type if hasattr(fichier, 'content_type') else ''
                        )
                        db.session.add(db_fichier)
                        db.session.commit()
        
        flash('Contact ajouté avec succès!', 'success')
        return redirect(url_for('modifier_contact', contact_id=contact.id))
    
    return render_template('fiche_contact.html', 
                         rues=rues,
                         last_db_update=get_db_last_update())

@app.route('/contact/<int:contact_id>', methods=['GET', 'POST'])
def modifier_contact(contact_id):
    """Page de modification d'un contact existant"""
    print(f"DEBUG: Loading template from: {os.path.abspath('templates/fiche_contact.html')}")  # Log template path
    # Charger la liste des rues depuis le fichier JSON
    with open('rues.json', 'r', encoding='utf-8') as f:
        rues = json.load(f)

    contact = Contact.query.get_or_404(contact_id)
    
    if request.method == 'POST':
        # Mise à jour des données du contact
        contact.nom_prenom = request.form.get('nom_prenom', '')
        contact.telephone = request.form.get('telephone', '')
        contact.email = request.form.get('email', '')
        contact.origine = request.form.get('origine', '')
        contact.rue = request.form.get('rue', '')
        contact.numero = request.form.get('numero', '')
        contact.etage_boite = request.form.get('etage_boite', '')
        contact.zones = ','.join(request.form.getlist('zones')) if request.form.getlist('zones') else ''
        contact.statut = request.form.get('statut', '')
        contact.futur = 'futur' in request.form
        contact.type_bien = request.form.get('type_bien', '')
        contact.copropriete = ','.join(request.form.getlist('copropriete')) if request.form.getlist('copropriete') else ''
        contact.nb_unites = request.form.get('nb_unites', 0) if request.form.get('nb_unites') else 0
        contact.total_unites = request.form.get('total_unites', 0) if request.form.get('total_unites') else 0
        contact.revenus = request.form.get('revenus', '')
        contact.composition_familiale = request.form.get('composition_familiale', '')
        contact.famille_nombreuse = 'famille_nombreuse' in request.form
        contact.fracture_numerique = 'fracture_numerique' in request.form
        contact.demande_initiale = request.form.get('demande_initiale', '')
        contact.thematiques = ','.join(request.form.getlist('thematiques')) if request.form.getlist('thematiques') else ''
        contact.type_travaux = ','.join(request.form.getlist('type_travaux')) if request.form.getlist('type_travaux') else ''
        contact.primes_introduites = ','.join(request.form.getlist('primes_introduites')) if request.form.getlist('primes_introduites') else ''
        
        db.session.commit()
        
        # Gestion de l'ajout d'un nouvel historique de contact
        date_contact = request.form.get('date_contact')
        type_contact = request.form.get('type_contact')
        
        if date_contact and type_contact:
            historique = HistoriqueContact(
                contact_id=contact.id,
                date=datetime.strptime(date_contact, '%Y-%m-%d').date(),
                type_contact=type_contact,
                interventions=','.join(request.form.getlist('interventions')) if request.form.getlist('interventions') else '',
                commentaire=request.form.get('commentaire', '')
            )
            db.session.add(historique)
            db.session.commit()
                # ✅ Mettre à jour date_creation si la date d’historique est plus ancienne
            hist_dt = datetime.combine(historique.date, time.min)
            if contact.date_creation is None or hist_dt < contact.date_creation:
                contact.date_creation = hist_dt
                db.session.commit()

            # AJOUTER CETTE PARTIE POUR GERER LES FICHIERS
            if 'fichiers' in request.files:
                fichiers = request.files.getlist('fichiers')
                for fichier in fichiers:
                    if fichier and fichier.filename != '' and allowed_file(fichier.filename):
                        filename = secure_filename(fichier.filename)
                        contact_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(contact.id))
                        if not os.path.exists(contact_folder):
                            os.makedirs(contact_folder)

                        filepath = os.path.join(contact_folder, filename)
                        fichier.save(filepath)

                        db_fichier = FichierHistorique(
                            historique_id=historique.id,
                            nom_fichier=filename,
                            chemin_fichier=os.path.join(str(contact.id), filename),
                            type_fichier=fichier.content_type if hasattr(fichier, 'content_type') else ''
                        )
                        db.session.add(db_fichier)
                        db.session.commit()
        
        print(f"DEBUG: Redirection vers modifier_contact avec id={contact.id}")  # Log de debug
        flash('Contact mis à jour avec succès!', 'success')
        return redirect(url_for('modifier_contact', contact_id=contact.id))
    
    # Trier les historiques du plus récent au plus ancien
    contact.historique_contacts = sorted(contact.historique_contacts, key=lambda h: h.date, reverse=True)

    return render_template('fiche_contact.html', 
                         contact=contact, 
                         rues=rues, 
                         rue_preselec=contact.rue,
                         last_db_update=get_db_last_update())        
    

@app.route('/contact/supprimer/<int:contact_id>', methods=['POST'])
def supprimer_contact(contact_id):
    """Suppression d'un contact"""
    contact = Contact.query.get_or_404(contact_id)
    db.session.delete(contact)
    db.session.commit()
    
    flash('Contact supprimé avec succès!', 'success')
    return redirect(url_for('index'))

@app.route('/historique/modifier/<int:historique_id>', methods=['GET', 'POST'])
def modifier_historique(historique_id):
    """Modification d'un élément de l'historique des contacts"""
    historique = HistoriqueContact.query.get_or_404(historique_id)
    contact_id = historique.contact_id
    
    if request.method == 'POST':
        # Mise à jour des données de l'historique
        historique.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        historique.type_contact = request.form.get('type_contact')
        historique.interventions = ','.join(request.form.getlist('interventions')) if request.form.getlist('interventions') else ''
        historique.commentaire = request.form.get('commentaire', '')
        
        # Gestion des fichiers à supprimer
        if 'supprimer_fichiers' in request.form:
            fichier_ids = request.form.getlist('supprimer_fichiers')
            for fichier_id in fichier_ids:
                fichier = FichierHistorique.query.get(fichier_id)
                if fichier:
                    # Supprimer le fichier du système de fichiers
                    chemin_complet = os.path.join(app.config['UPLOAD_FOLDER'], fichier.chemin_fichier)
                    if os.path.exists(chemin_complet):
                        os.remove(chemin_complet)
                    # Supprimer l'entrée de la base de données
                    db.session.delete(fichier)
        
        # Gestion des nouveaux fichiers
        if 'fichiers' in request.files:
            fichiers = request.files.getlist('fichiers')
            for fichier in fichiers:
                if fichier and fichier.filename != '' and allowed_file(fichier.filename):
                    filename = secure_filename(fichier.filename)
                    contact_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(contact_id))
                    if not os.path.exists(contact_folder):
                        os.makedirs(contact_folder)

                    filepath = os.path.join(contact_folder, filename)
                    fichier.save(filepath)

                    db_fichier = FichierHistorique(
                        historique_id=historique.id,
                        nom_fichier=filename,
                        chemin_fichier=os.path.join(str(contact_id), filename),
                        type_fichier=fichier.content_type if hasattr(fichier, 'content_type') else ''
                    )
                    db.session.add(db_fichier)
        
        db.session.commit()
        flash('Entrée d\'historique modifiée avec succès!', 'success')
        return redirect(url_for('modifier_contact', contact_id=contact_id))
    
    # Préparer les données pour le formulaire
    interventions = historique.interventions.split(',') if historique.interventions else []
    
    return render_template('modifier_historique.html', 
                         historique=historique,
                         interventions=interventions,
                         contact_id=contact_id)

@app.route('/historique/supprimer/<int:historique_id>', methods=['POST'])
def supprimer_historique(historique_id):
    """Suppression d'un élément de l'historique des contacts"""
    historique = HistoriqueContact.query.get_or_404(historique_id)
    contact_id = historique.contact_id
    
    db.session.delete(historique)
    db.session.commit()

    # Supprimer d'abord les fichiers associés
    try:
        # Supprimer d'abord tous les fichiers associés à cet historique
        for fichier in historique.fichiers:
            # Supprimer le fichier du système de fichiers
            chemin_complet = os.path.join(app.config['UPLOAD_FOLDER'], fichier.chemin_fichier)
            if os.path.exists(chemin_complet):
                os.remove(chemin_complet)
            # Supprimer l'entrée de la base de données
            db.session.delete(fichier)
        
        # Supprimer l'historique lui-même
        db.session.delete(historique)
        db.session.commit()
        
        flash('Entrée d\'historique supprimée avec succès!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression: {str(e)}', 'error')
    
    return redirect(url_for('modifier_contact', contact_id=contact_id))
    
    

@app.route('/fichier/<int:fichier_id>')
def telecharger_fichier(fichier_id):
    """Téléchargement d'un fichier"""
    fichier = FichierHistorique.query.get_or_404(fichier_id)
    chemin_complet = os.path.join(app.config['UPLOAD_FOLDER'], fichier.chemin_fichier)
    
    if os.path.exists(chemin_complet):
        return send_file(chemin_complet, as_attachment=True, download_name=fichier.nom_fichier)
    else:
        flash('Fichier introuvable', 'error')
        return redirect(url_for('modifier_contact', contact_id=fichier.historique.contact_id))

@app.route('/fichier/supprimer/<int:fichier_id>', methods=['POST'])
def supprimer_fichier(fichier_id):
    """Suppression d'un fichier"""
    fichier = FichierHistorique.query.get_or_404(fichier_id)
    contact_id = fichier.historique.contact_id

    # Supprimer le fichier du système de fichiers
    chemin_complet = os.path.join(app.config['UPLOAD_FOLDER'], fichier.chemin_fichier)
    if os.path.exists(chemin_complet):
        os.remove(chemin_complet)

    # Supprimer l'entrée de la base de données
    db.session.delete(fichier)
    db.session.commit()

    flash('Fichier supprimé avec succès!', 'success')
    return redirect(url_for('modifier_contact', contact_id=contact_id))

import json

@app.route('/')
def formulaire():
    with open('rues.json', 'r', encoding='utf-8') as f:
        rues = json.load(f)
    
    return render_template('templates/fiche_contact.html', rues=rues, rue_preselec=rue_preselec)

@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if request.method == 'POST':
        comment = request.form.get('comment', '').strip()
        if comment:
            new_feedback = Feedback(comment=comment)
            db.session.add(new_feedback)
            db.session.commit()
            flash('Merci pour votre suggestion !', 'success')
            return redirect(url_for('feedback'))
    
    # Récupérer tous les feedbacks triés par date décroissante
    feedbacks = Feedback.query.order_by(Feedback.created_at.desc()).all()
    return render_template('feedback.html', feedbacks=feedbacks)

@app.route('/stats')
def stats():
    # Base query - only contacts with at least one historique_contact in 2025
    contacts_2025 = Contact.query.join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).distinct()

    # DEMANDEUR - ZONE CONCERNEE
    zone_concernée = dict(db.session.query(
        Contact.zones, 
        func.count(Contact.id)
    ).join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).group_by(Contact.zones).all())
    
    # DEMANDEUR - STATUT
    statut_demandeur = dict(db.session.query(
        Contact.statut, 
        func.count(Contact.id)
    ).join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).group_by(Contact.statut).all())
    
    # DEMANDEUR - CATEGORIE REVENUS
    categorie_revenus = dict(db.session.query(
        Contact.revenus, 
        func.count(Contact.id)
    ).join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).group_by(Contact.revenus).all())
    
    # CONTACT - NOMBRE DEMANDEURS
    nombre_demandeurs_annee = contacts_2025.count()
    nombre_demandeurs_renouvele = contacts_2025.filter(
        extract('year', Contact.date_creation) < 2025
    ).count()
    nombre_demandeurs_total = nombre_demandeurs_annee + nombre_demandeurs_renouvele
    
    # CONTACT - ORIGINE
    origine_contact = dict(db.session.query(
        Contact.origine, 
        func.count(Contact.id)
    ).join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).group_by(Contact.origine).all())
    
    # LOGEMENT - TYPE DE BIEN
    type_bien = dict(db.session.query(
        Contact.type_bien, 
        func.count(Contact.id)
    ).join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).group_by(Contact.type_bien).all())
    
    # LOGEMENT - COPROPRIETE
    copropriete_enregistree = contacts_2025.filter(
        Contact.copropriete.ilike('%enregistrée%')
    ).count()
    type_syndic = dict(db.session.query(
        func.substr(Contact.copropriete, 1, 20), 
        func.count(Contact.id)
    ).join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).group_by(func.substr(Contact.copropriete, 1, 20)).all())
    
    # DEMANDE D'ORIGINE
    demande_origine = dict(db.session.query(
        Contact.demande_initiale, 
        func.count(Contact.id)
    ).join(HistoriqueContact).filter(
        extract('year', HistoriqueContact.date) == 2025
    ).group_by(Contact.demande_initiale).all())
    
    # THEMATIQUES ABORDEES
    thematiques_abordees = {}
    for contact in contacts_2025.filter(Contact.thematiques != None).all():
        for t in contact.thematiques.split(','):
            thematiques_abordees[t.strip()] = thematiques_abordees.get(t.strip(), 0) + 1
    
    # TYPE DE TRAVAUX
    type_travaux = {}
    for contact in contacts_2025.filter(Contact.type_travaux != None).all():
        for t in contact.type_travaux.split(','):
            type_travaux[t.strip()] = type_travaux.get(t.strip(), 0) + 1
    
    # INTERVENTIONS - GENERALITES
    interventions_generalites = {}
    for hist in HistoriqueContact.query.filter(
        HistoriqueContact.interventions != None,
        extract('year', HistoriqueContact.date) == 2025
    ).all():
        for i in hist.interventions.split(','):
            interventions_generalites[i.strip()] = interventions_generalites.get(i.strip(), 0) + 1
    
    # INTERVENTIONS - ENVOI PERSONNES RELAIS
    envoi_personnes_relais = {}
    for hist in HistoriqueContact.query.filter(
        HistoriqueContact.interventions.ilike('%envoi%'),
        extract('year', HistoriqueContact.date) == 2025
    ).all():
        for i in hist.interventions.split(','):
            if 'envoi' in i.lower():
                envoi_personnes_relais[i.strip()] = envoi_personnes_relais.get(i.strip(), 0) + 1

    return render_template('stats.html', stats={
        'zone_concernée': zone_concernée,
        'statut_demandeur': statut_demandeur,
        'categorie_revenus': categorie_revenus,
        'nombre_demandeurs_annee': nombre_demandeurs_annee,
        'nombre_demandeurs_renouvele': nombre_demandeurs_renouvele,
        'nombre_demandeurs_total': nombre_demandeurs_total,
        'origine_contact': origine_contact,
        'type_bien': type_bien,
        'copropriete_enregistree': copropriete_enregistree,
        'type_syndic': type_syndic,
        'demande_origine': demande_origine,
        'thematiques_abordees': thematiques_abordees,
        'type_travaux': type_travaux,
        'interventions_generalites': interventions_generalites,
        'envoi_personnes_relais': envoi_personnes_relais
    })


if __name__ == '__main__':
    app.run(debug=True)
