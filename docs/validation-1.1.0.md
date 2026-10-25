# 1.1.0 配布検証

検証日: 2026-10-25

環境: Windows / Unity 2022.3.22f1 / VRChat Avatars SDK 3.10.4 / Modular Avatar 1.18.1 / NDMF 1.14.3。

- BOOTH 原版の全24 GUIDを、新版の VPM ZIP と unitypackage の両方で保持。
- 原版の Prefab を使ったアバターを保存し、左右別の耳マテリアルと配置を Override した状態から更新。
- VPM ZIP を隔離プロジェクトへ導入し、旧 Prefab / root Animator Controller の参照と Override が維持されることを確認。
- 生成 unitypackage を Unity の ImportPackage API で実インポートし、完了イベント後に同じ互換性を確認。
- 両形式で、新規配置と既存アバター更新の MA / NDMF 生成に成功。左右音源2個、固定2本、解除2本を確認。
- 生成クリップを適用し、FreezeToWorld の値と 0.65 秒の保持を確認。
- EatEar 分の Expression Parameters は8 bit。検証用アバター全体では SDK 既定分を含め32 bit。
- 配布 Prefab の Missing Script は0、パッケージ外の Assets への依存は0。
- Python の配布検査6件に成功。GUID維持・互換Controller・外部参照・不正パス・meta欠落/重複・再現可能性を検証。

VCC / ALCOM の画面を使った実インストール、VRChat Build & Test、実機/リモート音響は未実施。VPM 移行では公式仕様の legacyFolders を使用し、隔離プロジェクトで旧フォルダを置き換えて検証した。
