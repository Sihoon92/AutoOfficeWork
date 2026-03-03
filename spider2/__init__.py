"""
Spider 2.0-Lite Text-to-SQL 평가 모듈

기존 APC QuerySpec/Builder 패턴을 임의 스키마에 대응할 수 있도록 일반화.
LangGraph Simple Loop로 자가 수정(Self-Correction) 루프를 추가.

구성:
    spider2.schema       - Spider2QuerySpec Pydantic 모델
    spider2.builder      - QuerySpec → SQL 문자열 조립
    spider2.schema_loader- SQLite DB → 스키마 텍스트 변환
    spider2.graph        - LangGraph 워크플로우 (load→generate→execute→validate)
    spider2.evaluator    - Spider 2.0-Lite JSONL 평가 스크립트
"""
from spider2.schema import Spider2QuerySpec
from spider2.builder import Spider2Builder, Spider2BuilderError

__all__ = ["Spider2QuerySpec", "Spider2Builder", "Spider2BuilderError"]
