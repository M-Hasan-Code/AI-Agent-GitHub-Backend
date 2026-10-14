import asyncio
import os
from pathlib import PurePosixPath
from typing import Annotated, List, Literal, TypedDict
from pydantic import BaseModel
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Request
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openrouter import ChatOpenRouter
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pinecone import Pinecone
from utilities.fetch_repo import fetch_repo_text
from utilities.tokens import get_current_user

load_dotenv()

class ChatRequest(BaseModel):
    question: str

router = APIRouter(prefix="/rag", tags=["rag"])

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("github-rag")

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
)

embeddings = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
model = ChatOpenRouter(model_name="nvidia/nemotron-3.5-lightning:free")

class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: str
    repo_name: str
    context: str
    indexed: bool

def get_namespace(state: State) -> str:
    return f"{state['user_id']}:{state['repo_name']}"

def get_vectorstore(namespace: str) -> PineconeVectorStore:
    return PineconeVectorStore(index=index, embedding=embeddings, namespace=namespace)

async def check_index(state: State):
    stats = await asyncio.to_thread(index.describe_index_stats)
    return {"indexed": get_namespace(state) in stats.namespaces}

def route_after_check(state: State) -> Literal["index_repo", "retrieve"]:
    return "retrieve" if state["indexed"] else "index_repo"

async def index_repo(state: State):
    items = await fetch_repo_text(
        state["repo_name"],
        {"user_id": state["user_id"]}
    )
    docs = []

    structure = "\n".join(
        f"{item['type'].capitalize()}: {item['path']}"
        for item in items
        if item["type"] in ["folder", "file"]
    )
    docs.append(
        Document(
            page_content=f"Repository Structure:\n{structure}",
            metadata={"type": "repository_structure"}
        )
    )

    for item in items:
        if item["type"] == "file" and item["content"]:
            path = item["path"]
            folder = str(PurePosixPath(path).parent)
            for chunk in splitter.split_text(item["content"]):
                docs.append(
                    Document(
                        page_content=f"Folder: {folder}\nFile: {path}\n\n{chunk}",
                        metadata={
                            "type": "file_content",
                            "path": path,
                            "folder": folder
                        }
                    )
                )

    vectorstore = get_vectorstore(get_namespace(state))
    for i in range(0, len(docs), 10):
        await vectorstore.aadd_documents(docs[i:i + 10])
        await asyncio.sleep(1)

    return {"indexed": True}

async def retrieve(state: State):
    question = state["messages"][-1].content
    namespace = get_namespace(state)
    vector_store = get_vectorstore(namespace)

    question_lower = question.lower()

    # Light detection: kya user kisi file ka full code maang raha hai?
    is_file_request = any(
        keyword in question_lower 
        for keyword in [".py", ".js", ".ts", ".md", "full code", "complete code", "generate code", "show code"]
    )

    # File request ho to thoda zyada, warna kam
    k = 8 if is_file_request else 5
    fetch_k = 20 if is_file_request else 12

    retriever = vector_store.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": k,
            "fetch_k": fetch_k,
            "lambda_mult": 0.65
        }
    )

    docs = await retriever.ainvoke(question)

    # Duplicate remove
    unique_docs = []
    seen = set()
    for doc in docs:
        key = hash(doc.page_content[:120])
        if key not in seen:
            seen.add(key)
            unique_docs.append(doc)

    context = "\n\n---\n\n".join(doc.page_content for doc in unique_docs)
    return {"context": context}

def route_after_retrieve(state: State) -> Literal["generate", "no_context"]:
    return "generate" if state["context"].strip() else "no_context"

async def generate(state: State):
    system = SystemMessage(
        content=f"""
You are a strict repository code assistant.

STRICT OUTPUT RULES:
- When user asks for a file's code, reply with ONLY the code.
- Start directly with the markdown code block.
- Do NOT write any title, explanation, introduction, summary, key components, or setup instructions.
- Do NOT write sentences like "Based on the repository context" or "Here is the complete code".
- Do NOT add ## headings of any kind.
- Only output the reconstructed code inside one ```python code block.
- If parts are missing, put a short comment inside the code.

REPOSITORY CONTEXT:
====================
{state["context"]}
====================
"""
    )

    response = await model.ainvoke([system] + state["messages"])
    return {"messages": [response]}

async def no_context(state: State):
    return {"messages": [AIMessage(content="Is repo mein is sawal ka jawab nahi mila.")]}

def build_graph(checkpointer):
    builder = StateGraph(State)
    builder.add_node("check_index", check_index)
    builder.add_node("index_repo", index_repo)
    builder.add_node("retrieve", retrieve)
    builder.add_node("generate", generate)
    builder.add_node("no_context", no_context)

    builder.add_edge(START, "check_index")
    builder.add_conditional_edges("check_index", route_after_check)
    builder.add_edge("index_repo", "retrieve")
    builder.add_conditional_edges("retrieve", route_after_retrieve)
    builder.add_edge("generate", END)
    builder.add_edge("no_context", END)

    return builder.compile(checkpointer=checkpointer)

@router.post("/{repo_name}/chat")
async def chat_with_repo(
    repo_name: str,
    data: ChatRequest,
    request: Request,
    user=Depends(get_current_user),
):
    user_id = str(user["user_id"])
    namespace = user_id + ":" + repo_name
    config = {"configurable": {"thread_id": namespace}}

    result = await request.app.state.graph.ainvoke(
        {
            "messages": [HumanMessage(content=data.question)],
            "user_id": user_id,
            "repo_name": repo_name,
        },
        config,
    )

    return {
        "answer": result["messages"][-1].content,
        "context": result.get("context", "")
    }