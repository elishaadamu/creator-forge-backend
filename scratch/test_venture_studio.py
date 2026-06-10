import os
import sys

# Add base directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Temporarily disable API keys to test fallback paths during API downtime
os.environ["GEMINI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

from app.database import SessionLocal, init_db
from app.models.creator import Creator, ProductRecommendation, PostSuggestion, Partnership, Analysis
from app.services import content_calendar as calendar_svc
from app.services import discovery
from app.services import analysis as analysis_svc
from app.services import product_recommendation as rec_svc

def test_venture_studio():
    print("Initializing Database...")
    init_db()  # This will auto-create the new tables in creator_forge.db if SQLite is used
    
    db = SessionLocal()
    
    try:
        # Create a mock creator for testing
        print("\n1. Creating test creator...")
        creator, created = discovery.create_or_get_creator(
            db=db,
            handle="test_marketing_agent",
            platform="youtube",
            display_name="Test Marketing Agent Channel",
            bio="Sharing the best marketing hacks, SaaS tools, and business automation guides.",
            follower_count=120000,
            niche=["marketing", "saas", "automation"],
            discovery_source="test_script"
        )
        print(f"Creator: {creator.display_name} (ID: {creator.id}, Status: {creator.status})")
        
        # Run AI analysis
        print("\n2. Running AI analysis...")
        analysis = analysis_svc.run_ai_analysis(db, creator.id, actor="test_script")
        print(f"Analysis summary: {analysis.summary[:100]}...")
        print(f"Engagement quality score: {analysis.engagement_quality_score}")
        
        # Generate product recommendations
        print("\n3. Generating product recommendations...")
        recs = rec_svc.generate_recommendations(db, creator.id, actor="test_script")
        print(f"Generated {len(recs)} recommendations.")
        for r in recs:
            print(f"  - {r.product_name} ({r.revenue_potential}) - Status: {r.status}")
            
        # Select and approve the top recommendation
        top_rec = recs[0]
        top_rec.status = "approved"
        db.commit()
        print(f"\n4. Approved top recommendation: {top_rec.product_name}")
        
        # Test content calendar generation service
        print("\n5. Generating content calendar suggestions...")
        suggestions = calendar_svc.generate_calendar(db, creator.id, top_rec.id, actor="test_script")
        print(f"Generated {len(suggestions)} suggestions:")
        for s in suggestions:
            print(f"  - [{s.platform}] Hook: {s.hook} (Status: {s.status})")
            print(f"    Body: {s.body[:120]}...\n")
            
        # Test creating a partnership record
        print("\n6. Creating venture partnership record...")
        partnership = Partnership(
            creator_id=creator.id,
            product_recommendation_id=top_rec.id,
            equity_share=0.5,
            status="negotiating",
            notes="Initial discussion about revenue sharing."
        )
        db.add(partnership)
        db.commit()
        db.refresh(partnership)
        print(f"Partnership created with equity share {partnership.equity_share * 100}% and status: {partnership.status}")
        
        # Clean up test data
        print("\n7. Cleaning up test data...")
        db.delete(partnership)
        for s in suggestions:
            db.delete(s)
        for r in recs:
            db.delete(r)
        db.delete(analysis)
        db.delete(creator)
        db.commit()
        print("Cleanup complete!")
        
        print("\nALL TESTS PASSED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"\nTEST FAILED with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_venture_studio()
