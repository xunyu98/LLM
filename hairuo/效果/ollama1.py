import pandas as pd
from tqdm import tqdm
import requests
import json

file_name ="/Users/xunyu/PycharmProjects/hairuo/效果/测试集.xlsx"
df = pd.read_excel(file_name)
random_questions = df['问题'].fillna(' ')
print(random_questions)
modelname = "deepseek-r1:1.5b"


url = "http://localhost:11434/api/v1/generate"
headers = {
    "Content-Type": "application/json"
}

result_file_name = f"{file_name.split('.')[0].rsplit('/')[-1]}_{modelname}_result.xlsx"
result = []
i = 0
for j in tqdm(range(len(random_questions))):
    i += 1
    answer = ""
    try:
        data = {
        "model": modelname,
        "prompt": random_questions[j],
        "stream": False,
        "options": {
            "temperature": 0.7,
            "max_tokens": 100
            }
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        result = response.json()
        answer = response["response"]

    except Exception as e:
        print(e)
    result.append({modelname: answer})
    if i % 1 == 0 or j == len(random_questions) - 1:
        df = pd.DataFrame(result)
        df.to_excel(result_file_name, index=False)

