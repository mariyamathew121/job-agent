from langchain_openai import ChatOpenAI
from config.settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, LLM_MODEL

def get_llm(model=None, temperature=0.3):
    return ChatOpenAI(
        model           = model or LLM_MODEL,
        temperature     = temperature,
        openai_api_key  = OPENROUTER_API_KEY,
        openai_api_base = OPENROUTER_BASE_URL,
        default_headers = {
            "HTTP-Referer": "https://github.com/mariy/job-agent",
            "X-Title":      "AI Job Agent"
        }
    )

llm          = get_llm()
llm_precise  = get_llm(temperature=0.1)
llm_creative = get_llm(temperature=0.7)