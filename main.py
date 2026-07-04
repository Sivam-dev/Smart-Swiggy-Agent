import asyncio

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agent import create_builder


async def main():

    memory = MemorySaver()

    builder = await create_builder()

    graph = builder.compile(
        checkpointer=memory
    )

    config = {
        "configurable": {
            "thread_id": "food-agent-thread"
        }
    }

    print("=" * 60)
    print("🍽️ Food Ordering Agent Started")
    print("Type 'exit' anytime to quit.")
    print("=" * 60)

    first_turn = True

    while True:

        if first_turn:

            query = input("\nYou : ")

            if query.lower() == "exit":
                break

            result = await graph.ainvoke(
                {
                    "user_query": query
                },
                config=config
            )

            first_turn = False

        else:

            snapshot = graph.get_state(config)

            if not snapshot.next:
                print("\n✅ Conversation Finished")
                break

            user_reply = input("\nYou : ")

            if user_reply.lower() == "exit":
                break

            result = await graph.ainvoke(
                Command(resume=user_reply),
                config=config
            )

        print("\nAssistant:\n")

        if isinstance(result, dict):

            if result.get("assistant_response"):
                print(result["assistant_response"])

            elif result.get("follow_up_question"):
                print(result["follow_up_question"])

            elif result.get("__interrupt__"):
                interrupt = result["__interrupt__"]

                if len(interrupt) > 0:
                    print(interrupt[0].value)

            elif result.get("order_confirmation"):
                print(result["order_confirmation"])

            else:
                print("Processing complete.")

        else:
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
