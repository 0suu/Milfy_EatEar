# Milfy_EatEar

ミルフィの耳を掴んで食べられる Modular Avatar 対応ギミックです。
商品ページ: https://suu-sai.booth.pm/items/6754877
対応アバター: https://mk22.booth.pm/items/6571299

## 導入

1. ミルフィ 1.5.0 の unitypackage を導入済みの Unity 2022.3 プロジェクトを用意します。
2. VCC / ALCOM に https://suu31.net/vpm/eat-ear/index.json を登録して `jp.suu.eat-ear` を追加します。
3. `Packages/jp.suu.eat-ear/Runtime/Milfy_EatEar.prefab` をアバター直下に置きます。unitypackage 版では `Assets/SaiEatEar/Milfy_EatEar.prefab` にあります。
4. 耳には旧版と同じ Milfy 付属の `Hair_Another.mat` が初期状態で適用されます。アバターの耳に別の材質を使っている場合だけ、`Milfy_EatEar/EatEar_R_Physbone/EatEar_R` と `Milfy_EatEar/EatEar_L_Physbone/EatEar_L` をそれぞれ同じマテリアルへ設定します。
5. 元の `Armature/Hips/Spine/Chest/Neck/Head/Ear_Root/Ear.L` と `Ear.R` の PhysBone の `Allow Grabbing` を無効にします。耳の周りの髪・リボンも掴めない設定にすると操作しやすくなります。

VRChat SDK と Modular Avatar は VPM の依存パッケージとして必要です。検証環境は Unity 2022.3.22f1 / SDK 3.10.4 / MA 1.18.1 / NDMF 1.14.3 です。

## 更新

VPM 版と unitypackage 版は同じ Prefab・Animator・クリップ GUID を使用します。旧版を個別に改変している場合は更新前に複製を保存してください。VPM 導入時は旧 `Assets/SaiEatEar` または `Assets/sai/SaiEatEar` を `legacyFolders` で置き換えます。両形式を同時に残すと GUID が重複するため、どちらか一方を使います。

元 Prefab に繋がったアバターの設定と通常の Prefab Override は同じ GUID で引き継ぎます。Prefab の初期名は `Milfy_EatEar` です。アニメーションと音声は MA の Prefab 相対参照で適用されるため、旧名 `EatEar` の既存配置や配置後の改名にも対応します。旧版の Milfy_250326a.controller も参照互換性のため原版の内容で残しています。Prefab を完全に Unpack したコピーや Animator 自体を複製した構成は共有更新の対象外です。

## 利用条件

既存の BOOTH 配布条件を引き継ぎます。商品ページ https://suu-sai.booth.pm/items/6754877 を確認してください。本更新で MIT などの別ライセンスへ変更していません。旧配布物の readme.txt は導入手順のみで、追加の許諾・制限は記載されていませんでした。

## 動作

- 使用パラメーターは従来と同じ 8 bit です。
- 左右それぞれの耳の接触判定で、同じ側の音源を再生します。
- 音源は食べた地点で 0.65 秒固定し、約 0.575 秒の音声が終わってから追従へ戻します。
- 適用は MA / NDMF によるビルド時統合です。アバター本体の Animator への手動コピーは不要です。

Milfy の材質・テクスチャは本パッケージには含めません。付属 `Hair_Another.mat` を元の GUID で参照するため、Milfy の導入が必要です。マテリアルを移動した場合も GUID が同じなら参照は維持されます。
