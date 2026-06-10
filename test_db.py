from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.creator import Creator

engine = create_engine("sqlite:///creator_forge.db")
Session = sessionmaker(bind=engine)
db = Session()

c = db.query(Creator).filter(Creator.handle == 'MarquesBrownlee').first()
if c:
    print(f"Handle: {c.handle}, Display: {c.display_name}, Followers: {c.follower_count}, Bio: {c.bio}")
else:
    print("Creator MarquesBrownlee not found")

c2 = db.query(Creator).filter(Creator.handle == 'mkbhd').first()
if c2:
    print(f"Handle: {c2.handle}, Display: {c2.display_name}, Followers: {c2.follower_count}, Bio: {c2.bio}")
