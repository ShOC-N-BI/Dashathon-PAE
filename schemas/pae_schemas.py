from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


def _to_str(v: Any) -> Optional[str]:
    """
    Coerce any non-string value the AI might return into a safe string or None.
    Handles: None, [], {}, lists of strings, ints, etc.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v if v.strip() else None
    if isinstance(v, list):
        # If the AI returned a list, join non-empty items into a single string
        parts = [str(i) for i in v if i]
        return ", ".join(parts) if parts else None
    return str(v)


class OpsLimit(BaseModel):
    description:      Optional[str] = None
    battle_entity:    Optional[str] = Field(alias="battleEntity",    default=None)
    state_hypothesis: Optional[str] = Field(alias="stateHypothesis", default=None)
    model_config = {"populate_by_name": True}

    @field_validator("description", "battle_entity", "state_hypothesis", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> Optional[str]:
        return _to_str(v)


class GoalContribution(BaseModel):
    battle_goal: Optional[str] = Field(alias="battleGoal", default=None)
    effect:      Optional[str] = None
    model_config = {"populate_by_name": True}

    @field_validator("battle_goal", "effect", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> Optional[str]:
        return _to_str(v)


class PaeEffect(BaseModel):
    id:                 str
    effect_operator:    str                    = Field(alias="effectOperator")
    description:        Optional[str]          = None
    time_window:        Optional[str]          = Field(alias="timeWindow",        default=None)
    state_hypothesis:   Optional[str]          = Field(alias="stateHypothesis",   default=None)
    ops_limits:         list[OpsLimit]         = Field(alias="opsLimits",         default_factory=list)
    goal_contributions: list[GoalContribution] = Field(alias="goalContributions", default_factory=list)
    recommended:        bool
    ranking:            Optional[int]          = None
    model_config = {"populate_by_name": True}

    @field_validator("description", "time_window", "state_hypothesis", mode="before")
    @classmethod
    def coerce_str(cls, v: Any) -> Optional[str]:
        return _to_str(v)

    @field_validator("ops_limits", mode="before")
    @classmethod
    def coerce_ops_limits(cls, v: Any) -> list:
        # If the AI returned None or a non-list, return empty list
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return v

    @field_validator("goal_contributions", mode="before")
    @classmethod
    def coerce_goal_contributions(cls, v: Any) -> list:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return v


class PaeOutput(BaseModel):
    id:                   Optional[str]       = None
    label:                str
    description:          str
    request_id:           str                 = Field(alias="requestId")
    gbc_id:               Optional[str]       = Field(alias="gbcId",              default=None)
    entities_of_interest: list[str]           = Field(alias="entitiesOfInterest", default_factory=list)
    battle_entity:        Optional[list[str]] = Field(alias="battleEntity",       default=None)
    battle_effects:       list[PaeEffect]     = Field(alias="battleEffects",      default_factory=list)
    chat:                 list[str]           = Field(default_factory=list)
    is_done:              bool                = Field(alias="isDone")
    originator:           Optional[str]       = None
    last_updated:         datetime            = Field(alias="lastUpdated")
    model_config = {"populate_by_name": True}

    @field_validator("entities_of_interest", mode="before")
    @classmethod
    def coerce_entities(cls, v: Any) -> list:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        if not isinstance(v, list):
            return []
        return [str(i) for i in v if i]

    @field_validator("battle_entity", mode="before")
    @classmethod
    def coerce_battle_entity(cls, v: Any) -> Optional[list]:
        if v is None:
            return None
        if isinstance(v, str):
            return [v]
        if not isinstance(v, list):
            return None
        return [str(i) for i in v if i]


class PaeInput(BaseModel):
    gbc_id:     Optional[str] = Field(alias="gbcId",    default=None)
    request_id: str           = Field(alias="requestId")
    track_id:   Optional[str] = Field(alias="trackId",  default=None)
    originator: str
    model_config = {"populate_by_name": True}


class PaeInputCreated(BaseModel):
    pae_input: PaeInput = Field(alias="paeInput")
    model_config = {"populate_by_name": True}


class PaeOutputCreatedOrUpdated(BaseModel):
    pae_output: PaeOutput = Field(alias="paeOutput")
    model_config = {"populate_by_name": True}
