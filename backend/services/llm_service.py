from typing import AsyncGenerator
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from core.config import get_settings

settings = get_settings()

_prompt = PromptTemplate.from_template(
    "You are a helpful assistant. Please summarize the following text concisely:\n\n{text}"
)


def _build_llm() -> BaseChatModel:
    """Factory that returns the configured LangChain chat model."""
    provider = settings.llm_provider.lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=0.3,
            api_key=settings.api_key.get_secret_value(),
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_model,
            temperature=0.3,
            api_key=settings.openai_api_key.get_secret_value(),
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.anthropic_model,
            temperature=0.3,
            api_key=settings.anthropic_api_key.get_secret_value(),
        )
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}'. Choose: gemini | openai | anthropic"
        )


llm = _build_llm()


def summarize_text(text: str) -> str:
    chain = _prompt | llm
    response = chain.invoke({"text": text})
    return response.content


async def summarize_text_stream(text: str) -> AsyncGenerator[str, None]:
    """Async generator that streams summary tokens via LangChain's astream."""
    chain = _prompt | llm
    async for chunk in chain.astream({"text": text}):
        if chunk.content:
            yield chunk.content