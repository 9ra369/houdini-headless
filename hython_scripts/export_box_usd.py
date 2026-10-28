"""
hython で box を作って USD に書き出すテストスクリプト

実行例（リポジトリのルートで実行）:
  python -m app.houdini_env hython hython_scripts/export_box_usd.py [出力フォルダ]

出力フォルダを省略すると、リポジトリの samples/ に書き出す
"""
import os
import sys
import hou

# 出力先: 引数で指定したフォルダ、省略時はリポジトリの samples/
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(repo_root, "samples")
os.makedirs(out_dir, exist_ok=True)
usd_path = os.path.join(out_dir, "box.usda").replace("\\", "/")
hip_path = os.path.join(out_dir, "export_box_usd.hip").replace("\\", "/")

# 先に hip の場所を決めて $HIP を出力先に向ける
# （sopimport のレイヤーは $HIP/usd/ に書き出されるため。未保存のままだとカレントフォルダになる）
hou.hipFile.setName(hip_path)

# --- 1. SOP で box を作る -------------------------------------------
geo = hou.node("/obj").createNode("geo", "box_geo")
box = geo.createNode("box", "box1")
box.parmTuple("size").set((1.0, 1.0, 1.0))
box.setDisplayFlag(True)
box.setRenderFlag(True)

# --- 2. LOP (Solaris) に取り込む -------------------------------------
stage_net = hou.node("/stage")
sop_import = stage_net.createNode("sopimport", "import_box")
sop_import.parm("soppath").set(box.path())

# --- 3. USD ROP で書き出す ------------------------------------------
usd_rop = stage_net.createNode("usd_rop", "write_usd")
usd_rop.setInput(0, sop_import)
usd_rop.parm("lopoutput").set(usd_path)

usd_rop.render()  # 書き出し実行

# --- 4. 確認 ---------------------------------------------------------
print("USD written to:", usd_path)
print("Prims in stage:")
for prim in sop_import.stage().Traverse():
    print("  ", prim.GetPath(), prim.GetTypeName())

# 中身を GUI で確認したいとき用に hip も保存しておく
hou.hipFile.save(hip_path)
print("HIP saved to:", hip_path)
