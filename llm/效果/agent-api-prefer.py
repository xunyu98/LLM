import time
import json
import random
from datetime import datetime

from locust import task, HttpUser, events, LoadTestShape
from locust.runners import logger
from locust.exception import StopUser
import pandas as pd
import os
import sqlite3
import requests

# 服务器执行脚本格式参考 根据实际测试修改host值
# locust -f agent-api-prefer.py --host=http://10.110.146.201:8000 --logfile=prefer-log.txt

# ---------------需修改变量---------------------------------------------------
# 目标最长时延 单位秒
max_first_char_time = 1
# 目标最短时延 单位秒
min_first_char_time = 0.98
# 固定测试的并发总数，在寻优测试前执行，最后一次结果作为寻优初始并发数
fixed_user_count = [10, 20, 30, 40, 50]
# 最大运行时长 单位秒
max_running_time = 600 * 5
# 单次运行时长 单位秒
single_running_time = 600
# 最大重复并发测试 在目标时间附近时，每次测试并发可能不会变动，这里是最大重复并发数:跑了3次了，第四次还是同并发
max_same_user = 3
max_same_users = [0] * (max_same_user + 1)
# 模型名称 需要根据测试模型修改，一般作为请求Body体值
model_name = "DeepSeek-R1-70B"

path = "/v1/chat/completions"
# --------------------------------------------------------------------------


# ---------------按需修改变量-------------------------------------------------
# 获取token的地址
# get_token_url = "http://100.200.128.83:13009/auth/createToken"
# # 接口Token值 为None时执行方法获取，否则直接使用传入值
# global_token = None
# # 获取token值时传入的body体
# get_token_body = {
#     "userid": 1222121,
#     "username": "test1",
#     "password": "test1",
#     "source": "AGENTSTORE",
#     "expires": 600
# }
# 是否流式请求
is_stream = True
# -------------------------------------------------------------------------

question_list = []
# 当前运行轮次 总运行轮次=最大运行时长/单次运行时长 包含固定测试轮次，默认1无需修改
current_running_cycle = 1
# 当前执行的用户并发数 默认值为固定测试并发首项，无需修改
current_user_count = fixed_user_count[0]
# 每秒最大并发数 递进步长 推荐100以内 一般无需修改
spawn_rate = 100
# 当前并发下首Token时延数据 默认0秒 由上轮次测试结束后计算 无需修改
get_first_char_time = 0

# 常用接口header值，一般无需修改
headers = {"content-type": "application/json",
           'Authorization': 'Bearer token-abc123'}
# 问题列表文件，该文件放在脚本同目录下，无需修改，若修改了文件名，则需要修改
questions_list_file = 'questions_in.xlsx'
# 生成的DB文件名称，无需修改
sqlite3_path = 'test' + datetime.now().strftime('%Y%m%d%H%M%S') + '.db'
conn = sqlite3.connect(sqlite3_path)


# 控制并发数及时间方法
class ConcurrencyController(LoadTestShape):
    # 每秒运行一次这个方法
    def tick(self):
        global max_running_time
        global single_running_time
        global current_running_cycle
        global current_user_count
        global get_first_char_time
        global max_first_char_time
        global fixed_user_count
        print("当前第 " + str(current_running_cycle) + " 轮,并发数为 " + str(current_user_count) + " ")
        # 当前程序运行时长
        run_time = self.get_run_time()
        # 超过最大运行时长 立即停止测试
        if run_time >= max_running_time:
            return None
        if current_running_cycle < len(fixed_user_count):
            if run_time < current_running_cycle * single_running_time:
                return current_user_count, spawn_rate
            else:
                find_avg_char_first_time()
                current_user_count = fixed_user_count[current_running_cycle]
                current_running_cycle = current_running_cycle + 1
                return current_user_count, spawn_rate
        if run_time < current_running_cycle * single_running_time:
            return current_user_count, spawn_rate
        else:
            find_avg_char_first_time()
            current_running_cycle = current_running_cycle + 1
            if max_first_char_time >= get_first_char_time >= min_first_char_time:
                return None
            else:
                current_user_count = int(current_user_count * (max_first_char_time / get_first_char_time))
                # 超过最大重复并发数 立即停止测试
                if check_same_user(current_user_count):
                    return None
            return current_user_count, spawn_rate


