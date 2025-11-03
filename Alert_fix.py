from flask import Flask, request, jsonify
import os
import json
import datetime
import subprocess
import re
import google.generativeai as genai
from dotenv import load_dotenv
import requests

app = Flask(__name__)
load_dotenv()

# ===============================
# 初期設定
# ===============================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
BASE_DIR = "results"
os.makedirs(BASE_DIR, exist_ok=True)

# ===============================
# 補助関数群
# ===============================
def save_json(data, prefix):
    """アラートJSONなどを保存"""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_path = os.path.join(BASE_DIR, datetime.datetime.now().strftime("%Y%m%d"))
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, f"{prefix}_{ts}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"📁 JSONを保存: {path}")
    return path

def validate_script(script_content):
    """危険コマンド検出によるガードレール"""
    forbidden_patterns = [
        r"\brm\s+-rf\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bsystemctl\s+(stop|disable)\b",
        r"\bapt(-get)?\s+install\b",
        r"\byum\s+install\b",
        r"\bsysctl\b",
        r"\bmount\b|\bumount\b",
        r"\becho\s+.+\s*>\s*/etc/",
    ]
    violations = []
    for pattern in forbidden_patterns:
        if re.search(pattern, script_content):
            violations.append(pattern)
    return (len(violations) == 0, violations)

def generate_script(prompt_text, filename):
    """Gemini でスクリプト生成"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt_text)
    script = response.text.strip()
    script_path = os.path.join(BASE_DIR, "generated_scripts", filename)
    os.makedirs(os.path.dirname(script_path), exist_ok=True)

    # スクリプト安全性チェック
    is_safe, violations = validate_script(script)
    if not is_safe:
        print("⚠️ ガードレール警告: 危険コマンドが検出されました")
        print("違反パターン:", violations)
        script = "# BLOCKED: 危険コマンドが含まれていたため実行を停止しました。\n" + script

    with open(script_path, "w") as f:
        f.write(script)
    print(f"✅ スクリプト生成: {script_path}")
    return script_path

def execute_script(script_path, prefix):
    """スクリプトを実行し結果を保存"""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = os.path.join(BASE_DIR, "exec_results")
    os.makedirs(result_dir, exist_ok=True)
    stdout_path = os.path.join(result_dir, f"{prefix}_stdout_{ts}.log")
    stderr_path = os.path.join(result_dir, f"{prefix}_stderr_{ts}.log")

    with open(stdout_path, "w") as out, open(stderr_path, "w") as err:
        subprocess.run(["bash", script_path], stdout=out, stderr=err, text=True)

    print(f"📝 実行ログ保存: {stdout_path}, {stderr_path}")
    return stdout_path, stderr_path

def get_prometheus_metric(prometheus_url, metric_expr):
    """Prometheus APIからメトリクスを取得"""
    response = requests.get(prometheus_url, params={"query": metric_expr})
    data = response.json()
    if data.get("status") == "success" and data["data"]["result"]:
        try:
            return float(data["data"]["result"][0]["value"][1])
        except Exception:
            return None
    return None

# ===============================
# メイン処理
# ===============================
@app.route("/alert", methods=["POST"])
def handle_alert():
    alert = request.json
    save_json(alert, "alert")

    # JSONから動的に取得
    namespace = alert.get("namespace", "default")
    pod = alert.get("pod", "")
    metric_name = alert.get("metric", "container_memory_usage_bytes")
    threshold = float(alert.get("threshold", 90.0))
    prometheus_url = alert.get("prometheus_url", "http://c0a22169-monitoring:30900/api/v1/query")

    # PromQL を組み立て（Pod指定は任意）
    pod_selector = f", pod='{pod}'" if pod else ""
    metric_expr = (
        f"(sum by (pod, namespace) ({metric_name}{{namespace='{namespace}'{pod_selector}}})"
        f"/ sum by (pod, namespace) (container_spec_memory_limit_bytes{{namespace='{namespace}'{pod_selector}}} > 0)) * 100"
    )

    metric_before = get_prometheus_metric(prometheus_url, metric_expr)
    print(f"🎯 対象メトリクス: {metric_expr}")
    print(f"📊 しきい値: {threshold}, 現状値(before): {metric_before}")

    # 汎用プロンプト
    confirm_prompt = f"{namespace} namespace の Pod の {metric_name} の状況を確認する bash スクリプトを生成してください。"
    fix_prompt = f"{namespace} namespace の Pod の {metric_name} を安全に低下させる bash スクリプトを生成してください。ただし再起動や削除は行わないでください。"

    confirm_path = generate_script(confirm_prompt, "confirm.sh")
    fix_path = generate_script(fix_prompt, "fix_issue.sh")

    execute_script(confirm_path, "confirm")
    execute_script(fix_path, "fix_issue")

    metric_after = get_prometheus_metric(prometheus_url, metric_expr)
    success = metric_after is not None and metric_after < threshold
    improved = metric_after < metric_before if (metric_before and metric_after) else False

    print(f"📉 評価結果 → before={metric_before}, after={metric_after}, success={success}, improved={improved}")

    return jsonify({
        "metric_before": metric_before,
        "metric_after": metric_after,
        "success": success,
        "improved": improved
    })

# ===============================
# 実行
# ===============================
if __name__ == "__main__":
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print(f"✅ GEMINI_API_KEY が設定されました（長さ: {len(api_key)}）")
    else:
        print("❌ GEMINI_API_KEY が設定されていません。")
    app.run(host="0.0.0.0", port=5000, debug=True)
