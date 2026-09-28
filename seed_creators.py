import os
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.creator import Creator, Contact
from app.models.campaign import Campaign
from app.database import Base

url = os.getenv("DATABASE_URL", "postgres://0a0059eb17b467f0d2d68bf2fbe6b48947ff9ea3ca15b25bce7af7dcd351f7bf:sk_iuYADgFkOSebAPvowfb1O@pooled.db.prisma.io:5432/postgres?sslmode=require")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

engine = create_engine(url)
Session = sessionmaker(bind=engine)
db = Session()

verified_creators = [
    {
        "handle": "MicrosoftEducation",
        "platform": "youtube",
        "display_name": "Microsoft Education",
        "bio": "Empowering every student and educator on the planet to achieve more. Innovation, digital learning tools, and modern classroom pedagogy.",
        "profile_url": "https://www.youtube.com/@MicrosoftEducation",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_nL7iL0Q6KkKqgP1gJ4bZq4-Zt5i8Q2kR=s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 232000,
        "niche": ["Education", "Tech"],
        "location": "Redmond, WA, USA",
        "website": "https://education.microsoft.com",
        "email_public": "edusupport@microsoft.com",
        "status": "discovered",
        "discovery_source": "curated_verification",
        "engagement_score": 7.8,
    },
    {
        "handle": "ThinMatrix",
        "platform": "youtube",
        "display_name": "ThinMatrix",
        "bio": "Indie game developer building 3D simulation games from scratch in Java and OpenGL. Creating devlogs, game design tutorials, and creative coding.",
        "profile_url": "https://www.youtube.com/@ThinMatrix",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_k6Fk6W_s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 264000,
        "niche": ["Design & Creative", "Game Development", "Education"],
        "location": "United Kingdom",
        "website": "https://thinmatrix.com",
        "email_public": "thinmatrix@gmail.com",
        "status": "qualified",
        "discovery_source": "curated_verification",
        "engagement_score": 8.4,
    },
    {
        "handle": "FluxAcademy",
        "platform": "youtube",
        "display_name": "Flux Academy (Ran Segall)",
        "bio": "Helping web designers and freelancers master UI/UX, Webflow, client strategy, and premium digital design businesses.",
        "profile_url": "https://www.youtube.com/@FluxAcademy",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_flux_s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 455000,
        "niche": ["Design & Creative", "Education", "Business"],
        "location": "Israel / Global",
        "website": "https://flux-academy.com",
        "email_public": "hello@flux-academy.com",
        "status": "discovered",
        "discovery_source": "curated_verification",
        "engagement_score": 8.6,
    },
    {
        "handle": "WillPaterson",
        "platform": "youtube",
        "display_name": "Will Paterson",
        "bio": "Graphic designer, logo specialist, and brand identity consultant. Tutorials on Adobe Illustrator, Hand Lettering, and Freelance Design Careers.",
        "profile_url": "https://www.youtube.com/@WillPaterson",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_willp_s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 832000,
        "niche": ["Design & Creative", "Education"],
        "location": "United Kingdom",
        "website": "https://willpaterson.design",
        "email_public": "willpatersoncontact@gmail.com",
        "status": "discovered",
        "discovery_source": "curated_verification",
        "engagement_score": 7.9,
    },
    {
        "handle": "daniel_sin",
        "platform": "youtube",
        "display_name": "Daniel Sin",
        "bio": "Tech reviewer focusing on productivity workflows, iPad accessories, desk setups, and creative software ecosystems.",
        "profile_url": "https://www.youtube.com/@daniel_sin",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_daniel_s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 215000,
        "niche": ["Tech", "Design & Creative"],
        "location": "USA",
        "website": "https://danielsin.com",
        "email_public": "business@danielsin.com",
        "status": "discovered",
        "discovery_source": "curated_verification",
        "engagement_score": 8.1,
    },
    {
        "handle": "FemkeDesign",
        "platform": "youtube",
        "display_name": "Femke Design",
        "bio": "Product designer sharing candid advice about UX design, product strategy, portfolio reviews, and designing at scale in tech.",
        "profile_url": "https://www.youtube.com/@femkedesign",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_femke_s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 118000,
        "niche": ["Design & Creative", "Education"],
        "location": "Canada",
        "website": "https://femke.design",
        "email_public": "hello@femke.design",
        "status": "discovered",
        "discovery_source": "curated_verification",
        "engagement_score": 8.7,
    },
    {
        "handle": "GameDevGuide",
        "platform": "youtube",
        "display_name": "Game Dev Guide (Matt)",
        "bio": "In-depth Unity engine architecture, C# programming patterns, procedural generation, and game production tutorials.",
        "profile_url": "https://www.youtube.com/@GameDevGuide",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_gamedev_s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 284000,
        "niche": ["Education", "Game Development", "Tech"],
        "location": "Canada",
        "website": "https://gamedevguide.com",
        "email_public": "business@gamedevguide.com",
        "status": "discovered",
        "discovery_source": "curated_verification",
        "engagement_score": 8.5,
    },
    {
        "handle": "humphreytalks",
        "platform": "youtube",
        "display_name": "Humphrey Yang",
        "bio": "Simplifying personal finance, investing, business principles, and wealth building for the next generation of digital builders.",
        "profile_url": "https://www.youtube.com/@humphreytalks",
        "avatar_url": "https://yt3.googleusercontent.com/ytc/AIdro_humphrey_s176-c-k-c0x00ffffff-no-rj",
        "follower_count": 860000,
        "niche": ["Education", "Finance", "Business"],
        "location": "USA",
        "website": "https://humphreyyang.com",
        "email_public": "humphrey@humphreytalks.com",
        "status": "discovered",
        "discovery_source": "curated_verification",
        "engagement_score": 8.2,
    }
]

try:
    for c_data in verified_creators:
        existing = db.query(Creator).filter(Creator.handle == c_data["handle"]).first()
        if not existing:
            c = Creator(
                id=str(uuid.uuid4()),
                handle=c_data["handle"],
                platform=c_data["platform"],
                display_name=c_data["display_name"],
                bio=c_data["bio"],
                profile_url=c_data["profile_url"],
                avatar_url=c_data["avatar_url"],
                follower_count=c_data["follower_count"],
                niche=c_data["niche"],
                location=c_data["location"],
                website=c_data["website"],
                email_public=c_data["email_public"],
                status=c_data["status"],
                discovery_source=c_data["discovery_source"],
                engagement_score=c_data["engagement_score"],
            )
            db.add(c)
            # Add contact record as well
            if c_data.get("email_public"):
                contact = Contact(
                    id=str(uuid.uuid4()),
                    creator_id=c.id,
                    contact_type="email",
                    value=c_data["email_public"],
                    source="public_profile",
                    is_public=True,
                    is_verified=True,
                    is_valid=True,
                )
                db.add(contact)
    db.commit()
    count = db.query(Creator).count()
    print(f"Seeding completed successfully! Total creators in database: {count}")
except Exception as e:
    print(f"Error seeding creators: {e}")
    db.rollback()
finally:
    db.close()
