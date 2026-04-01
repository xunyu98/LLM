import pandas as pd
from tqdm import tqdm
import requests

file_name = "/Users/xunyu/PycharmProjects/hairuo/效果/测试集.xlsx"
sheet_name = "Sheet1"
questions_name = "问题"

url = "http://58.56.78.5:32535/v1/chat/completions"
model_name = "Qwen3-32B"
df = pd.read_excel(file_name, engine="openpyxl", sheet_name=sheet_name)
questions = df[questions_name]

prompt_tokens = []
completion_tokens = []
total_tokens = []
output_answers = []
for i in tqdm(range(len(questions))):
    body = {
        "model": model_name,
        "messages": [
            {
                "role": "assistant",
                "content": questions[i]
            }
        ]
    }
    proxies = {
    "http": None,
    "https": None,
}
    response = requests.post(url, json=body, proxies=proxies).json()
    print(response)
    try:
        prompt_tokens.append(response['usage']['prompt_tokens'])
        completion_tokens.append(response['usage']['completion_tokens'])
        total_tokens.append(response['usage']['total_tokens'])
        output_answers.append(response['choices'][0]['message']['content'])
        print(response['choices'][0]['message']['content'])
    except Exception as e:
        prompt_tokens.append(-1)
        completion_tokens.append(-1)
        total_tokens.append(-1)
        output_answers.append('')
        print(e)

data = {"问题": questions, "答案": output_answers}
df = pd.DataFrame(data)
df.to_excel(f'result-{model_name}-{file_name}-{sheet_name}.xlsx', index=False, engine='openpyxl')
