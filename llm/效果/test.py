import pandas as pd
from tqdm import tqdm
import requests
import json
import time
import os

# ===== 关键修复 1：配置项集中管理（避免路径/模型硬编码）=====
CONFIG = {
    "file_path": "/Users/xunyu/PycharmProjects/hairuo/效果/测试集.xlsx",
    "sheet_name": "Sheet1",
    "question_col": "问题",
    "ollama_url": "http://localhost:11434/api/generate",  # ✅ 修正为标准 Ollama 端点
    "model_name": "qwen3:4b",
    "output_dir": "/Users/xunyu/PycharmProjects/hairuo/效果/results",  # ✅ 指定英文目录
    "timeout_sec": 30  # ⚠️ 合理超时（原600000秒=7天！）
}

# ===== 关键修复 2：安全创建输出目录 =====
os.makedirs(CONFIG["output_dir"], exist_ok=True)

# ===== 关键修复 3：使用正确的Ollama API端点 =====
df = pd.read_excel(CONFIG["file_path"], engine="openpyxl", sheet_name=CONFIG["sheet_name"])
questions = df[CONFIG["question_col"]].astype(str).fillna("")  # ✅ 处理空值

prompt_tokens = []
completion_tokens = []
output_answers = []

# ===== 关键修复 4：添加响应诊断 + 流式响应处理 =====
for i in tqdm(range(len(questions)), desc="Processing Q&A"):
    body = {
        "model": CONFIG["model_name"],
        "prompt": questions[i],
        "stream": False,  # 明确要求非流式
        "options": {
            "temperature": 0.7,
            "num_predict": 100  # ✅ Ollama 参数名是 num_predict (非 max_tokens)
        }
    }
    
    try:
        # ✅ 添加超时 + 验证状态码
        response = requests.post(
            CONFIG["ollama_url"],
            json=body,
            timeout=CONFIG["timeout_sec"]
        )
        
        # ===== 诊断区块（保留到问题解决后）=====
        if response.status_code != 200:
            print(f"\n❌ 请求失败 [状态码: {response.status_code}]")
            print(f"🔍 响应内容: {response.text[:300]}")
            output_answers.append(f"ERROR_{response.status_code}")
            continue
            
        # ===== 关键修复 5：安全解析 Ollama 响应 =====
        try:
            # 尝试标准解析
            data1 = response.json()
            answer = data1.get("response", "").strip()
        except (requests.exceptions.JSONDecodeError, json.JSONDecodeError):
            # 处理意外流式响应（常见于Ollama）
            if "application/json" in response.headers.get("Content-Type", ""):
                # 方案A：合并多JSON对象（Ollama流式响应被错误返回）
                try:
                    parts = [json.loads(part) for part in response.text.strip().split("}") if part.strip()]
                    answer = "".join(p.get("response", "") for p in parts if isinstance(p, dict))
                except:
                    # 方案B：提取所有文本内容
                    answer = response.text.replace('}{', '').replace('{', '').replace('}', '')
            else:
                # 非JSON响应（如错误页）
                answer = f"非JSON响应: {response.text[:200]}"
        
        # ===== 关键修复 6：记录 token 信息 =====
        if "context" in locals().get("data1", {}):
            prompt_tokens.append(len(data1["context"]))
        else:
            prompt_tokens.append(0)
        
        output_answers.append(answer)
        time.sleep(0.1)  # ✅ 优雅限流（避免本地服务过载）
        
    except Exception as e:
        print(f"\n🔥 严重错误 (问题 {i}): {str(e)}")
        print(f"🔍 问题内容: '{questions[i][:50]}...'")
        output_answers.append(f"EXCEPTION_{type(e).__name__}")
        prompt_tokens.append(0)
        time.sleep(1)  # 错误后暂停

# ===== 关键修复 7：安全生成输出文件名 =====
safe_model_name = CONFIG["model_name"].replace(":", "_").replace("/", "_")
output_file = os.path.join(
    CONFIG["output_dir"],
    f"result_{safe_model_name}_{CONFIG['sheet_name']}.xlsx"
)

# ===== 保存结果 =====
result_df = pd.DataFrame({
    "问题": questions,
    "答案": output_answers,
    "prompt_tokens": prompt_tokens
})

result_df.to_excel(output_file, index=False, engine='openpyxl')
print(f"\n✅ 结果已保存至: {output_file}")
print(f"📊 共处理 {len(questions)} 个问题，失败率: {sum('ERROR' in str(a) for a in output_answers)/len(questions):.1%}")