import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, JSON
from app.database import Base


def _now():
    return datetime.utcnow()


class WorkflowState(Base):
    __tablename__ = "workflow_states"

    id = Column(String, primary_key=True, default="default")
    active_section = Column(String, default="section1")      # 'section1' | 'section2' | 'crm'
    active_step = Column(Integer, default=1)                 # 1..6
    selected_creator_id = Column(String, nullable=True)
    active_project_id = Column(String, nullable=True)
    pitch_sent_map = Column(JSON, default=dict)
    ai_choice_map = Column(JSON, default=dict)
    answer_sent_map = Column(JSON, default=dict)
    persuasion_sent_map = Column(JSON, default=dict)
    creator_stage_map = Column(JSON, default=dict)
    extra_state = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
