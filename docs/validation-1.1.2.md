# 1.1.2 マテリアル互換性検証

Milfy 1.5.0 の原版 unitypackage と BOOTH 旧 EatEar 配布物を照合した。

- 旧 EatEar の左右の初期材質参照は `5d8891854cdf32c4599914cc30e6355d`。
- この GUID は Milfy 付属の `Assets/PLUSONE/Milfy/Materials/kaihen(Another)/Hair_Another.mat`。現在の保存先が個人用フォルダでも、元アセットの出自は変わらない。
- Default Material へ置き換えていた2参照を復元。Milfy 本体の材質・テクスチャは EatEar に同梱しない。
- 隔離 Unity に原版の材質と必要なテクスチャを導入し、主テクスチャまで解決されることを確認。
- 1.1.0 の Default Material を継承したまま保存した Prefab は、1.1.2 への更新で元の Hair_Another へ回復。
- 元から左右別に設定していた材質 Override と配置 Override、root Controller 参照を維持。
- VPM ZIP と unitypackage の実インポートで、新規配置・カスタム Override 付き更新・Default Material からの回復の3ケースがすべて MA/NDMF 生成成功。
- 左右音源2、固定2、解除2、EatEar分8 bitを維持。表示名は Milfy_EatEar。
- 配布検査7件に成功。GUID維持と元材質への参照、Milfy素材本体の非同梱を検査。

環境は Unity 2022.3.22f1 / SDK 3.10.4 / MA 1.18.1 / NDMF 1.14.3。VRChat 実機・リモート音響は未実施。
