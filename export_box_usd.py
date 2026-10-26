"""
hython で box を作って USD に書き出すテストスクリプト

実行例 (Windows):
  "C:\\Program Files\\Side Effects Software\\Houdini 21.0.xxx\\bin\\hython.exe" export_box_usd.py
"""
import os
import hou

# 出力先: このスクリプトと同じフォルダに box.usda を書き出す
out_dir = os.path.dirname(os.path.abspath(__file__))
usd_path = os.path.join(out_dir, "box.usda").replace("\\", "/")
hip_path = os.path.join(out_dir, "export_box_usd.hip").replace("\\", "/")

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
