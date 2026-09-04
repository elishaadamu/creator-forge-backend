from datetime import datetime
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.workflow_state import WorkflowState
from app.models.creator import Creator
from app.models.project import CoLaunchProject

router = APIRouter(prefix="/api/workflow-state", tags=["workflow-state"])


class WorkflowStateUpdate(BaseModel):
    active_section: Optional[str] = None
    active_step: Optional[int] = None
    selected_creator_id: Optional[str] = None
    active_project_id: Optional[str] = None
    pitch_sent_map: Optional[dict[str, Any]] = None
    ai_choice_map: Optional[dict[str, Any]] = None
    answer_sent_map: Optional[dict[str, Any]] = None
    persuasion_sent_map: Optional[dict[str, Any]] = None
    creator_stage_map: Optional[dict[str, Any]] = None
    extra_state: Optional[dict[str, Any]] = None
    replace: Optional[bool] = False


def _format_state(state: WorkflowState) -> dict:
    return {
        "id": state.id,
        "active_section": state.active_section or "section1",
        "active_step": state.active_step or 1,
        "selected_creator_id": state.selected_creator_id,
        "active_project_id": state.active_project_id,
        "pitch_sent_map": state.pitch_sent_map or {},
        "ai_choice_map": state.ai_choice_map or {},
        "answer_sent_map": state.answer_sent_map or {},
        "persuasion_sent_map": state.persuasion_sent_map or {},
        "creator_stage_map": state.creator_stage_map or {},
        "extra_state": state.extra_state or {},
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _get_or_create_state(db: Session) -> WorkflowState:
    state = db.get(WorkflowState, "default")
    if not state:
        state = WorkflowState(
            id="default",
            active_section="section1",
            active_step=1,
            pitch_sent_map={},
            ai_choice_map={},
            answer_sent_map={},
            persuasion_sent_map={},
            creator_stage_map={},
            extra_state={},
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


@router.get("")
def get_workflow_state(db: Session = Depends(get_db)):
    """Retrieve shared cross-device workflow state from the Render database."""
    state = _get_or_create_state(db)
    creator_count = db.query(Creator).count()
    if creator_count == 0 and (state.creator_stage_map or state.selected_creator_id):
        state.selected_creator_id = None
        state.creator_stage_map = {}
        state.pitch_sent_map = {}
        state.ai_choice_map = {}
        state.answer_sent_map = {}
        state.persuasion_sent_map = {}
        state.active_project_id = None
        db.commit()
        db.refresh(state)
    return _format_state(state)


@router.delete("")
def reset_workflow_state(db: Session = Depends(get_db)):
    """Reset global workflow state back to pristine empty baseline."""
    state = _get_or_create_state(db)
    state.active_section = "section1"
    state.active_step = 1
    state.selected_creator_id = None
    state.active_project_id = None
    state.pitch_sent_map = {}
    state.ai_choice_map = {}
    state.answer_sent_map = {}
    state.persuasion_sent_map = {}
    state.creator_stage_map = {}
    state.extra_state = {}
    state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(state)
    return _format_state(state)


@router.post("")
@router.patch("")
@router.put("")
def update_workflow_state(body: WorkflowStateUpdate, db: Session = Depends(get_db)):
    """Update and synchronize global workflow state across all connected devices."""
    state = _get_or_create_state(db)

    if body.active_section is not None:
        state.active_section = body.active_section
    if body.active_step is not None:
        state.active_step = body.active_step
    if body.selected_creator_id is not None:
        state.selected_creator_id = body.selected_creator_id
    if body.active_project_id is not None:
        state.active_project_id = body.active_project_id

    if body.replace:
        if body.pitch_sent_map is not None:
            state.pitch_sent_map = body.pitch_sent_map
        if body.ai_choice_map is not None:
            state.ai_choice_map = body.ai_choice_map
        if body.answer_sent_map is not None:
            state.answer_sent_map = body.answer_sent_map
        if body.persuasion_sent_map is not None:
            state.persuasion_sent_map = body.persuasion_sent_map
        if body.creator_stage_map is not None:
            state.creator_stage_map = body.creator_stage_map
        if body.extra_state is not None:
            state.extra_state = body.extra_state
    else:
        if body.pitch_sent_map is not None:
            merged = dict(state.pitch_sent_map or {})
            merged.update(body.pitch_sent_map)
            state.pitch_sent_map = merged

        if body.ai_choice_map is not None:
            merged = dict(state.ai_choice_map or {})
            merged.update(body.ai_choice_map)
            state.ai_choice_map = merged

        if body.answer_sent_map is not None:
            merged = dict(state.answer_sent_map or {})
            merged.update(body.answer_sent_map)
            state.answer_sent_map = merged

        if body.persuasion_sent_map is not None:
            merged = dict(state.persuasion_sent_map or {})
            merged.update(body.persuasion_sent_map)
            state.persuasion_sent_map = merged

        if body.creator_stage_map is not None:
            merged = dict(state.creator_stage_map or {})
            merged.update(body.creator_stage_map)
            state.creator_stage_map = merged

        if body.extra_state is not None:
            merged = dict(state.extra_state or {})
            merged.update(body.extra_state)
            state.extra_state = merged

    state.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(state)
    return _format_state(state)
