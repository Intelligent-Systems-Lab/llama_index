from typing import Any, List, Optional, Sequence

from llama_index.bridge.langchain import (
    BaseChatMemory,
    ChatMessageHistory,
    ConversationBufferMemory,
)
from llama_index.chat_engine.types import (
    BaseChatEngine,
    AgentChatResponse,
    StreamingAgentChatResponse,
)
from llama_index.indices.query.base import BaseQueryEngine
from llama_index.indices.service_context import ServiceContext
from llama_index.langchain_helpers.agents.agents import (
    AgentExecutor,
    AgentType,
    initialize_agent,
)
from llama_index.llm_predictor.base import LLMPredictor
from llama_index.llms.base import ChatMessage
from llama_index.llms.langchain import LangChainLLM
from llama_index.llms.langchain_utils import (
    from_lc_messages,
    is_chat_model,
    to_lc_messages,
)
from llama_index.tools.query_engine import QueryEngineTool


class ReActChatEngine(BaseChatEngine):
    """ReAct Chat Engine.

    Use a ReAct agent loop with query engine tools. Implemented via LangChain agent.
    """

    def __init__(
        self,
        query_engine_tools: Sequence[QueryEngineTool],
        llm: LangChainLLM,
        memory: BaseChatMemory,
        system_prompt: Optional[str] = None,
        verbose: bool = False,
    ) -> None:
        self._query_engine_tools = query_engine_tools
        self._llm = llm
        self._memory = memory
        self._system_prompt = system_prompt
        self._verbose = verbose

        self._agent = self._create_agent()

    @classmethod
    def from_defaults(
        cls,
        query_engine_tools: Sequence[QueryEngineTool],
        service_context: Optional[ServiceContext] = None,
        memory: Optional[BaseChatMemory] = None,
        chat_history: Optional[List[ChatMessage]] = None,
        verbose: bool = False,
        system_prompt: Optional[str] = None,
        prefix_messages: Optional[List[ChatMessage]] = None,
        **kwargs: Any,
    ) -> "ReActChatEngine":
        """Initialize a ReActChatEngine from default parameters."""
        del kwargs  # Unused

        service_context = service_context or ServiceContext.from_defaults()
        if not isinstance(service_context.llm_predictor, LLMPredictor):
            raise ValueError("Currently only supports LLMPredictor.")
        llm = service_context.llm_predictor.llm
        if not isinstance(llm, LangChainLLM):
            raise ValueError("Currently only supports LangChain based LLM.")
        lc_llm = llm.llm

        if chat_history is not None and memory is not None:
            raise ValueError("Cannot specify both memory and chat_history.")

        if memory is None:
            lc_messages = to_lc_messages(chat_history or [])
            lc_history = ChatMessageHistory(messages=lc_messages)

            memory = ConversationBufferMemory(
                memory_key="chat_history",
                chat_memory=lc_history,
                return_messages=is_chat_model(lc_llm),
            )

        if prefix_messages is not None:
            raise NotImplementedError(
                "prefix_messages is not supported for ReActChatEngine."
            )

        return cls(
            query_engine_tools=query_engine_tools,
            llm=llm,
            memory=memory,
            system_prompt=system_prompt,
            verbose=verbose,
        )

    @classmethod
    def from_query_engine(
        cls,
        query_engine: BaseQueryEngine,
        name: Optional[str] = None,
        description: Optional[str] = None,
        service_context: Optional[ServiceContext] = None,
        memory: Optional[BaseChatMemory] = None,
        chat_history: Optional[List[ChatMessage]] = None,
        verbose: bool = False,
        **kwargs: Any,
    ) -> "ReActChatEngine":
        query_engine_tool = QueryEngineTool.from_defaults(
            query_engine=query_engine, name=name, description=description
        )
        return cls.from_defaults(
            query_engine_tools=[query_engine_tool],
            service_context=service_context,
            memory=memory,
            chat_history=chat_history,
            verbose=verbose,
            **kwargs,
        )

    def _create_agent(self) -> AgentExecutor:
        tools = [qe_tool.as_langchain_tool() for qe_tool in self._query_engine_tools]
        agent_kwargs = {}
        if is_chat_model(self._llm.llm):
            agent_type = AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION
            if self._system_prompt is not None:
                agent_kwargs["system_message"] = self._system_prompt
        else:
            agent_type = AgentType.CONVERSATIONAL_REACT_DESCRIPTION
            if self._system_prompt is not None:
                agent_kwargs["prefix"] = self._system_prompt

        return initialize_agent(
            tools=tools,
            llm=self._llm.llm,
            agent=agent_type,
            memory=self._memory,
            verbose=self._verbose,
            agent_kwargs=agent_kwargs,
        )

    @property
    def chat_history(self) -> List[ChatMessage]:
        assert isinstance(self._memory, ConversationBufferMemory)
        return from_lc_messages(self._memory.chat_memory.messages)

    def chat(
        self, message: str, chat_history: Optional[List[ChatMessage]] = None
    ) -> AgentChatResponse:
        if chat_history is not None:
            raise NotImplementedError(
                "chat_history argument is not supported for ReActChatEngine."
            )

        response = self._agent.run(input=message)
        return AgentChatResponse(response=response)

    async def achat(
        self, message: str, chat_history: Optional[List[ChatMessage]] = None
    ) -> AgentChatResponse:
        if chat_history is not None:
            raise NotImplementedError(
                "chat_history argument is not supported for ReActChatEngine."
            )

        response = await self._agent.arun(input=message)
        return AgentChatResponse(response=response)

    def stream_chat(
        self, message: str, chat_history: Optional[List[ChatMessage]] = None
    ) -> StreamingAgentChatResponse:
        raise NotImplementedError("stream_chat() is not supported for ReActChatEngine.")

    async def astream_chat(
        self, message: str, chat_history: Optional[List[ChatMessage]] = None
    ) -> StreamingAgentChatResponse:
        raise NotImplementedError(
            "astream_chat() is not supported for ReActChatEngine."
        )

    def reset(self) -> None:
        self._memory.clear()
        self._agent = self._create_agent()
