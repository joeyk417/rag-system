from __future__ import annotations

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import ValidationError

from app.agent.adaptive_rag_state import AdaptiveRAGState, RouterQuery
from app.config import settings
from app.core.providers.base import BaseLLMProvider
from app.db.models import Tenant
from app.schemas.chat import TokenUsage

logger = logging.getLogger(__name__)

# Type alias for an async node callable
_Node = Callable[[AdaptiveRAGState], Coroutine[Any, Any, dict[str, Any]]]

# Default routing config used when tenant config is absent
_DEFAULT_ROUTING = {
    "retrieve_keywords": [
        "document", "SOP", "drawing", "spec", "procedure",
        "formulation", "engineering", "installation", "compound",
    ],
    "web_search_keywords": ["latest", "current", "news", "price", "today", "market"],
    "sql_keywords": ["employee", "department", "salary", "count", "how many"],
}
_DEFAULT_ENABLED_ROUTES = ["retrieve", "web_search"]


def make_route_question_node(
    tenant: Tenant,
    provider: BaseLLMProvider,
) -> _Node:
    """Return an async node that classifies the query and sets datasource.

    Reads tenant.config["routing"] for keyword hints and
    tenant.config["enabled_routes"] for allowed routes.

    Fail-safe: if the LLM returns an invalid or disabled datasource,
    defaults to "retrieve".
    """

    async def route_question_node(state: AdaptiveRAGState) -> dict[str, Any]:
        query = state["query"]
        config = tenant.config or {}
        routing = config.get("routing", _DEFAULT_ROUTING)
        enabled_routes: list[str] = config.get("enabled_routes", _DEFAULT_ENABLED_ROUTES)

        routing_hints = json.dumps(routing, indent=2)
        enabled_str = ", ".join(enabled_routes)

        system_prompt = (
            "You are a query routing assistant. "
            "Given the user's question, decide which data source to query. "
            f"Available data sources: {enabled_str}. "
            "Use the routing keywords as a guide but apply judgment. "
            "Respond ONLY with valid JSON matching: "
            '{"datasource": "<source>", "reasoning": "<brief explanation>"}'
        )
        user_message = (
            f"USER QUESTION:\n{query}\n\n"
            f"ROUTING HINTS:\n{routing_hints}\n\n"
            f"Choose the best datasource from: {enabled_str}"
        )

        datasource = "retrieve"  # fail-safe default
        try:
            raw, _ = await provider.generate(
                system_prompt,
                user_message,
                response_format={"type": "json_object"},
            )
            decision = RouterQuery.model_validate(json.loads(raw))
            if decision.datasource in enabled_routes:
                datasource = decision.datasource
            else:
                logger.warning(
                    "agent.route: datasource '%s' not in enabled_routes %s — falling back to 'retrieve'",
                    decision.datasource,
                    enabled_routes,
                )
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning("agent.route: parse error — defaulting to 'retrieve'", exc_info=exc)

        logger.info(
            "agent.route",
            extra={"tenant": tenant.tenant_id, "query": query, "datasource": datasource},
        )
        return {"datasource": datasource}

    return route_question_node


def make_web_search_agent_node() -> _Node:
    """Return an async node that runs a LangChain ReAct agent with Tavily tool.

    Uses ChatOpenAI + TavilySearchResults. Skips gracefully if TAVILY_API_KEY
    or OPENAI_API_KEY is not configured.
    """

    async def web_search_agent_node(state: AdaptiveRAGState) -> dict[str, Any]:
        if not settings.tavily_api_key:
            logger.warning("agent.web_search_agent.skipped: TAVILY_API_KEY not set")
            return {"answer": "Web search is not configured.", "sources": [], "usage": None}
        if not settings.openai_api_key:
            logger.warning("agent.web_search_agent.skipped: OPENAI_API_KEY not set")
            return {"answer": "LLM provider is not configured.", "sources": [], "usage": None}

        query = state["query"]
        logger.info("agent.web_search_agent", extra={"query": query})

        llm = ChatOpenAI(
            model=settings.openai_llm_model,
            api_key=settings.openai_api_key,  # type: ignore[arg-type]
        )
        tools = [TavilySearchResults(
            max_results=3,
            tavily_api_key=settings.tavily_api_key,  # type: ignore[call-arg]
        )]
        agent = create_react_agent(llm, tools)

        try:
            result = await agent.ainvoke({"messages": [("human", query)]})
            # Final message from the agent is the synthesised answer
            messages = result.get("messages", [])
            answer = messages[-1].content if messages else "No answer generated."
        except Exception as exc:
            logger.warning("agent.web_search_agent.failed", extra={"error": str(exc)})
            answer = "Web search failed. Please try again."

        # Usage tracking: LangGraph ReAct agent doesn't expose token counts directly;
        # we return None and accept this as a known limitation for the web path.
        logger.info(
            "agent.web_search_agent.done",
            extra={"answer_chars": len(answer)},
        )
        return {"answer": answer, "sources": [], "usage": None}

    return web_search_agent_node


def make_sql_agent_node() -> _Node:
    """Return an async node stub for future SQL agent routing.

    Raises NotImplementedError — this route must never appear in enabled_routes
    until a real SQL agent is implemented.
    """

    async def sql_agent_node(state: AdaptiveRAGState) -> dict[str, Any]:
        raise NotImplementedError(
            "SQL agent is not yet implemented. "
            "Remove 'sql_agent' from tenant.config['enabled_routes'] to prevent this route."
        )

    return sql_agent_node
