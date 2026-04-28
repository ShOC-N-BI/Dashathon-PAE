from sqlalchemy.orm import Session
from ..models import BC3Weapons

class BC3WeaponsRepo:
    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> list[BC3Weapons]:
        return self.session.query(BC3Weapons).all()

    def get_by_jtn(self, jtn: str) -> list[BC3Weapons]:
        return self.session.query(BC3Weapons).filter(
            BC3Weapons.jtn == jtn
        ).all()