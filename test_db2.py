from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.creator import Creator

engine = create_engine("sqlite:///creator_forge.db")
Session = sessionmaker(bind=engine)
db = Session()

for c in db.query(Creator).all():
    print(f"Handle: {c.handle}, Niche: {c.niche}, Email: {c.email_public}")
