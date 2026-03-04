from openai import OpenAI, AzureOpenAI
from utils import extract_all_blocks
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment


def _default_model():
    """Return the model name from env, falling back to gpt-4o."""
    return os.environ.get("LLM_MODEL", "gpt-4o")


def _build_client(azure=False, model=None):
    """Build an OpenAI-compatible client.

    Priority:
      1. Internal API  — LLM_BASE_URL + LLM_API_KEY are set in .env
      2. Azure OpenAI  — azure=True flag
      3. OpenAI        — standard OPENAI_API_KEY
    """
    llm_base_url = os.environ.get("LLM_BASE_URL")
    llm_api_key = os.environ.get("LLM_API_KEY")

    if llm_base_url and llm_api_key:
        # OpenAI-compatible internal API
        return OpenAI(
            base_url=llm_base_url,
            api_key=llm_api_key,
        )

    if azure:
        api_version = "2024-12-01-preview" if model in ["o1-preview", "o1-mini"] else None
        kwargs = dict(
            azure_endpoint=os.environ.get("AZURE_ENDPOINT"),
            api_key=os.environ.get("AZURE_OPENAI_KEY"),
        )
        if api_version:
            kwargs["api_version"] = api_version
        return AzureOpenAI(**kwargs)

    # Standard OpenAI
    kwargs = dict(api_key=os.environ.get("OPENAI_API_KEY"))
    if model in ["o1-preview", "o1-mini"]:
        kwargs["api_version"] = "2024-12-01-preview"
    return OpenAI(**kwargs)


class GPTChat:
    def __init__(self, azure=False, model=None, temperature=1) -> None:
        if model is None:
            model = _default_model()

        self.client = _build_client(azure=azure, model=model)
        self.messages = []
        self.model = model
        self.temperature = float(temperature)

    def get_model_response(self, prompt, code_format):
        self.messages.append({"role": "user", "content": prompt})
        sql_query = []
        max_try = 0
        while not sql_query and max_try < 3:
            max_try += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    temperature=self.temperature
                )
            except Exception as e:
                if "Error code" in str(e):
                    print("Error code: 400, exit: " + str(e))
                    sys.exit(0)
                print(e)
                return e
            choices = response.choices
            if choices:
                main_content = choices[0].message.content
                sql_query = extract_all_blocks(main_content, code_format)
                self.messages.append({"role": "assistant", "content": main_content})
            if not sql_query:
                print(f"sql_query: {sql_query}, max_try: {max_try}")
                self.messages.append({"role": "user", "content": f"Please answer in ```{code_format}``` format with one sql query."})
                continue

        return sql_query

    def get_model_response_txt(self, prompt):
        self.messages.append({"role": "user", "content": prompt})
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                temperature=self.temperature
            )
        except Exception as e:
            print(e)
            return e
        choices = response.choices
        if choices:
            main_content = choices[0].message.content

        self.messages.append({"role": "assistant", "content": main_content})
        return main_content

    def get_message_len(self):
        return sum([len(i['content']) for i in self.messages])

    def init_messages(self):
        self.messages = []
