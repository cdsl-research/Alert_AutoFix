# Alert_AutoFix
## 概要
このFlaskアプリケーションは，Alertmanagerから送信されるアラートをJSON形式で受け取り，Gemini APIを用いて自動的に対処スクリプトを生成，評価，再生成するWebhookエンドポイントです． 生成されたスクリプトは実行後に結果を解析し，有効でない場合には再度プロンプトを修正してスクリプトを再生成します．

## 環境 
- OS： Ubuntu 24.04.2 LTS
- Python： 3.12.3
- Gemini： gemini-2.5-flash 

## Python ライブラリ： 
- flask
- os
- google.generativeai
- re
- requests
- dotenv

## 主な構成ファイル
| ファイル名   | 内容 |
| ------------- | ------------- |
| gemini_alert.py  | Flaskアプリ本体  |
| requirements.txt  | 実行に必要なPythonパッケージ  |
| .env  | GEMINI_API_KEY などの環境変数用  |


## 動作の流れ 
1. Alertmanagerから/alertエンドポイントにJSON形式のアラートを受信
2. 受信したアラートをもとに，Gemini APIへプロンプトを送信
3. Geminiの応答からbashスクリプトを抽出し，fix_issue.shとして保存
4. 生成されたスクリプトを実行し，標準出力・エラー出力をログとして保存
5. メトリクスがしきい値を下回らない場合はプロンプトを再生成して再試行
6. 有効なスクリプトが得られるまで繰り返す

## 注意事項 
- Gemini APIの利用にはAPIキーの設定が必要です
  ```export GEMINI_APIKEY="your-api-key"```
- APIの利用には料金や使用制限が発生する場合があります
- gemini_alert.py内のURLやPod名など実際の環境に合わせて変更する箇所があります．
- 生成されるスクリプトは生成AIによって作成されるため必ず復旧できるわけではないです．内容は必ず確認してからの実行，プロンプトを追加するなどして対応してください．

## 使用例 
今回は以下のコマンドを実行して仮想環境で説明します． 
### 1. 仮想環境の作成と有効化
```
$ python3 -m venv gemini
$
```
```
$ source gemini/bin/activate
(gemini) $
   ```
### 2. Gemini APIキー設定 
```
$ export GEMINI_APIKEY="your-api-key"
(gemini) $
```
### 3. Flaskアプリ起動 
```
$ python3 gemini_alert.py 
✅ GEMINI_API_KEY が設定されました（長さ: 39）
 * Serving Flask app 'gemini_alert'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.100.78:5000
Press CTRL+C to quit
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 128-429-581
```

### 4. 動作確認
今回はテストとして別のターミナルでcurlを実行し，動作の確認を行います．
```
$ curl -X POST http://localhost:5000/alert -H "Content-Type: application/json" -d '{
  "namespace": "redmine",
  "pod": "redmine-659869bc68-q7w4g",
  "metric": "container_memory_usage_bytes",
  "threshold": 85.0,
  "prometheus_url": "http://c0a22169-monitoring:30900/api/v1/query"
}'
```
curlを実行したら，以下のようにFlaskアプリを起動した結果の下に表示されます．
```
$ python3 gemini_alert.py 
✅ GEMINI_API_KEY が設定されました（長さ: 39）
 * Serving Flask app 'gemini_alert'
 * Debug mode: on
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.100.78:5000
Press CTRL+C to quit
 * Restarting with stat
✅ GEMINI_API_KEY が設定されました（長さ: 39）
 * Debugger is active!
 * Debugger PIN: 128-429-581
📁 JSONを保存: results/20251102/alert_20251102_170941.json
🎯 対象メトリクス: (sum by (pod, namespace) (container_memory_usage_bytes{namespace='redmine', pod='redmine-659869bc68-q7w4g'})/ sum by (pod, namespace) (container_spec_memory_limit_bytes{namespace='redmine', pod='redmine-659869bc68-q7w4g'} > 0)) * 100
📊 しきい値: 85.0, 現状値(before): 96.17691040039062
WARNING: All log messages before absl::InitializeLog() is called are written to STDERR
E0000 00:00:1762103381.815367  103809 alts_credentials.cc:93] ALTS creds ignored. Not running on GCP and untrusted ALTS is not enabled.
⚠️ ガードレール警告: 危険コマンドが検出されました
違反パターン: ['\\bapt(-get)?\\s+install\\b', '\\byum\\s+install\\b']
✅ スクリプト生成: results/generated_scripts/confirm.sh
✅ スクリプト生成: results/generated_scripts/fix_issue.sh
```
保存されたスクリプトやログは/resultsで確認できます． 
```
$ ls
20251102  exec_results  generated_scripts
(gemini) $
```
/generated_scriptsには以下のようなスクリプトが保存されます．
```
$ cat fix_issue.sh
Redmine namespace の Pod の `container_memory_usage_bytes` を再起動や削除なしに安全に低下させるのは、**アプリケーション自体がメモリを解放するように設計されていない限り、非常に困難です。** `container_memory_usage_bytes` には、アプリケーションが使用しているメモリ（ヒープ、スタック、データなど）と、OSがキャッシュしているファイルデータなどが含まれます。

このスクリプトは、以下の点に焦点を当てて作成されています。

1.  **診断情報の提供:** どのPodが、どのようなプロセスで、どの程度のメモリを使用しているかを把握する。
2.  **OSレベルのキャッシュクリアの試行:** アプリケーションのメモリ自体ではなく、OSがファイルシステムなどで使用しているキャッシュを一時的に解放します。これは効果が一時的であり、アプリケーションの根本的なメモリ使用量には影響しません。また、コンテナが十分な権限を持っている場合にのみ成功します。
3.  **根本的な解決策への誘導:** 永続的なメモリ使用量の削減には、アプリケーションレベルのチューニングや設定変更が必要であることを明確にします。

---

```bash
#!/bin/bash