# DB文件导出为EXCEL文件方法，无需修改
def to_excel(results):
    user_count = []
    is_stream_ = []
    questions = []
    answers = []
    use_time = []
    output_num = []
    tokens = []
    first_char_time = []
    char_per_sec = []
    token_per_sec = []
    for row in results:
        user_count.append(row[0])
        is_stream_.append(row[1])
        questions.append(row[2])
        answers.append(row[3])
        use_time.append(row[4])
        output_num.append(row[5])
        tokens.append(row[6])
        first_char_time.append(row[7])
        char_per_sec.append(row[8])
        token_per_sec.append(row[9])
    data = pd.DataFrame(
        {
            "并发数": user_count,
            "问题": questions,
            "响应时间（秒）": use_time,
            "平均每秒字符数": char_per_sec,
            "平均每秒token数": token_per_sec,
            "首字符时间（秒）": first_char_time,
            "答案字符长度": output_num,
            "tokens": tokens
        }
    )

    # 求平均值
    data_avg = pd.Series(
        [
            data['并发数'].mean(),
            '平均值',
            data['响应时间（秒）'].mean(),
            data['平均每秒字符数'].mean(),
            data['平均每秒token数'].mean(),
            data['首字符时间（秒）'].mean(),
            data['答案字符长度'].mean(),
            data['tokens'].mean()
        ], index=data.columns)

    new_data = data._append(data_avg, ignore_index=True)

    # 文件路径
    excel_path = f'result--' + datetime.now().strftime('%Y%m%d%H%M%S') + '.xlsx'
    # 如果excel文件不存在，则创建excel文件，并写入并发数据
    if not os.path.isfile(excel_path):
        new_data.to_excel(excel_path, index=False, sheet_name=f"并发{user_count[0]}结果")
    else:
        # 如果excel存在
        with pd.ExcelWriter(excel_path, mode='a', engine='openpyxl') as writer:
            new_data.to_excel(writer, index=False, sheet_name=f"并发{user_count[0]}结果")


# 创建DB文件，无需修改
def create_table():
    # 创建一个Cursor:
    cursor = conn.cursor()
    # 创建表
    create_table_sql = '''
    CREATE TABLE IF NOT EXISTS results (
        user_count INTEGER,
        stream BOOLEAN,
        question TEXT,
        answer TEXT,
        use_time REAL,
        output_num INTEGER,
        tokens INTEGER,
        first_char_sec REAL,
        char_per_sec REAL,
        token_per_sec REAL
    );
    '''
    # 执行创建表的SQL语句
    cursor.execute(create_table_sql)
    # 提交事务
    conn.commit()
    # 关闭Cursor
    cursor.close()


# 查询DB文件，无需修改
def find_data():
    # 创建一个Cursor:
    cursor = conn.cursor()
    # 查询用户并发数
    query_user_sql = '''
            SELECT DISTINCT user_count FROM results;
            '''
    cursor.execute(query_user_sql)
    user_results = cursor.fetchall()
    user_count = [row[0] for row in user_results]
    for user in user_count:
        # 查询数据
        query_data_sql = f'''
                SELECT * FROM results WHERE user_count={user};
                '''
        result = cursor.execute(query_data_sql).fetchall()
        to_excel(result)
    # 关闭Cursor:
    cursor.close()
    # 提交事务:
    conn.commit()


# 获取前一个并发的平均首字符时间，无需修改
def find_avg_char_first_time():
    global get_first_char_time
    global current_user_count
    # 创建一个Cursor:
    cursor = conn.cursor()
    # 获取前一个并发的平均首字符时间
    query_sql = '''
               SELECT IFNULL(AVG(first_char_sec),0) FROM results WHERE user_count = ?;
               '''
    cursor.execute(query_sql, (current_user_count,))
    avg_char_first_time = cursor.fetchone()
    get_first_char_time = avg_char_first_time[0]
    print("本轮次平均首Token时间为: " + str(get_first_char_time))
    # 关闭Cursor:
    cursor.close()
    # 提交事务:
    conn.commit()


# 保存数据，无需修改
def save_data(sql, result_data):
    # 创建一个Cursor:
    cursor = conn.cursor()
    cursor.execute(sql, result_data)
    # 提交事务:
    conn.commit()
    # 关闭Cursor
    cursor.close()


# 检查是否到达重复并发阈值 users: 上次并发数
def check_same_user(users):
    global max_same_users
    print(users)
    print(max_same_users)
    max_same_users.append(users)
    max_same_users.pop(0)
    print(max_same_users)
    return all(max_same_users[0] == users for users in max_same_users)



