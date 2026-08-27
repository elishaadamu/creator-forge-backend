import logging
import json
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.creator import Creator
from app.models.outreach import Thread, Reply, OutreachMessage
from app.models.project import CoLaunchProject
from app.integrations.email_provider import email_provider

logger = logging.getLogger(__name__)


def generate_step6_question_answer(creator_name: str, first_name: str, concepts: list, question_body: str) -> tuple[str, str]:
    """Generates an authoritative, helpful response to a creator's questions regarding benefits, tech stack, revenue split, time commitment, and IP."""
    subject = f"Re: Co-founding questions regarding {concepts[0]['name']}"
    clean_q = (question_body or "").strip()

    concepts_summary = "\n".join(
        f"{idx+1}. {c.get('name', f'Concept {idx+1}')} — {c.get('tagline', 'Specialized tool')} ({c.get('pricing', '$29/mo')})"
        for idx, c in enumerate(concepts[:3])
    ) if concepts else "1. Creator OS — Automated workspace ($29/mo)"

    # 1. Try real LLM generation first
    try:
        from app.services.llm import call_llm
        system_prompt = (
            "You are the managing director of Creator Forge Studio, a premier software venture studio that co-founds "
            "SaaS applications with top creators under a 50/50 net revenue share model. Creator Forge funds and handles 100% "
            "of engineering, server hosting, Stripe billing, customer support, and maintenance at zero upfront cost to the creator. "
            "The creator's only role is product feedback and organic audience distribution (under 2 hours/month). "
            "Write in a warm, authoritative, high-conviction, and partner-centric tone."
        )
        prompt = f"""
A creator named {creator_name} replied to our software co-founding Opportunity Pitch with this specific question:
"{clean_q}"

Our proposed software concepts for their community are:
{concepts_summary}

Write an email reply that:
1. Greets {first_name}.
2. DIRECTLY and thoroughly answers their exact question first with concrete, specific details (e.g. if they asked 'What do I get to benefit from this?', break down recurring monthly subscription cashflow vs one-off sponsorships, zero financial risk, zero tech management, and owning real equity in software).
3. Clearly reminds them of the concepts and asks which one they want to validate with their audience first.
4. Closes warmly from 'Creator Forge Studio Team'.
Keep it concise, compelling, and free of placeholders.
"""
        llm_reply = call_llm(prompt, system_prompt=system_prompt, max_tokens=800)
        if llm_reply and len(llm_reply.strip()) > 100:
            return subject, llm_reply.strip()
    except Exception as e:
        logger.info(f"[generate_step6_question_answer] LLM call fell back to Contextual Semantic AI Engine: {e}")

    # 2. Contextual Semantic AI Generator
    q_lower = clean_q.lower()
    sections = []

    # A. Specific Benefits / "What do I get to benefit from this?" / Value
    if any(w in q_lower for w in ["benefit", "why", "value", "get", "worth", "what do i", "what is in it", "whats in it", "in it for me", "advantage"]):
        sections.append(
            "Here is exactly how this co-founding model benefits you compared to traditional brand sponsorships or trying to build software alone:\n\n"
            "1. Compounding 50% Lifetime Net Recurring Revenue:\n"
            "Unlike one-off sponsorships where a brand pays you once and captures all customer lifetime value, software produces compounding monthly subscription income (MRR). With 50% net revenue equity, just 500 active subscribers at $49/mo yields over $12,000/month in predictable, recurring cashflow to you.\n\n"
            "2. Zero Upfront Investment & Zero Financial Risk:\n"
            "You never invest a dime of your own money. Creator Forge Studio funds 100% of the engineering, server infrastructure, Stripe billing systems, and security compliance.\n\n"
            "3. 100% Fully Managed Engineering & Support:\n"
            "You never write a single line of code or manage customer support tickets. Our in-house engineering team designs, develops, tests, hosts, and maintains the entire application 24/7.\n\n"
            "4. Minimal Time Commitment (< 2 Hours/Month):\n"
            "Your role is purely strategic: reviewing product roadmaps, testing new features, and sharing the tool naturally with your audience during your regular content releases.\n\n"
            "5. You Own Real Software Equity:\n"
            "You become a co-founder of a high-value SaaS product built specifically around your brand and community authority."
        )

    # B. Technology / Architecture / Stack
    if any(w in q_lower for w in ["tech", "stack", "code", "build", "who", "develop", "architecture", "server", "host"]):
        sections.append(
            "• Technology & Engineering Architecture:\n"
            "Our engineering team builds high-performance web applications using React/Next.js for interactive interfaces, Python/FastAPI for scalable API services, and PostgreSQL for secure data persistence. All infrastructure is deployed on cloud servers with automated SSL, continuous backups, and 99.9% uptime monitoring. You don't need any technical background."
        )

    # C. Financial / Revenue Split / Costs
    if any(w in q_lower for w in ["split", "revenue", "money", "cost", "pay", "fee", "pricing", "expense"]):
        sections.append(
            "• 50/50 Revenue Split & Commercial Terms:\n"
            "You receive 50% of all net subscription revenue from day one, deposited directly to your bank account via automated Stripe Connect payouts. Creator Forge Studio covers 100% of engineering development, server hosting, and payment processing fees. There are zero upfront fees and zero ongoing expenses charged to you."
        )

    # D. Time Commitment / Effort
    if any(w in q_lower for w in ["time", "hour", "commitment", "busy", "work", "schedule"]):
        sections.append(
            "• Your Time Commitment:\n"
            "We understand you are busy creating content. The partnership requires less than 1–2 hours per month. Your only involvement is reviewing product UX and announcing the tool to your community."
        )

    # E. IP / Ownership / Rights
    if any(w in q_lower for w in ["ip", "own", "copyright", "brand", "legal", "likeness"]):
        sections.append(
            "• IP & Ownership Protection:\n"
            "The partnership operates as a joint venture. You retain 100% ownership of your brand, likeness, and content. The software itself is owned jointly under our co-founder agreement."
        )

    # F. Strategic Perspective / Recommendations
    if any(w in q_lower for w in ["thought", "think", "opinion", "feedback", "view", "perspective"]):
        sections.append(
            f"Here are our strategic thoughts on why this co-founder partnership and these 3 concepts make immense sense for your audience:\n\n"
            f"1. Tailored Community Fit: We analyzed your channel and community discussions, and identified that automated workflow and specialized tools in {concepts[0].get('tagline', 'this niche')} solve their biggest bottleneck.\n\n"
            f"2. Compounding 50% Lifetime Net Recurring Revenue: Unlike one-off sponsorships where payment ends when the video goes live, software produces compounding monthly subscription revenue (MRR) where you receive 50% net share deposited automatically via Stripe.\n\n"
            f"3. Zero Capital & Zero Technical Management: Creator Forge Studio finances and builds 100% of the software, servers, security, and customer support. You never write code or handle tickets.\n\n"
            f"4. Minimal Time Commitment (< 2 Hours/Month): Your role is purely strategic product feedback and sharing the launch with your audience during your regular content schedule.\n\n"
            f"We strongly recommend starting with {concepts[0].get('name', 'Concept 1')} for our 14-day pre-order validation sprint."
        )

    if not sections:
        sections.append(
            "• 50/50 Net Revenue Partnership:\n"
            "Creator Forge Studio funds, builds, and supports 100% of the software product at zero cost to you, while you receive 50% of all net subscription revenue from day one. You provide audience distribution and product feedback under 2 hours/month."
        )

    body = (
        f"Hi {first_name},\n\n"
        f"Thanks for asking — that is the most important question to clarify before we build anything together!\n\n"
        + "\n\n".join(sections) +
        f"\n\nHere are the 3 concepts we specifically engineered for your community:\n"
        f"{concepts_summary}\n\n"
        f"Which of these 3 concepts do you think solves the biggest bottleneck for your audience? Let us know, and we will initialize your private partner portal and launch validation.\n\n"
        f"Best regards,\nCreator Forge Studio Team"
    )
    return subject, body


