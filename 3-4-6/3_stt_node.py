from miniROS import *

################################################GUI节点#################################################

import json 
import easygui
import time
gui_node = Node('GUI')
@initialize(gui_node)
def init():
    gui_node.messages = [] # 用于存储别的节点发来的信息
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    print(config)
    password = easygui.passwordbox('请输入登录密码')
    if password ==  config['password']:
        easygui.msgbox('登录成功，欢迎进入机器人操作系统')    
    else:
        easygui.msgbox('登录失败')
        miniROS.stop()

@set_task(gui_node, loop=True, main=True)
def set_input():
    # 将阻塞时收到的信息全部显示出来
    while gui_node.messages:
        message = gui_node.messages.pop(0)
        easygui.msgbox(message)

    choice = easygui.buttonbox('请选择操作', choices=['刷新状态','开始聊天', '设定角色'])

    if choice == '刷新状态':
        gui_node.node_continue()

    if choice == '开始聊天':
        Bus.publish('start_chat', None)
        while not gui_node.messages:
            pass
        choice = easygui.buttonbox(gui_node.messages.pop(0), '聊天信息',choices=['语音输入','文字输入','取消'])

        if choice == '语音输入':
            Bus.publish('record_signal', True)
            time.sleep(3)
            Bus.publish('record_signal', False)
            gui_node.node_continue()
        if choice == '文字输入':
            message = easygui.enterbox('请输入聊天内容', '聊天信息')
        else:
            message = None

        while message:
            Bus.publish('continue_chat', message)
            while not gui_node.messages:
                time.sleep(0.001)
            message = easygui.enterbox(gui_node.messages.pop(0), '聊天信息')

        gui_node.node_continue()


    if choice == '设定角色':
        character = easygui.enterbox('请输入角色性格', '角色性格')
        talk_manner = easygui.enterbox('请输入说话方式', '说话方式')
        if not character or not talk_manner:
            gui_node.node_continue()
        else:
            Bus.publish('setting', {'character':character, 'talk_manner':talk_manner})

    
    while not gui_node.messages:
        pass


@subscribe(gui_node, 'message')
def handler(data):
    gui_node.messages.append(data)



################################################提示词节点#################################################
import json
prompt_node = Node('Prompt')

@initialize(prompt_node)
def init():
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    prompt_node.character = config['character']
    prompt_node.talk_manner = config['talk_manner']
    
@subscribe(prompt_node, 'start_chat')
def handler(data):
    prompt = f"请完全重置你自己的性格和说话方式，接下来我和你的对话, 请你的性格是：{prompt_node.character}，\
            你和我的对话方式是：{prompt_node.talk_manner}。回答必须限定60字以内。如果明白，用符合人设的10个字以内的回答回复。"
    Bus.publish('prompt', {'prompt':prompt, 'is_first':True})

@subscribe(prompt_node, 'continue_chat')
def handler(data):
    Bus.publish('prompt', {'prompt':data, 'is_first':False})
     
@subscribe(prompt_node, 'setting')
def handler(data):
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    with open('config.json', 'w', encoding='utf-8') as f:
        config['character'] = data['character']
        config['talk_manner'] = data['talk_manner']
        json.dump(config, f)
    Bus.publish('message','设置成功')
    prompt_node.character = data['character']
    prompt_node.talk_manner = data['talk_manner']


################################################大模型节点#################################################
import requests
import json

# 此处的 API_Key 和 Secrete_Key 可从教程https://developer.baidu.com/article/detail.html?id=1089328 自己执行获得
# 此处调用的是文心一言的大模型，此处需要自己充值一些，以防余额不足
LLM_node = Node('LLM')


@initialize(LLM_node)
def init():
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    request_url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={config['API_Key']}&client_secret={config['Secret_Key']}"
    payload = json.dumps("")
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    try:
        response = requests.request("POST", request_url, headers=headers, data=payload)
    except Exception as e:
        print(e)
    LLM_node.url = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/ernie-4.0-turbo-8k?access_token=" + response.json().get("access_token")

    LLM_node.payload = {"messages":[]}
    
    
@subscribe(LLM_node, 'prompt')
def handler(data):
    if data['is_first']:
        LLM_node.payload = {"messages":[]}
    LLM_node.payload["messages"].append({
                "role": "user",
                "content": data['prompt']
            })

    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", LLM_node.url, headers=headers, data=json.dumps(LLM_node.payload)).json()
    error=response.get('error_msg')
    
    if not error:
        answer=response.get('result')
        LLM_node.payload["messages"].append({
                    "role": "assistant",
                    "content": answer
                })
    else:
        answer = 'error: ' + error
        LLM_node.payload["messages"].pop()
        
    Bus.publish('message', answer)
    Bus.publish('text_to_speak', answer)


###################################################文字转语音节点########################################
import pyttsx3

TTS_node = Node('TTS')

@initialize(TTS_node)
def init():
    engine = pyttsx3.init()
    rate = engine.getProperty('rate') 
    engine.setProperty('rate', rate+50)
    TTS_node.engine = engine

@subscribe(TTS_node, 'text_to_speak')
def handler(answer):
    TTS_node.engine.say(answer)
    TTS_node.engine.runAndWait()



################################################麦克风录音节点##################################
import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np
import time

record_node = Node('record', fs=44100, filename='record.wav')

@initialize(record_node)
def init():
    record_node.is_recording = False

@set_task(record_node, loop=True)
def setup_record():
    # 等待开始录音
    while not record_node.is_recording:
        time.sleep(0.01)
    # 初始化录音缓存
    recording = []
    
    # 开始录音
    try:
        with sd.InputStream(samplerate=record_node.fs, channels=2, dtype='float32') as stream:
            while record_node.is_recording:
                data, _ = stream.read(1024)
                recording.append(data)
    except Exception as e:
        print(e)
    # 录音结束后处理和保存文件
    recording_array = np.concatenate(recording, axis=0)  # 合并数组
    wav_data = np.int16(recording_array / np.max(np.abs(recording_array)) * 32767)
    wav.write(record_node.filename, record_node.fs, wav_data)
    Bus.publish('STT', record_node.filename)

@subscribe(record_node, 'record_signal')
def handle(is_started):
    record_node.is_recording = is_started
    


###################################################语音转文字节点#########################################
import assemblyai as aai

STT_node = Node('STT')

@initialize(STT_node)
def init():
    # 此处的密钥需要自己登陆网址https://www.assemblyai.com/，注册即可获得，免费使用
    aai.settings.api_key = "59057d149d6a468b84b94a65ed646f7a"
    STT_node.config = aai.TranscriptionConfig(language_code='zh')
    STT_node.transcriber = aai.Transcriber()
    
@subscribe(STT_node, 'STT')
def handler(filename):
    # 通过assemblyai库将语音转文字
    transcript = STT_node.transcriber.transcribe(filename, config=STT_node.config)
    if transcript.status == aai.TranscriptStatus.error:
        print(transcript.error)
    else:
        print(transcript.text)
        Bus.publish('prompt', transcript.text)
    


#################################################注册要运行的节点###########################################
LLM_node.register()
prompt_node.register()
gui_node.register()
TTS_node.register()
record_node.register()
STT_node.register()
miniROS.run()