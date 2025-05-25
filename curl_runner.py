import yaml
import subprocess
import sys
from pathlib import Path
import platform
import json
from urllib.parse import urlencode
import re

def load_curl_config(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def build_curl_command(config, show_headers):
    method = config.get('method', 'GET')
    base_url = config['url']
    
    params = config.get('params', {})
    if params and method.upper() == 'GET':
        query_string = urlencode(params)
        full_url = f"{base_url}?{query_string}"
    else:
        full_url = base_url

    cmd = ['curl', '-s']
    if show_headers:
        cmd += ['-D', '-']
    cmd += ['-X', method, full_url]

    headers = config.get('headers', {})
    for key, value in headers.items():
        cmd += ['-H', f'{key}: {value}']

    if method.upper() in ['POST', 'PUT']:
        if 'data' in config:
            cmd += ['-d', config['data']]
        elif params:
            for k, v in params.items():
                cmd += ['--data-urlencode', f'{k}={v}']

    cmd += ['-w', '\nHTTP Status: %{http_code}\n']
    return cmd

def quote_arg_bash(arg):
    # 特殊文字が利用されている場合シングルクォートで囲む
    if any(c in arg for c in [' ', '?', '{', '}', ':', '"', '&']):
        return f"'{arg}'"
    return arg

def quote_arg_ps(arg):
    # 今のところbash版と同じで問題なさそう
    return quote_arg_bash(arg)

def parse_curl_output(output, show_headers):
    http_code = output.strip()[-3:]
    full_response = output.strip()[:-16] # 'HTTP Status: ' + ' 999' = 16

    if show_headers:
        header, unused, body = full_response.partition('\r\n\r\n')
        if not body:
            header, unused, body = full_response.partition('\n\n')
        return header.strip(), body.strip(), http_code
    else:
        return '', full_response.strip(), http_code

def handle_error(message):
    ERROR_CODE = "ERROR"
    print(message)
    return ERROR_CODE

def needs_bearer_token(config):
    
    # Bearer トークンを抽出
    authorization_value = config["headers"].get("Authorization")
    if authorization_value is None:
        return None     # トークン取得不要
    #print(f"authorization_value===> {authorization_value}")
    match = re.search(r"\[([^\]]+)\]", authorization_value)
    if match:
        # トークンの取得が必要
        auth_yaml = match.group(1)  # 抽出した値
        print(f"{auth_yaml} によるトークン取得を実施します")  # 出力: token_issue_sooni.yml
        config_path = Path("curl_templates") / auth_yaml
        if not config_path.exists():
            return handle_error(f"{auth_yaml}ファイルが見つかりません。")

        tconfig = load_curl_config(config_path)
        api_name = tconfig.get('api_name', '（名称未設定）')
        cmd = build_curl_command(tconfig, False)
        print(f"Token取得 curl ===> {cmd}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        header, body, http_code = parse_curl_output(result.stdout, False)
        print(f"httpステータスコード: {http_code}\n")
        try:
            if int(http_code) != 200:
                return handle_error(f"http_code:{http_code} トークン取得に失敗")
        except ValueError:
            return handle_error(f"無効な HTTP ステータスコード: {http_code}")
        
        if not body:
            return handle_error("レスポンスボディが空です")
        try:
            # JSON を辞書型に変換
            parsed = json.loads(body)
            #print(json.dumps(parsed, indent=2, ensure_ascii=False))
            # accesstoken の値を取得
            access_token = parsed.get("accesstoken")
            if not access_token:  # 取得できなかった場合の処理を追加
                return handle_error("アクセストークンの取得に失敗しました。")
            #print(access_token) 
            # [] 内の文字列を "newtoken" に置き換える
            config["headers"]["Authorization"] = re.sub(r"\[.*?\]",access_token, config["headers"]["Authorization"])
            return access_token

        except json.JSONDecodeError:
            print(body)
            return handle_error("JSON変換でエラー発生")

    else:
        # トークン取得不要
        return None
    
def main():
    if len(sys.argv) < 2:
        print("使い方: python curl_runner.py get_echo.yml [--show-header]")
        sys.exit(1)

    yaml_filename = sys.argv[1]
    show_headers = '--show-header' in sys.argv[2:]

    config_path = Path("curl_templates") / yaml_filename
    config = load_curl_config(config_path)
    api_name = config.get('api_name', '（名称未設定）')
    
    # トークン認証が必要か否か
    if needs_bearer_token(config) == "ERROR":
        print("トークン取得中にエラー発生！処理を中断します。")
        sys.exit(1)    

    cmd = build_curl_command(config, show_headers)
    print(f"cmd===> {cmd}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 実行結果の整形
    header, body, http_code = parse_curl_output(result.stdout, show_headers)

    cmd[-1] = cmd[-1].replace('\n', '\\n') # 最後の要素の '\n' をエスケープ    
    bash_cmd = ' '.join(quote_arg_bash(arg) for arg in cmd) 
    ps_cmd = ' '.join(quote_arg_ps(arg) for arg in cmd) 

    print("=== 実行コマンド ===")
    print(f"対象API名: {api_name}")
    print("[bash/macOS 用]")
    print(bash_cmd)
    print("[PowerShell 用]")
    print(ps_cmd)

    print("\n=== 実行結果 ===")
    print(f"httpステータスコード: {http_code}\n")

    if show_headers:
        print("レスポンスヘッダ:")
        print(header)

    print("\nレスポンスボディ:")
    try:
        parsed = json.loads(body)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        print(body)

if __name__ == '__main__':
    main()
