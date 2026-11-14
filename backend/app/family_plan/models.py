from sqlmodel import Field, SQLModel


class FamilyPlanPayload(SQLModel):
    meeting_place: str = Field(default="", max_length=240)
    emergency_contact: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=2000)
    water_ready: bool = False
    medication_ready: bool = False
    documents_ready: bool = False
    evacuation_route_ready: bool = False


class FamilyPlan(FamilyPlanPayload, table=True):
    user_id: str = Field(primary_key=True)
