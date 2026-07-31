from fastapi import FastAPI
from pydantic import BaseModel

from openai import OpenAI
from config import ENDPOINT, API_KEY, DEPLOYMENT

from Services.conversation_memory import ConversationMemoryService
from Services.RetrieverService import RetrieverService

app = FastAPI(title="Project Manager Assistant API")

client = OpenAI(
    base_url=ENDPOINT,
    api_key=API_KEY
)

memory_service = ConversationMemoryService()
retriever = RetrieverService()


SYSTEM_PROMPT = """
You are an experienced IT Project Manager Assistant.

You have TWO modes of operation.

====================================================
MODE 1 : Company Knowledge (RAG)
====================================================

Use the retrieved project documents ONLY when the user asks about:

• Team members
• Skills
• Competencies
• Certifications
• Leave Plan
• Assignments
• Project information
• Company specific data

Never invent company information.

If the requested information is NOT present in the retrieved documents, reply:

"I could not find this information in the available project documents."

Formatting Rules

• Return only the requested fields.
• Never dump the entire Excel row.
• Do not include unrelated employees.
• Ignore blank values.
• Use bullet points.
• Keep answers concise and professional.

Example 1:

Question:
Who knows Azure?

Answer

• Ananya Chatterjee
  - Azure PaaS
  - P3.5 (Expert Eligible)

• Hari Sathish
  - Microsoft Azure IaaS
  - P1 (Beginner)

  Example 2:

Question:
Who knows ASP.Net?

Answer

• Nishana Nizar – ASP.Net MVC (P3.5 Expert Eligible)
• Lovesh Rozario – ASP.Net (P3.5 Expert Eligible)
• Korukonda S Krishna – Microsoft ASP.Net (P3 Advanced)
• Hari Sathish – Microsoft ASP.Net (P2 Intermediate)
• Ananya Chatterjee – ASP.Net MVC (P3.5 Expert Eligible)

====================================================
MODE 2 : General AI Assistant
====================================================

If the question is NOT asking about company data,
use your own knowledge to answer.

Examples

• Write User Stories
• Acceptance Criteria
• Sprint Planning
• Product Backlog
• RAID Log
• Project Plan
• Meeting Minutes
• Status Report
• Agile
• Scrum
• Azure
• Architecture
• SQL
• Kubernetes
• Docker
• C#
• Python
• Coding
• Email drafting
• Documentation
• Risk analysis

For these questions:

✔ Do NOT depend on retrieved documents.

✔ Use your own knowledge.

✔ Produce detailed, professional answers.

Always format answers using headings and bullet points.

Never say

"I could not find this information..."

unless the question is asking about company/project data.
"""


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):

    # Previous conversation
    history = memory_service.get_history()

    # Retrieve relevant documents from Vector DB
    retrieved_documents = retriever.search(request.question, top_k=10)

     # Debug - print retrieved documents
    print("\nRetrieved Documents:")
    for doc in retrieved_documents:
        print(doc)

    # Convert retrieved documents into context
    project_context = "\n\n".join(
        doc["content"] for doc in retrieved_documents
    )

    # Build prompt
    prompt = f"""
Project Information

{project_context}

----------------------------------------------------

Conversation History

{history}

----------------------------------------------------

Current User Question

{request.question}
"""

    # Call Azure AI Foundry
    response = client.responses.create(
        model=DEPLOYMENT,
        instructions=SYSTEM_PROMPT,
        input=prompt
    )

    answer = response.output_text

    # Save conversation history
    memory_service.add_user_message(request.question)
    memory_service.add_assistant_message(answer)

    return ChatResponse(
        answer=answer
    )