import requests
api_url = "http://localhost:11434"


def generate_text(model, prompt):
    url = f"{api_url}/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "max_tokens": 100
        }
    }

    response = requests.post(url, json=data)
    if response.status_code == 200:

        result = response.json()
        print(result)
        a = result["response"]
        return a
    else:
        return f"请求失败，状态码: {response.status_code}"


answer = generate_text("deepseek-r1:1.5b", "你是谁")
print("模型回答:", answer)