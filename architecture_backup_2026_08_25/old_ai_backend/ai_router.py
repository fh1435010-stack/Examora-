import os
import requests


class AIProviderError(Exception):
    """Raised when an AI provider cannot complete a request."""
    pass


def ask_openai_compatible(
    provider_name,
    base_url,
    api_key_env,
    model_env,
    default_model,
    prompt
):
    api_key = os.getenv(api_key_env)

    if not api_key:
        raise AIProviderError(
            f"{provider_name} API key is not configured"
        )

    model = os.getenv(model_env, default_model)

    url = base_url.rstrip("/") + "/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Examora AI, an educational AI assistant. "
                    "Prioritize factual accuracy and conceptual understanding. "
                    "Do not invent facts. "
                    "If uncertain, say so clearly. "
                    "Explain concepts according to the student's education level."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=60
        )
    except requests.RequestException as error:
        raise AIProviderError(
            f"{provider_name} connection error: {error}"
        )

    if not response.ok:
        raise AIProviderError(
            f"{provider_name} error {response.status_code}: "
            f"{response.text}"
        )

    try:
        result = response.json()
        answer = result["choices"][0]["message"]["content"]

        if not answer:
            raise AIProviderError(
                f"{provider_name} returned an empty answer"
            )

        return answer

    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise AIProviderError(
            f"Unexpected {provider_name} response: {error}"
        )


def ask_gemini(prompt):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise AIProviderError(
            "Gemini API key is not configured"
        )

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-2.0-flash"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=60
        )
    except requests.RequestException as error:
        raise AIProviderError(
            f"Gemini connection error: {error}"
        )

    if not response.ok:
        raise AIProviderError(
            f"Gemini error {response.status_code}: "
            f"{response.text}"
        )

    try:
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise AIProviderError(
            f"Unexpected Gemini response: {error}"
        )


def ask_groq(prompt):
    return ask_openai_compatible(
        "Groq",
        "https://api.groq.com/openai/v1",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "llama-3.3-70b-versatile",
        prompt
    )


def ask_cerebras(prompt):
    return ask_openai_compatible(
        "Cerebras",
        "https://api.cerebras.ai/v1",
        "CEREBRAS_API_KEY",
        "CEREBRAS_MODEL",
        "gpt-oss-120b",
        prompt
    )


def ask_deepseek(prompt):
    return ask_openai_compatible(
        "DeepSeek",
        "https://api.deepseek.com",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "deepseek-chat",
        prompt
    )


def ask_mistral(prompt):
    return ask_openai_compatible(
        "Mistral",
        "https://api.mistral.ai/v1",
        "MISTRAL_API_KEY",
        "MISTRAL_MODEL",
        "mistral-small-latest",
        prompt
    )


def ask_examora_ai(prompt):
    errors = []

    providers = [
        ("Gemini", ask_gemini),
        ("Groq", ask_groq),
        ("Cerebras", ask_cerebras),
        ("DeepSeek", ask_deepseek),
        ("Mistral", ask_mistral)
    ]

    for provider_name, provider_function in providers:
        try:
            answer = provider_function(prompt)

            return {
                "success": True,
                "provider": provider_name,
                "answer": answer,
                "errors": errors
            }

        except Exception as error:
            errors.append(
                f"{provider_name}: {str(error)}"
            )

    return {
        "success": False,
        "provider": None,
        "answer": None,
        "errors": errors
    }