# 执行创建表（DB文件）:
create_table()


# 无需修改
@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument('--model_name', type=str, default=model_name, help='')


# 总测试开始时运行一次，方法内容目前为获取token，一般无需修改，除非token响应结果位置有变更
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    global question_list


# 总测试结束后运行一次，无需修改
@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    find_data()
    logger.info("性能测试结束 ...")


# 执行测试任务类
class Task(HttpUser):
    # 初始化数据
    def on_start(self):
        global question_list
        global max_running_time

        global model_name

        df = pd.read_excel(questions_list_file)
        question_list = df['prompt'].values
        model_name = self.environment.parsed_options.model_name
        # logger.info('数据初始化完成，开始测试...')

    def on_stop(self):
        global max_running_time
        # logger.info("性能测试结束")

    # 流式
    @task(1)
    def stream(self):
        global model_name
        global path
        global is_stream
        global question_list
        question = random.choice(question_list)
        # 请求的问题
        logger.info(f"question requests: {question}")
        # body = {
        #     "model": model_name,
        #     "stream": is_stream,
        #     "messages": [
        #         {
        #             "role": "user",
        #             "content": question
        #         }
        #     ]
        # }
        body = {"model": model_name, "stream": True, "temperature": 0.9, "top_p": 0.7, "messages": [{"role": "user", "content": question}]}

        i = 0
        # 初始化最后的答案为空字符串
        last_answer = ''
        last_time = None
        first_byte_time = None
        start_time = time.time()
        with self.client.post(path, json=body, stream=True, headers=headers) as response:
            if response.status_code == 200:
                for chunk in response.iter_lines():
                    if chunk:
                        last_time = time.time()
                        decoded_chunk = chunk.decode('utf-8', errors='ignore')  # 可能需要根据实际情况选择编码方式
                        # 心跳检测
                        if 'ping' in decoded_chunk:
                            continue
                        if 'DONE' in decoded_chunk:
                            break
                        if str(decoded_chunk).startswith("data: "):
                            data = json.loads(decoded_chunk.split('data: ')[1])
                            if data['choices'][0]['finish_reason'] != 'stop':
                                if i == 0:
                                    first_byte_time = time.time()
                                i += 1
                                if 'content' in data['choices'][0]['delta']:
                                    last_answer += data['choices'][0]['delta']['content']
                            else:
                                break
                        else:
                            logger.info(f"模型请求失败，问题：{question}, 状态码：{decoded_chunk}")
                            return
            else:
                logger.info(
                    f"接口请求失败，问题：{question}, 状态码：{response.status_code}, 响应参数：{str(response.content)}")
                logger.info("========================================================")
                return
            tokens = i
            answer = str(last_answer)
            output_num = len(answer)
            use_time = last_time - start_time if last_time else None
            char_per_sec = output_num / use_time
            token_per_sec = tokens / use_time
            # 计算首字符时间
            first_char_sec = first_byte_time - start_time if first_byte_time else None
            # 插入一条记录:
            insert_data_sql = '''
            INSERT INTO results
            (user_count, stream, question, answer, use_time, output_num, tokens, first_char_sec, char_per_sec, token_per_sec)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            '''
            result_data = (
                self.environment.runner.user_count,  # user_count
                is_stream,  # stream
                str(question),  # question
                answer,  # answer
                use_time,  # use_time
                output_num,  # output_num
                tokens,  # tokens
                first_char_sec,  # first_char_sec
                char_per_sec,  # char_per_sec
                token_per_sec  # token_per_sec
            )
            save_data(insert_data_sql, result_data)

            # 并发数
            logger.info(f"当前用户数: {self.environment.runner.user_count}")
            # 模型名称
            logger.info(f"model name: {model_name}")
            # 是否流式
            logger.info(f"is stream: {is_stream}")
            # 答案
            logger.info(f"answer: {answer}")
            # 响应时长
            logger.info(f"use time: {use_time}")
            # 答案字符长度
            logger.info(f"answer num: {output_num}")
            # tokens
            logger.info(f"tokens: {tokens}")
            # 首字符时间
            logger.info(f"first_char_sec:{first_char_sec}")
            # 每秒字符数
            logger.info(f"char_per_sec:{char_per_sec}")
            # 每秒token数
            logger.info(f"token_per_sec:{token_per_sec}")
            logger.info("========================================================")
