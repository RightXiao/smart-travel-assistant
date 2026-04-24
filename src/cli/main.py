import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agents.travel_assistant import TravelAssistant


def main():
    parser = argparse.ArgumentParser(
        description="智能旅行助手 - 为你提供专业的旅游攻略",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python -m src.cli.main                      # 进入交互式对话模式
  python -m src.cli.main "我想去北京旅游3天"    # 直接提问
        """,
    )
    parser.add_argument(
        "question",
        nargs="?",
        help="旅行相关的问题，如果不提供则进入交互模式",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🧳 智能旅行助手")
    print("=" * 60)
    print()

    try:
        assistant = TravelAssistant()
    except Exception as e:
        print(f"初始化失败：{e}")
        print("\n请确保已在 .env 文件中配置了正确的 API 密钥。")
        return

    if args.question:
        print(f"你：{args.question}\n")
        print("助手：", end="", flush=True)
        response = assistant.chat(args.question)
        print(response)
    else:
        print("进入交互模式，输入 'quit' 或 'exit' 退出\n")
        messages = []
        while True:
            try:
                user_input = input("你：")
            except (KeyboardInterrupt, EOFError):
                print("\n\n再见！")
                break
            if user_input.lower() in ["quit", "exit", "退出", "q"]:
                print("\n再见！")
                break
            if not user_input.strip():
                continue
            messages.append({"role": "user", "content": user_input})
            print("\n助手：", end="", flush=True)
            response = assistant.chat(user_input, chat_history=messages[:-1])
            print(response)
            print()
            messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
