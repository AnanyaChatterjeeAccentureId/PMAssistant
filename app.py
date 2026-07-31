from openai import OpenAI
from config import ENDPOINT, API_KEY, DEPLOYMENT

client = OpenAI(
    base_url=ENDPOINT,
    api_key=API_KEY
)

conversation = []

SYSTEM_PROMPT = """
You are an experienced IT Project Manager Assistant.

Responsibilities:
- Help prepare project plans
- Create sprint plans
- Generate user stories
- Create meeting minutes
- Prepare status reports
- Identify project risks
- Help with Agile and Scrum
- Answer professionally using bullet points whenever appropriate.
"""

print("=" * 50)
print("Project Manager Assistant")
print("Type 'exit' to quit")
print("=" * 50)

while True:

    user_input = input("\nYou: ")

    if user_input.lower() == "exit":
        print("Goodbye!")
        break

    conversation.append({
        "role": "user",
        "content": user_input
    })

    response = client.responses.create(
        model=DEPLOYMENT,
        instructions=SYSTEM_PROMPT,
        input=conversation
    )

    answer = response.output_text

    print("\nAssistant:")
    print(answer)

    conversation.append({
        "role": "assistant",
        "content": answer
    })