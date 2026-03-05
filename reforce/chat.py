import os
import sys

from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from utils import extract_all_blocks

try:
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def _default_model():
    """Return the model name from env, falling back to gpt-4o."""
    return os.environ.get("LLM_MODEL", "gpt-4o")


def _build_llm(azure=False, model=None, temperature=1.0):
    """Build a LangChain ChatOpenAI-compatible LLM.

    Priority:
      1. Internal API  — LLM_BASE_URL + LLM_API_KEY are set in .env
      2. Azure OpenAI  — azure=True flag
      3. OpenAI        — standard OPENAI_API_KEY
    """
    llm_base_url = os.environ.get("LLM_BASE_URL")
    llm_api_key = os.environ.get("LLM_API_KEY")

    if llm_base_url and llm_api_key:
        return ChatOpenAI(
            model=model,
            base_url=llm_base_url,
            api_key=llm_api_key,
            temperature=temperature,
            max_retries=3,
        )

    if azure:
        api_version = (
            "2024-12-01-preview" if model in ["o1-preview", "o1-mini"] else "2024-02-01"
        )
        return AzureChatOpenAI(
            azure_deployment=model,
            azure_endpoint=os.environ.get("AZURE_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_KEY"),
            api_version=api_version,
            temperature=temperature,
            max_retries=3,
        )

    return ChatOpenAI(
        model=model,
        api_key=os.environ.get("OPENAI_API_KEY"),
        temperature=temperature,
        max_retries=3,
    )


def _dict_to_lc_message(m):
    """Convert {"role": ..., "content": ...} dict to LangChain message object."""
    role = m.get("role", "user")
    content = m.get("content", "")
    if role == "assistant":
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    return HumanMessage(content=content)


class GPTChat:
    def __init__(self, azure=False, model=None, temperature=1) -> None:
        if model is None:
            model = _default_model()

        self.llm = _build_llm(azure=azure, model=model, temperature=float(temperature))
        self.messages = []  # list of {"role": ..., "content": ...} dicts
        self.model = model
        self.temperature = float(temperature)

    def _invoke(self):
        """Convert self.messages dicts → LangChain messages and invoke LLM.

        Raises:
            Exception: propagates any LLM connection or API error to the caller.
        """
        lc_messages = [_dict_to_lc_message(m) for m in self.messages]
        response = self.llm.invoke(lc_messages)
        return response.content

    def get_model_response(self, prompt, code_format):
        """Send prompt, return list of extracted code blocks (e.g. SQL).

        Retries up to 3 times if the model returns no code block.
        Raises on LLM connection / API errors (400 causes sys.exit).
        """
        self.messages.append({"role": "user", "content": prompt})
        sql_query = []
        max_try = 0
        while not sql_query and max_try < 3:
            max_try += 1
            try:
                main_content = self._invoke()
            except Exception as e:
                if "400" in str(e):
                    print("Error code: 400, exit: " + str(e))
                    sys.exit(0)
                raise  # propagate to caller for proper handling
            self.messages.append({"role": "assistant", "content": main_content})
            sql_query = extract_all_blocks(main_content, code_format)
            if not sql_query:
                print(f"sql_query: {sql_query}, max_try: {max_try}")
                self.messages.append(
                    {"role": "user", "content": f"Please answer in ```{code_format}``` format with one sql query."}
                )

        return sql_query

    def get_model_response_txt(self, prompt):
        """Send prompt, return plain text response string.

        Raises on LLM connection / API errors.
        """
        self.messages.append({"role": "user", "content": prompt})
        main_content = self._invoke()  # raises on error
        self.messages.append({"role": "assistant", "content": main_content})
        return main_content

    def get_message_len(self):
        return sum([len(i['content']) for i in self.messages])

    def init_messages(self):
        self.messages = []
