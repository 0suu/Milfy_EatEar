# Milfy_EatEar

BOOTH: https://suu-sai.booth.pm/items/6754877

パッケージの導入方法は [README](Packages/jp.suu.milfy-eat-ear/README.md) を参照してください。

## 開発とリリース

配布物は Packages/jp.suu.milfy-eat-ear を共通ソースとして生成します。ローカルでは、リポジトリのルートから次を実行してください。

python -m unittest discover -s tests -p 'test_*.py'
python scripts/build_release.py --version 1.3.0

生成先は dist/ です。SHA256SUMS には VPM zip と unitypackage のチェックサムが入ります。テストは配布対象アセットとmeta、外部GUID参照、unitypackageのパス、安全性、アーカイブの再現性を検証します。

GitHub Release は Actions の Build EatEar Release から起動します。入力する version は Packages/jp.suu.milfy-eat-ear/package.json と一致させてください。次の版では manifest の version と url の版を同時に更新します。既存の同名tagがある版は再リリースできません。workflow はテストとビルドを通した後、VPM zip、unitypackage、SHA256SUMS をReleaseへ添付します。

SUU_HOME_DISPATCH_TOKEN が設定されていれば suu-home へ eat-ear-release を通知します。設定されていない場合は、Release完了後に suu-home の update-vpm-from-release.yml を develop で手動実行し、workflowのnoticeに表示された package_name、version、release_url、zip_sha256 を入力してください。
