import sys
import subprocess

# venv内で実行されていない場合、エラーメッセージを出して終了
if not (
    hasattr(sys, "real_prefix")
    or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
):
    print("このボットはvenv内で実行する必要があります！")
    print("Windowsの場合: py -m venv venv を実行後、 .\\venv\\Scripts\\activate で、")
    print(
        "Mac / Linuxの場合: python3 -m venv venv を実行後、 source venv/bin/activate で、"
    )
    print("venvの環境を作り、スクリプトを再度実行してください。")
    sys.exit(1)

print("ボットの実行に必要なライブラリを取得中です...")

# pipをsubprocessで実行 (venvの中のpipを使う)
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True
)

import asyncio

import asyncpg
from cryptography.fernet import Fernet


async def main():
    print("[Jihanki Setup Script]")
    print(
        "このスクリプトでは、自販機をセットアップするために必要な設定をかんたんに行うことができます。"
    )
    print("【注意】")
    print("このスクリプトを実行するには、PostgreSQLのデータベースが必要です。")
    print("(supabase等で簡単に手に入れることができます。)")
    print(
        "また、このスクリプトを実行したことで起きた不都合や損害について、作成者であるねんねこは一切の責任を負いません。"
    )
    if input("確認しましたか？[y/N]: ").lower() != "y":
        sys.exit(0)
    discordToken = input("自販機を動かす予定のボットのトークンを入力してください: ")
    dsn = input("PostgreSQLのDSNを入力してください: ")
    errorWebhook = input(
        "エラーが起きた際にエラーログを送信するWebhookのURLを入力してください: "
    )
    if input("ウェブサイトでの決済履歴確認機能を利用しますか？[y/N]: ").lower() == "y":
        oauth2ClientId = input("oAuth2のクライアントIDを入力してください: ")
        oauth2Secret = input("oAuth2のクライアントシークレットを入力してください: ")
        redirectUrl = input("oAuth2のリダイレクトURLを入力してください: ")
    else:
        oauth2ClientId = ""
        oauth2Secret = ""
        redirectUrl = ""
    defaultProxy = input(
        "デフォルトでユーザーが使用するプロキシを入力してください(省略可): "
    )
    env = f"""discord={discordToken}
dsn={dsn}
fernet_key={Fernet.generate_key().decode()}
error_webhook={errorWebhook}
oauth2_client_id={oauth2ClientId}
oauth2_secret={oauth2Secret}
redirect_uri={redirectUrl}
default_proxy={defaultProxy}

"""
    with open(".env", "w") as f:
        f.write(env)


if __name__ == "__main__":
    asyncio.run(main())