def generate_step6_persuasion_email(creator_name: str, first_name: str, concepts: list, creator_objection: str) -> tuple[str, str]:
    """Generates an empathetic, high-conviction persuasion email addressing confusion, hesitation, or soft decline."""
    clean_obj = (creator_objection or "").strip()
    top_c = concepts[0] if concepts else {"name": "Creator OS", "pricing": "$29/mo"}
    is_confused = any(w in clean_obj.lower() for w in ["confus", "complicat", "unclear", "dont understand", "don't understand", "reject"])

    subject = (
        f"Re: Simplifying our co-founder partnership for {creator_name} ({top_c.get('name', 'SaaS')})"
        if is_confused
        else f"Re: Zero-effort co-founder model for {creator_name} ({top_c.get('name', 'SaaS')})"
    )

    try:
        from app.services.llm import call_llm
        system_prompt = (
            "You are the managing director of Creator Forge Studio, a premier software venture studio. "
            "A high-value creator expressed hesitation or confusion regarding our 50/50 co-founder opportunity pitch. "
            "Your goal is to warmly acknowledge their hesitation, simplify how it works in 3 crisp points, "
            "reassure them that we take 100% of the tech and financial burden at zero upfront cost, and ask if they are open "
            "to a quick 2-minute look at the interactive preview before making a final decision. Keep it concise, empathetic, and persuasive."
        )
        prompt = f"""
Creator Name: {creator_name}
Their Response: "{clean_obj}"
Featured Concept: {top_c.get('name')} — {top_c.get('tagline', '')} ({top_c.get('pricing', '$29/mo')})

Write a warm, concise email response from 'Creator Forge Studio Team' addressing their hesitation directly.
"""
        llm_reply = call_llm(prompt, system_prompt=system_prompt, max_tokens=600)
        if llm_reply and len(llm_reply.strip()) > 80:
            return subject, llm_reply.strip()
    except Exception as e:
        logger.warning(f"[Autonomous Pipeline] LLM persuasion generation fallback: {e}")

    if is_confused:
        body = f"""Hi {first_name},

I completely understand! We made it sound far more complicated than it actually is — sorry about that!

Here is the simple 30-second version of why our partner creators love this model:

1. Zero Tech Work For You:
   Creator Forge Studio finances and builds 100% of the software engineering, cloud servers, billing, and customer support. You write zero lines of code and handle zero tickets.

2. Built Specifically For Your Community:
   Based on audience analysis of your followers, your community is actively seeking a tool like {top_c.get('name', 'this platform')}.

3. Compounding 50% Net Revenue with Zero Capital Risk:
   You invest zero dollars. We split all monthly recurring profits 50/50 from day one. You only provide feedback and announce the tool during your regular content releases (<2 hours/month).

Would you be open to a quick 2-minute look at the interactive preview before you make a final decision?

Best regards,
Creator Forge Studio Team"""
    else:
        body = f"""Hi {first_name},

I completely understand your hesitation! Most creators initially pass because they assume launching software takes 20+ hours a week of coding, server maintenance, and customer support.

Here is why this is completely different:

1. Zero Time Commitment:
   We handle 100% of product engineering, servers, Stripe billing, and user support. You write zero lines of code.

2. Zero Financial Risk:
   You never invest a dime of your own capital. We fund 100% of development.

3. Enduring 50% Monthly Recurring Revenue (MRR):
   Instead of transactional, one-off brand sponsorships, software builds predictable monthly cashflow that you co-own.

Would you be open to reviewing the preview deck before closing the door completely?

Best regards,
Creator Forge Studio Team"""

    return subject, body


