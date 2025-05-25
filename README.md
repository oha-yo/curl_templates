-- 仮想環境作成
python -m venv myenv

.\myenv\Scripts\activate

pip install -r requirements.txt


python curl_runner.py sample1.yml
