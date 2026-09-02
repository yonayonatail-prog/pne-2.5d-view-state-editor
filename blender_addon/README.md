# PNE 2.5D View State Editor v0.1

`PNE 2.5D View State Editor v0.1 — FIX仕様.md` を基準にした、Blender 4.2+ 用アドオンです。Blender 5.2 LTSでヘッドレス統合テスト済みです。

画面項目と基本操作の日本語解説：[PNE 2.5D View State Editor 解説](../docs/PNE_2.5D_View_State_Editor_解説.md)

## インストール

1. Blenderの `Edit > Preferences > Add-ons` を開く。
2. `Install from Disk...` で `pne_2_5d_view_state_editor_v0.1.1.zip` を選ぶ。
3. `PNE 2.5D View State Editor` を有効化する。
4. 3D Viewport右側のSidebarを開き、`PNE 2.5D` タブを選ぶ。

## 最短の確認手順

1. `.blend` を保存する。未保存の場合、サンプル用Source PNGはBlenderの一時フォルダに作成される。
2. `Build Sample Character` を押す。
3. Yawを0〜90°で動かす。隣接する4 ViewがDITHERで切り替わる。
4. Blink / Brow / Mouth / Smile / Jawを動かし、遷移中のA/B両Stateに同じShape Key値が入ることを確認する。
5. `Validate Character` を押す。
6. Outputを指定し、`Export Runtime Bundle` を押す。

## Trace-to-ShapeKey

`PNE 2.5D > Trace-to-ShapeKey` では、開眼／閉眼など2枚以上の顔パーツ画像から、頂点対応済みのShape Key Meshを生成できます。

最短の確認手順：

1. `Role = Upper Eyelid`、`Side = Left`または`Right`を選ぶ。
2. `Basis / Open`へ開眼上瞼PNG、`Target / Closed`へ閉眼上瞼PNGを指定する。
3. 半閉じ素材がある場合は`Half (Optional)`へ指定する。
4. 透明背景素材では`Trace Mode = Alpha`を使う。
5. `Preview Paths`で緑のBasis Pathと紫のTarget Pathを確認する。
6. `Build ShapeKey Pair`を押す。
7. `Blink Preview`を0〜1で動かし、形状を確認する。
8. `Assign To Current View`で現在のView Stateへ割り当てる。

既定の`Stations = 32`では、64頂点／31 QuadのRibbon Meshを生成します。Open、Half、Closedは独立Meshとして使わず、同じRibbon Topologyの`Basis / BlinkHalf / Blink`へ変換されます。処理結果はBlender Text datablockの`PNE_TRACE_LOG`へ記録されます。

確認用ファイル：

```text
pne_trace_to_shapekey_demo.blend
blender_addon/test_output/trace_to_shapekey/trace_to_shapekey_preview.png
```

出力:

```text
export/
├─ character.glb
├─ character.states.json
├─ texture_build.json
└─ textures/
   ├─ front_0/
   ├─ front_30/
   ├─ side_30/
   └─ side_0/
```

各ViewのTexture Packは選択したView Stateの `Base / Face Parts / Occlusion / Jaw` で差し替えられます。Source画像は上書きされません。

## KTX2

- `toktx` のパスをExport欄に設定した場合はBasis LZ圧縮KTX2を生成する。
- 未設定または利用不可の場合も、内蔵ライターで非圧縮RGBA8 KTX2を生成する。
- Three.jsでは用途に応じて構成済みの `KTX2Loader` をResidency Managerへ渡す。

## Validator

View ID / Yaw / `pne_id` の重複、必須Role、Collection・Object・Shape Key・Textureの存在、Custom Property、Render Order、Concept Z、Mirror Source、32px UV Margin、Texture解像度を検査します。Errorが1件でもある場合、Runtime Bundle Exportは停止します。

## Three.js Runtime

既存ビューアーの [pne-view-state-runtime.ts](../viewer/app/pne-view-state-runtime.ts) に以下を実装しています。

- 4×4 Bayerの相補DITHER Material
- `transparent = true` / `depthWrite = false` / `renderOrder`
- Active A/B + Prefetch + LRU Cache
- View数上限とGPU Memory Budgetに基づくdispose
- KTX2Loader等を注入できるTexture Loader境界

## テスト

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python 'C:\works\2.5D\blender_addon\tests\integration_test.py'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python 'C:\works\2.5D\blender_addon\tests\persistence_test.py'
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python 'C:\works\2.5D\blender_addon\tests\trace_integration_test.py'
```

統合テストはアドオン登録、4 Viewサンプル、Yaw補間、Expression同期、Validator、16 KTX2、GLB/JSON Export、Residency JSON、別プロセスでの `.blend` 再読込を検証します。
