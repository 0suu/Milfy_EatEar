# Milfy_EatEar

BOOTH: https://suu-sai.booth.pm/items/6754877

パッケージの導入方法は [README](Packages/jp.suu.milfy-eat-ear/README.md) を参照してください。

## 開発とリリース

配布物は Packages/jp.suu.milfy-eat-ear を共通ソースとして生成します。ローカルでは、リポジトリのルートから次を実行してください。version の値は package.json の現在の値に合わせます。

python -m unittest discover -s tests -p 'test_*.py'
python scripts/build_release.py --version 1.3.1

生成先は dist/ です。SHA256SUMS には VPM zip と unitypackage のチェックサムが入ります。テストは配布対象アセットとmeta、外部GUID参照、unitypackageのパス、安全性、アーカイブの再現性を検証します。

GitHub Release は Actions の Build EatEar Release を main から起動し、version を入力します。workflow が package.json の version と配布 URL を更新し、テストとビルドを通してから main にコミットします。更新後のコミットにタグを付け、VPM zip、unitypackage、SHA256SUMS を Release へ添付します。既存の同名 tag は上書きしません。変更履歴に該当版がない場合は警告します。

コミット後・タグ作成前に失敗した場合は、同じ version で再実行できます。タグ作成後に失敗した場合は、既存のタグと Release の状態を確認してから復旧してください。

SUU_HOME_DISPATCH_TOKEN が設定されていれば suu-home へ eat-ear-release を通知します。設定されていない場合は、Release完了後に suu-home の update-vpm-from-release.yml を main で手動実行し、workflowのnoticeに表示された package_name、version、release_url、zip_sha256 を入力してください。
