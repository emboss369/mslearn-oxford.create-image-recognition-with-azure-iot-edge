import os
import asyncio # asyncio は async/await 構文を使い 並行処理の コードを書くためのライブラリ
import sys
import signal # 非同期イベントにハンドラを設定する
import threading # スレッドベースの並列処理
from azure.iot.device.aio import IoTHubModuleClient # このライブラリは、IoT デバイスから Azure IoT サービスと通信するための非同期クライアントを提供します。

# main.py ファイルの上部で、json ライブラリをインポートします。
import json

import CameraCapture
from CameraCapture import CameraCapture

# Event indicating client stop
stop_event = threading.Event()

SPEECH_MAP_FILENAME = None


# global counters
# TEMPERATURE_THRESHOLD、RECEIVED_MESSAGES および TWIN_CALLBACKS 変数の
# グローバル定義を追加します。 温度のしきい値により、データが IoT Hub に送信される
# 基準値が設定されます。データは、マシンの測定温度がこの値を超えると送信されます。
TEMPERATURE_THRESHOLD = 25
TWIN_CALLBACKS = 0
RECEIVED_MESSAGES = 0


def create_client():
    client = IoTHubModuleClient.create_from_edge_environment()

    # 受信したメッセージを処理する機能を定義する
    # Azure IoT Edge ルート通信コールバックは receive_message_handler() で実装されています。
    # Pythonでは関数内で関数を定義できます。receive_message_handler関数は、create_client関数内のネストした関数ですね
    async def receive_message_handler(message):
        global RECEIVED_MESSAGES # 関数内でグローバル変数にアクセス
        print("Message received")
        size = len(message.data) # ログ表示のためにメッセージサイズ取得
        message_text = message.data.decode('utf-8') # データをデコードする
        print("    Data: <<<{data}>>> & Size={size}".format(data=message.data, size=size))
        print("    Properties: {}".format(message.custom_properties))
        RECEIVED_MESSAGES += 1
        print("Total messages received: {}".format(RECEIVED_MESSAGES))


    # 受信したツインパッチに対応する機能を定義する。
    # これは、設定変更をIoT Hub側から行える機能で、例えば温度センサーが日本全国100箇所にあったとするじゃない？
    # その場合に全国行脚しなくてもIoT Hub上（クラウド上）で操作すれば、例えば下の例のようにTEMPERATURE_THRESHOLDの値を
    # 変更できちゃう、というわけです。
    async def receive_twin_patch_handler(twin_patch):
        global SPEECH_MAP_FILENAME
        global TWIN_CALLBACKS
        print("Twin Patch received")
        print("     {}".format(twin_patch))
        if "SpeechMapFilename" in twin_patch:
            SPEECH_MAP_FILENAME = twin_patch["SpeechMapFilename"]
            
        TWIN_CALLBACKS += 1
        print("Total calls confirmed: {}".format(TWIN_CALLBACKS))

    try:
        # クライアントにハンドラーを設定する
        client.on_message_received = receive_message_handler
        client.on_twin_desired_properties_patch_received = receive_twin_patch_handler
    except:
        # 障害発生時のクリーンアップ
        client.shutdown()
        raise

    return client


async def run_sample(client):
    global SPEECH_MAP_FILENAME
    # このコルーチンをカスタマイズして、モジュールが開始するあらゆるタスクを実行させる
    # e.g. 送信
    try:
        VIDEO_PATH = os.getenv('Video', '0')
        PREDICT_THRESHOLD = os.getenv('Threshold', .75)
        IMAGE_PROCESSING_ENDPOINT = os.getenv('AiEndpoint', 'http://localhost:80/image')
        AZURE_SPEECH_SERVICES_KEY = os.getenv('azureSpeechServicesKey', '2f57f2d9f1074faaa0e9484e1f1c08c1')
        SPEECH_MAP_FILENAME = os.getenv('SpeechMapFilename', 'speech_map_american.json')

    except ValueError as error:
        print(error)
        sys.exit(1)
    with CameraCapture(VIDEO_PATH, AZURE_SPEECH_SERVICES_KEY, PREDICT_THRESHOLD, IMAGE_PROCESSING_ENDPOINT, SPEECH_MAP_FILENAME, None) as capture:
        print(capture)
        while True:
            capture.scan(SPEECH_MAP_FILENAME)
            await asyncio.sleep(1)


def main():

    # Pythonのバージョンをチェックして古ければエラーで止めます。
    if not sys.version >= "3.5.3":
        raise Exception( "The sample requires python 3.5.3+. Current version of Python: %s" % sys.version )
    print ( "IoT Hub Client for Python" )

    # NOTE: Client is implicitly connected due to the handler being set on it
    client = create_client()

    # Edgeでモジュール終了時にクリーンアップするハンドラを定義する。
    def module_termination_handler(signal, frame):
        print ("IoTHubClient sample stopped by Edge")
        stop_event.set()

    # Edgeの終了ハンドラを設定する
    signal.signal(signal.SIGTERM, module_termination_handler)

    # サンプルを実行する
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_sample(client))
    except Exception as e:
        print("Unexpected error %s " % e)
        raise
    finally:
        print("Shutting down IoT Hub Client...")
        loop.run_until_complete(client.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
