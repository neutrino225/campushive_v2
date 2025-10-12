import asyncio
from multiagent.graph.supervisor import run_supervisor_async

async def main():
    # sample prompt for exam generation
    question = (
        "Generate a final exam for Computer Networks with 5 questions, worth 50 marks. "
        "Focus on routing, TCP congestion control, and network security."
    )
    result = await run_supervisor_async(question, session_id="exam_demo", user_role="faculty")
    print("Route:", result.get("route"))
    print("\n=== Generated Exam ===\n")
    print(result.get("response"))

if __name__ == "__main__":
    asyncio.run(main())
