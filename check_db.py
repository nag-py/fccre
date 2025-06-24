from app import app
from models import db, Feedback

with app.app_context():
    db.create_all()
    print("Tables vérifiées/créées avec succès")
    print("Modèle Feedback existe :", hasattr(Feedback, '__tablename__'))
