"""
routers/meetings.py — 会议纪要
"""
import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, date
from pydantic import BaseModel, Field
from database import get_db, Meeting
from routers.auth import require_auth

router = APIRouter(prefix="/api/meetings", tags=["Meetings"])
R = dict

class MeetingCreate(BaseModel):
    title: str = ""
    meeting_type: str = "regular"
    meeting_date: str = ""
    duration_minutes: int = 60
    location: str = ""
    attendees: str = ""
    minutes: str = ""
    decisions: str = ""  # JSON string
    action_items: str = ""  # JSON string

def _to_dict(r):
    def parse_json(s):
        if not s:
            return []
        try:
            v = json.loads(s)
            return v if isinstance(v, list) else [v]
        except:
            return []
    return {
        "id": r.id,
        "title": r.title,
        "meeting_type": r.meeting_type,
        "meeting_date": (r.meeting_date.strftime("%Y-%m-%d %H:%M") if isinstance(r.meeting_date, date) else r.meeting_date) if r.meeting_date else "",
        "duration_minutes": r.duration_minutes or 60,
        "location": r.location or "",
        "organizer": r.organizer,
        "attendees": r.attendees or "",
        "minutes": r.minutes or "",
        "decisions": parse_json(r.decisions),
        "action_items": parse_json(r.action_items),
        "status": r.status,
        "created": (r.creation.strftime("%Y-%m-%d %H:%M") if isinstance(r.creation, datetime) else r.creation) if r.creation else "",
        "modified": (r.modified.strftime("%Y-%m-%d %H:%M") if isinstance(r.modified, datetime) else r.modified) if r.modified else "",
    }

@router.get("/list")
def meeting_list(
    meeting_type: str = Query("all"),
    from_date: str = Query(None),
    to_date: str = Query(None),
    status: str = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_auth),
):
    q = db.query(Meeting)
    if meeting_type and meeting_type != "all":
        q = q.filter(Meeting.meeting_type == meeting_type)
    if status:
        q = q.filter(Meeting.status == status)
    if from_date:
        q = q.filter(Meeting.meeting_date >= datetime.fromisoformat(from_date))
    if to_date:
        q = q.filter(Meeting.meeting_date <= datetime.fromisoformat(to_date))
    rows = q.order_by(Meeting.meeting_date.desc()).all()
    return R(data={"items": [_to_dict(r) for r in rows], "length": len(rows)})

@router.post("/create")
def meeting_create(body: MeetingCreate,
                   db: Session = Depends(get_db),
                   current_user=Depends(require_auth)):
    dt = datetime.fromisoformat(body.meeting_date) if body.meeting_date else datetime.now()
    r = Meeting(
        title=body.title,
        meeting_type=body.meeting_type,
        meeting_date=dt,
        duration_minutes=body.duration_minutes,
        location=body.location,
        organizer=current_user.username,
        attendees=body.attendees,
        minutes=body.minutes,
        decisions=body.decisions,
        action_items=body.action_items,
        status="scheduled" if not body.minutes else "completed",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return R(data=_to_dict(r), message="Meeting created")

@router.delete("/delete/{id}")
def meeting_delete(id: int, db: Session = Depends(get_db),
                   current_user=Depends(require_auth)):
    r = db.query(Meeting).get(id)
    if not r or r.organizer != current_user.username:
        return R(message="403", status_code=403)
    db.delete(r)
    db.commit()
    return R(message="Meeting deleted", status_code=204)