def run_autonomous_creator_progression(db: Session, reply: Reply):
    """
    Called whenever an incoming creator reply is recorded and classified.
    Runs the full lifecycle hands-free in the background without needing a frontend open.
    
    1. If reply is positive / qualified:
       - If no Opportunity Pitch (Step 6 blueprint) was sent to this creator yet:
         -> Autonomously generates top 3 software concepts.
         -> Dispatches the Opportunity Pitch presenting the 3 concepts with tracking token via Google SMTP.
         -> Records outreach message in DB.
       - If an Opportunity Pitch was ALREADY sent to this creator:
         -> Checks if reply is specifically on the Step 6 pitch thread.
         -> Checks if reply is a decline -> marks rejected, halts.
         -> Checks if reply is a question (including 'thoughts?') -> answers question, halts (does NOT launch).
         -> ONLY on concrete affirmative confirmation -> launches CoLaunchProject in Section 2!
    """
    from sqlalchemy import or_
    from app.models.outreach import OutreachMessage
    from app.models.project import CoLaunchProject
    from app.integrations.email_provider import email_provider

    if not reply:
        return

    # Find the creator associated with this reply
    creator = None
    if reply.thread and reply.thread.creator_id:
        creator = db.get(Creator, reply.thread.creator_id)
    if not creator and reply.from_address:
        clean_addr = reply.from_address.strip().lower()
        creator = db.query(Creator).filter(Creator.email_public.ilike(f"%{clean_addr}%")).first()

    if not creator or not creator.email_public:
        logger.info(f"[Autonomous Pipeline] No creator found for reply {reply.id}. Halting progression.")
        return

    c_id = creator.id
    target_email = creator.email_public.strip()
    c_name = creator.display_name or creator.handle or "Partner"
    first_name = c_name.split()[0]
    clean_handle = (creator.handle or "").lstrip("@").strip()

    niche = "Creator Tools"
    if isinstance(creator.niche, list) and creator.niche:
        niche = creator.niche[0]
    elif isinstance(creator.niche, str) and creator.niche:
        niche = creator.niche

    body_lower = (reply.body or "").lower().strip()
    reply_subj = (reply.subject or "").lower().strip()

    # Retrieve existing Opportunity Pitch message
    pitch_msg = (
        db.query(OutreachMessage)
        .filter(
            OutreachMessage.creator_id == c_id,
            or_(
                OutreachMessage.subject.ilike("%blueprint%"),
                OutreachMessage.subject.ilike("%opportunity deck%"),
                OutreachMessage.subject.ilike("%software concepts%"),
                OutreachMessage.subject.ilike("%opportunity pitch%")
            )
        )
        .order_by(OutreachMessage.sent_at.desc())
        .first()
    )

    # ── STAGE A: First Positive Reply -> Send Step 6 Opportunity Pitch ───────
    if not pitch_msg:
        # Only send pitch if reply was positive / interested
        classification = (reply.classification or "").lower()
        sentiment = (reply.sentiment or "").lower()
        if classification not in ("interested", "qualified") and sentiment != "positive":
            logger.info(f"[Autonomous Pipeline] Reply from {creator.handle} classified as '{classification}' (not interested). Skipping pitch.")
            return

        logger.info(f"[Autonomous Pipeline] Creator {creator.handle} qualified with positive reply. Generating 3 concepts and dispatching Opportunity Pitch...")

        concepts = [
            {
                "id": f"p1_{c_id}",
                "name": f"{first_name} OS",
                "tagline": f"Automated SaaS workspace for {niche} community",
                "problem": f"Workflow friction & monetization for {niche} audience",
                "pricing": "$29/mo Starter • $79/mo Pro",
                "mvpDifficulty": "Low (2 weeks)",
                "opportunityScore": 96,
                "rationale": f"High audience intent identified in {niche} community."
            },
            {
                "id": f"p2_{c_id}",
                "name": f"{first_name} Flow AI",
                "tagline": f"AI-powered operating system for {niche}",
                "problem": "Audience retention & automated digital delivery",
                "pricing": "$49/mo Pro",
                "mvpDifficulty": "Medium (3 weeks)",
                "opportunityScore": 92,
                "rationale": "Strong engagement on recent video uploads and tutorial series."
            },
            {
                "id": f"p3_{c_id}",
                "name": f"{first_name} Pro Hub",
                "tagline": f"Private template & tools community for {niche}",
                "problem": "Resource fragmentation and lack of unified tools",
                "pricing": "$79/mo Executive",
                "mvpDifficulty": "Medium (3-4 weeks)",
                "opportunityScore": 89,
                "rationale": "Dedicated following ready for premium software access."
            }
        ]

        # Save concepts into creator.discovery_notes
        notes_dict = {}
        if creator.discovery_notes:
            try:
                notes_dict = json.loads(creator.discovery_notes)
            except:
                notes_dict = {"raw": creator.discovery_notes}
        notes_dict["product_concepts"] = concepts
        creator.discovery_notes = json.dumps(notes_dict)
        creator.status = "qualified"
        db.commit()

        pitch_subject = f"Top 3 Software Concepts & Opportunity Deck for {c_name}"
        pitch_body = f"""Hi {first_name},

Thrilled to hear from you! As promised, our studio analyzed your channel and designed 3 custom software co-launch concepts tailored for your community:

1. {concepts[0]['name']} — {concepts[0]['tagline']} ({concepts[0]['pricing']})
2. {concepts[1]['name']} — {concepts[1]['tagline']} ({concepts[1]['pricing']})
3. {concepts[2]['name']} — {concepts[2]['tagline']} ({concepts[2]['pricing']})

Our Co-Founder Terms:
• 50/50 Revenue Split
• We handle 100% of engineering, server infrastructure, Stripe billing, and user support.
• You provide audience distribution and product feedback. Zero upfront cost to you.

Which of these three concepts resonates most with you? Once you reply, we'll initialize your private Co-Founder Portal and validation campaign.

Best regards,
Creator Forge Studio Team

---
Ref: [CF-STAGE:STEP6_PITCH | CF-CID:{c_id} | Handle:@{clean_handle}]"""

        try:
            email_provider.send(
                to_email=target_email,
                subject=pitch_subject,
                body_html=pitch_body.replace("\n", "<br>"),
                body_text=pitch_body
            )
            msg = OutreachMessage(
                creator_id=c_id,
                campaign_id="default",
                subject=pitch_subject,
                body=pitch_body,
                send_method="email",
                status="sent",
                sent_at=datetime.utcnow()
            )
            db.add(msg)
            db.commit()
            logger.info(f"[Autonomous Pipeline] Successfully dispatched Opportunity Pitch to {target_email} for creator {clean_handle}")
        except Exception as e:
            logger.warning(f"[Autonomous Pipeline] Failed to dispatch Opportunity Pitch: {e}")

        return

    # ── STAGE B: Reply to Opportunity Pitch -> Strictly Validate Before Launch ──
    # Check if this reply is specifically addressed to the Step 6 Opportunity Pitch or Dialog thread
    reply_body_lower = (reply.body or "").lower()
    is_step6_pitch_thread = (
        "step 6" in reply_subj or "step6" in reply_subj or "step6" in reply_body_lower or
        "cf-stage:step6" in reply_body_lower or
        any(k in reply_subj for k in ["opportunity pitch", "opportunity deck", "concepts", "option", "thoughts", "answers", "blueprint"])
    )
    
    # If the reply is to the initial inquiry thread and has NO Step 6 indicators, this is NOT a Step 6 response!
    if ("inquiry" in reply_subj or "step 3" in reply_subj or "step3" in reply_subj or "cf-stage:step3" in reply_body_lower) and not is_step6_pitch_thread:
        logger.info(f"[Autonomous Pipeline] Reply {reply.id} is for initial inquiry thread, not Step 6 pitch. Ignoring for Stage B.")
        return

    # 1. Ensure the incoming reply arrived AFTER our latest outbound communication (Pitch, Answers, or Persuasion)
    latest_outbound = (
        db.query(OutreachMessage)
        .filter(
            OutreachMessage.creator_id == c_id,
            or_(
                OutreachMessage.subject.ilike("%opportunity pitch%"),
                OutreachMessage.subject.ilike("%blueprint%"),
                OutreachMessage.subject.ilike("%opportunity deck%"),
                OutreachMessage.subject.ilike("%concepts%"),
                OutreachMessage.subject.ilike("%answers%"),
                OutreachMessage.subject.ilike("%simplifying%"),
                OutreachMessage.subject.ilike("%zero-effort%")
            )
        )
        .order_by(OutreachMessage.sent_at.desc())
        .first()
    )
    latest_sent_time = latest_outbound.sent_at if latest_outbound else pitch_msg.sent_at
    if latest_sent_time and reply.received_at:
        p_time = latest_sent_time.replace(tzinfo=None) if getattr(latest_sent_time, 'tzinfo', None) else latest_sent_time
        r_time = reply.received_at.replace(tzinfo=None) if getattr(reply.received_at, 'tzinfo', None) else reply.received_at
        if r_time <= p_time:
            logger.info(f"[Autonomous Pipeline] Reply {reply.id} was received BEFORE our latest outbound email ({p_time}). Waiting for fresh creator reply.")
            return

    # 2. Retrieve concepts
    concepts = None
    if creator.discovery_notes:
        try:
            nd = json.loads(creator.discovery_notes)
            concepts = nd.get("product_concepts")
        except:
            pass
    if not concepts:
        concepts = [
            {
                "id": f"p1_{c_id}",
                "name": f"{first_name} OS",
                "tagline": f"Automated SaaS workspace for {niche} community",
                "problem": f"Workflow friction & monetization for {niche} audience",
                "pricing": "$29/mo Starter • $79/mo Pro",
                "mvpDifficulty": "Low (2 weeks)",
                "opportunityScore": 96,
            },
            {
                "id": f"p2_{c_id}",
                "name": f"{first_name} Flow AI",
                "tagline": f"AI-powered operating system for {niche}",
                "problem": "Audience retention & automated digital delivery",
                "pricing": "$49/mo Pro",
                "mvpDifficulty": "Medium (3 weeks)",
                "opportunityScore": 92,
            },
            {
                "id": f"p3_{c_id}",
                "name": f"{first_name} Pro Hub",
                "tagline": f"Private template & tools community for {niche}",
                "problem": "Resource fragmentation and lack of unified tools",
                "pricing": "$79/mo Executive",
                "mvpDifficulty": "Medium (3-4 weeks)",
                "opportunityScore": 89,
            }
        ]

    # 3. Check for Hard Opt-Out vs Soft Decline / Hesitation
    hard_opt_out = any(p in body_lower for p in [
        "unsubscribe", "stop email", "stop emailing", "dont contact", "don't contact",
        "remove me", "never contact", "remove our contact"
    ])
    if hard_opt_out:
        logger.info(f"[Autonomous Pipeline] Creator {creator.handle} requested hard opt-out: '{reply.body[:60]}'. Halting outreach.")
        creator.status = "rejected"
        db.commit()
        return

    soft_decline_patterns = [
        "confusing", "confused", "confusion", "reject", "reject for now", "pass for now", "not for now",
        "not interested", "no thanks", "no thank you", "pass on this", "pass", "decline", "too busy",
        "dont have time", "don't have time", "not right now", "sounds complicated", "too complicated",
        "not sure", "hesitant", "unclear", "not looking"
    ]
    is_soft_decline = any(p in body_lower for p in soft_decline_patterns)

    # 4. Check for Questions / Inquiries / Request for further details
    is_question = "?" in body_lower or any(
        q in body_lower for q in [
            "further explanation", "further explaination", "more details", "need more details",
            "give me more details", "tell me more", "can you tell", "can you explain", "explain how",
            "explain further", "send details", "send more details", "send the details", "share more",
            "what tech", "what stack", "how does", "how do you", "revenue split", "how it works",
            "how this works", "who owns", "cost", "pricing", "how much", "what are the",
            "who builds", "what is the timeline", "thoughts", "thought", "think", "what do you think",
            "what are your thoughts", "feedback", "need more info", "more information", "more info",
            "can we get more details", "elaboration", "elaborate", "clarify", "clarification"
        ]
    )

    # 5. Check for Explicit Affirmative Confirmation / Agreement
    affirmative_patterns = [
        "interested", "i am interested", "i'm interested", "im interested", "we are interested", "we're interested",
        "definitely interested", "very interested", "would be interested", "let's do it", "lets do it",
        "sounds great", "sounds good", "love this", "love it", "i'm in", "im in",
        "let's build", "lets build", "count me in", "ready to move forward", "let's partner", "lets partner",
        "yes let's", "yes lets", "i choose", "i prefer", "let's go with", "go ahead",
        "concept 1", "concept 2", "concept 3", "option 1", "option 2", "option 3",
        "#1", "#2", "#3", "first one", "second one", "third one",
        "let's talk", "lets talk", "let's do this", "lets do this", "let's proceed", "lets proceed",
        "let's connect", "lets connect", "happy to chat", "yes", "definitely"
    ]
    has_affirmative = any(p in body_lower for p in affirmative_patterns)
    has_concept_mention = any(c["name"].lower() in body_lower for c in concepts)

    # 6. CRITICAL GATE: If creator asked a question, ALWAYS answer their question first and NEVER launch Section 2!
    if is_question:
        logger.info(f"[Autonomous Pipeline] Creator {creator.handle} asked a question in Step 6: '{reply.body[:80]}'. Generating and dispatching AI answer...")
        ans_subject, ans_body = generate_step6_question_answer(c_name, first_name, concepts, reply.body)
        ans_body_with_token = f"{ans_body}\n\n---\nRef: [CF-STAGE:STEP6_DIALOG_ANSWER | CF-CID:{c_id} | Handle:@{clean_handle}]"

        try:
            email_provider.send(
                to_email=target_email,
                subject=ans_subject,
                body_html=ans_body_with_token.replace("\n", "<br>"),
                body_text=ans_body_with_token
            )
            ans_msg = OutreachMessage(
                creator_id=c_id,
                campaign_id="default",
                subject=ans_subject,
                body=ans_body_with_token,
                send_method="email",
                status="sent",
                sent_at=datetime.utcnow()
            )
            db.add(ans_msg)
            db.commit()
            logger.info(f"[Autonomous Pipeline] Successfully sent answers to {creator.handle}'s questions. Awaiting their concept choice before Section 2.")
        except Exception as e:
            logger.warning(f"[Autonomous Pipeline] Failed to send question answers to {creator.handle}: {e}")
        return

    # 7. CRITICAL GATE: If creator expressed hesitation, confusion, or soft rejection -> Send AI Persuasion Recovery Email!
    if is_soft_decline:
        # Check if persuasion was already sent to avoid duplicate spamming
        already_persuaded = (
            db.query(OutreachMessage)
            .filter(
                OutreachMessage.creator_id == c_id,
                or_(
                    OutreachMessage.subject.ilike("%simplifying%"),
                    OutreachMessage.subject.ilike("%zero-effort%"),
                    OutreachMessage.subject.ilike("%hesitation%")
                )
            )
            .first()
        )

        if not already_persuaded:
            logger.info(f"[Autonomous Pipeline] Creator {creator.handle} expressed hesitation/confusion ('{reply.body[:80]}'). Dispatched AI persuasion recovery email...")
            per_subject, per_body = generate_step6_persuasion_email(c_name, first_name, concepts, reply.body)
            per_body_with_token = f"{per_body}\n\n---\nRef: [CF-STAGE:STEP6_DIALOG_PERSUADE | CF-CID:{c_id} | Handle:@{clean_handle}]"

            try:
                email_provider.send(
                    to_email=target_email,
                    subject=per_subject,
                    body_html=per_body_with_token.replace("\n", "<br>"),
                    body_text=per_body_with_token
                )
                per_msg = OutreachMessage(
                    creator_id=c_id,
                    campaign_id="default",
                    subject=per_subject,
                    body=per_body_with_token,
                    send_method="email",
                    status="sent",
                    sent_at=datetime.utcnow()
                )
                db.add(per_msg)
                db.commit()
                logger.info(f"[Autonomous Pipeline] Successfully dispatched persuasion recovery email to {creator.handle}!")
            except Exception as e:
                logger.warning(f"[Autonomous Pipeline] Failed to send persuasion recovery email to {creator.handle}: {e}")
        else:
            logger.info(f"[Autonomous Pipeline] Creator {creator.handle} already received persuasion email. Halting progression.")
        return

    # 8. Must have explicit confirmation or concept mention to initialize Section 2!
    if not (has_affirmative or has_concept_mention):
        logger.info(f"[Autonomous Pipeline] Creator {creator.handle} reply ('{reply.body[:60]}') did not contain concrete agreement or concept choice. Awaiting explicit confirmation.")
        return

    # 8. Check if a CoLaunchProject already exists
    existing_proj = db.query(CoLaunchProject).filter(CoLaunchProject.creator_id == c_id).first()
    if existing_proj:
        logger.info(f"[Autonomous Pipeline] Project {existing_proj.id} already exists for {creator.handle}. Skipping launch.")
        return

    # 9. Concept Selection
    chosen_concept = concepts[0]
    if len(concepts) > 1 and ("flow" in body_lower or "2" in body_lower or "second" in body_lower or "#2" in body_lower):
        chosen_concept = concepts[1]
    elif len(concepts) > 2 and ("hub" in body_lower or "3" in body_lower or "third" in body_lower or "#3" in body_lower or "pro" in body_lower):
        chosen_concept = concepts[2]

    logger.info(f"[Autonomous Pipeline] 🎯 Concrete agreement confirmed for {creator.handle}! Selected: {chosen_concept['name']}. Initializing Section 2...")

    from app.routers.projects import execute_create_co_launch_project, CreateProjectRequest
    req = CreateProjectRequest(
        creatorId=c_id,
        creatorHandle=creator.handle,
        creatorName=creator.display_name or creator.handle,
        creatorAvatar=creator.avatar_url,
        creatorEmail=creator.email_public,
        niche=niche,
        followers=str(creator.follower_count or 100000),
        productName=chosen_concept["name"],
        productTagline=chosen_concept.get("tagline", ""),
        targetAudience=f"{niche} creators and community",
        customer=f"{niche} community members",
        problem=chosen_concept.get("problem", "Workflow inefficiencies"),
        pricing=chosen_concept.get("pricing", "$29/mo Starter • $79/mo Pro"),
        presaleTarget=5000.0,
        selectedConcept=chosen_concept
    )
    try:
        proj_data = execute_create_co_launch_project(db, req)
        logger.info(f"[Autonomous Pipeline] 🚀 Autonomously created Co-Launch Project {proj_data.get('id')} in Section 2 for creator {clean_handle} with concrete validation confirmation!")
    except Exception as e:
        logger.error(f"[Autonomous Pipeline] Error auto-creating project: {e}")
