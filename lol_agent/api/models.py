"""
Shortsyt API — Pydantic Request & Response Models
"""
from typing import Optional, List, Tuple
from pydantic import BaseModel


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PipelineStartRequest(BaseModel):
    source_path: str
    clip_start: float = 0.0
    clip_end: float = 20.0
    action_type: str = "pentakill"
    champion_name: str = "Katarina"
    rank: str = "Gold"
    peak_moment: float = 17.0
    hook_text: str = "PENTAKILL"
    output_filename: str = "short_output.mp4"
    use_speed_ramp: bool = True
    use_zoom_punch: bool = True
    use_smart_camera: bool = True
    combat_segments: Optional[List[Tuple[float, float]]] = None
    expo_push_token: Optional[str] = None
    game_type: Optional[str] = "lol"


class YouTubeAuthCodeRequest(BaseModel):
    code: str


class YouTubeUploadRequest(BaseModel):
    filename: str
    title: str
    description: str = ""
    tags: List[str] = []
    privacy: str = "private"
    pinned_comment: Optional[str] = None
    thumbnail_path: Optional[str] = None
    publish_at: Optional[str] = None


class PostCommentRequest(BaseModel):
    text: str


class RegisterPushTokenRequest(BaseModel):
    expo_token: str


class AutoDetectRequest(BaseModel):
    source_path: str
    action_type: Optional[str] = None
    champion_name: Optional[str] = "Katarina"


class SaveMetadataRequest(BaseModel):
    title: str = ""
    description: str = ""
    tags: List[str] = []
    champion_name: Optional[str] = None
    action_type: Optional[str] = None
    hook_text: Optional[str] = None
    clip_start: Optional[float] = None
    clip_end: Optional[float] = None
    peak_moment: Optional[float] = None
    use_speed_ramp: Optional[bool] = None
    use_zoom_punch: Optional[bool] = None
    use_smart_camera: Optional[bool] = None
    source_path: Optional[str] = None


class UserCorrectionRequest(BaseModel):
    param_name: str
    old_value: str = ""
    new_value: str
    source: str = "ui_manual"
    reason: str = ""


class DarkRunRequest(BaseModel):
    dry_run: bool = False
    videos: int = 2


class ReserveSlotRequest(BaseModel):
    slot_id: str
    title: Optional[str] = ""
    champion: Optional[str] = ""
    frag_type: Optional[str] = "outplay"
    source_clip: Optional[str] = ""
    output_video: Optional[str] = ""
    notes: Optional[str] = ""


class AnalyzeFragRequest(BaseModel):
    clip_path: str


class AutoFillCalendarRequest(BaseModel):
    max_slots: int = 4
