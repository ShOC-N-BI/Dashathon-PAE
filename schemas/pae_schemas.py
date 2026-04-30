from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class OpsLimit(BaseModel):
    description:      str
    battle_entity:    str = Field(alias="battleEntity")
    state_hypothesis: str = Field(alias="stateHypothesis")
    model_config = {"populate_by_name": True}


class GoalContribution(BaseModel):
    battle_goal: str = Field(alias="battleGoal")
    effect:      str
    model_config = {"populate_by_name": True}


class PaeEffect(BaseModel):
    id:                 str
    effect_operator:    str                    = Field(alias="effectOperator")
    description:        str
    time_window:        str                    = Field(alias="timeWindow")
    state_hypothesis:   str                    = Field(alias="stateHypothesis")
    ops_limits:         list[OpsLimit]         = Field(alias="opsLimits",         default_factory=list)
    goal_contributions: list[GoalContribution] = Field(alias="goalContributions", default_factory=list)
    recommended:        bool
    ranking:            Optional[int]          = None
    model_config = {"populate_by_name": True}


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
