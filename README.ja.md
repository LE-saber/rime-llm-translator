# Rime LLM Translator

[English](README.md) · [简体中文](README_CN.md) · [繁體中文](https://github.com/LE-saber/rime-llm-translator/blob/main/README.zh-TW.md) · [日本語](https://github.com/LE-saber/rime-llm-translator/blob/main/README.ja.md)

[v0.3.0 をダウンロード](https://github.com/LE-saber/rime-llm-translator/releases/tag/v0.3.0) · [変更履歴](CHANGELOG.md)

**Ubuntu 24.04 amd64、GNOME 46、IBus、Luna Pinyin（朙月拼音）**向けの中国語入力、軽量オフライン翻訳、任意のクラウド AI。繁体字入力も利用できます。Windows や他のデスクトップはこのリリースの対応範囲外です。

通常の入力で英語・日本語の翻訳候補を表示し、長い中国語はフローティングエディターで修正してから訳文を送れます。ネイティブ GTK3、C/IBus、CPU 専用 Bergamot INT8 が一つのオフラインワーカーを共有します。モデルは同梱され、pip、GPU、ローカルコンパイル、初回モデル取得は不要です。

## 画面

大きな編集可能原文欄、コンパクトな言語別プレビュー、アイコン操作、設定可能な送信時 AI：

![ネイティブの明るいフローティングエディター](docs/images/long-text-light.png)

AI 処理中はスピナーと経過秒数を表示します。

![AI 翻訳の進行表示](docs/images/ai-sending.png)

[暗いエディター](docs/images/long-text-dark.png) · [GUI 設定](docs/images/settings.png)。画像は GitHub Actions のネイティブ GTK テストで公開テキストとローカル模擬 API を使って取得した、UI と操作の例です。

## インストール・更新

[Release](https://github.com/LE-saber/rime-llm-translator/releases/tag/v0.3.0) の `.deb` と `SHA256SUMS` を同じフォルダーへ取得します。

```bash
sha256sum --check SHA256SUMS
sudo apt install ./rime-llm-translator_0.3.0_amd64.deb
```

新規インストール：

```bash
rime-llm-translator setup && rime-llm-translator enable
```

プレビューから更新してキーと設定を保持する場合：

```bash
rime-llm-translator sync && rime-llm-translator enable
```

APT 以外はデスクトップ利用者として実行します。**ログアウトして再ログイン**後、設定 → キーボード → 入力ソースで中国語 → Rime Translator を追加します。必要なら Ctrl+grave で Luna Pinyin を選びます。`sync` / `enable` はユーザー用 GNOME ブリッジを導入します。ユーザー拡張が全体で無効なら GNOME Extensions で有効にしてください。`doctor` でフローティングパネルのブリッジが active となることを確認します。

通常の Rime とは独立し、このエンジンは `~/.config/ibus/rime-llm` を使います。オフライン英語/日本語に資格情報は不要です。`rime-llm-translator settings` またはアプリランチャーで設定を開きます。

## 使い方

| 操作 | 動作 |
| --- | --- |
| 通常の中国語入力 | 中国語候補と `🌐 MT · EN/JA` を表示。遅れて届いた結果も追加キーなしで更新 |
| AI キー、既定 Ctrl+Shift+Enter | 選択した中国語候補を明示的に API で修正。自動確定なし |
| エディターを開く、既定 Alt+Space | 空欄のサイズ変更可能な最前面パネル。選択中国語は履歴へ |
| パネル内で編集 | Rime の確定文字を原文欄へ蓄積し、オフラインプレビューを更新 |
| 送信、既定 Ctrl+Enter | 最後に選択した実入力欄へプレビュー言語を送信し、成功時に消去 |
| 原文が空のとき ↑ / ↓ | 未送信で閉じた下書きも含め、最近のローカル文を呼出 |

送信先はパネルを開いている間に最後に選んだ実入力欄です。A から開き、B を選び、パネルへ戻ると B に送ります。同じウィンドウの別欄でも動作します。パネルや設定欄は送信先になりません。GNOME 連携で対象を復帰・確認し、対象の消滅/無効化や送信失敗時には原文を保持します。グローバル貼付や疑似タイプ入力は使いません。

**ライブプレビューはオフライン MT です。API URL、モデル、空でないキーを設定すると送信時 AI が既定で有効になり、無効化もできます。** 手動 AI は現在の文/言語だけに適用します。編集、言語変更、送信成功後は MT に戻ります。AI の失敗、タイムアウト、古い出力、切れた出力を黙って MT へ置き換えて送ることはありません。明示した AI 操作だけが設定先へ文字を送信します。

GUI でキーを記録できます。DoubleAlt / TripleAlt、パネル内マウス側面ボタンにも対応します。Alt+Space が GNOME メニューと競合する場合は Ctrl+Alt+Space 等へ変更してください。これは Rime Translator へのキーイベントに依存し、デスクトップ全体のホットキーではありません。

```bash
rime-llm-translator hotkey DoubleAlt
```

Double Alt は中国語候補選択中、同じ Alt の押下・解放を 400 ms 内に 2 回行います。デスクトップや VM ホストがイベントを奪う場合があります。[長文の仕様と確認](docs/LONG_TEXT.md)を参照してください。

## リソースと制約

- ネイティブ推論は 1 プロセス/1 スレッド、モデル方向は一度に一つ。60 秒のアイドル後に子プロセスが終了します。パネルは必要時に読み込み、ブラウザーランタイムは使いません。
- 中国語→英語 tiny、英語→日本語 base-memory を介した日本語翻訳。OpenCC は MT 用コピーだけを正規化し、AI には元の中国語を渡します。基本的な下訳なので、固有名詞、数字、否定などは人が確認してください。上流の tiny モデルはレジストリーで Release 指定されていません。
- CPU/VM に SSE4.1 が必要です。通常候補は UTF-8 1,200 bytes、パネルは 32 KiB までで順番に分割翻訳します。オフラインは英語/日本語、他の設定言語には AI が必要です。
- MT と AI は別サービス/キャッシュで、各 350 件 / 10 MiB。ログに原文、訳文、キーを残しません。任意のローカル履歴は重複を除いて最大 50 件、消去・無効化できます。

Release の `RESOURCE_REPORT.md` と `mt-benchmark.json` にビルドのサイズ、ディスク、RSS、遅延、公開例文があります。システム依存分は別で、runner の測定値は VM の速度を予測しません。

## 診断・クリーンアップ・開発

```bash
rime-llm-translator doctor
rime-llm-translator install-offline
rime-llm-translator cleanup-legacy
rime-llm-translator cleanup-legacy --apply
```

`install-offline` は同梱資源の確認です。`cleanup-legacy` は確認だけを行い、`--apply` で選択対象を削除します。キー、設定、履歴、Rime 辞書は保持します。共有 pip キャッシュ/Argos モデルには別の明示オプションが必要です。[更新と清理](docs/UPGRADE_CLEANUP.md)、[手動確認](docs/MANUAL_TEST.md)、[ビルド](docs/DEVELOPMENT.md)、[履歴](CHANGELOG.md)を参照してください。

GitHub Actions は Ubuntu 24.04 のインストール、単体テスト、実 Rime/IBus/GTK、GNOME 46 Wayland のフォーカス/送信、模擬 AI 障害、ネットワーク無効のネイティブ推論確認を定義します。WSL は使用しません。実クラウドの品質と利用者のアプリ/VM は別途手動確認が必要です。

## ソースとライセンス

フロントエンドは GPLv3-or-later の [ibus-rime 1.5.0](https://github.com/rime/ibus-rime/tree/d525f18b45123869af0055cc8402d459ebdbb9e3) 由来で、ソースとライセンスは [frontend/](frontend/) とパッケージに含まれます。Mozilla 推論ソース、固定依存関係、ライセンスは `/usr/share/doc/rime-llm-translator/inference-source.tar.xz` にあり、ラッパーソースとリビジョンも添付します。Mozilla モデルは MPL 2.0、ハッシュ/ライセンスは [models.lock.json](native/mt/models.lock.json) に記録します。第三者の各ライセンスを保持します。ルートの Ollama Lua 試作は未使用の上流参考資料で、インストール後の実行経路ではありません。

新しい繁体字中国語と日本語の紹介はオンライン文書です。既存 v0.3.0 パッケージに含まれるのは従来の英語/簡体字中国語文書で、文書 PR による再ビルドは行っていません。
