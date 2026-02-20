"""SQLAlchemy ORM 모델"""
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class ApcBatch(Base):
    __tablename__ = "apc_batch"

    batch_id     = Column(String(50), primary_key=True)
    product_code = Column(String(50))
    line_id      = Column(String(20))
    start_time   = Column(DateTime, nullable=False)
    end_time     = Column(DateTime)
    status       = Column(String(20), default="completed")
    created_at   = Column(DateTime)

    measurements = relationship("ApcMeasurement", back_populates="batch")


class ApcMeasurement(Base):
    __tablename__ = "apc_measurement"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    batch_id    = Column(String(50), ForeignKey("apc_batch.batch_id"))
    param_name  = Column(String(100))
    param_value = Column(Float)
    unit        = Column(String(20))
    measured_at = Column(DateTime, nullable=False)

    batch = relationship("ApcBatch", back_populates="measurements")
