"""
진입점: CLI 대화 루프

실행:
  python main.py
  python main.py "2월 1일부터 20일까지 배치 수 알려줘"  # 단일 질문
"""
import sys
from src.agent import build_agent, run


def main():
    agent = build_agent()

    # 단일 질문 모드
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        print(run(question, agent))
        return

    # 대화 루프 모드
    print("APC 데이터 조회 어시스턴트입니다. 종료하려면 'q' 또는 'exit'를 입력하세요.\n")
    while True:
        try:
            question = input("질문: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if question.lower() in ("q", "exit", "quit"):
            break
        if not question:
            continue

        answer = run(question, agent)
        print(f"\n답변: {answer}\n")


if __name__ == "__main__":
    main()
