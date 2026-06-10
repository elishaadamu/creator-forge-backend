from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.creator import Creator

engine = create_engine("sqlite:///creator_forge.db")
Session = sessionmaker(bind=engine)
db = Session()

for handle in ['mkbhd', 'MarquesBrownlee']:
    c = db.query(Creator).filter(Creator.handle == handle).first()
    if c:
        c.follower_count = 18000000
        c.bio = "MKBHD: Quality Tech Videos | YouTuber | Geek | Consumer Electronics | Tech Head | Internet Personality!"
        c.niche = ["tech", "consumer electronics"]
        db.commit()
        print(f"Updated {handle}")
