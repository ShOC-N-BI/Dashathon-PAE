from sqlalchemy.orm import Session
from ..models import BC3Client

class BC3ClientRepo:
    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> list[BC3Client]:
        return self.session.query(BC3Client).all()

    def get_by_tracknumber(self, tracknumber: int) -> BC3Client | None:
        return self.session.query(BC3Client).filter(
            BC3Client.tracknumber == tracknumber
        ).first()