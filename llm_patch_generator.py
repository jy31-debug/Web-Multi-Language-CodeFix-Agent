from dotenv import load_dotenv
import os

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


load_dotenv()


def get_deepseek_llm():
    """
    Create a LangChain ChatOpenAI client configured for DeepSeek.
    DeepSeek uses an OpenAI-compatible API format.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    if not api_key:
        return None

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
    )


def build_patch_prompt():
    return ChatPromptTemplate.from_messages(
        [
            (
    "system",
    """
You are a careful CodeFix Agent.

Your task is to repair buggy code based on:
1. the user's requirement,
2. the programming language,
3. the original source code,
4. optional error or test information,
5. optional retrieved context.

Rules:
- Return the full fixed code, not only a fragment.
- Do not add markdown code fences.
- Keep the original code style as much as possible.
- Do not invent files that are not provided.
- If the input is a single file, return only the fixed content of that file.
- If the user's requirement is written in Chinese, write ERROR_CAUSE and FIX_SUMMARY in Chinese.
- If the user's requirement is written in English, write ERROR_CAUSE and FIX_SUMMARY in English.
- The code itself must remain valid code in the target programming language.

Output format:

ERROR_CAUSE:
<brief explanation in the same language as the user requirement>

FIX_SUMMARY:
<brief summary in the same language as the user requirement>

FIXED_CODE:
<full fixed code>
""",
),
            (
                "human",
                """
User requirement:
{user_requirement}

Programming language:
{language}

Original source code:
{source_code}

Error or test information:
{error_info}

Retrieved context:
{retrieved_context}
""",
            ),
        ]
    )


def fallback_generate_patch(
    user_requirement: str,
    language: str,
    source_code: str,
    error_info: str = "",
    retrieved_context: str = "",
) -> dict:
    """
    Fallback mode when DEEPSEEK_API_KEY is not configured.
    This keeps the pipeline runnable without a real LLM call.
    """
    return {
        "success": False,
        "mode": "fallback",
        "error_cause": "DEEPSEEK_API_KEY is not configured, so no real LLM call was made.",
        "fix_summary": "Returned original code as fallback output.",
        "fixed_code": source_code,
        "raw_output": "Fallback mode: no API key.",
    }


def parse_llm_output(raw_output: str) -> dict:
    error_cause = ""
    fix_summary = ""
    fixed_code = ""

    if "ERROR_CAUSE:" in raw_output and "FIX_SUMMARY:" in raw_output and "FIXED_CODE:" in raw_output:
        try:
            after_error = raw_output.split("ERROR_CAUSE:", 1)[1]
            error_cause, after_summary_marker = after_error.split("FIX_SUMMARY:", 1)
            fix_summary, fixed_code = after_summary_marker.split("FIXED_CODE:", 1)

            return {
                "success": True,
                "mode": "llm",
                "error_cause": error_cause.strip(),
                "fix_summary": fix_summary.strip(),
                "fixed_code": fixed_code.strip(),
                "raw_output": raw_output,
            }
        except ValueError:
            pass

    return {
        "success": True,
        "mode": "llm_unparsed",
        "error_cause": "",
        "fix_summary": "LLM output did not strictly match the expected format.",
        "fixed_code": raw_output.strip(),
        "raw_output": raw_output,
    }


def generate_patch(
    user_requirement: str,
    language: str,
    source_code: str,
    error_info: str = "",
    retrieved_context: str = "",
) -> dict:
    """
    Generate a repaired version of the source code using LangChain + DeepSeek.

    If the LLM API call fails because of network or SSL issues, the function
    returns a safe fallback result instead of crashing the whole Agent workflow.
    """
    llm = get_deepseek_llm()

    if llm is None:
        return fallback_generate_patch(
            user_requirement=user_requirement,
            language=language,
            source_code=source_code,
            error_info=error_info,
            retrieved_context=retrieved_context,
        )

    prompt = build_patch_prompt()
    chain = prompt | llm | StrOutputParser()

    try:
        raw_output = chain.invoke(
            {
                "user_requirement": user_requirement,
                "language": language,
                "source_code": source_code,
                "error_info": error_info,
                "retrieved_context": retrieved_context,
            }
        )

        return parse_llm_output(raw_output)

    except Exception as exc:
        return {
            "success": False,
            "mode": "llm_error_fallback",
            "error_cause": f"LLM API call failed: {exc}",
            "fix_summary": "Returned original code because the LLM API call failed.",
            "fixed_code": source_code,
            "raw_output": str(exc),
        }

def main():
    print("=== Day 19 LLM Patch Generator Test ===")

    source_code = """def add(a, b):
    return a - b
"""

    user_requirement = "Fix this function. It should return the sum of a and b."

    result = generate_patch(
        user_requirement=user_requirement,
        language="python",
        source_code=source_code,
        error_info="The function returns subtraction instead of addition.",
        retrieved_context="This is a simple arithmetic function.",
    )

    print("success:", result["success"])
    print("mode:", result["mode"])
    print("\nERROR_CAUSE:")
    print(result["error_cause"])
    print("\nFIX_SUMMARY:")
    print(result["fix_summary"])
    print("\nFIXED_CODE:")
    print(result["fixed_code"])


if __name__ == "__main__":
    main()