# Redmineの名前空間を設定
NAMESPACE="redmine"

echo "--- Redmine Podsのメモリ使用量を安全に低下させる試み ---"
echo "注意: Podの再起動や削除を行わずに、アプリケーションのメモリ使用量を根本的に削減することは非常に困難です。"
echo "このスクリプトは、現在の状況の診断情報を提供し、OSレベルのキャッシュをクリアする可能性のある一時的な措置を提案します。"
echo "アプリケーションのメモリ使用量を永続的に削減するには、Redmineアプリケーション自体のチューニングが必要です。"
echo "---"

# 1. 現在のRedmine Podsのメモリ使用量 (kubectl top)
echo "1. 現在のRedmine Podsのメモリ使用量 (kubectl top pods -n $NAMESPACE --sort-by=memory):"
# ヘッダー行とメモリ使用量が多い順に表示
kubectl top pods -n "$NAMESPACE" --sort-by=memory | head -n 1
kubectl top pods -n "$NAMESPACE" --sort-by=memory | grep -E "^(NAME|$NAMESPACE)" # Redmine Podsのみをフィルタリング
echo ""

# 2. 各Pod内のメモリ使用状況の詳細診断とOSキャッシュクリアの試行
echo "2. 各Pod内のメモリ使用状況の詳細診断とOSキャッシュクリアの試行:"
PODS=$(kubectl get pods -n "$NAMESPACE" -o custom-columns=":metadata.name" --no-headers)

if [ -z "$PODS" ]; then
    echo "Redmine namespace ($NAMESPACE) にPodが見つかりませんでした。"
else
    for POD in $PODS; do
        echo "--- Pod: $POD ---"
        echo "  a. Pod内のプロセス別メモリ使用量 (ps aux):"
        # psコマンドが存在するか確認し、存在すれば実行
        if kubectl exec -n "$NAMESPACE" "$POD" -- sh -c "command -v ps >/dev/null"; then
            kubectl exec -n "$NAMESPACE" "$POD" -- ps aux --sort=-rss | head -n 10 || echo "プロセス情報の取得に失敗しました。"
        else
            echo "    psコマンドがコンテナ内に見つからないか、実行できません。"
        fi
        echo ""

        echo "  b. Pod内のメモリ統計情報 (free -h):"
        # freeコマンドが存在するか確認し、存在すれば実行
        if kubectl exec -n "$NAMESPACE" "$POD" -- sh -c "command -v free >/dev/null"; then
            kubectl exec -n "$NAMESPACE" "$POD" -- free -h || echo "メモリ統計情報の取得に失敗しました。"
        else
            echo "    freeコマンドがコンテナ内に見つからないか、実行できません。"
        fi
        echo ""

        echo "  c. Pod内のトッププロセス (top -b -n 1):"
        # topコマンドが存在するか確認し、存在すればバッチモードで1回実行
        if kubectl exec -n "$NAMESPACE" "$POD" -- sh -c "command -v top >/dev/null"; then
            kubectl exec -n "$NAMESPACE" "$POD" -- top -b -n 1 | head -n 10 || echo "トッププロセスの取得に失敗しました。"
        else
            echo "    topコマンドがコンテナ内に見つからないか、実行できません。"
        fi
        echo ""

        echo "  d. OSレベルのキャッシュクリアの試行 (sync; echo 1 > /proc/sys/vm/drop_caches):"
        echo "     これはアプリケーションが使用しているメモリを直接削減するものではなく、ファイルシステムキャッシュなどを解放します。"
        echo "     効果は一時的であり、コンテナが十分な権限 (privileged mode または CAP_SYS_ADMIN) を持っている場合にのみ成功します。"
        echo "     **ほとんどのプロダクション環境のコンテナでは、セキュリティ上の理由からこの操作を行う権限がありません。**"

        # /proc/sys/vm/drop_caches への書き込みを試行
        # エラーメッセージは /dev/null にリダイレクトし、成功/失敗のみを判定
        if kubectl exec -n "$NAMESPACE" "$POD" -- sh -c "sync; echo 1 > /proc/sys/vm/drop_caches" 2>/dev/null; then
            echo "     -> キャッシュクリアコマンドが実行されました。効果は短期的で、アプリケーションメモリには影響しない可能性があります。"
        else
            echo "     -> キャッシュクリアコマンドの実行に失敗しました。通常、権限不足が原因です。"
            echo "        (例: 'Permission denied' または '/proc/sys/vm/drop_caches: Read-only file system')"
        fi
        echo ""
    done
fi

echo "---"
echo "3. 推奨される次のステップ (より効果的なメモリ削減のために):"
echo "   以下の解決策は、多くの場合、Podの再起動やアプリケーション設定の変更を伴います。"
echo ""
echo "   a. アプリケーションレベルのチューニング:"
echo "     - **RedmineのWebサーバー設定の見直し:** (Puma/Unicorn/Passengerなど)"
echo "       - ワーカー数やスレッド数を現在の負荷に合わせて調整します。過剰なワーカー数はメモリを浪費します。これには通常、設定ファイルの変更とPodの再起動が必要です。"
echo "       - 例: `WEB_CONCURRENCY` 環境変数の調整など。"
echo "     - **RubyのGC (Garbage Collection) チューニング:**"
echo "       - 環境変数 `RUBY_GC_HEAP_GROWTH_FACTOR`, `RUBY_GC_HEAP_INIT_SLOTS` などでGC動作を調整できる場合があります。ただし、これは高度なチューニングであり、慎重に行う必要があります。"
echo "     - **プラグインやカスタムコードの監査:**"
echo "       - メモリリークを引き起こしている可能性のあるRedmineプラグインやカスタムコードがないか確認します。"
echo ""
echo "   b. Kubernetesリソースの調整:"
echo "     - **Podのリソース制限 (requests/limits) の最適化:**"
echo "       - Podの定義 (`Deployment` など) で `resources.limits.memory` が適切に設定されているか確認します。過度に低いとOOMKillの原因になりますが、高すぎると他のPodがメモリ不足になる可能性があります。"
echo "       - `resources.requests.memory` を現実的な値に設定し、スケジューラが適切なノードにPodを配置できるようにします。"
echo "       - これらの変更はPodの再起動を伴います。"
echo "     - **Deploymentのレプリカ数の増減:**"
echo "       - 各Podの負荷が高い場合、レプリカ数を増やすことで負荷を分散し、結果的に各Podのメモリ使用量が安定する可能性があります。これにはノードリソースの確認が必要です。"
echo ""
echo "   c. Redmine Podの再起動 (許容される場合):"
echo "     - 一時的なメモリ肥大化やリークは、Podの再起動で解消されることが多いです。"
echo "     - `kubectl rollout restart deployment <deployment-name> -n $NAMESPACE` コマンドで安全にローリング再起動が可能です。"
echo ""
echo "---"
echo "このスクリプトは、メモリ使用量の根本的な解決策ではなく、診断と非常に限定的な一時的な緩和策を提供することに留意してください。"
echo "真のメモリ削減は、アプリケーションの振る舞いを変えることによって達成されます。"

```　

### スクリプトの使用方法

1.  **保存:** 上記のスクリプトを `reduce_redmine_memory.sh` のような名前で保存します。
2.  **実行権限の付与:** `chmod +x reduce_redmine_memory.sh`
3.  **実行:** `./reduce_redmine_memory.sh`

### 重要な考慮事項

*   **権限:** `kubectl exec` を使用してPod内でコマンドを実行するため、Kubernetesクラスターに対する適切な `kubectl` 権限（特に `exec` 権限）が必要です。
*   **コンテナイメージ:** コンテナイメージによっては、`ps`, `free`, `top` などのコマンドがインストールされていない場合があります。その場合、スクリプトは「コマンドが見つからない」というメッセージを表示します。
*   **`drop_caches` の制限:** ほとんどのプロダクション環境のコンテナは、セキュリティ上の理由から `/proc/sys/vm/drop_caches` への書き込み権限を持っていません。したがって、この機能が実際にメモリを解放する可能性は低いです。また、解放されるのはOSキャッシュであり、Redmineアプリケーション自体のメモリ使用量ではありません。
*   **Ruby on Railsのメモリ管理:** Rubyアプリケーションは、通常、一定量のメモリを消費し続ける傾向があります。ガベージコレクションによってメモリが解放されますが、使用済みメモリがOSに完全に返還されるとは限りません。プロセスを再起動しない限り、大幅なメモリ削減は難しい場合があります。

このスクリプトは、現状の把握と限定的な一時対策として役立ちますが、根本的なメモリ使用量の問題解決には、Redmineアプリケーションとその環境のより詳細な分析とチューニングが必要です。
$
```
  
## おわりに
本アプリは、Gemini API を活用してアラート対応の支援を行うツールです． 生成 AI に依存しているため、まだ完全な自動復旧はできません。 今後は、生成されたスクリプトを安全に自動実行する仕組みの実装が課題です。
